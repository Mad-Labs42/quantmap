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

VALID_TRUTH_STATUS = frozenset({"explicit", "reconstructed", "inferred_limited", "unknown"})
VALID_POLICY_ID = frozenset({
    "profile_default",
    "user_directed_sparse_custom",
    "depth_required_relaxation",
    "acpm_exception",
    "legacy_reconstructed",
    "legacy_unknown",
})
VALID_POLICY_MODIFIERS = frozenset({"campaign_override", "acpm_exception_reference"})
VALID_FINAL_AUTHORITY = frozenset({
    "methodology_profile",
    "execution_mode",
    "campaign_yaml",
    "acpm_governed_exception",
    "legacy_reader",
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
            policy_effect = "user_directed_sparse_custom"
            reason = "legacy custom user-directed sparse subset compatibility"
        elif run_mode == "quick":
            layer_id = "mode_quick_depth_floor"
            policy_effect = "depth_required_relaxation"
            reason = "quick mode single-cycle depth requires relaxed sample floor"
        else:
            layer_id = f"mode_{run_mode}_filter"
            policy_effect = "depth_required_relaxation"
            reason = f"{run_mode} mode filter override"

        layers.append({
            "layer_id": layer_id,
            "authority": "execution_mode",
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
            "authority": "campaign_yaml",
            "source": "campaign.elimination_overrides",
            "source_id": "campaign_yaml",
            "policy_effect": "campaign_override",
            "overrides": yaml_overrides,
            "reason": "campaign YAML elimination_overrides",
        })

    return layers


# ---------------------------------------------------------------------------
# Policy classification helpers
# ---------------------------------------------------------------------------

def _classify_policy(
    override_layers: list[dict[str, Any]],
    base_gates: Mapping[str, Any],
    expected_filters: dict[str, Any],
) -> tuple[str, list[str], str, list[str]]:
    """Return (policy_id, policy_modifiers, final_authority, authority_chain)."""
    authorities = [layer["authority"] for layer in override_layers]
    has_execution_mode = "execution_mode" in authorities
    has_campaign_yaml = "campaign_yaml" in authorities

    # Determine primary policy_id from the first (lowest-precedence) non-YAML layer.
    mode_layer = next(
        (lay for lay in override_layers if lay["authority"] == "execution_mode"),
        None,
    )
    if mode_layer is None:
        policy_id = "profile_default"
    else:
        effect = mode_layer.get("policy_effect", "")
        if effect == "user_directed_sparse_custom":
            policy_id = "user_directed_sparse_custom"
        else:
            policy_id = "depth_required_relaxation"

    policy_modifiers: list[str] = []
    if has_campaign_yaml:
        policy_modifiers.append("campaign_override")

    # Authority chain: always starts with methodology_profile
    authority_chain: list[str] = ["methodology_profile"]
    if has_execution_mode:
        authority_chain.append("execution_mode")
    if has_campaign_yaml:
        authority_chain.append("campaign_yaml")

    # Final authority is the highest-precedence layer that actually changed a key,
    # or methodology_profile if no layer changed anything.
    if has_campaign_yaml:
        yaml_layer = next(
            (lay for lay in override_layers if lay["authority"] == "campaign_yaml"),
            None,
        )
        yaml_changes = {
            k: v
            for k, v in (yaml_layer.get("overrides") or {}).items()
            if base_gates.get(k) != v or any(
                lay.get("overrides", {}).get(k) != v
                for lay in override_layers
                if lay["authority"] == "execution_mode"
            )
        }
        if yaml_changes:
            final_authority = "campaign_yaml"
        elif has_execution_mode:
            final_authority = "execution_mode"
        else:
            final_authority = "methodology_profile"
    elif has_execution_mode:
        final_authority = "execution_mode"
    else:
        final_authority = "methodology_profile"

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
            if run_mode == "custom":
                inferred: dict[str, float] = {"min_valid_warm_count": 1}
                notes = ["Inferred from legacy run_mode=custom convention; min_valid_warm_count likely 1"]
            else:
                inferred = {"min_valid_warm_count": 3}
                notes = ["Inferred from legacy run_mode=quick convention; min_valid_warm_count likely 3"]
            return {
                "truth_status": "inferred_limited",
                "policy_id": "legacy_unknown",
                "policy_modifiers": [],
                "final_policy_authority": "legacy_reader",
                "authority_chain": ["legacy_reader"],
                "effective_filters": inferred,
                "effective_filters_sha256": None,
                "changed_filter_keys": [],
                "rankability_affecting_keys": [],
                "scoring_confirmation": {"status": "unavailable", "score_effective_filters_sha256": None, "confirmed_at_utc": None},
                "legacy_reader": {
                    "label": "legacy_inferred_limited",
                    "inferred_from": [f"campaigns.run_mode={run_mode}"],
                    "notes": notes,
                },
            }
        return {
            "truth_status": "unknown",
            "policy_id": "legacy_unknown",
            "policy_modifiers": [],
            "final_policy_authority": "unknown",
            "authority_chain": ["unknown"],
            "effective_filters": None,
            "effective_filters_sha256": None,
            "changed_filter_keys": [],
            "rankability_affecting_keys": [],
            "scoring_confirmation": {"status": "unavailable", "score_effective_filters_sha256": None, "confirmed_at_utc": None},
            "legacy_reader": {
                "label": "legacy_unknown",
                "inferred_from": [],
                "notes": ["No persisted methodology gates or run-plan override evidence"],
            },
        }

    # Reconstruct from available persisted evidence
    effective: dict[str, float] = dict(gates)
    effective.update(filter_overrides)
    effective.update(yaml_overrides)
    has_yaml = bool(yaml_overrides)

    # truth_status: reconstructed only when gates quality is sufficient
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
        "policy_id": "legacy_reconstructed",
        "policy_modifiers": ["campaign_override"] if has_yaml else [],
        "final_policy_authority": "campaign_yaml" if has_yaml else "legacy_reader",
        "authority_chain": (
            ["methodology_profile", "legacy_reader"]
            + (["campaign_yaml"] if has_yaml else [])
        ),
        "effective_filters": effective,
        "effective_filters_sha256": canonical_json_sha256(effective) if effective else None,
        "changed_filter_keys": changed,
        "rankability_affecting_keys": rankability,
        "scoring_confirmation": {"status": "unavailable", "score_effective_filters_sha256": None, "confirmed_at_utc": None},
        "legacy_reader": {
            "label": "legacy_reconstructed",
            "inferred_from": [
                "methodology_snapshots.gates_json",
                "run_plan_json.filter_overrides",
            ],
            "notes": notes,
        },
    }
