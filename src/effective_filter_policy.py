"""
QuantMap — effective_filter_policy.py

ACPM Slice 2: helpers for building, hashing, and projecting the run-effective
filter policy record stored in campaign_start_snapshot.effective_filter_policy_json.

This module is the sole builder of the v1 policy schema.  It does not load DB rows
directly, does not own methodology selection, and does not mutate reports or export.

Callers:
  src/runner.py  — builds and writes the policy after score_campaign() returns
  src/trust_identity.py — reads the persisted JSON or synthesizes a legacy projection
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# v1 schema constants
# ---------------------------------------------------------------------------

SCHEMA_ID = "quantmap.effective_filter_policy"
SCHEMA_VERSION = 1

_AUTH_CAMPAIGN_YAML = "campaign_yaml"
_AUTH_EXECUTION_MODE = "execution_mode"
_AUTH_METHODOLOGY_PROFILE = "methodology_profile"
_AUTH_LEGACY_READER = "legacy_reader"

_MOD_CAMPAIGN_OVERRIDE = "campaign_override"

_POL_USER_DIRECTED_CUSTOM = "user_directed_sparse_custom"
_POL_DEPTH_RELAXATION = "depth_required_relaxation"
_POL_PROFILE_DEFAULT = "profile_default"
_POL_LEGACY_UNKNOWN = "legacy_unknown"
_POL_LEGACY_RECONSTRUCTED = "legacy_reconstructed"

_KEY_MIN_VALID_WARM_COUNT = "min_valid_warm_count"

_UNAVAILABLE_SCORING_CONFIRMATION: dict[str, Any] = {
    "status": "unavailable",
    "score_effective_filters_sha256": None,
    "confirmed_at_utc": None,
}

VALID_TRUTH_STATUS = frozenset({"explicit", "reconstructed", "inferred_limited", "unknown"})
VALID_POLICY_ID = frozenset({
    _POL_PROFILE_DEFAULT,
    _POL_USER_DIRECTED_CUSTOM,
    _POL_DEPTH_RELAXATION,
    "acpm_exception",
    _POL_LEGACY_RECONSTRUCTED,
    _POL_LEGACY_UNKNOWN,
})
VALID_POLICY_MODIFIERS = frozenset({_MOD_CAMPAIGN_OVERRIDE, "acpm_exception_reference"})
VALID_FINAL_AUTHORITY = frozenset({
    _AUTH_METHODOLOGY_PROFILE,
    _AUTH_EXECUTION_MODE,
    _AUTH_CAMPAIGN_YAML,
    "acpm_governed_exception",
    _AUTH_LEGACY_READER,
    "unknown",
})
VALID_SCORING_CONFIRMATION_STATUS = frozenset({"not_confirmed", "confirmed", "mismatch", "unavailable"})

# Keys that, when changed from base gates, directly affect pass/eliminate populations.
# All changed elimination keys are rankability-affecting in v1 (no finer typing yet).
ELIMINATION_KEY_SET = frozenset({
    "max_cv",
    "max_thermal_events",
    "max_outliers",
    "max_warm_ttft_p90_ms",
    "min_success_rate",
    "min_warm_tg_p10",
    "min_valid_warm_count",
})


# ---------------------------------------------------------------------------
# Canonical hash
# ---------------------------------------------------------------------------

def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    """Return a stable sha256 hex digest of a JSON-serializable mapping.

    Keys are sorted and floats are normalized so key-order differences in
    otherwise-equal dicts produce the same hash.
    """
    text = json.dumps(dict(value), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Override layer builder
# ---------------------------------------------------------------------------

def build_override_layers(
    run_plan_snapshot: Mapping[str, Any],
    yaml_filter_overrides: Mapping[str, float] | None,
) -> list[dict[str, Any]]:
    """Build ordered override layers from run-plan mode overrides and YAML overrides.

    Layer ordering matches the merge precedence used in runner.py:
      1. mode-level overrides (from RunPlan.filter_overrides)
      2. campaign YAML overrides (YAML wins on conflict)
    """
    layers: list[dict[str, Any]] = []

    mode_overrides: dict[str, float] = dict(run_plan_snapshot.get("filter_overrides") or {})
    run_mode: str = str(run_plan_snapshot.get("run_mode") or "unknown")

    if mode_overrides:
        if run_mode == "custom":
            layer_id = "mode_custom_sparse_floor"
            policy_effect = _POL_USER_DIRECTED_CUSTOM
            reason = "legacy custom user-directed sparse subset compatibility"
        elif run_mode == "quick":
            layer_id = "mode_quick_depth_floor"
            policy_effect = _POL_DEPTH_RELAXATION
            reason = "quick mode single-cycle depth requires relaxed sample floor"
        else:
            layer_id = f"mode_{run_mode}_filter"
            policy_effect = _POL_DEPTH_RELAXATION
            reason = f"{run_mode} mode filter override"

        layers.append({
            "layer_id": layer_id,
            "authority": _AUTH_EXECUTION_MODE,
            "source": "run_plan.filter_overrides",
            "source_id": run_mode,
            "policy_effect": policy_effect,
            "overrides": mode_overrides,
            "reason": reason,
        })

    yaml_overrides: dict[str, float] = dict(yaml_filter_overrides or {})
    if yaml_overrides:
        layers.append({
            "layer_id": "campaign_yaml_override",
            "authority": _AUTH_CAMPAIGN_YAML,
            "source": "campaign.elimination_overrides",
            "source_id": "campaign_yaml",
            "policy_effect": _MOD_CAMPAIGN_OVERRIDE,
            "overrides": yaml_overrides,
            "reason": "campaign YAML elimination_overrides",
        })

    return layers


# ---------------------------------------------------------------------------
# Policy classification helpers
# ---------------------------------------------------------------------------

def _get_yaml_changes(
    override_layers: list[dict[str, Any]],
    base_gates: Mapping[str, Any],
) -> dict[str, Any]:
    yaml_layer = next(
        (lay for lay in override_layers if lay["authority"] == _AUTH_CAMPAIGN_YAML),
        None,
    )
    if not yaml_layer:
        return {}
    return {
        k: v
        for k, v in (yaml_layer.get("overrides") or {}).items()
        if base_gates.get(k) != v or any(
            lay.get("overrides", {}).get(k) != v
            for lay in override_layers
            if lay["authority"] == _AUTH_EXECUTION_MODE
        )
    }

def _classify_policy(
    override_layers: list[dict[str, Any]],
    base_gates: Mapping[str, Any],
    expected_filters: dict[str, Any],
) -> tuple[str, list[str], str, list[str]]:
    """Return (policy_id, policy_modifiers, final_authority, authority_chain)."""
    authorities = [layer["authority"] for layer in override_layers]
    has_execution_mode = _AUTH_EXECUTION_MODE in authorities
    has_campaign_yaml = _AUTH_CAMPAIGN_YAML in authorities

    # Determine primary policy_id from the first (lowest-precedence) non-YAML layer.
    mode_layer = next(
        (lay for lay in override_layers if lay["authority"] == _AUTH_EXECUTION_MODE),
        None,
    )
    if mode_layer is None:
        policy_id = _POL_PROFILE_DEFAULT
    else:
        effect = mode_layer.get("policy_effect", "")
        if effect == _POL_USER_DIRECTED_CUSTOM:
            policy_id = _POL_USER_DIRECTED_CUSTOM
        else:
            policy_id = _POL_DEPTH_RELAXATION

    policy_modifiers: list[str] = []
    if has_campaign_yaml:
        policy_modifiers.append(_MOD_CAMPAIGN_OVERRIDE)

    # Authority chain: always starts with methodology_profile
    authority_chain: list[str] = [_AUTH_METHODOLOGY_PROFILE]
    if has_execution_mode:
        authority_chain.append(_AUTH_EXECUTION_MODE)
    if has_campaign_yaml:
        authority_chain.append(_AUTH_CAMPAIGN_YAML)

    # Final authority is the highest-precedence layer that actually changed a key,
    # or methodology_profile if no layer changed anything.
    if has_campaign_yaml and _get_yaml_changes(override_layers, base_gates):
        final_authority = _AUTH_CAMPAIGN_YAML
    elif has_execution_mode:
        final_authority = _AUTH_EXECUTION_MODE
    else:
        final_authority = _AUTH_METHODOLOGY_PROFILE

    return policy_id, policy_modifiers, final_authority, authority_chain


# ---------------------------------------------------------------------------
# Policy builder
# ---------------------------------------------------------------------------

def build_effective_filter_policy(
    base_gates: Mapping[str, float],
    base_source: Mapping[str, Any],
    override_layers: list[dict[str, Any]],
    score_effective_filters: Mapping[str, float] | None = None,
    *,
    created_by: str = "runner",
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the complete v1 effective_filter_policy_json record.

    base_gates        — profile.gate_overrides (base methodology gates)
    base_source       — dict with source, snapshot_id, profile_name, etc.
    override_layers   — ordered layers from build_override_layers()
    score_effective_filters — what score_campaign() actually applied;
                              when provided, a confirmation object is computed
    """
    now = created_at_utc or datetime.now(timezone.utc).isoformat()

    # Apply layers in order (mode first, YAML second — YAML wins on conflict)
    expected_filters: dict[str, float] = dict(base_gates)
    for layer in override_layers:
        expected_filters.update(layer.get("overrides") or {})

    changed_keys = [
        k for k, v in expected_filters.items() if base_gates.get(k) != v
    ]
    rankability_keys = [k for k in changed_keys if k in ELIMINATION_KEY_SET]

    policy_id, policy_modifiers, final_authority, authority_chain = _classify_policy(
        override_layers, base_gates, expected_filters
    )

    expected_sha = canonical_json_sha256(expected_filters)

    # Scoring confirmation: cross-check only, not a second authority.
    scoring_confirmation: dict[str, Any]
    if score_effective_filters is not None:
        actual_sha = canonical_json_sha256(score_effective_filters)
        if expected_sha == actual_sha:
            scoring_confirmation = {
                "status": "confirmed",
                "score_effective_filters_sha256": actual_sha,
                "confirmed_at_utc": now,
            }
        else:
            scoring_confirmation = {
                "status": "mismatch",
                "expected_effective_filters_sha256": expected_sha,
                "score_effective_filters_sha256": actual_sha,
                "confirmed_at_utc": now,
            }
    else:
        scoring_confirmation = {
            "status": "not_confirmed",
            "score_effective_filters_sha256": None,
            "confirmed_at_utc": None,
        }

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "truth_status": "explicit",
        "policy_id": policy_id,
        "policy_modifiers": policy_modifiers,
        "final_policy_authority": final_authority,
        "authority_chain": authority_chain,
        "created_by": created_by,
        "created_at_utc": now,
        "base_gates_source": dict(base_source),
        "base_gates": dict(base_gates),
        "override_layers": override_layers,
        "effective_filters": expected_filters,
        "changed_filter_keys": changed_keys,
        "rankability_affecting_keys": rankability_keys,
        "effective_filters_sha256": expected_sha,
        "scoring_confirmation": scoring_confirmation,
        "legacy_reader": {"label": None, "inferred_from": [], "notes": []},
    }


