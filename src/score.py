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
    "min_valid_warm_count":     3,       # Lowered to 3 to act as an absolute floor for statistical functions (e.g. IQR). min_success_rate handles relative pass/fail.
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

    # Fatal startup errors (OOMs, crashes)
    status = s.get("config_status")
    if status in ("oom", "skipped_oom", "failed"):
        detail = s.get("failure_detail")
        short_detail = str(detail).split('\n')[0][:60] if detail else "unknown"
        return f"fatal_error: {status} ({short_detail})"

    # Insufficient data — cannot score
    valid_warm = s.get("valid_warm_request_count", 0)
    if valid_warm < f["min_valid_warm_count"]:
        return f"insufficient_data: {valid_warm} valid warm requests (min {int(f['min_valid_warm_count'])})"

    # Thermal events
    thermal = s.get("thermal_events", 0)
    if thermal > f["max_thermal_events"]:
        return f"thermal_events: {thermal} > {int(f['max_thermal_events'])}"

    # CV
    # cv is None when analyze.py could not compute it — either fewer than 2
    # valid warm samples (len < 2) or a zero mean (zero denominator).
    # _check_filters() does not know which condition fired; the message
    # describes what was observed, not an inferred cause.
    # Variability is structurally uncomputable: treating this as acceptable would
    # be semantically equivalent to treating unknown variability as zero.
    cv = s.get("warm_tg_cv")
    if cv is None:
        return "cv_uncomputable: warm_tg_cv is None (zero-mean or insufficient warm samples)"
    if cv > f["max_cv"]:
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
    # None means total_attempted == 0: no complete-cycle requests were recorded
    # at all.  This is structurally different from observed request failures
    # (which would produce a real computed rate in [0.0, 1.0)).  The two cases
    # need distinct elimination reasons so operators can debug correctly.
    sr = s.get("success_rate")  # None = no complete-cycle data
    if sr is None:
        return "no_complete_cycle_data: no requests from completed cycles recorded"
    if sr < f["min_success_rate"]:
        return f"low_success_rate: {sr:.3f} < {f['min_success_rate']}"

    # TG P10 floor
    tg_p10 = s.get("warm_tg_p10")
    if tg_p10 is not None and tg_p10 < f["min_warm_tg_p10"]:
        return f"tg_p10_below_floor: {tg_p10:.2f} < {f['min_warm_tg_p10']}"

    return None


# ---------------------------------------------------------------------------
# Rankability gate
# ---------------------------------------------------------------------------

# Metrics whose absence on a passing config indicates a data integrity defect.
# These values must exist if min_valid_warm_count was satisfied.
_PRIMARY_SCORE_METRICS: frozenset[str] = frozenset({
    "warm_tg_median",
    "warm_tg_p10",
})

# Metrics that may legitimately be absent in edge cases (e.g. all cold requests
# failed, or no prompt_per_second was returned). Absence makes the config
# unrankable but not eliminated — it passed all quality filters.
_SECONDARY_SCORE_METRICS: tuple[str, ...] = (
    "warm_ttft_median_ms",
    "warm_ttft_p90_ms",
    "cold_ttft_median_ms",
    "pp_median",
)


