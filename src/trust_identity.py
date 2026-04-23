"""
Snapshot-first identity helpers for Phase 1 trust surfaces.

This module is intentionally small: it loads persisted historical identity and
labels legacy fallbacks. It does not own scoring, reporting, or export policy.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.db import get_connection
from src.artifact_paths import (
    ARTIFACT_CAMPAIGN_SUMMARY,
    ARTIFACT_RUN_REPORTS,
    ARTIFACT_METADATA,
    ARTIFACT_RAW_TELEMETRY,
    ARTIFACT_TYPES_DEPRECATED,
)


class TrustIdentityError(RuntimeError):
    """Raised when persisted trust evidence is missing or unusable."""


class MethodologySnapshotError(TrustIdentityError):
    """Raised when historical methodology cannot safely drive scoring."""


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _fetch_current_methodology(conn: sqlite3.Connection, campaign_id: str) -> dict[str, Any]:
    try:
        row = conn.execute(
            """
            SELECT *
            FROM methodology_snapshots
            WHERE campaign_id=? AND is_current=1
            ORDER BY id DESC
            LIMIT 1
            """,
            (campaign_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None

    if row:
        return {
            "id": row["id"],
            "source": "methodology_snapshot",
            "snapshot_kind": row["snapshot_kind"],
            "version": row["methodology_version"],
            "profile_name": row["profile_name"],
            "profile_version": row["profile_version"],
            "weights": _json_loads(row["weights_json"], {}),
            "gates": _json_loads(row["gates_json"], {}),
            "anchors": _json_loads(row["anchors_json"], {}),
            "capture_quality": row["capture_quality"],
            "capture_source": row["capture_source"],
            "profile_yaml_content": row["profile_yaml_content"],
            "registry_yaml_content": row["registry_yaml_content"],
            "source_paths": _json_loads(row["source_paths_json"], {}),
            "source_hashes": _json_loads(row["source_hashes_json"], {}),
        }

    row = conn.execute(
        "SELECT notes_json FROM campaigns WHERE id=?", (campaign_id,)
    ).fetchone()
    notes = _json_loads(row["notes_json"], {}) if row and row["notes_json"] else {}
    legacy = notes.get("governance_methodology")
    if legacy:
        return {
            "id": legacy.get("methodology_snapshot_id"),
            "source": "legacy_notes_json",
            "snapshot_kind": "legacy_partial",
            "version": legacy.get("version"),
            "profile_name": legacy.get("profile_name"),
            "profile_version": legacy.get("profile_version"),
            "weights": legacy.get("weights", {}),
            "gates": legacy.get("gates", {}),
            "anchors": legacy.get("references", {}),
            "capture_quality": legacy.get("capture_quality") or "legacy_partial",
            "capture_source": "campaigns.notes_json.governance_methodology",
            "profile_yaml_content": None,
            "registry_yaml_content": None,
            "source_paths": {},
            "source_hashes": {},
        }

    return {
        "id": None,
        "source": "unknown",
        "snapshot_kind": "missing",
        "version": None,
        "profile_name": None,
        "profile_version": None,
        "weights": {},
        "gates": {},
        "anchors": {},
        "capture_quality": "unknown",
        "capture_source": "none",
        "profile_yaml_content": None,
        "registry_yaml_content": None,
        "source_paths": {},
        "source_hashes": {},
    }


@dataclass
class TrustIdentity:
    campaign_id: str
    campaign: dict[str, Any]
    start_snapshot: dict[str, Any]
    baseline: dict[str, Any]
    quantmap: dict[str, Any]
    run_plan: dict[str, Any]
    methodology: dict[str, Any]
    telemetry_provider: dict[str, Any]
    execution_environment: dict[str, Any]
    sources: dict[str, str]
    filter_policy: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.filter_policy is None:
            self.filter_policy = {}

    @property
    def has_snapshot_baseline(self) -> bool:
        return self.sources.get("baseline") == "snapshot"


def load_run_identity(campaign_id: str, db_path: Path) -> TrustIdentity:
    """Load the snapshot-first historical identity for a campaign."""
    with get_connection(db_path) as conn:
        camp_row = conn.execute(
            "SELECT * FROM campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        snap_row = conn.execute(
            "SELECT * FROM campaign_start_snapshot WHERE campaign_id=?",
            (campaign_id,),
        ).fetchone()
        campaign = dict(camp_row) if camp_row else {}
        snap = dict(snap_row) if snap_row else {}
        methodology = _fetch_current_methodology(conn, campaign_id)

    baseline_identity = _json_loads(snap.get("baseline_identity_json"), {})
    quantmap_identity = _json_loads(snap.get("quantmap_identity_json"), {})
    run_plan = _json_loads(snap.get("run_plan_json"), {})
    from src.telemetry_provider import provider_evidence_from_snapshot  # noqa: PLC0415
    from src.execution_environment import execution_environment_from_snapshot  # noqa: PLC0415

    telemetry_provider = provider_evidence_from_snapshot(snap)
    execution_environment = execution_environment_from_snapshot(snap)

    # ACPM Slice 2: resolve filter_policy from persisted v1 JSON or legacy projection.
    filter_policy_raw = snap.get("effective_filter_policy_json")
    if filter_policy_raw:
        filter_policy = _json_loads(filter_policy_raw, {})
        filter_policy_source = "snapshot"
    else:
        from src.effective_filter_policy import project_legacy_filter_policy  # noqa: PLC0415
        _campaign_yaml_raw = snap.get("campaign_yaml_content")
        _campaign_yaml: dict[str, Any] | None = None
        if _campaign_yaml_raw:
            try:
                import yaml as _yaml  # noqa: PLC0415
                _parsed = _yaml.safe_load(_campaign_yaml_raw)
                _campaign_yaml = _parsed if isinstance(_parsed, dict) else None
            except Exception:
                pass
        filter_policy = project_legacy_filter_policy(methodology, run_plan, _campaign_yaml)
        _ts = filter_policy.get("truth_status", "unknown")
        filter_policy_source = f"legacy_{_ts}"

    sources = {
        "campaign": "snapshot" if snap.get("campaign_yaml_content") else "legacy_incomplete",
        "baseline": "snapshot" if snap.get("baseline_yaml_content") else (
            "legacy_hash_only" if snap.get("baseline_yaml_sha256") or campaign.get("baseline_sha256") else "unknown"
        ),
        "quantmap": "snapshot" if quantmap_identity else "legacy_unrecorded",
        "run_plan": "snapshot" if run_plan else "derived_legacy",
        "methodology": methodology.get("source", "unknown"),
        "telemetry_provider": telemetry_provider.get("source", "unknown"),
        "execution_environment": execution_environment.get("source", "snapshot"),
        "filter_policy": filter_policy_source,
    }

    return TrustIdentity(
        campaign_id=campaign_id,
        campaign=campaign,
        start_snapshot=snap,
        baseline=baseline_identity,
        quantmap=quantmap_identity,
        run_plan=run_plan,
        methodology=methodology,
        telemetry_provider=telemetry_provider,
        execution_environment=execution_environment,
        sources=sources,
        filter_policy=filter_policy,
    )


def load_methodology_snapshot(campaign_id: str, db_path: Path) -> dict[str, Any]:
    """Load the current persisted methodology snapshot or an explicit legacy label."""
    with get_connection(db_path) as conn:
        return _fetch_current_methodology(conn, campaign_id)


def methodology_source_label(methodology: dict[str, Any]) -> str:
    """Return a stable human-facing methodology evidence label."""
    source = methodology.get("source")
    quality = methodology.get("capture_quality")
    capture_source = str(methodology.get("capture_source") or "")
    snapshot_kind = str(methodology.get("snapshot_kind") or "")
    if (
        source == "methodology_snapshot"
        and ("current_input" in capture_source or snapshot_kind == "current_input_rescore")
    ):
        return "current_input_explicit"
    if source == "methodology_snapshot" and quality == "complete":
        return "snapshot_complete"
    if source == "methodology_snapshot" and quality == "legacy_partial":
        return "legacy_partial_methodology"
    if source == "methodology_snapshot" and quality:
        return f"snapshot_{quality}"
    if source == "legacy_notes_json":
        return "legacy_partial_methodology"
    if source == "current_input":
        return "current_input_explicit"
    return "methodology_unknown"


def _registry_from_yaml_content(raw_yaml: str):
    from src import governance  # noqa: PLC0415

    raw = yaml.safe_load(raw_yaml) or {}
    if not isinstance(raw, dict) or "metrics" not in raw:
        raise MethodologySnapshotError("methodology registry snapshot is missing top-level metrics")
    metrics = {}
    for name, fields in raw["metrics"].items():
        metrics[name] = governance.MetricDefinition(canonical_name=name, **fields)
    return governance.MetricRegistry(metrics)


def _profile_from_yaml_content(raw_yaml: str):
    from src import governance  # noqa: PLC0415

    raw = yaml.safe_load(raw_yaml) or {}
    if not isinstance(raw, dict):
        raise MethodologySnapshotError("methodology profile snapshot is not a mapping")
    return governance.ExperimentProfile(**raw)


def load_methodology_for_historical_scoring(
    campaign_id: str,
    db_path: Path,
    *,
    allow_current_input: bool = False,
    profile_name: str | None = None,
    force_new_anchors: bool = False,
) -> tuple[Any, Any, dict[str, float], dict[str, dict[str, Any]], int | None, str]:
    """
    Return methodology material for scoring.

    Historical mode requires a complete methodology snapshot. Current-input mode
    explicitly uses live governance files and returns a label that callers must
    preserve in outputs.
    """
    from src import governance  # noqa: PLC0415

    if allow_current_input:
        profile, registry = governance.load_current_methodology(profile_name)
        return profile, registry, {}, {}, None, "current_input_explicit"

    methodology = load_methodology_snapshot(campaign_id, db_path)
    if (
        methodology.get("source") == "methodology_snapshot"
        and methodology.get("capture_quality") == "complete"
        and not force_new_anchors
    ):
        profile_yaml = methodology.get("profile_yaml_content")
        registry_yaml = methodology.get("registry_yaml_content")
        if not profile_yaml or not registry_yaml:
            raise MethodologySnapshotError(
                f"Methodology snapshot for {campaign_id} is marked complete "
                "but is missing profile or registry content."
            )
        try:
            profile = _profile_from_yaml_content(profile_yaml)
            registry = _registry_from_yaml_content(registry_yaml)
            governance.validate_profile_against_registry(profile, registry)
        except Exception as exc:
            raise MethodologySnapshotError(
                f"Methodology snapshot for {campaign_id} could not be rehydrated: {exc}"
            ) from exc

        refs: dict[str, float] = {}
        ref_snapshot: dict[str, dict[str, Any]] = {}
        for metric_name, ref in (methodology.get("anchors") or {}).items():
            if not isinstance(ref, dict):
                continue
            val = ref.get("value")
            if val is not None:
                refs[metric_name] = val
            ref_snapshot[metric_name] = ref

        return (
            profile,
            registry,
            refs,
            ref_snapshot,
            methodology.get("id"),
            methodology_source_label(methodology),
        )

    label = methodology_source_label(methodology)
    raise MethodologySnapshotError(
        f"Refusing snapshot-locked scoring for {campaign_id}: "
        f"methodology evidence is {label}, not snapshot_complete. "
        "Use explicit current-input mode to score with current profile/registry files."
    )


def load_artifact_summaries(campaign_id: str, db_path: Path) -> list[dict[str, Any]]:
    """Return artifact rows with stable defaults for trust-surface readers."""
    with get_connection(db_path) as conn:
        try:
            rows = conn.execute(
                """
                SELECT artifact_type, path, sha256, created_at, status, producer,
                       error_message, updated_at, verification_source
                FROM artifacts
                WHERE campaign_id=?
                ORDER BY created_at DESC, artifact_type
                """,
                (campaign_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

    artifacts: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["status"] = d.get("status") or "legacy_path_only"
        d["verification_source"] = d.get("verification_source") or "legacy_unverified"
        artifacts.append(d)
    return artifacts


def _collect_statuses(check_types: tuple, by_type: dict) -> list:
    """Return a status string for each artifact type in check_types."""
    result = []
    for atype in check_types:
        row = by_type.get(atype)
        result.append("missing" if row is None else (row.get("status") or "legacy_path_only"))
    return result


def summarize_report_artifact_status(
    campaign_id: str,
    db_path: Path,
    expected_types: tuple[str, ...] | None = None,
) -> str:
    """Return the campaign-level aggregate report status from artifact rows.

    Checks for the approved artifact contract types first.  Also accepts old
    legacy type names so rows written before the redesign migration still count
    toward completeness rather than being treated as missing.

    expected_types may be overridden by callers during transition; if None the
    new canonical types are used.
    """
    # New canonical types for the 4-artifact contract (imported from artifact_paths).
    _NEW_TYPES = (
        ARTIFACT_CAMPAIGN_SUMMARY,
        ARTIFACT_RUN_REPORTS,
        ARTIFACT_METADATA,
        ARTIFACT_RAW_TELEMETRY,
    )
    # Legacy types written before the rename migration (imported from artifact_paths).
    _LEGACY_TYPES = tuple(
        t
        for t in (
            "report_md",
            "report_v2_md",
            "scores_csv",
            "raw_jsonl",
            "telemetry_jsonl",
        )
        if t in ARTIFACT_TYPES_DEPRECATED
    )

    artifacts = load_artifact_summaries(campaign_id, db_path)
    by_type = {row.get("artifact_type"): row for row in artifacts}
    if not by_type:
        return "legacy_unknown"

    if expected_types is not None:
        # Explicit override: use exactly these types.
        statuses = _collect_statuses(expected_types, by_type)
    else:
        # Auto: check new types; fall back to legacy equivalents if new are absent.
        # A campaign that was run before the redesign only has old-type rows;
        # we must not report it as "partial" just because new-type rows are missing.
        has_any_new = any(atype in by_type for atype in _NEW_TYPES)
        check_types = _NEW_TYPES if has_any_new else _LEGACY_TYPES
        statuses = _collect_statuses(check_types, by_type)

    if statuses and all(status == "complete" for status in statuses):
        return "complete"
    if any(status == "failed" for status in statuses):
        return "partial"
    if any(
        status in {"partial", "missing", "legacy_path_only", "legacy_unverified"}
        for status in statuses
    ):
        return "partial"
    return "partial"


def load_baseline_for_historical_use(
    campaign_id: str,
    db_path: Path,
    fallback_baseline: dict[str, Any] | None = None,
    *,
    allow_current_input: bool = False,
) -> tuple[dict[str, Any], str]:
    """
    Return baseline content for historical interpretation.

    Snapshot content wins. A current fallback is only returned when explicitly
    allowed by the caller, and the source label makes that weaker truth visible.
    """
    identity = load_run_identity(campaign_id, db_path)
    raw = identity.start_snapshot.get("baseline_yaml_content")
    if raw:
        try:
            parsed = yaml.safe_load(raw) or {}
            if isinstance(parsed, dict):
                return parsed, "snapshot"
        except yaml.YAMLError:
            return {}, "snapshot_unparseable"

    if allow_current_input and fallback_baseline is not None:
        return fallback_baseline, "current_input_explicit"

    if fallback_baseline is not None:
        return {}, identity.sources.get("baseline", "legacy_incomplete")

    return {}, identity.sources.get("baseline", "unknown")