# ---------------------------------------------------------------------------
# Legacy projection (trust_identity seam for null rows)
# ---------------------------------------------------------------------------

def _project_inferred_legacy(run_mode: str) -> dict[str, Any]:
    if run_mode == "custom":
        inferred: dict[str, float] = {_KEY_MIN_VALID_WARM_COUNT: 1}
        notes = ["Inferred from legacy run_mode=custom convention; min_valid_warm_count likely 1"]
    else:
        inferred = {_KEY_MIN_VALID_WARM_COUNT: 3}
        notes = ["Inferred from legacy run_mode=quick convention; min_valid_warm_count likely 3"]
        
    return {
        "truth_status": "inferred_limited",
        "policy_id": _POL_LEGACY_UNKNOWN,
        "policy_modifiers": [],
        "final_policy_authority": _AUTH_LEGACY_READER,
        "authority_chain": [_AUTH_LEGACY_READER],
        "effective_filters": inferred,
        "effective_filters_sha256": None,
        "changed_filter_keys": [],
        "rankability_affecting_keys": [],
        "scoring_confirmation": _UNAVAILABLE_SCORING_CONFIRMATION,
        "legacy_reader": {
            "label": "legacy_inferred_limited",
            "inferred_from": [f"campaigns.run_mode={run_mode}"],
            "notes": notes,
        },
    }

