"""
QuantMap — analyze.py

Statistical analysis of campaign results from lab.sqlite.
Computes per-config statistics from valid warm request data.

Metrics computed:
    warm_tg_median, warm_tg_p10, warm_tg_p90, warm_tg_cv, warm_tg_mean, warm_tg_std
    warm_ttft_median, warm_ttft_p90, warm_ttft_p10
    cold_ttft_median, cold_ttft_p90
    pp_median, pp_p10, pp_p90
    thermal_events (count)
    outlier_count (TG values below IQR floor)
    success_rate
    speed_medium_warm_tg_median, speed_medium_degradation_pct

Only valid cycles (status='complete') contribute to statistics.
Invalid cycles are retained in raw.jsonl but excluded from all analysis.

OUTLIER DEFINITION:
    A warm TG value is an outlier if it falls below Q1 - 1.5 * IQR.
    Applied per-config across all valid warm speed_short requests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np

from src.db import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core analysis function
# ---------------------------------------------------------------------------

def analyze_campaign(campaign_id: str, db_path: Path) -> dict[str, dict[str, Any]]:
    """
    Compute per-config statistics for all configs in a campaign.

    Returns a dict mapping config_id -> stats_dict.
    Each stats_dict contains all metrics described in the module docstring.

    Only includes requests where:
      - cycle_status = 'complete'  (cycle was valid)
      - outcome = 'success'
    """
    logger.info("Analyzing campaign: %s", campaign_id)

    with get_connection(db_path) as conn:
        # ── All data is loaded in a single connection open/close. ──────────────
        # Processing happens entirely in-memory after this block closes.
        # This avoids the previous pattern of opening 2 extra connections per
        # config inside the processing loop (HIGH-3).

        # All valid request records for this campaign
        df = pd.read_sql_query(
            """
            SELECT r.*
            FROM requests r
            JOIN cycles c ON r.cycle_id = c.id
            WHERE r.campaign_id = ?
              AND r.cycle_status = 'complete'
              AND c.status = 'complete'
              AND r.outcome = 'success'
            """,
            conn,
            params=(campaign_id,),
        )

        # Thermal events per config
        thermal_df = pd.read_sql_query(
            """
            SELECT config_id,
                   COUNT(*) as event_count
            FROM telemetry
            WHERE campaign_id = ?
              AND (power_limit_throttling = 1 OR cpu_temp_c >= 100.0)
            GROUP BY config_id
            """,
            conn,
            params=(campaign_id,),
        )

        # All config IDs (including those with no valid requests)
        all_configs_df = pd.read_sql_query(
            "SELECT id, status, failure_detail FROM configs WHERE campaign_id = ?",
            conn,
            params=(campaign_id,),
        )
        all_configs = all_configs_df.to_dict("records")

        # Request counts per config: total attempted and successful.
        # Previously fetched one-at-a-time inside the loop (2 queries × N configs);
        # now loaded in a single GROUP BY query before the loop. (HIGH-3 fix)
        counts_df = pd.read_sql_query(
            """
            SELECT config_id,
                   COUNT(*)                                           AS total_attempted,
                   SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS total_success
            FROM requests
            WHERE campaign_id = ?
              AND cycle_status = 'complete'
            GROUP BY config_id
            """,
            conn,
            params=(campaign_id,),
        )

    thermal_by_config = dict(zip(thermal_df["config_id"], thermal_df["event_count"]))
    counts_by_config: dict[str, tuple[int, int]] = {
        row.config_id: (int(row.total_attempted), int(row.total_success))
        for _, row in counts_df.iterrows()
    }

    stats: dict[str, dict[str, Any]] = {}

    for cfg_row in all_configs:
        config_id = cfg_row["id"]
        status = cfg_row["status"]
        failure_detail = cfg_row["failure_detail"]

        cfg_df = df[df["config_id"] == config_id]
        
        # If the config failed to even generate requests (e.g. OOM, bad config),
        # return a dummy struct so it isn't completely erased from the report.
        if len(cfg_df) == 0 and status in ("oom", "skipped_oom", "failed"):
            stats[config_id] = {
                "valid_warm_request_count": 0,
                "config_status": status,
                "failure_detail": failure_detail,
                "success_rate": None,
            }
            continue

        # Separate warm/cold and request types
        warm_short = cfg_df[
            (cfg_df["is_cold"] == 0) & (cfg_df["request_type"] == "speed_short")
        ]
        cold_reqs = cfg_df[cfg_df["is_cold"] == 1]
        warm_medium = cfg_df[
            (cfg_df["is_cold"] == 0) & (cfg_df["request_type"] == "speed_medium")
        ]

        # TG (predicted_per_second) for warm speed_short
        warm_tg = warm_short["predicted_per_second"].dropna().values

        # TTFT for warm and cold
        warm_ttft = warm_short["ttft_ms"].dropna().values
        cold_ttft = cold_reqs["ttft_ms"].dropna().values

        # PP (prompt_per_second) — speed_short warm requests only.
        # Using all request types would conflate prompt throughput across
        # contexts of very different lengths (speed_medium uses a 2× longer
        # prompt), making pp_median non-comparable across campaigns or with
        # the warm TG metric which is also speed_short-only. (LOW-6 fix)
        pp = warm_short["prompt_per_second"].dropna().values

        valid_warm_count = len(warm_tg)
        valid_cold_count = len(cold_ttft)

        # Success rate from pre-loaded counts (no DB round-trip per config).
        # Numerator is ALL successful requests of any type — not just speed_short.
        # The original code omitted speed_medium / quality_* warm successes from
        # the numerator while counting them in the denominator, causing systematic
        # underreporting of success_rate. (Fixed in analyze.py previously.)
        total_attempted, total_success = counts_by_config.get(config_id, (0, 0))
        # None signals no complete-cycle requests at all — structurally different
        # from observed failures (which produce a real rate in [0.0, 1.0)).
        # _check_filters() branches on None to emit a distinct elimination reason.
        success_rate = (
            total_success / total_attempted if total_attempted > 0 else None
        )

        # Compute outliers (IQR method on warm TG)
        outlier_count = 0
        if len(warm_tg) >= 4:
            q1 = np.percentile(warm_tg, 25)
            q3 = np.percentile(warm_tg, 75)
            iqr = q3 - q1
            lower_fence = q1 - 1.5 * iqr
            outlier_count = int(np.sum(warm_tg < lower_fence))

        # Coefficient of variation (std/mean).
        # Uses ddof=1 (sample std) throughout — warm_tg values are a sample drawn
        # from the true performance distribution, not the full population.
        # ddof=0 (population std) would underestimate spread by sqrt(n/(n-1));
        # at n=25 that's ~2%, small but methodologically incorrect. (MED-2 fix)
        warm_tg_cv = (
            float(np.std(warm_tg, ddof=1) / np.mean(warm_tg))
            if len(warm_tg) >= 2 and np.mean(warm_tg) > 0
            else None
        )

        # speed_medium degradation
        speed_medium_tg: float | None = None
        speed_medium_degradation_pct: float | None = None
        if len(warm_medium) > 0 and "predicted_per_second" in warm_medium.columns:
            med_vals = warm_medium["predicted_per_second"].dropna().values
            if len(med_vals) > 0:
                speed_medium_tg = float(np.median(med_vals))
                if len(warm_tg) > 0:
                    ref_tg = float(np.median(warm_tg))
                    if ref_tg > 0:
                        speed_medium_degradation_pct = (
                            (ref_tg - speed_medium_tg) / ref_tg * 100.0
                        )

        stats[config_id] = {
            "config_status": status,
            "failure_detail": failure_detail,
            # Warm TG stats
            "warm_tg_median": float(np.median(warm_tg)) if len(warm_tg) > 0 else None,
            "warm_tg_p10": float(np.percentile(warm_tg, 10)) if len(warm_tg) > 0 else None,
            "warm_tg_p90": float(np.percentile(warm_tg, 90)) if len(warm_tg) > 0 else None,
            "warm_tg_mean": float(np.mean(warm_tg)) if len(warm_tg) > 0 else None,
            "warm_tg_std": float(np.std(warm_tg, ddof=1)) if len(warm_tg) >= 2 else None,
            "warm_tg_cv": warm_tg_cv,

            # Warm TTFT stats
            "warm_ttft_median_ms": float(np.median(warm_ttft)) if len(warm_ttft) > 0 else None,
            "warm_ttft_p90_ms": float(np.percentile(warm_ttft, 90)) if len(warm_ttft) > 0 else None,
            "warm_ttft_p10_ms": float(np.percentile(warm_ttft, 10)) if len(warm_ttft) > 0 else None,

            # Cold TTFT stats
            "cold_ttft_median_ms": float(np.median(cold_ttft)) if len(cold_ttft) > 0 else None,
            "cold_ttft_p90_ms": float(np.percentile(cold_ttft, 90)) if len(cold_ttft) > 0 else None,

            # PP stats
            "pp_median": float(np.median(pp)) if len(pp) > 0 else None,
            "pp_p10": float(np.percentile(pp, 10)) if len(pp) > 0 else None,
            "pp_p90": float(np.percentile(pp, 90)) if len(pp) > 0 else None,

            # Reliability
            "thermal_events": thermal_by_config.get(config_id, 0),
            "outlier_count": outlier_count,
            "success_rate": success_rate,
            "valid_warm_request_count": valid_warm_count,
            "valid_cold_request_count": valid_cold_count,
            "total_attempted": total_attempted,

            # speed_medium
            "speed_medium_warm_tg_median": speed_medium_tg,
            "speed_medium_degradation_pct": speed_medium_degradation_pct,
        }

        logger.info(
            "Config %s: warm_tg_median=%.2f p10=%.2f cv=%.3f "
            "ttft_median=%.0fms outliers=%d thermal=%d",
            config_id,
            stats[config_id]["warm_tg_median"] or 0,
            stats[config_id]["warm_tg_p10"] or 0,
            stats[config_id]["warm_tg_cv"] or 0,
            stats[config_id]["warm_ttft_median_ms"] or 0,
            stats[config_id]["outlier_count"],
            stats[config_id]["thermal_events"],
        )

    return stats


def get_telemetry_summary(campaign_id: str, config_id: str, db_path: Path) -> dict[str, Any]:
    """
    Return telemetry summary for a specific config.
    Used in report.py to explain outliers via thermal/background correlation.
    """
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                AVG(cpu_temp_c) as avg_cpu_temp,
                MAX(cpu_temp_c) as max_cpu_temp,
                AVG(gpu_temp_c) as avg_gpu_temp,
                MAX(gpu_temp_c) as max_gpu_temp,
                AVG(gpu_util_pct) as avg_gpu_util,
                AVG(cpu_util_pct) as avg_cpu_util,
                AVG(ram_used_gb) as avg_ram_gb,
                MAX(ram_used_gb) as max_ram_gb,
                AVG(gpu_vram_used_mb) as avg_vram_mb,
                MAX(gpu_vram_used_mb) as max_vram_mb,
                AVG(cpu_power_w) as avg_cpu_power,
                MAX(cpu_power_w) as max_cpu_power,
                SUM(CASE WHEN power_limit_throttling=1 THEN 1 ELSE 0 END) as throttle_samples,
                COUNT(*) as total_samples
            FROM telemetry
            WHERE campaign_id=? AND config_id=?
            """,
            (campaign_id, config_id),
        ).fetchone()

    if row is None:
        return {}

    return dict(row)


