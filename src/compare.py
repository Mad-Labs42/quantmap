"""QuantMap — compare.py

Forensic cross-campaign comparison engine.
Produces a structured CompareResult (JSON-serializable) covering:
- Methodology compatibility grading
- Shared config intersection deltas
- Winner side-by-side analysis
- Elimination/Reach analysis
- System/Environment deltas
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from src import audit_methodology
from src.db import get_connection

logger = logging.getLogger("compare")

# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

class CampaignMeta(TypedDict):
    id: str
    name: str
    status: str
    created_at: str
    run_mode: str | None

class MethodologyResult(TypedDict):
    grade: str  # compatible | warnings | mismatch
    compatibility_score: float
    registry_version_match: bool
    anchor_deltas: list[dict[str, Any]]
    warnings: list[str]

class EnvDelta(TypedDict):
    category: str
    val_a: Any
    val_b: Any
    is_regression: bool
    label: str

class ConfigDelta(TypedDict):
    config_id: str
    tg_a: float
    tg_b: float
    tg_delta_pct: float
    ttft_a: float
    ttft_b: float
    ttft_delta_pct: float
    cv_a: float
    cv_b: float
    significance_label: str  # inside noise band | likely meaningful | low confidence
    flags: list[str]

@dataclass
class CompareResult:
    campaign_a: CampaignMeta
    campaign_b: CampaignMeta

    # Methodology
    methodology: MethodologyResult

    # Environment
    env_deltas: list[EnvDelta]

    # Winners
    winner_a: dict[str, Any] | None = None
    winner_b: dict[str, Any] | None = None
    winner_shift_tg_pct: float | None = None

    # Intersection Set (Shared Configs)
    shared_configs: list[ConfigDelta] = field(default_factory=list)
    median_shared_tg_shift_pct: float = 0.0

    # Elimination / Reach
    lost_in_b: list[str] = field(default_factory=list)
    gained_in_b: list[str] = field(default_factory=list)
    elimination_counts_a: dict[str, int] = field(default_factory=dict)
    elimination_counts_b: dict[str, int] = field(default_factory=dict)

    # Interpretation
    primary_finding: str = ""
    overall_confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

# ---------------------------------------------------------------------------
# Analytical Logic
# ---------------------------------------------------------------------------

def calculate_significance(delta_pct: float, cv_a: float, cv_b: float) -> str:
    """Uncertainty-aware labeling logic.
    Refined beyond simple delta > CV.
    """
    abs_delta = abs(delta_pct)
    # Heuristic: the 'noise floor' is roughly the combined CV
    noise_floor = (cv_a + cv_b) * 100.0 / 2.0  # approximate combined % noise floor

    if abs_delta < noise_floor:
        return "inside noise band"
    if abs_delta > noise_floor * 3.0:
        return "likely meaningful"
    return "low confidence / insufficient evidence"

def get_campaign_meta(conn: Any, campaign_id: str) -> CampaignMeta:
    row = conn.execute(
        "SELECT id, name, status, created_at, run_mode FROM campaigns WHERE id=?",
        (campaign_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Campaign {campaign_id} not found in database.")

    d = dict(row)
    return {
        "id": d["id"],
        "name": d["name"],
        "status": d["status"],
        "created_at": d["created_at"],
        "run_mode": d.get("run_mode")
    }

def get_config_scores(conn: Any, campaign_id: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM scores WHERE campaign_id=?", (campaign_id,)
    ).fetchall()
    # Explicitly convert each row to a dict for .get() support later
    return {r["config_id"]: dict(r) for r in rows}

def get_eliminations(conn: Any, campaign_id: str) -> dict[str, str]:
    rows = conn.execute(
        "SELECT id, elimination_reason FROM configs WHERE campaign_id=? AND status='eliminated'",
        (campaign_id,)
    ).fetchall()
    return {r["id"]: r["elimination_reason"] for r in rows}

def get_start_snapshot(db_path: Path, campaign_id: str) -> dict[str, Any]:
    from src.trust_identity import load_run_identity

    return load_run_identity(campaign_id, db_path).start_snapshot

def grade_methodology(campaign_a_id: str, campaign_b_id: str, db_path: Path) -> MethodologyResult:
    """Wraps audit_methodology to produce a graded compatibility result."""
    m1 = audit_methodology.get_methodology(campaign_a_id, db_path)
    m2 = audit_methodology.get_methodology(campaign_b_id, db_path)

    if not m1 or not m2:
        return {
            "grade": "mismatch",
            "compatibility_score": 0.0,
            "registry_version_match": False,
            "anchor_deltas": [],
            "warnings": ["Methodology snapshots missing."]
        }

    v1 = m1.get("version", "unknown")
    v2 = m2.get("version", "unknown")
    registry_match = (v1 == v2)
    q1 = m1.get("capture_quality")
    q2 = m2.get("capture_quality")
    quality_warnings = []
    if q1 != "complete" or q2 != "complete":
        quality_warnings.append(
            f"Methodology evidence is incomplete: {campaign_a_id}={q1}, {campaign_b_id}={q2}"
        )

    refs1 = m1.get("references", {})
    refs2 = m2.get("references", {})
    all_metrics = sorted(set(refs1.keys()) | set(refs2.keys()))

    anchor_deltas = []
    mismatches = 0
    drifts = []

    for m in all_metrics:
        r1 = refs1.get(m, {})
        r2 = refs2.get(m, {})
        v1_val = r1.get("value")
        v2_val = r2.get("value")
        status = "match"
        if v1_val != v2_val:
            status = "drift"
            mismatches += 1
            drifts.append(f"Anchor {m} drifted: {v1_val} -> {v2_val}")

        anchor_deltas.append({
            "metric": m,
            "val_a": v1_val,
            "val_b": v2_val,
            "status": status
        })

    grade = "compatible"
    if mismatches > 0:
        grade = "warnings"
    if quality_warnings:
        grade = "mismatch"
    if not registry_match:
        grade = "mismatch"

    warnings = quality_warnings + drifts
    if not registry_match:
        warnings.insert(0, f"Registry version mismatch: {v1} vs {v2}")

    return {
        "grade": grade,
        "compatibility_score": 1.0 - (mismatches / max(len(all_metrics), 1)),
        "registry_version_match": registry_match,
        "anchor_deltas": anchor_deltas,
        "warnings": warnings
    }

def generate_compare_result(id_a: str, id_b: str, db_path: Path) -> CompareResult:
    """Main entry point for generating the comparison data model."""
    with get_connection(db_path) as conn:
        meta_a = get_campaign_meta(conn, id_a)
        meta_b = get_campaign_meta(conn, id_b)

        scores_a = get_config_scores(conn, id_a)
        scores_b = get_config_scores(conn, id_b)

        elim_a = get_eliminations(conn, id_a)
        elim_b = get_eliminations(conn, id_b)

    snap_a = get_start_snapshot(db_path, id_a)
    snap_b = get_start_snapshot(db_path, id_b)

    # 1. Methodology
    meth = grade_methodology(id_a, id_b, db_path)

    # 2. Environment Deltas
    env_deltas = []
    for key, label in [
        ("nvidia_driver", "NVIDIA Driver"),
        ("os_version", "OS Version"),
        ("gpu_name", "GPU"),
        ("power_plan", "Power Plan")
    ]:
        val_a = snap_a.get(key)
        val_b = snap_b.get(key)
        if val_a != val_b:
            env_deltas.append({
                "category": key,
                "label": label,
                "val_a": val_a,
                "val_b": val_b,
                "is_regression": False # Hard to auto-judge regression on driver version
            })

    try:
        from src.execution_environment import execution_environment_from_snapshot

        env_a = execution_environment_from_snapshot(snap_a)
        env_b = execution_environment_from_snapshot(snap_b)
        if env_a.get("support_tier") != env_b.get("support_tier"):
            env_deltas.append({
                "category": "execution_support_tier",
                "label": "Execution support tier",
                "val_a": env_a.get("support_tier"),
                "val_b": env_b.get("support_tier"),
                "is_regression": False,
            })
    except Exception:
        pass

    try:
        from src.telemetry_provider import provider_evidence_label

        provider_a = provider_evidence_label(snap_a)
        provider_b = provider_evidence_label(snap_b)
        if provider_a != provider_b:
            env_deltas.append({
                "category": "telemetry_provider_evidence",
                "label": "Telemetry provider evidence",
                "val_a": provider_a,
                "val_b": provider_b,
                "is_regression": False,
            })
    except Exception:
        pass

    # Thermal trend
    temp_a = snap_a.get("cpu_temp_at_start_c")
    temp_b = snap_b.get("cpu_temp_at_start_c")
    if temp_a and temp_b and abs(temp_a - temp_b) > 5:
        env_deltas.append({
            "category": "thermal",
            "label": "Start CPU Temp",
            "val_a": f"{temp_a}C",
            "val_b": f"{temp_b}C",
            "is_regression": temp_b > temp_a
        })

    # 3. Shared Configs (Intersection Set)
    shared_ids = sorted(set(scores_a.keys()) & set(scores_b.keys()))
    config_deltas = []
    tg_shifts = []

    for cid in shared_ids:
        s_a = scores_a[cid]
        s_b = scores_b[cid]

        tg_a = s_a.get("warm_tg_median") or 0.0
        tg_b = s_b.get("warm_tg_median") or 0.0
        ttft_a = s_a.get("warm_ttft_median_ms") or 0.0
        ttft_b = s_b.get("warm_ttft_median_ms") or 0.0
        cv_a = s_a.get("warm_tg_cv") or 0.0
        cv_b = s_b.get("warm_tg_cv") or 0.0

        tg_delta_pct = (tg_b - tg_a) / tg_a * 100.0 if tg_a > 0 else 0.0
        ttft_delta_pct = (ttft_b - ttft_a) / ttft_a * 100.0 if ttft_a > 0 else 0.0

        tg_shifts.append(tg_delta_pct)

        config_deltas.append({
            "config_id": cid,
            "tg_a": tg_a,
            "tg_b": tg_b,
            "tg_delta_pct": tg_delta_pct,
            "ttft_a": ttft_a,
            "ttft_b": ttft_b,
            "ttft_delta_pct": ttft_delta_pct,
            "cv_a": cv_a,
            "cv_b": cv_b,
            "significance_label": calculate_significance(tg_delta_pct, cv_a, cv_b),
            "flags": []
        })

    import statistics
    median_shift = statistics.median(tg_shifts) if tg_shifts else 0.0

    # 4. Winners
    winner_a_id = next((cid for cid, s in scores_a.items() if s.get("is_score_winner")), None)
    winner_b_id = next((cid for cid, s in scores_b.items() if s.get("is_score_winner")), None)

    w_a = scores_a.get(winner_a_id) if winner_a_id else None
    w_b = scores_b.get(winner_b_id) if winner_b_id else None

    winner_shift_tg_pct = None
    if w_a and w_b:
        tg_wa = w_a.get("warm_tg_median") or 0.0
        tg_wb = w_b.get("warm_tg_median") or 0.0
        if tg_wa > 0:
            winner_shift_tg_pct = (tg_wb - tg_wa) / tg_wa * 100.0

    # 5. Elimination Diff
    lost_in_b = sorted(set(elim_b.keys()) - set(elim_a.keys()))
    gained_in_b = sorted(set(elim_a.keys()) - set(elim_b.keys()))

    def count_reasons(elim_dict):
        counts = {}
        for r in elim_dict.values():
            counts[r] = counts.get(r, 0) + 1
        return counts

    # Interpretation
    primary = "No significant performance shift observed."
    if abs(median_shift) > 5:
        dir_label = "improvement" if median_shift > 0 else "regression"
        primary = f"Significant overall {dir_label} ({median_shift:+.1f}% TG) detected across shared configs."
    elif winner_shift_tg_pct and abs(winner_shift_tg_pct) > 5:
        primary = f"Winner performance shifted by {winner_shift_tg_pct:+.1f}% TG, despite stable shared-config baseline."

    return CompareResult(
        campaign_a=meta_a,
        campaign_b=meta_b,
        methodology=meth,
        env_deltas=env_deltas,
        winner_a=w_a,
        winner_b=w_b,
        winner_shift_tg_pct=winner_shift_tg_pct,
        shared_configs=config_deltas,
        median_shared_tg_shift_pct=median_shift,
        lost_in_b=lost_in_b,
        gained_in_b=gained_in_b,
        elimination_counts_a=count_reasons(elim_a),
        elimination_counts_b=count_reasons(elim_b),
        primary_finding=primary,
        overall_confidence="high" if meth["grade"] == "compatible" else "medium"
    )