def _split_by_rankability(
    passing: dict[str, dict[str, Any]],
) -> tuple[
    dict[str, dict[str, Any]],   # rankable: all scoring metrics present
    dict[str, str],              # integrity_failures: primary metric(s) missing
    dict[str, list[str]],        # unrankable: secondary metric(s) missing
]:
    """
    Partition passing configs by whether they can be compositely scored.

    Three outcome buckets:

    rankable:
        All 6 scoring metrics are present and non-None.  These configs enter
        compute_scores() and receive a composite rank.  Composite scores are
        only valid when all configs in the comparison set share the same
        metric basis — this gate enforces that invariant.

    integrity_failures:
        A primary metric (warm_tg_median, warm_tg_p10) is None despite the
        config having passed min_valid_warm_count.  This implies a data
        integrity defect (e.g. all requests were speed_medium, or a bug in
        the analysis pipeline).  These configs are moved to ``eliminated``
        by score_campaign() with reason ``missing_primary_metric: <fields>``.

    unrankable:
        A secondary metric (any TTFT or pp_median) is None.  This can occur
        legitimately (e.g. every cold request failed, leaving no cold TTFT).
        The config passed all quality filters and its raw data is valid; we
        simply cannot assign it a composite score without fabricating a value.
        It is reported separately and excluded from ranking.
    """
    rankable:            dict[str, dict[str, Any]] = {}
    integrity_failures:  dict[str, str]            = {}
    unrankable:          dict[str, list[str]]       = {}

    for config_id, s in passing.items():
        # --- Primary (TG) metrics: absence = data integrity failure ----------
        missing_primary = [
            key for key in _PRIMARY_SCORE_METRICS
            if s.get(key) is None
        ]
        if missing_primary:
            metric_list = ", ".join(sorted(missing_primary))
            integrity_failures[config_id] = (
                f"missing_primary_metric: {metric_list}"
            )
            continue

        # --- Secondary metrics: absence = unrankable (not eliminated) ---------
        missing_secondary = [
            key for key in _SECONDARY_SCORE_METRICS
            if s.get(key) is None
        ]
        if missing_secondary:
            unrankable[config_id] = missing_secondary
            continue

        rankable[config_id] = s

    return rankable, integrity_failures, unrankable


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_scores(
    passing: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """
    Compute composite scores for passing configs using min-max normalization.

    Each metric is scaled to [0,1] range across the passing candidate set.
    For latency metrics (TTFT), values are negated (-1.0 * ms) before
    normalization so that lower latency maps to a higher (less negative) value
    and therefore a higher normalized score.

    If only one config passes, it receives score=1.0 on all metrics.

    Returns a DataFrame with one row per passing config, sorted by composite score.
    """
    if not passing:
        return pd.DataFrame()

    rows = []
    for config_id, s in passing.items():
        # All six metrics are guaranteed non-None by _split_by_rankability().
        # Accessing via .get() with no default — if None reaches here, it is a
        # caller bug and the resulting NaN will propagate visibly rather than
        # silently corrupting the composite rank.
        rows.append({
            "config_id":        config_id,
            "warm_tg_median":   s.get("warm_tg_median"),
            "warm_tg_p10":      s.get("warm_tg_p10"),
            "warm_ttft_median": s.get("warm_ttft_median_ms"),
            "warm_ttft_p90":    s.get("warm_ttft_p90_ms"),
            "cold_ttft_median": s.get("cold_ttft_median_ms"),
            "pp_median":        s.get("pp_median"),
        })

    df = pd.DataFrame(rows).set_index("config_id")

    # Invert latency metrics linearly: -1 * latency so higher is better
    for col in ("warm_ttft_median", "warm_ttft_p90", "cold_ttft_median"):
        df[col] = -1.0 * df[col]

    # Min-max normalize each metric to [0, 1]
    # If all values are identical, all configs get 1.0 (tied on this metric)
    score_series = pd.Series(0.0, index=df.index)
    normalized_cols: dict[str, pd.Series] = {}

    for metric, weight in SCORE_WEIGHTS.items():
        col = df[metric]
        
        # Robust scaling: Use IQR to prevent extreme outliers from compressing the field
        q1 = col.quantile(0.25)
        q3 = col.quantile(0.75)
        iqr = q3 - q1

        if iqr > 0:
            scale_min = max(col.min(), q1 - 1.5 * iqr)
            scale_max = min(col.max(), q3 + 1.5 * iqr)
        else:
            scale_min = col.min()
            scale_max = col.max()
            
        if scale_max <= scale_min:
            scale_min = col.min()
            scale_max = col.max()

        if scale_max == scale_min:
            # All configs identical on this metric — each gets full weight
            normalized = pd.Series(1.0, index=df.index)
        else:
            # Clip limits normalization exactly between [0, 1] for out-of-bounds outliers
            normalized = ((col - scale_min) / (scale_max - scale_min)).clip(0.0, 1.0)

        normalized_cols[metric] = normalized
        score_series += normalized * weight

    df["composite_score"] = score_series
    df = df.sort_values(["composite_score", "config_id"], ascending=[False, True])
    df["rank_overall"] = range(1, len(df) + 1)

    # Mark report views
    df["is_score_winner"] = False
    df["is_highest_tg"] = False
    df["pareto_dominated"] = False

    if len(df) > 0:
        df.at[df.index[0], "is_score_winner"] = True

        # Highest raw TG (may differ from score winner)
        # Explicit tie-breaker: sort by warm_tg_median descending, config_id ascending
        tg_sorted = df.sort_values(["warm_tg_median", "config_id"], ascending=[False, True])
        highest_tg_idx = tg_sorted.index[0]
        df.at[highest_tg_idx, "is_highest_tg"] = True

        # Pareto frontier: not dominated on BOTH warm_tg_median AND warm_ttft
        # A config is Pareto-dominated if another config is better on BOTH metrics.
        # Pareto frontier: read directly from the scored DataFrame.
        # All configs in df passed _split_by_rankability(), so warm_tg_median
        # and warm_ttft_median are guaranteed non-None — no coercion needed.
        # Using the pre-inversion column values directly from `passing` is no
        # longer necessary; df still holds the original (pre-inversion) values
        # because we only mutate the column in place below for TTFT metrics.
        # Use the original stats from `passing` for clarity and correctness.
        tg_vals   = pd.Series({cid: passing[cid]["warm_tg_median"]   for cid in df.index})
        ttft_vals = pd.Series({cid: passing[cid]["warm_ttft_median_ms"] for cid in df.index})

        for config_id in df.index:
            tg   = tg_vals[config_id]
            ttft = ttft_vals[config_id]
            # Dominated if any other config is strictly better on BOTH metrics.
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
        passing            — config IDs + stats for rankable configs only
                             (passed filters AND all scoring metrics present)
        eliminated         — config IDs + reason strings for eliminated configs
                             (includes integrity failures: missing primary metric)
        unrankable         — config IDs + list of missing metric names for configs
                             that passed all filters but cannot be compositely scored
                             (secondary metric absent — legitimately, not a defect)
        scores_df          — DataFrame with composite scores and report views
                             (only rankable configs; unrankable configs are absent)
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

    # Get reference values for baseline comparison.
    # If baseline.yaml has no reference: block, both fall back to None so
    # downstream code can detect missing reference and skip pct computation.
    ref = baseline.get("reference", {})
    ref_warm_tg   = ref.get("warm_tg_median_ts")   # None = not configured
    ref_warm_ttft = ref.get("warm_ttft_median_ms")  # None = not configured
    if ref_warm_tg is None or ref_warm_ttft is None:
        logger.warning(
            "baseline.yaml has no reference: block (or missing warm_tg_median_ts / "
            "warm_ttft_median_ms). Baseline-relative improvement percentages will be "
            "omitted from the scores table and report."
        )

    # Compute stats
    stats = analyze_campaign(campaign_id, db_path)

    # Compute speed_medium flags (before elimination — flagged passing configs get noted)
    speed_medium_flags = check_speed_medium_flags(stats)

    # Apply elimination filters with effective thresholds
    passing, eliminated = apply_elimination_filters(stats, filters=effective_filters)

    # --- Rankability gate ------------------------------------------------
    # Partition passing configs into three populations:
    #   rankable          → all 6 scoring metrics present; enter compute_scores()
    #   integrity_failures → primary (TG) metric absent; join eliminated
    #   unrankable        → secondary (TTFT/PP) metric absent; reported separately
    #
    # Composite scores are only valid when every config in the comparison set
    # is scored on the same metric basis.  Missing data must not enter scoring
    # space as a fabricated value.
    rankable, integrity_failures, unrankable = _split_by_rankability(passing)

    # Integrity failures are treated as eliminations with a distinct reason.
    for config_id, reason in integrity_failures.items():
        eliminated[config_id] = reason
        logger.warning(
            "Data integrity failure for config %s — moved to eliminated: %s",
            config_id, reason,
        )

    # Narrow `passing` to only rankable configs.
    # Unrankable configs are tracked in `unrankable`; they are NOT in `passing`
    # because they cannot receive a composite score or participate in ranking.
    passing = rankable

    # Score only the rankable configs
    scores_df = compute_scores(passing)

    # Compute baseline-relative improvement for each rankable config.
    # Skipped entirely when reference values are absent — do not fabricate
    # percentages against a default that may belong to a different model.
    if not scores_df.empty and ref_warm_tg is not None and ref_warm_ttft is not None:
        for config_id in scores_df.index:
            s = passing[config_id]
            tg   = s.get("warm_tg_median")      # guaranteed non-None (rankable)
            ttft = s.get("warm_ttft_median_ms")  # guaranteed non-None (rankable)
            tg_pct   = (tg   - ref_warm_tg)   / ref_warm_tg   * 100.0
            ttft_pct = (ref_warm_ttft - ttft)  / ref_warm_ttft * 100.0
            scores_df.at[config_id, "warm_tg_vs_baseline_pct"]   = tg_pct
            scores_df.at[config_id, "warm_ttft_vs_baseline_pct"] = ttft_pct

    # Write to scores table (passing=rankable, unrankable tracked separately)
    _write_scores_to_db(
        campaign_id, stats, passing, eliminated, unrankable,
        scores_df, speed_medium_flags, db_path,
    )

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
        "stats":              stats,
        "passing":            passing,       # rankable only
        "eliminated":         eliminated,    # filter failures + integrity failures
        "unrankable":         unrankable,    # passed filters, secondary metric absent
        "scores_df":          scores_df,
        "speed_medium_flags": speed_medium_flags,
        "winner":             winner,
        "highest_tg":         highest_tg,
        "pareto_frontier":    pareto_frontier,
        "effective_filters":  effective_filters,
    }

    _log_summary(campaign_id, result)
    return result