def get_background_interference_summary(
    campaign_id: str, config_id: str, db_path: Path
) -> dict[str, Any]:
    """
    Summarize background interference events for a config.
    Returns counts of snapshots with defender/update/antivirus activity.
    """
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total_snapshots,
                SUM(defender_process_running) as defender_process_count,
                SUM(windows_update_active) as update_active_count,
                SUM(antivirus_scan_active) as av_scan_count,
                SUM(search_indexer_active) as search_indexer_count,
                AVG(high_cpu_process_count) as avg_high_cpu_procs,
                MAX(high_cpu_process_count) as max_high_cpu_procs,
                AVG(network_active_connections) as avg_connections,
                MAX(network_active_connections) as max_connections
            FROM background_snapshots
            WHERE campaign_id=? AND config_id=?
            """,
            (campaign_id, config_id),
        ).fetchone()

    if row is None:
        return {}

    return dict(row)


def get_vram_per_config(
    campaign_id: str,
    db_path: Path,
) -> "dict[str, dict[str, float | None]]":
    """
    Return peak and average GPU VRAM usage per config, plus total GPU VRAM.

    Queries telemetry.gpu_vram_used_mb grouped by config_id.
    Also reads gpu_vram_total_mb from campaign_start_snapshot.

    Returns:
        {
            config_id: {
                "peak_mb":  float,        # max observed VRAM used during this config
                "avg_mb":   float,        # mean VRAM used
                "total_mb": float | None, # physical GPU VRAM capacity (same for all configs)
            },
            ...
        }

    IMPORTANT: OOM and skipped_oom configs produce zero telemetry rows.
    They are absent from the returned dict. Callers MUST use .get(config_id)
    and handle None -- never dict[config_id] directly.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT config_id,
                   MAX(gpu_vram_used_mb)  AS peak_mb,
                   AVG(gpu_vram_used_mb)  AS avg_mb
            FROM telemetry
            WHERE campaign_id = ?
              AND gpu_vram_used_mb IS NOT NULL
            GROUP BY config_id
            """,
            (campaign_id,),
        ).fetchall()

        snap_row = conn.execute(
            "SELECT gpu_vram_total_mb FROM campaign_start_snapshot WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()

    total_mb = snap_row[0] if snap_row else None

    return {
        row[0]: {
            "peak_mb":  float(row[1]) if row[1] is not None else None,
            "avg_mb":   float(row[2]) if row[2] is not None else None,
            "total_mb": total_mb,
        }
        for row in rows
    }
