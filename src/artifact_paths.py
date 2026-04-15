"""Canonical artifact path helpers.

This module centralizes artifact root/type/model/campaign path construction so
writers do not hand-assemble paths in multiple places.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

APPROVED_ARTIFACT_TYPES = {"logs", "measurements", "reports", "environment"}

_SHARD_SUFFIX_RE = re.compile(r"-\d{5}-of-\d{5}$")
_NON_SLUG_CHARS_RE = re.compile(r"[^a-z0-9._-]+")


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
    """Return canonical report-family paths for one campaign."""
    reports_dir = artifact_dir(lab_root, "reports", model_identity, campaign_id, create=create)
    return {
        "dir": reports_dir,
        "report_md": reports_dir / "report.md",
        "report_v2_md": reports_dir / "report_v2.md",
        "scores_csv": reports_dir / "scores.csv",
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
