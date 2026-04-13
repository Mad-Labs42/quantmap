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
        warm_ttft_median_ms 0.20    Typical responsiveness (inverted)
        warm_ttft_p90_ms    0.10    Worst-case responsiveness (inverted)
        cold_ttft_median_ms 0.10    First impression (inverted)
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
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

import pandas as pd
import numpy as np
import yaml

from src.db import get_connection
from src.analyze import analyze_campaign
from src import governance
from src.trust_identity import (
    MethodologySnapshotError,
    load_methodology_for_historical_scoring,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Elimination filter thresholds — Governed by the Experiment Profile
# ---------------------------------------------------------------------------

class _LazyGovernanceMapping(Mapping[str, float]):
    """Mapping proxy that loads current governance only when values are used."""

    def __init__(self, loader: Callable[[], dict[str, float]]) -> None:
        self._loader = loader

    def _data(self) -> dict[str, float]:
        return self._loader()

    def __getitem__(self, key: str) -> float:
        return self._data()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data())

    def __len__(self) -> int:
        return len(self._data())

    def __repr__(self) -> str:
        return repr(self._data())


class _LazyGovernanceSet:
    """Set-like proxy for legacy metric constants without import-time loading."""

    def __init__(self, loader: Callable[[], frozenset[str]]) -> None:
        self._loader = loader

    def _data(self) -> frozenset[str]:
        return self._loader()

    def __contains__(self, value: object) -> bool:
        return value in self._data()

    def __iter__(self) -> Iterator[str]:
        return iter(self._data())

    def __len__(self) -> int:
        return len(self._data())

    def __repr__(self) -> str:
        return repr(self._data())


class _LazyGovernanceTuple:
    """Tuple-like proxy for legacy metric constants without import-time loading."""

    def __init__(self, loader: Callable[[], tuple[str, ...]]) -> None:
        self._loader = loader

    def _data(self) -> tuple[str, ...]:
        return self._loader()

    def __contains__(self, value: object) -> bool:
        return value in self._data()

    def __iter__(self) -> Iterator[str]:
        return iter(self._data())

    def __len__(self) -> int:
        return len(self._data())

    def __getitem__(self, index: int) -> str:
        return self._data()[index]

    def __repr__(self) -> str:
        return repr(self._data())


ELIMINATION_FILTERS: Mapping[str, float] = _LazyGovernanceMapping(
    governance.get_legacy_elimination_filters
)

# Scoring weights — Governed by the Experiment Profile
SCORE_WEIGHTS: Mapping[str, float] = _LazyGovernanceMapping(
    governance.get_legacy_score_weights
)

# Dimension Audit Safeguards (Phase 2 Refinements)
DIMENSION_FAILURE_MIN_CONFIGS = 3    # Only collapse if at least this many configs were tested
DIMENSION_WARNING_THRESHOLD   = 0.5  # Warn if > 50% NaN but not collapsed

# speed_medium degradation flag threshold
SPEED_MEDIUM_DEGRADATION_THRESHOLD = 5.0  # percent

_METHODOLOGY_HEADER = """
================================================================================
QuantMap Governance Methodology v1.0 (Stable)
Absolute-Reference Normalization Active
================================================================================
"""


