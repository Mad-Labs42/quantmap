"""
QuantMap — score.py

Elimination filtering and composite scoring for campaign results.

ELIMINATION FILTERS (applied before scoring, thresholds locked before data is seen):
    max_cv                  0.05    CV > 5% = too inconsistent
    max_thermal_events      0       Any throttling disqualifies
    max_outliers            3       More than 3 outliers per ~25 warm samples
    max_warm_ttft_p90_ms    500     P90 TTFT > 500ms is unacceptable
    min_success_rate        0.90    Allows ~3 transient failures per 30 requests
    min_warm_tg_p10         7.0     Hard floor below which config is unusable
    min_valid_warm_count    10      Require minimum samples for statistical validity

SCORING (Option A — min-max normalization, MDD §12.2 + fix):
    Each metric is normalized to [0,1] across the passing candidate set.
    Latency metrics are inverted (lower ms = higher score).
    Weights are applied to normalized values.

    score = sum(normalized_metric * weight for each metric)

    Weights:
        warm_tg_median      0.35    Primary metric
        warm_tg_p10         0.20    Worst-case floor
        warm_ttft_median    0.20    Typical responsiveness (inverted)
        warm_ttft_p90       0.10    Worst-case responsiveness (inverted)
        cold_ttft_median    0.10    First impression (inverted)
        pp_median           0.05    Prompt throughput

    NOTE: The original MDD formula mixed raw t/s values with pp_median (~100 t/s),
    causing pp to dominate regardless of its 5% weight. Min-max normalization
    corrects this: weights correspond to actual relative importance.

THREE REQUIRED REPORT VIEWS:
    1. Score winner      — highest composite score passing all filters
    2. Pareto frontier   — configs not dominated on both TG AND TTFT simultaneously
    3. Highest raw TG    — config with highest warm_tg_median passing filters

SPEED_MEDIUM FLAG:
    Configs where cycle-5 speed_medium warm TG drops >5% relative to speed_short
    median are flagged in the report for human review.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
import yaml

from src.db import get_connection
from src.analyze import analyze_campaign

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Elimination filter thresholds — LOCKED before any data is seen
# ---------------------------------------------------------------------------
ELIMINATION_FILTERS: dict[str, float] = {
    "max_cv":                   0.05,
    "max_thermal_events":       0,
    "max_outliers":             3,       # raised from 2: 3/25 = 12% of warm samples is acceptable
    "max_warm_ttft_p90_ms":     500.0,
    "min_success_rate":         0.90,    # lowered from 1.0: allows ~3 transient failures per 30 requests
    "min_warm_tg_p10":          7.0,
    "min_valid_warm_count":     10,      # Full: 4×5 + 4 = 24 warm speed_short; Standard: 2×5 + 4 = 14. Both exceed 10.
                                         # Quick mode injects filter_overrides={"min_valid_warm_count": 3} via RunPlan
                                         # because Quick's only cycle yields 4 warm speed_short (last req = speed_medium).
                                         # NOTE: counts above are warm speed_short only (analyze.py valid_warm_request_count).
                                         # warm_samples_per_config in run_plan.py includes speed_medium (+1 per config).
}

# Scoring weights — sum to 1.0
SCORE_WEIGHTS: dict[str, float] = {
    "warm_tg_median":    0.35,
    "warm_tg_p10":       0.20,
    "warm_ttft_median":  0.20,   # inverted before normalization
    "warm_ttft_p90":     0.10,   # inverted before normalization
    "cold_ttft_median":  0.10,   # inverted before normalization
    "pp_median":         0.05,
}

# speed_medium degradation flag threshold
SPEED_MEDIUM_DEGRADATION_THRESHOLD = 5.0  # percent


# ---------------------------------------------------------------------------
# Elimination
# ---------------------------------------------------------------------------

def apply_elimination_filters(
    stats: dict[str, dict[str, Any]],
    filters: dict[str, float] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """
    Apply elimination filters to config stats.

    Args:
        stats:   per-config statistics dict from analyze_campaign()
        filters: effective filter thresholds.  If None, uses ELIMINATION_FILTERS.
                 Pass a merged dict to apply campaign-level overrides (see
                 score_campaign(filter_overrides=...)).

    Returns:
        passing:    config_id -> stats for configs that passed all filters
        eliminated: config_id -> reason string for eliminated configs

    Filters are applied in a deterministic order. The first failing filter
    is recorded as the elimination reason.
    """
    effective = filters if filters is not None else ELIMINATION_FILTERS

    passing: dict[str, dict[str, Any]] = {}
    eliminated: dict[str, str] = {}

    for config_id, s in stats.items():
        reason = _check_filters(config_id, s, effective)
        if reason:
            eliminated[config_id] = reason
            logger.info("ELIMINATED %s: %s", config_id, reason)
        else:
            passing[config_id] = s
            logger.info("PASSING    %s: tg_median=%.2f cv=%.3f ttft_p90=%.0fms",
                        config_id,
                        s.get("warm_tg_median") or 0,
                        s.get("warm_tg_cv") or 0,
                        s.get("warm_ttft_p90_ms") or 0)

    logger.info(
        "Elimination complete: %d passing, %d eliminated",
        len(passing), len(eliminated),
    )
    return passing, eliminated


def _check_filters(config_id: str, s: dict[str, Any], f: dict[str, float]) -> str | None:
    """Return elimination reason string, or None if the config passes all filters."""

    # Insufficient data — cannot score
    valid_warm = s.get("valid_warm_request_count", 0)
    if valid_warm < f["min_valid_warm_count"]:
        return f"insufficient_data: {valid_warm} valid warm requests (min {int(f['min_valid_warm_count'])})"

    # Thermal events
    thermal = s.get("thermal_events", 0)
    if thermal > f["max_thermal_events"]:
        return f"thermal_events: {thermal} > {int(f['max_thermal_events'])}"

    # CV
    cv = s.get("warm_tg_cv")
    if cv is not None and cv > f["max_cv"]:
        return f"cv_too_high: {cv:.4f} > {f['max_cv']}"

    # Outliers
    outliers = s.get("outlier_count", 0)
    if outliers > f["max_outliers"]:
        return f"too_many_outliers: {outliers} > {int(f['max_outliers'])}"

    # Warm TTFT P90
    ttft_p90 = s.get("warm_ttft_p90_ms")
    if ttft_p90 is not None and ttft_p90 > f["max_warm_ttft_p90_ms"]:
        return f"warm_ttft_p90_too_high: {ttft_p90:.0f}ms > {f['max_warm_ttft_p90_ms']:.0f}ms"

    # Success rate
    sr = s.get("success_rate", 0.0)
    if sr < f["min_success_rate"]:
        return f"low_success_rate: {sr:.3f} < {f['min_success_rate']}"

    # TG P10 floor
    tg_p10 = s.get("warm_tg_p10")
    if tg_p10 is not None and tg_p10 < f["min_warm_tg_p10"]:
        return f"tg_p10_below_floor: {tg_p10:.2f} < {f['min_warm_tg_p10']}"

    return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_scores(
    passing: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """
    Compute composite scores for passing configs using min-max normalization.

    Each metric is scaled to [0,1] range across the passing candidate set.
    For latency metrics (TTFT), values are inverted (1/ms) before normalization
    so that lower latency maps to higher score.

    If only one config passes, it receives score=1.0 on all metrics.

    Returns a DataFrame with one row per passing config, sorted by composite score.
    """
    if not passing:
        return pd.DataFrame()

    rows = []
    for config_id, s in passing.items():
        rows.append({
            "config_id": config_id,
            "warm_tg_median":   s.get("warm_tg_median") or 0.0,
            "warm_tg_p10":      s.get("warm_tg_p10") or 0.0,
            "warm_ttft_median": s.get("warm_ttft_median_ms") or 9999.0,
            "warm_ttft_p90":    s.get("warm_ttft_p90_ms") or 9999.0,
            "cold_ttft_median": s.get("cold_ttft_median_ms") or 9999.0,
            "pp_median":        s.get("pp_median") or 0.0,
        })

    df = pd.DataFrame(rows).set_index("config_id")

    # Invert latency metrics: higher 1/ms = better
    for col in ("warm_ttft_median", "warm_ttft_p90", "cold_ttft_median"):
        df[col] = 1000.0 / df[col].clip(lower=1.0)  # 1000/ms → comparable range

    # Min-max normalize each metric to [0, 1]
    # If all values are identical, all configs get 1.0 (tied on this metric)
    score_series = pd.Series(0.0, index=df.index)
    normalized_cols: dict[str, pd.Series] = {}

    for metric, weight in SCORE_WEIGHTS.items():
        col = df[metric]
        col_min = col.min()
        col_max = col.max()

        if col_max == col_min:
            # All configs identical on this metric — each gets full weight
            normalized = pd.Series(1.0, index=df.index)
        else:
            normalized = (col - col_min) / (col_max - col_min)

        normalized_cols[metric] = normalized
        score_series += normalized * weight

    df["composite_score"] = score_series
    df = df.sort_values("composite_score", ascending=False)
    df["rank_overall"] = range(1, len(df) + 1)

    # Mark report views
    df["is_score_winner"] = False
    df["is_highest_tg"] = False
    df["pareto_dominated"] = False

    if len(df) > 0:
        df.at[df.index[0], "is_score_winner"] = True

        # Highest raw TG (may differ from score winner)
        highest_tg_idx = df["warm_tg_median"].idxmax()
        df.at[highest_tg_idx, "is_highest_tg"] = True

        # Pareto frontier: not dominated on BOTH warm_tg_median AND warm_ttft
        # A config is Pareto-dominated if another config is better on BOTH metrics.
        # We restore original warm_ttft for Pareto calculation.
        for metric, weight in SCORE_WEIGHTS.items():
            pass  # already done above

        # Recalculate from passing stats for Pareto (need original TG and TTFT)
        tg_vals = pd.Series(
            {cid: passing[cid].get("warm_tg_median") or 0.0 for cid in passing}
        )
        ttft_vals = pd.Series(
            {cid: passing[cid].get("warm_ttft_median_ms") or 9999.0 for cid in passing}
        )

        for config_id in df.index:
            tg = tg_vals.get(config_id, 0.0)
            ttft = ttft_vals.get(config_id, 9999.0)
            # Dominated if any other config has strictly better TG AND strictly better TTFT
            dominated = any(
                tg_vals[other] > tg and ttft_vals[other] < ttft
                for other in df.index
                if other != config_id
            )
            df.at[config_id, "pareto_dominated"] = dominated

    logger.info(
        "Scoring complete. Winner: %s (score=%.4f). Highest TG: %s. Pareto non-dominated: %d",
        df.index[0] if len(df) > 0 else "none",
        df["composite_score"].iloc[0] if len(df) > 0 else 0,
        df[df["is_highest_tg"]].index[0] if df["is_highest_tg"].any() else "none",
        int((~df["pareto_dominated"]).sum()),
    )

    return df


# ---------------------------------------------------------------------------
# speed_medium flag
# ---------------------------------------------------------------------------

def check_speed_medium_flags(stats: dict[str, dict[str, Any]]) -> dict[str, bool]:
    """
    Return dict mapping config_id -> True if speed_medium degradation > 5%.
    Flagged configs are highlighted in the report for human review.
    """
    flags: dict[str, bool] = {}
    threshold = SPEED_MEDIUM_DEGRADATION_THRESHOLD

    for config_id, s in stats.items():
        deg = s.get("speed_medium_degradation_pct")
        flagged = deg is not None and deg > threshold
        flags[config_id] = flagged
        if flagged:
            logger.warning(
                "speed_medium flag: %s degradation=%.1f%% (threshold %.0f%%)",
                config_id, deg, threshold,
            )

    return flags


# ---------------------------------------------------------------------------
# Main campaign scoring
# ---------------------------------------------------------------------------

def score_campaign(
    campaign_id: str,
    db_path: Path,
    baseline: dict[str, Any],
    filter_overrides: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Run the full analysis + scoring pipeline for a completed campaign.

    Args:
        campaign_id:      campaign to score
        db_path:          path to lab.sqlite
        baseline:         loaded baseline.yaml dict (for reference comparison)
        filter_overrides: optional threshold overrides merged on top of ELIMINATION_FILTERS.
                          Keys must match ELIMINATION_FILTERS keys; values replace defaults.
                          Unspecified keys use the ELIMINATION_FILTERS defaults.
                          runner.py builds this from two sources merged in priority order:
                            1. mode-level overrides from RunPlan.filter_overrides
                               (e.g. Custom mode injects {"min_valid_warm_count": 1})
                            2. campaign YAML elimination_overrides (YAML wins on conflict)

    Returns a dict with keys:
        stats              — per-config statistics from analyze_campaign()
        passing            — config IDs + stats that passed all filters
        eliminated         — config IDs + reason strings for eliminated configs
        scores_df          — DataFrame with composite scores and report views
        speed_medium_flags — dict of config_id -> bool
        winner             — config_id of score winner (or None)
        highest_tg         — config_id with highest raw TG (or None)
        pareto_frontier    — list of config_ids on Pareto frontier
        effective_filters  — the actual filter thresholds applied (for report audit)
    """
    # Build effective filter thresholds — defaults merged with any campaign overrides
    effective_filters: dict[str, float] = {**ELIMINATION_FILTERS, **(filter_overrides or {})}
    if filter_overrides:
        logger.info(
            "Campaign elimination overrides applied for %s: %s",
            campaign_id, filter_overrides,
        )

    # Get reference values for baseline comparison
    ref = baseline.get("reference", {})
    ref_warm_tg = ref.get("warm_tg_median_ts", 8.18)
    ref_warm_ttft = ref.get("warm_ttft_median_ms", 200.0)

    # Compute stats
    stats = analyze_campaign(campaign_id, db_path)

    # Compute speed_medium flags (before elimination — flagged passing configs get noted)
    speed_medium_flags = check_speed_medium_flags(stats)

    # Apply elimination filters with effective thresholds
    passing, eliminated = apply_elimination_filters(stats, filters=effective_filters)

    # Score passing configs
    scores_df = compute_scores(passing)

    # Compute baseline-relative improvement for each passing config
    if not scores_df.empty:
        for config_id in scores_df.index:
            s = passing[config_id]
            tg = s.get("warm_tg_median")
            ttft = s.get("warm_ttft_median_ms")
            tg_pct = ((tg - ref_warm_tg) / ref_warm_tg * 100.0) if tg else None
            ttft_pct = ((ref_warm_ttft - ttft) / ref_warm_ttft * 100.0) if ttft else None
            scores_df.at[config_id, "warm_tg_vs_baseline_pct"] = tg_pct
            scores_df.at[config_id, "warm_ttft_vs_baseline_pct"] = ttft_pct

    # Write to scores table
    _write_scores_to_db(campaign_id, stats, passing, eliminated, scores_df, speed_medium_flags, db_path)

    # Extract summary
    winner = scores_df.index[0] if not scores_df.empty else None
    highest_tg = (
        scores_df[scores_df["is_highest_tg"]].index[0]
        if not scores_df.empty and scores_df["is_highest_tg"].any()
        else None
    )
    pareto_frontier = (
        scores_df[~scores_df["pareto_dominated"]].index.tolist()
        if not scores_df.empty
        else []
    )

    result = {
        "stats": stats,
        "passing": passing,
        "eliminated": eliminated,
        "scores_df": scores_df,
        "speed_medium_flags": speed_medium_flags,
        "winner": winner,
        "highest_tg": highest_tg,
        "pareto_frontier": pareto_frontier,
        "effective_filters": effective_filters,  # actual thresholds applied (audit trail)
    }

    _log_summary(campaign_id, result)
    return result