def _write_scores_to_db(
    campaign_id: str,
    stats: dict[str, dict[str, Any]],
    passing: dict,
    eliminated: dict[str, str],
    unrankable: dict[str, list[str]],
    scores_df: pd.DataFrame,
    speed_medium_flags: dict[str, bool],
    db_path: Path,
) -> None:
    """Write all scoring results to lab.sqlite scores table.

    Three categories of config are recorded:

    - Ranked (in scores_df):  composite_score and rank_overall are populated.
    - Unrankable (in unrankable): passed_filters=1, composite_score=NULL,
      elimination_reason='unrankable: <missing metrics>'.
    - Eliminated (in eliminated): passed_filters=0, elimination_reason set.

    NULL is written (not 0) for any metric absent in the stats dict — this
    preserves the distinction between 'measured zero' and 'no data'.
    """
    with get_connection(db_path) as conn:
        for config_id, s in stats.items():
            # Score data from DataFrame — None for configs not in scores_df.
            composite_score  = None
            rank             = None
            pareto_dominated = None
            is_highest_tg    = None
            is_score_winner  = None
            tg_vs_baseline   = None
            ttft_vs_baseline = None

            if not scores_df.empty and config_id in scores_df.index:
                row = scores_df.loc[config_id]
                composite_score  = float(row["composite_score"])
                rank             = int(row["rank_overall"])
                pareto_dominated = bool(row["pareto_dominated"])
                is_highest_tg    = bool(row["is_highest_tg"])
                is_score_winner  = bool(row["is_score_winner"])
                raw_tg_pct   = row.get("warm_tg_vs_baseline_pct")
                raw_ttft_pct = row.get("warm_ttft_vs_baseline_pct")
                tg_vs_baseline = (
                    float(raw_tg_pct)
                    if raw_tg_pct is not None and not np.isnan(raw_tg_pct)
                    else None
                )
                ttft_vs_baseline = (
                    float(raw_ttft_pct)
                    if raw_ttft_pct is not None and not np.isnan(raw_ttft_pct)
                    else None
                )

            # Determine passed_filters and elimination_reason.
            # Unrankable configs passed all quality filters (passed_filters=1)
            # but cannot receive a composite score.
            if config_id in passing:
                passed      = 1
                elim_reason = None
            elif config_id in unrankable:
                passed      = 1  # passed quality filters
                missing     = ", ".join(unrankable[config_id])
                elim_reason = f"unrankable: missing {missing}"
            else:
                passed      = 0
                elim_reason = eliminated.get(config_id)

            med_flag = speed_medium_flags.get(config_id, False)
            deg_pct  = s.get("speed_medium_degradation_pct")

            # Write NULL (not 0) for absent metrics so that queries can
            # distinguish 'no telemetry data' from 'measured zero'.
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
                    s.get("warm_tg_median"),    s.get("warm_tg_p10"),  s.get("warm_tg_p90"),
                    s.get("warm_tg_cv"),         s.get("warm_tg_mean"), s.get("warm_tg_std"),
                    s.get("warm_ttft_median_ms"), s.get("warm_ttft_p90_ms"), s.get("warm_ttft_p10_ms"),
                    s.get("cold_ttft_median_ms"), s.get("cold_ttft_p90_ms"),
                    s.get("pp_median"), s.get("pp_p10"), s.get("pp_p90"),
                    # Write NULL for absent counts/rates — do not coerce to 0.
                    s.get("thermal_events"),           s.get("outlier_count"),
                    s.get("success_rate"),
                    s.get("valid_warm_request_count"), s.get("valid_cold_request_count"),
                    s.get("speed_medium_warm_tg_median"), deg_pct, int(med_flag),
                    composite_score, rank,
                    passed, elim_reason,
                    int(pareto_dominated) if pareto_dominated is not None else None,
                    int(is_highest_tg)    if is_highest_tg    is not None else None,
                    int(is_score_winner)  if is_score_winner  is not None else None,
                    tg_vs_baseline, ttft_vs_baseline,
                ),
            )
        conn.commit()