def rank_overall(passing_dict: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """
    Convenience wrapper for compute_scores used primarily by determinism tests.
    Takes a dict of config stats and returns the ranked DataFrame.
    """
    scores_df, _, _, _ = compute_scores(
        passing_dict, {}, passing_dict,
        governance.DEFAULT_PROFILE,
        governance.BUILTIN_REGISTRY,
        {},
    )
    return scores_df


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

    # Fatal startup errors (OOMs, crashes) or instrumentation degradation (Severity B)
    status = s.get("config_status")
    if status in ("oom", "skipped_oom", "failed", "degraded"):
        detail = s.get("failure_detail") or s.get("elimination_reason")
        short_detail = str(detail).split('\n')[0][:60] if detail else "unknown"
        category = "fatal_error" if status != "degraded" else "instrumentation_degraded"
        return f"{category}: {status} ({short_detail})"

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
_PRIMARY_SCORE_METRICS = _LazyGovernanceSet(governance.get_legacy_primary_score_metrics)

# Metrics that may legitimately be absent in edge cases.
# Absence makes the config unrankable but not eliminated.
_SECONDARY_SCORE_METRICS = _LazyGovernanceTuple(governance.get_legacy_secondary_score_metrics)


def _split_by_rankability(
    passing: dict[str, dict[str, Any]],
    registry: governance.MetricRegistry,
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

    primary_metrics = registry.get_required_score_metrics()
    secondary_metrics = registry.get_optional_score_metrics()

    for config_id, s in passing.items():
        # --- Primary (TG) metrics: absence = data integrity failure ----------
        missing_primary = [
            key for key in primary_metrics
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
            key for key in secondary_metrics
            if s.get(key) is None
        ]
        if missing_secondary:
            unrankable[config_id] = missing_secondary
            continue

        rankable[config_id] = s

    return rankable, integrity_failures, unrankable


# ---------------------------------------------------------------------------
# Phase 3.2: Statistical Hardening Utilities
# ---------------------------------------------------------------------------

def _apply_utility_transform(
    value: float | None,
    metric_name: str,
    rankable_stats: dict[str, dict[str, Any]],
    registry: governance.MetricRegistry,
    provided_reference: float | None = None,
) -> float:
    """
    Apply the Registry-governed transform to map raw metrics into [0, 1] utility space.
    """
    if value is None or np.isnan(value):
        return 0.0

    mdef = registry.get(metric_name)
    transform = mdef.default_transform
    params = mdef.transform_params or {}
    direction = mdef.objective_direction  # maximize | minimize

    if transform == governance.TransformFamily.raw:
        return float(value)

    if transform == governance.TransformFamily.reference_based:
        # Phase 3.3: Tiered Reference Lookup
        # 1. Use provided_reference (Registry or Baseline YAML)
        # 2. Fall back to best-in-batch (Cohort-Relative)
        anchor = provided_reference
        if anchor is None:
            all_vals = [s.get(metric_name) for s in rankable_stats.values() if s.get(metric_name) is not None]
            if not all_vals:
                return 0.0
            anchor = max(all_vals) if direction == governance.ObjectiveDirection.maximize else min(all_vals)

        if direction == governance.ObjectiveDirection.maximize:
            return float(value / anchor) if anchor > 0 else 0.0
        else:
            return float(anchor / value) if value > 0 else 0.0

    if transform == governance.TransformFamily.threshold_utility:
        threshold = params.get("threshold", 500.0)
        if direction == governance.ObjectiveDirection.minimize:
            return 1.0 if value <= threshold else 0.0
        else:
            return 1.0 if value >= threshold else 0.0

    if transform == governance.TransformFamily.saturating_utility:
        # Piecewise linear implementation (Phase 3.2 Locked Decision)
        if params.get("curve_type") == "piecewise_linear":
            x_sat = params.get("x_saturated", 100.0 if "cold" in metric_name else 50.0)
            x_zero = params.get("x_zero", 2500.0 if "cold" in metric_name else 500.0)
            
            if direction == governance.ObjectiveDirection.minimize:
                if value <= x_sat: return 1.0
                if value >= x_zero: return 0.0
                return float(1.0 - (value - x_sat) / (x_zero - x_sat))
            else:
                if value >= x_sat: return 1.0
                if value <= x_zero: return 0.0
                return float((value - x_zero) / (x_sat - x_zero))

    # Warning: No specific transform matched. 
    # Must NOT return raw value as it corrupts composite scores.
    logger.warning("No utility transform matched for %s (type: %s). Defaulting to 1.0 (optimistic)", metric_name, transform)
    return 1.0


def _compute_config_lcb(
    config_id: str,
    full_stats: dict[str, dict[str, Any]],
    rankable_stats: dict[str, dict[str, Any]],
    profile: governance.ExperimentProfile,
    registry: governance.MetricRegistry,
    provided_references: dict[str, float],
) -> tuple[float, float, str]:
    """
    Compute LCB composite score using either the Preferred (Cycle-Level)
    or Fallback (Metric-SE) method.
    
    Returns: (lcb_score, composite_se, method_label)
    """
    s = full_stats[config_id]
    cycles = s.get("cycle_stats", [])
    k = 1.0 if profile.confidence_policy == governance.ConfidencePolicy.lcb_k1 else 2.0
    weights = profile.weights

    # --- Preferred Method: Cycle-Level Empirical Distribution ---
    if cycles and len(cycles) >= 2:
        cycle_composites = []
        for cyc in cycles:
            comp = 0.0
            for m_name, w in weights.items():
                val = cyc.get(m_name)
                # Preferred method (cycle-level empirical) iterates over providing_references correctly
                u = _apply_utility_transform(val, m_name, rankable_stats, registry, provided_references.get(m_name))
                comp += u * w
            cycle_composites.append(comp)
        
        mean_comp = np.mean(cycle_composites)
        se_comp = np.std(cycle_composites, ddof=1) / np.sqrt(len(cycle_composites))
        lcb = mean_comp - k * se_comp
        return float(lcb), float(se_comp), "preferred (cycle-level empirical)"

    # --- Fallback Method: Per-Metric SE Aggregation ---
    # SE_comp = sqrt( sum( (w_i * SE_i)^2 ) )
    var_sum = 0.0
    point_est_comp = 0.0
    for m_name, w in weights.items():
        # Point estimate (Winsorized Mean for 3.2 rank-bearing metrics)
        val = s.get(f"{m_name}_winsorized_mean") or s.get(m_name)
        ref_val = provided_references.get(m_name)
        u = _apply_utility_transform(val, m_name, rankable_stats, registry, ref_val)
        point_est_comp += u * w
        
        # Standard Error of the metric
        # We need the std of the estimator. For mean, SE = std / sqrt(N)
        std_val = s.get(f"{m_name}_winsorized_std") or s.get(f"{m_name.replace('_median', '_std')}") or 0.0
        # Wait, if it's a p10, SE is complex. Fallback uses mean SE as proxy.
        n = s.get("valid_warm_request_count", 1)
        se_m = std_val / np.sqrt(n) if n > 0 else 0.0
        
        # Uncertainty (SE) propagation — Phase 3.2 Refinement
        # Scale raw SE by the transform sensitivity to get utility SE.
        mdef = registry.get(m_name)
        if mdef.default_transform == governance.TransformFamily.reference_based:
            # Anchor lookup must match point-estimate anchor for internal consistency
            anchor = ref_val
            if anchor is None:
                all_vals = [st.get(m_name) for st in rankable_stats.values() if st.get(m_name) is not None]
                anchor = max(all_vals) if mdef.objective_direction == governance.ObjectiveDirection.maximize else min(all_vals)
            
            u_se = se_m / anchor if anchor and anchor > 0 else 0.0
        elif mdef.default_transform == governance.TransformFamily.saturating_utility:
            params = mdef.transform_params or {}
            x_sat = params.get("x_saturated", 100.0 if "cold" in m_name else 50.0)
            x_zero = params.get("x_zero", 2500.0 if "cold" in m_name else 500.0)
            u_se = se_m / abs(x_zero - x_sat) if x_zero != x_sat else 0.0
        else:
            u_se = 0.0
            
        var_sum += (w * u_se) ** 2
        
    se_comp = np.sqrt(var_sum)
    lcb = point_est_comp - k * se_comp
    logger.debug("LCB Result for %s: point=%f, se=%f, lcb=%f", config_id, point_est_comp, se_comp, lcb)
    return float(lcb), float(se_comp), "fallback (per-metric aggregation)"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_scores(
    rankable_stats:    dict[str, dict[str, Any]],
    unrankable_id_map: dict[str, list[str]],
    full_stats:         dict[str, dict[str, Any]],
    profile:           governance.ExperimentProfile,
    registry:          governance.MetricRegistry,
    provided_references: dict[str, float],
) -> pd.DataFrame:
    """
    Compute composite scores for rankable configs and identify performance
    leaders across the full evidence set (rankable + unrankable).

    - Recommendation Set: rankable_stats. Config IDs that passed all gates.
      Receives composite_score and rank_overall.
    - Evidence Set: rankable + configs in unrankable_id_map.
      Used to compute absolute Highest TG and Pareto non-dominance.

    Returns:
        tuple[pd.DataFrame, list[str], list[str], list[str]]:
            - final_df containing all rankable + unrankable configs
            - collapsed_dimensions: list of metrics with 100% NaN (meeting min_configs)
            - high_nan_warnings: list of metrics exceeding DIMENSION_WARNING_THRESHOLD
            - nan_invalid_ids: configs excluded due to NaNs in surviving dimensions
    """
    # 1. Build rankable dataframe for recommendation metrics
    rankable_rows = []
    for config_id, s in rankable_stats.items():
        rankable_rows.append({
            "config_id":        config_id,
            "warm_tg_median":   s.get("warm_tg_median"),
            "warm_tg_p10":      s.get("warm_tg_p10"),
            "warm_ttft_median_ms": s.get("warm_ttft_median_ms"),
            "warm_ttft_p90_ms":    s.get("warm_ttft_p90_ms"),
            "cold_ttft_median_ms": s.get("cold_ttft_median_ms"),
            "pp_median":        s.get("pp_median"),
        })

    if not rankable_rows:
        df_rankable = pd.DataFrame(columns=["config_id"])
    else:
        df_rankable = pd.DataFrame(rankable_rows).set_index("config_id")

    # --- Phase 2: Pre-solver Dimension Audit ---
    # Identify dimensions where EVERY config is NaN (Sensor Collapse)
    surviving_dimensions = []
    collapsed_dimensions = []
    high_nan_warnings = []
    total_configs = len(df_rankable)

    for metric in profile.weights.keys():
        if metric not in df_rankable.columns: continue
        nan_count = df_rankable[metric].isnull().sum()
        
        # Collapse rule: 100% NaN AND reaching minimum config sample size
        if nan_count == total_configs and total_configs >= DIMENSION_FAILURE_MIN_CONFIGS:
            collapsed_dimensions.append(metric)
            logger.warning("SENSOR COLLAPSE: Dimension '%s' is 100%% NaN. Excluded from scoring.", metric)
        else:
            surviving_dimensions.append(metric)
            # Warning rule: High NaN rate but not collapsed
            if total_configs > 0 and (nan_count / total_configs) >= DIMENSION_WARNING_THRESHOLD:
                high_nan_warnings.append(metric)
                logger.info("DIMENSION WARNING: Metric '%s' has high NaN rate (%.1f%%)",
                            metric, (nan_count / total_configs) * 100.0)

    # Hard NaN Guard: Exclude configs that have NaNs in any SURVIVING dimension.
    # These configs are truth-invalidated for composite comparison.
    is_nan_invalid = df_rankable[surviving_dimensions].isnull().any(axis=1)
    nan_invalid_ids = df_rankable.index[is_nan_invalid].tolist()
    if nan_invalid_ids:
        logger.warning(
            "COMPOSITE EXCLUSION: %d configs excluded from ranking due to NaNs in surviving dimensions: %s",
            len(nan_invalid_ids), nan_invalid_ids
        )

    # The clean set for scoring and Pareto
    df_clean = df_rankable[~is_nan_invalid].copy()
            
    if not df_clean.empty:
        # Phase 3.2 Confidence-Aware Scoring (LCB)
        lcb_series = pd.Series(0.0, index=df_clean.index)
        se_series = pd.Series(0.0, index=df_clean.index)
        method_series = pd.Series("", index=df_clean.index)
        
        for cid in df_clean.index:
            lcb, se, method = _compute_config_lcb(cid, full_stats, rankable_stats, profile, registry, provided_references)
            lcb_series[cid] = lcb
            se_series[cid] = se
            method_series[cid] = method
            
        df_clean["composite_score"] = lcb_series
        df_clean["composite_se"] = se_series
        df_clean["lcb_method"] = method_series
        df_clean = df_clean.sort_values(["composite_score", "config_id"], ascending=[False, True])
        df_clean["rank_overall"] = range(1, len(df_clean) + 1)
        df_clean["is_score_winner"] = False
        df_clean.at[df_clean.index[0], "is_score_winner"] = True
    else:
        # If no clean configs, we still need column structure for reindex
        df_clean["composite_score"] = pd.Series(dtype=float)
        df_clean["rank_overall"] = pd.Series(dtype=float)
        df_clean["is_score_winner"] = pd.Series(dtype=bool)

    # 3. EVIDENCE SET: rankable + unrankable
    evidence_ids = list(rankable_stats.keys()) + list(unrankable_id_map.keys())
    df_evidence = pd.DataFrame(index=evidence_ids, columns=["is_highest_tg", "pareto_dominated"])
    df_evidence["is_highest_tg"] = False
    df_evidence["pareto_dominated"] = False

    if evidence_ids:
        # Build evidence dataframe for absolute leaders
        evidence_rows = []
        for cid in evidence_ids:
            s = full_stats[cid]
            evidence_rows.append({
                "config_id": cid,
                "warm_tg_median": s["warm_tg_median"],
                "warm_ttft_median_ms": s["warm_ttft_median_ms"],
            })
        df_evidence_inner = pd.DataFrame(evidence_rows).set_index("config_id")
        df_evidence.update(df_evidence_inner)

        # Phase 2: Pareto NaN Exclusion (Truthfulness Gate)
        # Any config with NaN in TG or TTFT median is excluded from the Pareto set entirely.
        # It is neither dominator nor dominated; it is mathematically invisible to ranking.
        valid_pareto_mask = df_evidence_inner["warm_tg_median"].notnull() & df_evidence_inner["warm_ttft_median_ms"].notnull()
        df_valid_pareto = df_evidence_inner[valid_pareto_mask]

        if not df_valid_pareto.empty:
            # Highest raw TG (among valid configs)
            tg_sorted = df_valid_pareto.sort_values(["warm_tg_median", "config_id"], ascending=[False, True])
            df_evidence.at[tg_sorted.index[0], "is_highest_tg"] = True

            # Pareto frontier calculation over the valid subset
            tg_vals   = df_valid_pareto["warm_tg_median"]
            ttft_vals = df_valid_pareto["warm_ttft_median_ms"]
            
            for cid in df_valid_pareto.index:
                tg = tg_vals[cid]
                ttft = ttft_vals[cid]
                
                dominated = False
                for other in df_valid_pareto.index:
                    if other == cid:
                        continue
                    
                    otg = tg_vals[other]
                    ottft = ttft_vals[other]
                    
                    # Hard NaN guards in dominance logic (Phase 2)
                    if not (np.isfinite(otg) and np.isfinite(ottft) and np.isfinite(tg) and np.isfinite(ttft)):
                        continue

                    # Hybrid tolerance checks
                    is_tg_near = np.isclose(otg, tg, atol=1e-9, rtol=1e-4)
                    is_ttft_near = np.isclose(ottft, ttft, atol=1e-9, rtol=1e-4)
                    
                    be_tg = (otg >= tg) or is_tg_near
                    be_ttft = (ottft <= ttft) or is_ttft_near
                    sb_tg = (otg > tg) and not is_tg_near
                    sb_ttft = (ottft < ttft) and not is_ttft_near
                    
                    if be_tg and be_ttft and (sb_tg or sb_ttft):
                        dominated = True
                        break
                        
                df_evidence.at[cid, "pareto_dominated"] = dominated
        else:
            logger.warning("Truthfulness Leak: No configs have finite TG/TTFT metrics for Pareto calculation.")

    # 4. UNIFY results into a single DataFrame for the reporter
    # rankable clean configs have scores/ranks; others (unrankable/NaN-invalid) have NaNs.
    final_df = df_clean.reindex(evidence_ids)
    final_df["is_highest_tg"]    = df_evidence["is_highest_tg"]
    final_df["pareto_dominated"] = df_evidence["pareto_dominated"]
    # Re-fill is_score_winner for unrankables as False
    final_df["is_score_winner"]  = final_df["is_score_winner"].fillna(False).astype(bool)
    
    # Add back warm metrics into final_df for those that were unrankable and thus NaN'd by reindex
    for cid in unrankable_id_map:
        final_df.at[cid, "warm_tg_median"] = full_stats[cid]["warm_tg_median"]
        final_df.at[cid, "warm_ttft_median_ms"] = full_stats[cid]["warm_ttft_median_ms"]

    # Final sort to ensure deterministic row order in the report/database
    # Rankable configs first (by rank), ties or unrankables by config_id
    final_df = final_df.sort_values(
        ["rank_overall", "config_id"], 
        ascending=[True, True], 
        na_position="last"
    )

    logger.info(
        "Scoring complete. Evidence set: %d config(s). Winner: %s. Highest TG: %s. Pareto non-dominated: %d",
        len(evidence_ids),
        final_df.index[0] if not final_df.empty else "none",
        final_df[final_df["is_highest_tg"]].index[0] if not final_df.empty and final_df["is_highest_tg"].any() else "none",
        int((~final_df["pareto_dominated"]).sum()) if not final_df.empty else 0,
    )

    return final_df, collapsed_dimensions, high_nan_warnings, nan_invalid_ids


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
    campaign: dict[str, Any] | None = None,
    filter_overrides: dict[str, float] | None = None,
    profile_name: str | None = None,
    force_new_anchors: bool = False,
    current_input: bool = False,
    current_input_reason: str = "initial_scoring",
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
    # Phase 1.1: historical scoring must be driven by persisted methodology
    # snapshots. Live governance files are allowed only for the initial
    # current-run scoring path or explicit current-input rescore.
    if force_new_anchors and not current_input:
        raise MethodologySnapshotError(
            "force_new_anchors requires explicit current-input mode; "
            "snapshot-locked scoring cannot re-anchor to current files."
        )

    (
        profile,
        registry,
        provided_references,
        ref_snapshot,
        methodology_snapshot_id,
        methodology_source,
    ) = load_methodology_for_historical_scoring(
        campaign_id,
        db_path,
        allow_current_input=current_input,
        profile_name=profile_name,
        force_new_anchors=force_new_anchors,
    )

    print(_METHODOLOGY_HEADER)
    logger.info(
        "Governance: %s v%s (%s)",
        profile.name,
        profile.version,
        methodology_source,
    )

    # Build effective filter thresholds — defaults merged with any campaign overrides.
    effective_filters: dict[str, float] = {**profile.gate_overrides, **(filter_overrides or {})}
    if filter_overrides:
        logger.info(
            "Campaign elimination overrides applied for %s: %s",
            campaign_id, filter_overrides,
        )

    if methodology_source == "current_input_explicit":
        # Build the tier-1 references (Registry > Baseline YAML > Fallback)
        # from the explicit current inputs, then persist them as a new snapshot.
        baseline_ref = baseline.get("reference", {})
        key_map = {
            "warm_tg_median": "warm_tg_median_ts",
            "warm_ttft_median_ms": "warm_ttft_median_ms"
        }

        for m_name in profile.weights.keys():
            mdef = registry.get(m_name)
            ref_val = None
            source = "best-in-batch"
            provenance = "cohort-relative"

            if mdef.fixed_reference_value is not None:
                ref_val = mdef.fixed_reference_value
                source = "registry"
                provenance = mdef.reference_provenance or "registry:generation_1"

            yaml_key = key_map.get(m_name)
            if yaml_key and baseline_ref.get(yaml_key) is not None:
                ref_val = baseline_ref[yaml_key]
                if source == "registry":
                    logger.warning("METHODOLOGY OVERRIDE: Baseline YAML superseding Registry for %s", m_name)
                source = "baseline_yaml"
                provenance = f"override:{baseline.get('name', 'unknown')}"

            if ref_val is not None:
                provided_references[m_name] = ref_val

            ref_snapshot[m_name] = {
                "value": ref_val,
                "source": source,
                "provenance": provenance,
            }

        methodology_snapshot_id = _persist_methodology_snapshot(
            campaign_id,
            ref_snapshot,
            db_path,
            profile=profile,
            registry=registry,
            snapshot_kind=(
                "current_input_rescore"
                if current_input_reason == "current_input_rescore"
                else "scoring"
            ),
            capture_quality="complete",
            capture_source=f"score_campaign:{current_input_reason}",
        )
    
    # Legacy ref vars for report logic (kept for backward compatibility with return dict/display)
    ref_warm_tg = provided_references.get("warm_tg_median")
    ref_warm_ttft = provided_references.get("warm_ttft_median_ms")

    # Compute stats
    stats = analyze_campaign(campaign_id, db_path)

    # Identify abandoned configs (in DB but not in current YAML)
    # Rule: configs in DB that are missing from the YAML's generated IDs.
    active_ids: set[str] = set()
    abandoned_ids: set[str] = set()
    if campaign:
        try:
            from src.runner import build_config_list  # noqa: PLC0415
            active_configs = build_config_list(baseline, campaign)
            active_ids = {c["config_id"] for c in active_configs}
            abandoned_ids = set(stats.keys()) - active_ids
            if abandoned_ids:
                logger.info(
                    "Identified %d abandoned configs (in DB but missing from current YAML)",
                    len(abandoned_ids)
                )
        except Exception as exc:
            logger.warning("Could not identify abandoned configs: %s", exc)

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
    rankable, integrity_failures, unrankable = _split_by_rankability(passing, registry)

    # Integrity failures are treated as eliminations with a distinct reason.
    for config_id, reason in integrity_failures.items():
        eliminated[config_id] = reason
        logger.warning(
            "Data integrity failure for config %s — moved to eliminated: %s",
            config_id, reason,
        )

    # Narrow `passing` to only rankable configs for legacy compatibility in return dict.
    # Unrankable configs are tracked in `unrankable`; they are NOT in `passing`
    # because they cannot receive a composite score or participate in ranking.
    passing = rankable

    # Score only the rankable configs, but compute evidence flags over evidence set
    scores_df, collapsed_dims, high_nan_warns, nan_invalid_ids = compute_scores(
        rankable, 
        unrankable, 
        stats,
        profile,
        registry,
        provided_references,
    )

    # Compute baseline-relative improvement for each rankable config.
    # Skipped entirely when reference values are absent — do not fabricate
    # percentages against a default that may belong to a different model.
    if not scores_df.empty and ref_warm_tg is not None and ref_warm_ttft is not None:
        for config_id in scores_df.index:
            if config_id not in passing:
                continue
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
        scores_df, speed_medium_flags, db_path, methodology_snapshot_id,
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
        "campaign_id":        campaign_id,
        "stats":              stats,
        "passing":            passing,       # rankable only
        "unrankable":         unrankable,
        "eliminated":         eliminated,
        "abandoned":          list(abandoned_ids),
        "scores_df":          scores_df,
        "winner":             winner,
        "highest_tg":         highest_tg,
        "pareto_frontier":    pareto_frontier,
        "effective_filters":  effective_filters,
        "collapsed_dimensions": collapsed_dims,
        "high_nan_warnings":  high_nan_warns,
        "nan_invalid_ids":    nan_invalid_ids,
        "governance_methodology": ref_snapshot,
        "methodology_snapshot_id": methodology_snapshot_id,
        "methodology_source": methodology_source,
        "provided_references": provided_references,
        "scoring_profile":    profile,
        "registry":           registry,
    }

    _log_summary(campaign_id, result)
    return result


def _persist_methodology_snapshot(
    campaign_id: str,
    snapshot: dict[str, Any],
    db_path: Path,
    *,
    profile: Any,
    registry: Any,
    snapshot_kind: str,
    capture_quality: str,
    capture_source: str,
) -> int:
    """
    Persist the methodology snapshot used to interpret a campaign.

    Also keeps the legacy notes_json block updated as a transitional reader
    bridge until all consumers have moved to methodology_snapshots.
    """
    profile_path = Path(getattr(governance, "_PROFILES_DIR")) / f"{profile.name}.yaml"
    registry_path = Path(getattr(governance, "_METRICS_YAML"))

    def _read_text(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None

    def _hash_text(text: str | None) -> str | None:
        if text is None:
            return None
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    profile_text = _read_text(profile_path)
    registry_text = _read_text(registry_path)
    actual_capture_quality = capture_quality
    if capture_quality == "complete" and (profile_text is None or registry_text is None):
        actual_capture_quality = "partial"
    now_utc = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        with conn:
            # Ensure the campaign row exists (UPSERT-lite)
            # Need to provide NOT NULL columns: name, created_at
            now_str = now_utc
            conn.execute(
                "INSERT OR IGNORE INTO campaigns (id, name, created_at, run_mode) VALUES (?, ?, ?, 'standard')", 
                (campaign_id, campaign_id, now_str)
            )

            conn.execute(
                "UPDATE methodology_snapshots SET is_current=0 WHERE campaign_id=?",
                (campaign_id,),
            )
            cur = conn.execute(
                """
                INSERT INTO methodology_snapshots (
                    campaign_id, created_at, snapshot_kind, methodology_version,
                    profile_name, profile_version, profile_yaml_content,
                    registry_yaml_content, weights_json, gates_json, anchors_json,
                    source_paths_json, source_hashes_json, capture_quality,
                    capture_source, is_current
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    campaign_id,
                    now_utc,
                    snapshot_kind,
                    "1.0",
                    profile.name,
                    profile.version,
                    profile_text,
                    registry_text,
                    json.dumps(dict(profile.weights), default=str),
                    json.dumps(dict(profile.gate_overrides), default=str),
                    json.dumps(snapshot, default=str),
                    json.dumps({
                        "profile_yaml": str(profile_path),
                        "registry_yaml": str(registry_path),
                    }),
                    json.dumps({
                        "profile_yaml_sha256": _hash_text(profile_text),
                        "registry_yaml_sha256": _hash_text(registry_text),
                    }),
                    actual_capture_quality,
                    capture_source,
                ),
            )
            snapshot_id = int(cur.lastrowid)
            
            # Load existing notes
            curr = conn.execute("SELECT notes_json FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            notes = {}
            if curr and curr[0]:
                try:
                    notes = json.loads(curr[0])
                except (json.JSONDecodeError, TypeError):
                    notes = {"legacy_notes": curr[0]}
            
            # Merge snapshot into a namespaced block
            notes["governance_methodology"] = {
                "version": "1.0",
                "snapshot_at_utc": now_utc,
                "references": snapshot,
                "methodology_snapshot_id": snapshot_id,
                "capture_quality": actual_capture_quality,
            }
            
            conn.execute(
                "UPDATE campaigns SET notes_json=? WHERE id=?",
                (json.dumps(notes), campaign_id)
            )
        logger.info(
            "Persisted governance methodology snapshot %s for %s",
            snapshot_id, campaign_id,
        )
        return snapshot_id
    finally:
        conn.close()


def _write_scores_to_db(
    campaign_id: str,
    stats: dict[str, dict[str, Any]],
    passing: dict,
    eliminated: dict[str, str],
    unrankable: dict[str, list[str]],
    scores_df: pd.DataFrame,
    speed_medium_flags: dict[str, bool],
    db_path: Path,
    methodology_snapshot_id: int | None,
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
        # Delete ALL prior score rows for this campaign before writing new ones.
        # Without this, configs removed from the YAML between runs retain stale
        # winner/pareto flags in the DB.  generate_c08() queries
        # "is_score_winner=1" — a ghost winner from a prior run would corrupt the
        # C08 config.  The DELETE is inside the same connection as the INSERTs so
        # both succeed or both fail atomically.
        conn.execute("DELETE FROM scores WHERE campaign_id=?", (campaign_id,))

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
                    warm_tg_vs_baseline_pct, warm_ttft_vs_baseline_pct,
                    methodology_snapshot_id
                ) VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
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
                    tg_vs_baseline, ttft_vs_baseline, methodology_snapshot_id,
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