def _write_scores_to_db(
    campaign_id: str,
    stats: dict[str, dict[str, Any]],
    passing: dict,
    eliminated: dict[str, str],
    scores_df: pd.DataFrame,
    speed_medium_flags: dict[str, bool],
    db_path: Path,
) -> None:
    """Write all scoring results to lab.sqlite scores table."""
    with get_connection(db_path) as conn:
        for config_id, s in stats.items():
            # Score data from DataFrame
            composite_score = None
            rank = None
            pareto_dominated = None
            is_highest_tg = None
            is_score_winner = None
            tg_vs_baseline = None
            ttft_vs_baseline = None

            if not scores_df.empty and config_id in scores_df.index:
                row = scores_df.loc[config_id]
                composite_score = float(row.get("composite_score", 0))
                rank = int(row.get("rank_overall", 0))
                pareto_dominated = bool(row.get("pareto_dominated", False))
                is_highest_tg = bool(row.get("is_highest_tg", False))
                is_score_winner = bool(row.get("is_score_winner", False))
                tg_vs_baseline = row.get("warm_tg_vs_baseline_pct")
                ttft_vs_baseline = row.get("warm_ttft_vs_baseline_pct")
                if tg_vs_baseline is not None and not np.isnan(tg_vs_baseline):
                    tg_vs_baseline = float(tg_vs_baseline)
                else:
                    tg_vs_baseline = None
                if ttft_vs_baseline is not None and not np.isnan(ttft_vs_baseline):
                    ttft_vs_baseline = float(ttft_vs_baseline)
                else:
                    ttft_vs_baseline = None

            passed = config_id in passing
            elim_reason = eliminated.get(config_id)
            med_flag = speed_medium_flags.get(config_id, False)
            deg_pct = s.get("speed_medium_degradation_pct")

            conn.execute(
                """INSERT OR REPLACE INTO scores (
                    campaign_id, config_id,
                    warm_tg_median, warm_tg_p10, warm_tg_p90,
                    warm_tg_cv, warm_tg_mean, warm_tg_std,
                    warm_ttft_median_ms, warm_ttft_p90_ms, warm_ttft_p10_ms,
                    cold_ttft_median_ms, cold_ttft_p90_ms,
                    pp_median, pp_p10, pp_p90,
                    thermal_events, outlier_count, success_rate,
                    valid_warm_request_count, valid_cold_request_count,
                    speed_medium_warm_tg_median, speed_medium_degradation_pct, speed_medium_flagged,
                    composite_score, rank_overall,
                    passed_filters, elimination_reason,
                    pareto_dominated, is_highest_tg, is_score_winner,
                    warm_tg_vs_baseline_pct, warm_ttft_vs_baseline_pct
                ) VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )""",
                (
                    campaign_id, config_id,
                    s.get("warm_tg_median"), s.get("warm_tg_p10"), s.get("warm_tg_p90"),
                    s.get("warm_tg_cv"), s.get("warm_tg_mean"), s.get("warm_tg_std"),
                    s.get("warm_ttft_median_ms"), s.get("warm_ttft_p90_ms"), s.get("warm_ttft_p10_ms"),
                    s.get("cold_ttft_median_ms"), s.get("cold_ttft_p90_ms"),
                    s.get("pp_median"), s.get("pp_p10"), s.get("pp_p90"),
                    s.get("thermal_events", 0), s.get("outlier_count", 0), s.get("success_rate", 0),
                    s.get("valid_warm_request_count", 0), s.get("valid_cold_request_count", 0),
                    s.get("speed_medium_warm_tg_median"), deg_pct, int(med_flag),
                    composite_score, rank,
                    int(passed), elim_reason,
                    int(pareto_dominated) if pareto_dominated is not None else None,
                    int(is_highest_tg) if is_highest_tg is not None else None,
                    int(is_score_winner) if is_score_winner is not None else None,
                    tg_vs_baseline, ttft_vs_baseline,
                ),
            )
        conn.commit()


