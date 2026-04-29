"""Canonical artifact path helpers.

This module centralizes artifact root/type/model/campaign path construction so
writers do not hand-assemble paths in multiple places.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from src.artifact_registry import ArtifactInventorySpec, build_artifact_inventory


APPROVED_ARTIFACT_TYPES = {"logs", "measurements", "reports", "environment"}

_SHARD_SUFFIX_RE = re.compile(r"-\d{5}-of-\d{5}$")
_NON_SLUG_CHARS_RE = re.compile(r"[^a-z0-9._-]+")


# =============================================================================
# CANONICAL 4-ARTIFACT CONTRACT
# =============================================================================
# These are the single authoritative definitions for artifact type strings,
# filenames, and roles.  All writers, readers, DB registrations, and indexes
# MUST use these constants — never inline string literals.
#
# Artifact type strings (used in the `artifacts` DB table artifact_type column)
ARTIFACT_CAMPAIGN_SUMMARY = "campaign_summary_md"
ARTIFACT_RUN_REPORTS      = "run_reports_md"
ARTIFACT_RAW_TELEMETRY    = "raw_telemetry_jsonl"
ARTIFACT_METADATA         = "metadata_json"
ARTIFACT_LEGACY_REPORT    = "report_md"

# Canonical output filenames
FILENAME_CAMPAIGN_SUMMARY = "campaign-summary.md"
FILENAME_RUN_REPORTS      = "run-reports.md"
FILENAME_RAW_TELEMETRY    = "raw-telemetry.jsonl"
FILENAME_METADATA         = "metadata.json"

# Human-readable roles (for display and index tables)
ARTIFACT_ROLES: dict[str, str] = {
    ARTIFACT_CAMPAIGN_SUMMARY: "user-facing summary",
    ARTIFACT_RUN_REPORTS:      "informational detail report",
    ARTIFACT_RAW_TELEMETRY:    "raw machine measurement stream",
    ARTIFACT_METADATA:         "structured provenance and scoring record",
}

# Deprecated artifact type strings still present in the DB for historical
# campaigns.  These are NOT written for new campaigns (Phase 6 complete).
# They are retained in listing/reading code for backwards compatibility with
# pre-Phase-6 campaigns only.
ARTIFACT_TYPES_DEPRECATED: frozenset[str] = frozenset({
    ARTIFACT_LEGACY_REPORT,
    "report_v2_md",
    "scores_csv",
    "raw_jsonl",
    "telemetry_jsonl",
    "config_yaml",
})


def artifact_root(lab_root: Path) -> Path:
    """Return the canonical artifact root for a lab root."""
    return lab_root / "artifacts"


def normalize_model_slug(model_identity: str) -> str:
    """Normalize model identity to the contract model-slug format."""
    base = _SHARD_SUFFIX_RE.sub("", (model_identity or "").strip())
    base = base.lower().replace(" ", "-")
    base = _NON_SLUG_CHARS_RE.sub("-", base)
    base = re.sub(r"-+", "-", base).strip("-._")
    return base or "unknown-model"


def normalize_campaign_slug(campaign_id: str) -> str:
    """Normalize campaign identity while preserving its stable identifier text."""
    text = (campaign_id or "").strip()
    text = text.replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown-campaign"


def infer_model_identity(model_name: str | None = None, model_path: str | Path | None = None) -> str:
    """Infer logical model identity from explicit name, path stem, or env path."""
    if model_name and str(model_name).strip():
        return str(model_name).strip()
    if model_path is not None:
        return _SHARD_SUFFIX_RE.sub("", Path(model_path).stem)
    env_model_path = os.getenv("QUANTMAP_MODEL_PATH", "").strip()
    if env_model_path:
        return _SHARD_SUFFIX_RE.sub("", Path(env_model_path).stem)
    return "unknown-model"


def artifact_dir(
    lab_root: Path,
    artifact_type: str,
    model_identity: str,
    campaign_id: str,
    *,
    create: bool = True,
) -> Path:
    """Return canonical artifact directory for one type/model/campaign tuple."""
    if artifact_type not in APPROVED_ARTIFACT_TYPES:
        raise ValueError(
            f"Invalid artifact_type '{artifact_type}'. "
            f"Allowed: {sorted(APPROVED_ARTIFACT_TYPES)}"
        )
    path = (
        artifact_root(lab_root)
        / artifact_type
        / normalize_model_slug(model_identity)
        / normalize_campaign_slug(campaign_id)
    )
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def find_artifact_dir(lab_root: Path, artifact_type: str, campaign_id: str) -> Path | None:
    """Find canonical artifact directory for campaign when model slug is unknown."""
    if artifact_type not in APPROVED_ARTIFACT_TYPES:
        raise ValueError(
            f"Invalid artifact_type '{artifact_type}'. "
            f"Allowed: {sorted(APPROVED_ARTIFACT_TYPES)}"
        )
    root = artifact_root(lab_root) / artifact_type
    if not root.exists():
        return None
    matches = sorted(root.glob(f"*/{normalize_campaign_slug(campaign_id)}"))
    if not matches:
        return None
    return matches[-1]


def report_paths(
    lab_root: Path,
    model_identity: str,
    campaign_id: str,
    *,
    create: bool = True,
) -> dict[str, Path]:
    """Return canonical report-family paths for one campaign.

    Approved artifact contract (4 formal outputs per campaign):
        campaign_summary_md  → campaign-summary.md   (primary human-facing summary)
        run_reports_md       → run-reports.md         (detailed human-readable evidence)
        metadata_json        → metadata.json          (structured provenance + scores + index)

    Measurements family (in artifacts/measurements/...):
        raw_telemetry_jsonl  → raw-telemetry.jsonl    (merged request + telemetry stream)

    Deprecated aliases (kept for backwards compatibility during migration):
        report_md            → alias for campaign_summary_md path
        report_v2_md         → alias for run_reports_md path
        scores_csv           → no longer a formal artifact; path retained for migration only
    """
    reports_dir = artifact_dir(lab_root, "reports", model_identity, campaign_id, create=create)
    campaign_summary = reports_dir / FILENAME_CAMPAIGN_SUMMARY
    run_reports      = reports_dir / FILENAME_RUN_REPORTS
    metadata         = reports_dir / FILENAME_METADATA
    return {
        "dir":                  reports_dir,
        # ── Approved 4-artifact contract ──────────────────────────────────
        "campaign_summary_md": campaign_summary,
        "run_reports_md":      run_reports,
        "metadata_json":       metadata,
        # ── Deprecated aliases: read-compat only, not written for new campaigns ─
        "report_md":           campaign_summary,    # DEPRECATED: alias for campaign_summary_md
        "report_v2_md":        run_reports,          # DEPRECATED: alias for run_reports_md
        "scores_csv":          reports_dir / "scores.csv",  # DEPRECATED: folded into metadata.json
    }


def measurement_paths(
    lab_root: Path,
    model_identity: str,
    campaign_id: str,
    *,
    create: bool = True,
) -> dict[str, Path]:
    """Return canonical measurement-family paths for one campaign.

    Approved artifact contract (measurements sub-family):
        raw_telemetry_jsonl  → raw-telemetry.jsonl  (merged request + telemetry stream)

    Deprecated (kept during migration):
        raw_jsonl            → raw.jsonl             (DEPRECATED: use raw_telemetry_jsonl)
        telemetry_jsonl      → telemetry.jsonl        (DEPRECATED: merged into raw_telemetry_jsonl)
    """
    meas_dir = artifact_dir(
        lab_root, "measurements", model_identity, campaign_id, create=create
    )
    return {
        "dir":                meas_dir,
        # ── Approved ──────────────────────────────────────────────────────
        "raw_telemetry_jsonl": meas_dir / FILENAME_RAW_TELEMETRY,
        # ── Deprecated aliases: read-compat only, not written for new campaigns ─
        "raw_jsonl":          meas_dir / "raw.jsonl",       # DEPRECATED: merged into raw_telemetry_jsonl
        "telemetry_jsonl":    meas_dir / "telemetry.jsonl", # DEPRECATED: merged into raw_telemetry_jsonl
    }


def compare_default_report_path(lab_root: Path, campaign_a: str, campaign_b: str) -> Path:
    """Return canonical default compare report path under the reports family."""
    pair = f"{campaign_a}_vs_{campaign_b}"
    compare_dir = artifact_dir(
        lab_root,
        "reports",
        "comparisons",
        pair,
        create=True,
    )
    return compare_dir / "compare.md"

def get_campaign_artifact_paths(
    lab_root: Path,
    campaign_id: str,
    db_path: "Path | None" = None,
) -> list[dict]:
    """Return canonical artifact path info for a campaign.

    Resolves each of the 4 canonical artifact paths using find_artifact_dir
    (no model slug required) and optionally enriches with DB-registered status.

    Each entry contains:
        artifact_type, filename, path (Path | None), exists (bool),
        db_status (str | None), sha256 (str | None).

    DB-registered paths take precedence over filesystem-constructed paths:
    when a DB row records a valid path for an artifact type, that path is used
    directly instead of constructing base_dir / fname from the filesystem
    discovery result. This avoids choosing the wrong model directory when the
    same campaign_id exists under multiple model slugs.

    db_path: if provided, DB rows from the artifacts table are loaded and merged.
    """
    report_dir = find_artifact_dir(lab_root, "reports", campaign_id)
    meas_dir = find_artifact_dir(lab_root, "measurements", campaign_id)
    specs = [
        ArtifactInventorySpec(
            artifact_type=ARTIFACT_CAMPAIGN_SUMMARY,
            filename=FILENAME_CAMPAIGN_SUMMARY,
            role=ARTIFACT_ROLES[ARTIFACT_CAMPAIGN_SUMMARY],
            candidate_path=(report_dir / FILENAME_CAMPAIGN_SUMMARY) if report_dir is not None else None,
        ),
        ArtifactInventorySpec(
            artifact_type=ARTIFACT_RUN_REPORTS,
            filename=FILENAME_RUN_REPORTS,
            role=ARTIFACT_ROLES[ARTIFACT_RUN_REPORTS],
            candidate_path=(report_dir / FILENAME_RUN_REPORTS) if report_dir is not None else None,
        ),
        ArtifactInventorySpec(
            artifact_type=ARTIFACT_METADATA,
            filename=FILENAME_METADATA,
            role=ARTIFACT_ROLES[ARTIFACT_METADATA],
            candidate_path=(report_dir / FILENAME_METADATA) if report_dir is not None else None,
        ),
        ArtifactInventorySpec(
            artifact_type=ARTIFACT_RAW_TELEMETRY,
            filename=FILENAME_RAW_TELEMETRY,
            role=ARTIFACT_ROLES[ARTIFACT_RAW_TELEMETRY],
            candidate_path=(meas_dir / FILENAME_RAW_TELEMETRY) if meas_dir is not None else None,
        ),
    ]

    if db_path is None:
        return [
            {
                "artifact_type": spec.artifact_type,
                "filename": spec.filename,
                "path": spec.candidate_path,
                "exists": spec.candidate_path.exists() if spec.candidate_path is not None else False,
                "db_status": None,
                "sha256": None,
            }
            for spec in specs
        ]

    inventory = build_artifact_inventory(campaign_id, db_path, specs)
    return [
        {
            "artifact_type": item["artifact_type"],
            "filename": item["filename"],
            "path": Path(item["path"]) if item["path"] else None,
            "exists": item["exists"],
            "db_status": item["db_status"],
            "sha256": item["sha256"],
        }
        for item in inventory
    ]