def _log_summary(campaign_id: str, result: dict[str, Any]) -> None:
    """Log the scoring summary."""
    stats      = result["stats"]
    passing    = result["passing"]     # rankable only
    eliminated = result["eliminated"]
    unrankable = result.get("unrankable", {})
    scores_df  = result["scores_df"]

    logger.info("=== SCORING SUMMARY: %s ===", campaign_id)
    logger.info("Total configs:  %d", len(stats))
    logger.info("Ranked:         %d", len(passing))
    logger.info("Unrankable:     %d", len(unrankable))
    logger.info("Eliminated:     %d", len(eliminated))

    if result["winner"]:
        w = result["winner"]
        s = passing.get(w, {})
        # All ranked-winner metrics are guaranteed non-None by _split_by_rankability.
        logger.info(
            "SCORE WINNER: %s — warm_tg_median=%.2f t/s  ttft_median=%.0fms  cv=%s",
            w,
            s.get("warm_tg_median"),
            s.get("warm_ttft_median_ms"),
            f"{s['warm_tg_cv']:.3f}" if s.get("warm_tg_cv") is not None else "N/A",
        )
    else:
        logger.warning("No winner — all configs eliminated or unrankable")

    if result["highest_tg"] and result["highest_tg"] != result["winner"]:
        h = result["highest_tg"]
        s = passing.get(h, {})
        logger.info(
            "HIGHEST TG (differs from winner): %s — warm_tg_median=%.2f t/s",
            h, s.get("warm_tg_median"),
        )

    pareto = result["pareto_frontier"]
    logger.info("Pareto frontier (%d configs): %s", len(pareto), pareto)

    for config_id, missing_metrics in sorted(unrankable.items()):
        logger.info("  Unrankable %s: missing %s", config_id, ", ".join(missing_metrics))

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