def _project_unknown_legacy() -> dict[str, Any]:
    return {
        "truth_status": "unknown",
        "policy_id": _POL_LEGACY_UNKNOWN,
        "policy_modifiers": [],
        "final_policy_authority": "unknown",
        "authority_chain": ["unknown"],
        "effective_filters": None,
        "effective_filters_sha256": None,
        "changed_filter_keys": [],
        "rankability_affecting_keys": [],
        "scoring_confirmation": _UNAVAILABLE_SCORING_CONFIRMATION,
        "legacy_reader": {
            "label": _POL_LEGACY_UNKNOWN,
            "inferred_from": [],
            "notes": ["No persisted methodology gates or run-plan override evidence"],
        },
    }

def _project_reconstructed_legacy(
    gates: dict[str, float],
    filter_overrides: dict[str, float],
    yaml_overrides: dict[str, float],
    cap_quality: str,
) -> dict[str, Any]:
    effective: dict[str, float] = dict(gates)
    effective.update(filter_overrides)
    effective.update(yaml_overrides)
    has_yaml = bool(yaml_overrides)

    if gates and cap_quality in ("complete",):
        truth_status = "reconstructed"
    else:
        truth_status = "inferred_limited"

    changed = [k for k, v in effective.items() if gates.get(k) != v]
    rankability = [k for k in changed if k in ELIMINATION_KEY_SET]

    notes: list[str] = ["Reconstructed from persisted methodology gates and run_plan.filter_overrides"]
    if has_yaml:
        notes.append("campaign YAML elimination_overrides applied")
    if cap_quality not in ("complete",):
        notes.append(f"methodology capture quality: {cap_quality}")

    return {
        "truth_status": truth_status,
        "policy_id": _POL_LEGACY_RECONSTRUCTED,
        "policy_modifiers": [_MOD_CAMPAIGN_OVERRIDE] if has_yaml else [],
        "final_policy_authority": _AUTH_CAMPAIGN_YAML if has_yaml else _AUTH_LEGACY_READER,
        "authority_chain": (
            [_AUTH_METHODOLOGY_PROFILE, _AUTH_LEGACY_READER]
            + ([_AUTH_CAMPAIGN_YAML] if has_yaml else [])
        ),
        "effective_filters": effective,
        "effective_filters_sha256": canonical_json_sha256(effective) if effective else None,
        "changed_filter_keys": changed,
        "rankability_affecting_keys": rankability,
        "scoring_confirmation": _UNAVAILABLE_SCORING_CONFIRMATION,
        "legacy_reader": {
            "label": _POL_LEGACY_RECONSTRUCTED,
            "inferred_from": [
                "methodology_snapshots.gates_json",
                "run_plan_json.filter_overrides",
            ],
            "notes": notes,
        },
    }

def project_legacy_filter_policy(
    methodology: Mapping[str, Any],
    run_plan: Mapping[str, Any],
    campaign_yaml: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Synthesize a bounded legacy projection for rows without v1 explicit JSON.

    Never writes to the DB.  Never promotes inferred facts to explicit truth.
    Returns a projection dict with the same top-level keys as a v1 explicit record
    so callers can handle both paths uniformly.
    """
    gates: dict[str, float] = dict(methodology.get("gates") or {})
    filter_overrides: dict[str, float] = dict(run_plan.get("filter_overrides") or {})
    yaml_overrides: dict[str, float] = dict((campaign_yaml or {}).get("elimination_overrides") or {})
    run_mode: str = str(run_plan.get("run_mode") or "")
    cap_quality: str = str(methodology.get("capture_quality") or "unknown")

    no_gates = not gates
    no_overrides = not filter_overrides

    # No persisted evidence — can we infer from run_mode convention?
    if no_gates and no_overrides:
        if run_mode in ("custom", "quick"):
            return _project_inferred_legacy(run_mode)
        return _project_unknown_legacy()

    return _project_reconstructed_legacy(gates, filter_overrides, yaml_overrides, cap_quality)