def _log_summary(campaign_id: str, result: dict[str, Any]) -> None:
    """Log the scoring summary."""
    stats = result["stats"]
    passing = result["passing"]
    eliminated = result["eliminated"]
    scores_df = result["scores_df"]

    logger.info("=== SCORING SUMMARY: %s ===", campaign_id)
    logger.info("Total configs: %d", len(stats))
    logger.info("Passing: %d", len(passing))
    logger.info("Eliminated: %d", len(eliminated))

    if result["winner"]:
        w = result["winner"]
        s = passing.get(w, {})
        logger.info(
            "SCORE WINNER: %s — warm_tg_median=%.2f t/s  ttft_median=%.0fms  cv=%.3f",
            w,
            s.get("warm_tg_median") or 0,
            s.get("warm_ttft_median_ms") or 0,
            s.get("warm_tg_cv") or 0,
        )
    else:
        logger.warning("No winner — all configs eliminated")

    if result["highest_tg"] and result["highest_tg"] != result["winner"]:
        h = result["highest_tg"]
        s = passing.get(h, {})
        logger.info(
            "HIGHEST TG (differs from winner): %s — warm_tg_median=%.2f t/s",
            h, s.get("warm_tg_median") or 0,
        )

    pareto = result["pareto_frontier"]
    logger.info("Pareto frontier (%d configs): %s", len(pareto), pareto)

    for elim_id, reason in sorted(eliminated.items()):
        logger.info("  Eliminated %s: %s", elim_id, reason)


# ---------------------------------------------------------------------------
# C08 interaction campaign generation
# ---------------------------------------------------------------------------

# Campaign IDs whose winners feed into C08.
_C08_DEPENDENCIES = [
    "C01_threads_batch",
    "C02_n_parallel",
    "C03_kv_cache_type",
    "C04_context_size",
    "C05_threads",
    "C06_ubatch",
    "C07_batch",
]

# Maps campaign IDs to the config variable name(s) they sweep.
_CAMPAIGN_VARIABLES: dict[str, list[str]] = {
    "C01_threads_batch": ["threads_batch"],
    "C02_n_parallel":    ["n_parallel"],
    "C03_kv_cache_type": ["kv_cache_type_k", "kv_cache_type_v"],
    "C04_context_size":  ["context_size"],
    "C05_threads":       ["threads"],
    "C06_ubatch":        ["ubatch_size"],
    "C07_batch":         ["batch_size"],
}


def generate_c08(db_path: Path, output_path: Path) -> bool:
    """
    Generate C08_interaction.yaml from C01-C07 winners.

    For each completed campaign in C01-C07, extracts the score winner's
    variable value(s). Combines all winners into a single interaction config
    that applies every winning value simultaneously.

    Returns True on success, False if any dependency is missing.
    """
    missing: list[str] = []
    winners: dict[str, Any] = {}  # variable_name -> winning value

    for campaign_id in _C08_DEPENDENCIES:
        with get_connection(db_path) as conn:
            row = conn.execute(
                """SELECT config_id, composite_score
                   FROM scores
                   WHERE campaign_id=? AND is_score_winner=1""",
                (campaign_id,),
            ).fetchone()

        if row is None:
            missing.append(campaign_id)
            continue

        winner_config_id = row["config_id"]

        # Extract the winning variable value from the configs table
        with get_connection(db_path) as conn:
            cfg_row = conn.execute(
                "SELECT variable_name, variable_value FROM configs WHERE id=?",
                (winner_config_id,),
            ).fetchone()

        if cfg_row is None:
            missing.append(f"{campaign_id} (winner {winner_config_id} not in configs)")
            continue

        var_name = cfg_row["variable_name"]
        var_value = json.loads(cfg_row["variable_value"])

        # For C03 (kv_cache_type), the winner applies to both K and V
        var_names = _CAMPAIGN_VARIABLES.get(campaign_id, [var_name])
        for vn in var_names:
            winners[vn] = var_value

        logger.info("  %s winner: %s = %s", campaign_id, var_name, var_value)

    if missing:
        print(f"ERROR: The following campaigns are not yet complete (no score winner):")
        for m in missing:
            print(f"  - {m}")
        print(f"\nComplete these campaigns first, then re-run --generate-c08.")
        return False

    # Build the combined interaction config value
    interaction_value = {
        "config_id": "C08_interaction_combined",
        "overrides": winners,
    }

    # Build the output YAML
    c08_data = {
        "campaign_id": "C08_interaction",
        "description": f"Interaction validation: winners from C01-C07 combined",
        "variable": "interaction",
        "values": [interaction_value],
        "type": "interaction",
        "auto_generated": True,
        "depends_on": _C08_DEPENDENCIES,
        "rationale": (
            "After primary sweeps C01-C07, this campaign tests the combined "
            "winning config to detect interaction effects between variables. "
            "If the combined config outperforms individual winners, the "
            "variables compose well. If it regresses, interaction effects "
            "exist and further investigation is needed."
        ),
        "notes": [
            "This YAML was auto-generated by: python -m src.score --generate-c08",
            "Do not edit manually — regenerate from score data instead",
            f"Winners applied: {json.dumps(winners, default=str)}",
        ],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(c08_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"Generated {output_path}")
    print(f"\nWinners combined into interaction config:")
    for var_name, var_value in sorted(winners.items()):
        print(f"  {var_name}: {var_value}")
    print(f"\nTotal configs: 1 (combined winner)")
    print(f"Validate with: python -m src.runner --validate C08_interaction")
    return True


# ---------------------------------------------------------------------------
# Finalist campaign generation
# ---------------------------------------------------------------------------

def generate_finalist(db_path: Path, output_path: Path) -> bool:
    """
    Generate Finalist.yaml from C08_interaction winner.

    The Finalist campaign runs the C08 winner through an exhaustive validation:
    10 cycles × full request matrix to confirm the champion config with high
    statistical confidence.

    Returns True on success, False if C08 is not complete.
    """
    with get_connection(db_path) as conn:
        row = conn.execute(
            """SELECT config_id, composite_score
               FROM scores
               WHERE campaign_id='C08_interaction' AND is_score_winner=1""",
        ).fetchone()

    if row is None:
        print("ERROR: C08_interaction has no score winner.")
        print("Complete the C08_interaction campaign first, then re-run --generate-finalist.")
        return False

    winner_config_id = row["config_id"]

    # Extract the full config from the configs table
    with get_connection(db_path) as conn:
        cfg_row = conn.execute(
            "SELECT config_values_json FROM configs WHERE id=?",
            (winner_config_id,),
        ).fetchone()

    if cfg_row is None:
        print(f"ERROR: Winner config {winner_config_id} not found in configs table.")
        return False

    full_config = json.loads(cfg_row["config_values_json"])

    finalist_data = {
        "campaign_id": "Finalist",
        "description": f"Champion validation: C08 winner ({winner_config_id}), exhaustive test",
        "variable": "interaction",
        "values": [{
            "config_id": "Finalist_champion",
            "overrides": full_config,
        }],
        "type": "validation",
        "auto_generated": True,
        "depends_on": ["C08_interaction"],
        "cycles_per_config": 10,
        "rationale": (
            f"Final validation of the C08 interaction winner ({winner_config_id}). "
            "Runs 10 cycles across the full workload matrix to confirm the champion "
            "config with high statistical confidence (50 warm samples)."
        ),
        "notes": [
            "This YAML was auto-generated by: python -m src.score --generate-finalist",
            "Do not edit manually — regenerate from score data instead",
            f"Champion config: {winner_config_id}",
        ],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(finalist_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"Generated {output_path}")
    print(f"\nChampion config from C08: {winner_config_id}")
    print(f"Cycles: 10 (exhaustive validation)")
    print(f"Validate with: python -m src.runner --validate Finalist")
    return True


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QuantMap scoring utilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--generate-c08", action="store_true",
        help="Generate C08_interaction.yaml from C01-C07 winners"
    )
    parser.add_argument(
        "--generate-finalist", action="store_true",
        help="Generate Finalist.yaml from C08_interaction winner"
    )
    return parser.parse_args()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    from src.config import LAB_ROOT

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = _parse_args()
    db_path = LAB_ROOT / "db" / "lab.sqlite"
    campaigns_dir = Path(__file__).parent.parent / "configs" / "campaigns"

    if args.generate_c08:
        ok = generate_c08(db_path, campaigns_dir / "C08_interaction.yaml")
        sys.exit(0 if ok else 1)

    if args.generate_finalist:
        ok = generate_finalist(db_path, campaigns_dir / "Finalist.yaml")
        sys.exit(0 if ok else 1)

    print("No action specified. Use --generate-c08 or --generate-finalist.")
    sys.exit(2)
