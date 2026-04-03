"""
QuantMap — report.py

Generates the campaign report in Markdown + CSV formats.

Report contents (MDD §14.1 + extended):
  1. Campaign metadata (ID, date, machine fingerprint, BIOS, build, model)
  2. S0-new anchor statistics for reference
  3. THREE required result views:
       a. Score winner (highest composite score passing all filters)
       b. Pareto frontier (not dominated on both TG median AND TTFT median)
       c. Highest raw TG (highest warm_tg_median passing filters)
  4. Full config ranking table with elimination reasons
  5. Statistical tables (median, P10, P90, CV, TTFT, outliers, thermal events)
  6. speed_medium flags (configs with >5% relative TG drop)
  7. Telemetry summary per config (temperature, power, VRAM, background)
  8. Background interference log (AV scan activity, Defender process, Update, Search)
  9. Winner declaration with confidence statement
 10. Production command (copy-paste ready, respects QUANTMAP_SERVER_HOST)

The report is gitignored (*.md rule). It is regenerable from lab.sqlite.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.db import get_connection
from src.analyze import analyze_campaign, get_telemetry_summary, get_background_interference_summary
from src.score import score_campaign


def _fmt_tel(val: float | int | None, fmt: str) -> str:
    """
    Format a telemetry value; return 'N/A' when the value is None.

    Using `or 0` to fill missing telemetry silently misrepresents the data —
    a user seeing '0.0' thinks the GPU was idle, not that the metric was
    unavailable (e.g. HWiNFO not running, sensor absent, or legacy data).
    This helper makes the absence explicit. (R6 fix)
    """
    if val is None:
        return "N/A"
    return format(val, fmt)


def _fmt_ambient(value: str | None) -> str:
    """
    Format an ambient env-var value for display in the report's batch block.

    Preserves the three-way distinction that matters for GPU device selection:
      null (not set)  → "<not set — all GPUs visible>"
      ""  (empty str) → "<empty string — CPU-only mode, no GPUs visible>"
      any other value → the value itself (e.g. "0", "1", "BY_BUS_ID")
    """
    if value is None:
        return "<not set — all GPUs visible>"
    if value == "":
        return "<empty string — CPU-only mode, no GPUs visible>"
    return value


def _config_to_server_args_for_report(config: dict) -> list[str]:
    """
    Reconstruct llama-server args from a stored config_values_json dict.
    Mirrors runner._config_to_server_args but lives here to avoid circular import.
    """
    args: list[str] = []
    if "context_size" in config:
        args += ["-c", str(config["context_size"])]
    args += ["-ngl", str(config.get("n_gpu_layers", 999))]
    ot = config.get("override_tensor")
    if ot:
        args += ["-ot", str(ot)]
    fa = config.get("flash_attn")
    if fa is False:
        args += ["-fa", "0"]
    elif fa is True:
        args += ["-fa", "1"]
    if config.get("jinja", True):
        args.append("--jinja")
    args += ["--threads", str(config.get("threads", 16))]
    args += ["--threads-batch", str(config.get("threads_batch", 16))]
    args += ["--threads-http", str(config.get("threads_http", 1))]  # always explicit (HIGH-5)
    args += ["-ub", str(config.get("ubatch_size", 512))]
    args += ["-b", str(config.get("batch_size", 2048))]
    n_parallel = config.get("n_parallel", 1)
    if n_parallel != 1:
        args += ["--parallel", str(n_parallel)]
    kv_k = config.get("kv_cache_type_k", "f16")
    kv_v = config.get("kv_cache_type_v", "f16")
    if kv_k != "f16":
        args += ["--cache-type-k", kv_k]
    if kv_v != "f16":
        args += ["--cache-type-v", kv_v]
    if not config.get("mmap", True):
        args.append("--no-mmap")
    if config.get("mlock", False):
        args.append("--mlock")
    if not config.get("cont_batching", True):
        args.append("--no-cont-batching")
    defrag = config.get("defrag_thold", 0.1)
    if defrag != 0.1:
        args += ["--defrag-thold", str(defrag) if defrag >= 0 else "-1"]
    return args

logger = logging.getLogger(__name__)

LAB_ROOT = Path(os.getenv("QUANTMAP_LAB_ROOT", r"D:/Workspaces/QuantMap"))


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _kv_bytes_per_token(
    baseline: dict,
    n_gpu_layers: int,
) -> float | None:
    """
    Estimate KV cache bytes consumed per token for a given n_gpu_layers.

    Formula:
        bytes_per_token = n_kv_layers_on_gpu * 2 * n_kv_heads * head_dim * bytes_per_element

    Returns None if required model architecture fields are absent from baseline.yaml.
    """
    model = baseline.get("model", {})
    config = baseline.get("config", {})

    n_layers = model.get("n_layers")
    n_kv_heads = model.get("n_kv_heads")
    d_model = model.get("d_model")

    if any(v is None for v in (n_layers, n_kv_heads, d_model)):
        return None

    # Derive head_dim. MiniMax M2.5: 64 query heads, 8 KV heads, d_model=7168
    # head_dim = d_model / n_heads; n_heads not stored — approximate as d_model / 112.
    n_heads_approx = d_model // 112 if d_model >= 112 else 64
    head_dim = d_model // n_heads_approx

    kv_type = config.get("kv_cache_type_k", "f16")
    bytes_map = {"f16": 2, "f32": 4, "q8_0": 1, "q4_0": 0.5, "q4_1": 0.5}
    bytes_per_element = bytes_map.get(kv_type, 2)

    n_kv_layers_on_gpu = min(n_gpu_layers, int(n_layers))

    # 2 = K + V tensors
    return n_kv_layers_on_gpu * 2 * int(n_kv_heads) * head_dim * bytes_per_element


def _ngl_sweep_section(
    campaign_id: str,
    campaign: dict,
    baseline: dict,
    scores_result: dict,
    stats: dict,
    db_path: Path,
) -> list[str]:
    """
    Build the 'GPU Layer Sweep — Throughput vs. VRAM' section for NGL campaigns.

    Returns a list of Markdown lines to be joined with newlines.
    Called from _build_markdown() when campaign.variable == 'n_gpu_layers'.
    """
    from src.analyze import get_vram_per_config  # noqa: PLC0415

    sections: list[str] = []
    sections.append("## GPU Layer Sweep — Throughput vs. VRAM\n")

    # Load all config rows (including oom / skipped_oom) ordered by NGL ascending
    with get_connection(db_path) as conn:
        config_rows = conn.execute(
            """SELECT id, variable_value, status, failure_detail
               FROM configs
               WHERE campaign_id = ?
               ORDER BY CAST(json_extract(variable_value, '$') AS INTEGER) ASC""",
            (campaign_id,),
        ).fetchall()

    if not config_rows:
        sections.append("_No configs recorded for this campaign._\n")
        return sections

    # VRAM data
    vram_data = get_vram_per_config(campaign_id, db_path)
    total_mb: float | None = None
    for v in vram_data.values():
        if v.get("total_mb") is not None:
            total_mb = v["total_mb"]
            break

    model_params_available = all(
        baseline.get("model", {}).get(k) is not None
        for k in ("n_layers", "n_kv_heads", "d_model")
    )

    # Score winner lookup
    scores_df = (scores_result or {}).get("scores_df")
    score_winner_id: str | None = None
    if scores_df is not None and not scores_df.empty and "is_score_winner" in scores_df.columns:
        winners = scores_df[scores_df["is_score_winner"] == 1]
        if not winners.empty:
            score_winner_id = winners.index[0]

    # Diminishing-returns computation
    viable_points: list[tuple[int, float]] = []
    for cfg_id_row, val_json, status, _ in config_rows:
        if status != "complete":
            continue
        try:
            ngl_val = int(json.loads(val_json))
        except (TypeError, ValueError):
            continue
        tg = stats.get(cfg_id_row, {}).get("warm_tg_median")
        if tg is not None:
            viable_points.append((ngl_val, float(tg)))

    diminishing_ngl: int | None = None
    if len(viable_points) >= 3:
        marginal_gains = [
            (
                viable_points[i][0],
                (viable_points[i][1] - viable_points[i - 1][1])
                / max(1, viable_points[i][0] - viable_points[i - 1][0]),
            )
            for i in range(1, len(viable_points))
        ]
        peak_marginal = max(g for _, g in marginal_gains)
        threshold = 0.15 * peak_marginal
        for ngl_val, gain in marginal_gains:
            if gain < threshold:
                diminishing_ngl = ngl_val
                break

    # Table
    header = "| NGL | TG (t/s) | TG P10 | VRAM Used | VRAM Free | Est. Max Context | Score | Notes |"
    sep    = "|-----|----------|--------|-----------|-----------|------------------|-------|-------|"
    sections.append(header)
    sections.append(sep)

    for cfg_id_row, val_json, status, failure_detail in config_rows:
        try:
            ngl_val = int(json.loads(val_json))
        except (TypeError, ValueError):
            ngl_val = "?"
        cfg_vram = vram_data.get(cfg_id_row)
        cfg_stats = stats.get(cfg_id_row, {})
        cfg_score_row = {}
        if scores_df is not None and not scores_df.empty and cfg_id_row in scores_df.index:
            cfg_score_row = scores_df.loc[cfg_id_row].to_dict()

        # VRAM columns
        free_mb: float | None = None
        if cfg_vram:
            peak_mb = cfg_vram.get("peak_mb")
            peak_str = f"{peak_mb:,.0f} MB" if peak_mb is not None else "N/A"
            if total_mb is not None and peak_mb is not None:
                free_mb = total_mb - peak_mb
                free_str = f"{free_mb:,.0f} MB"
            else:
                free_str = "N/A"
        else:
            peak_str = "—"
            free_str = "—"

        # Est. Max Context
        est_ctx_str = "—"
        if status == "complete" and free_mb is not None and model_params_available:
            bpt = _kv_bytes_per_token(baseline, int(ngl_val))
            if bpt and bpt > 0:
                est_tokens = int((free_mb * 1024 * 1024) / bpt)
                if est_tokens >= 1000:
                    est_ctx_str = f"{est_tokens // 1000}K"
                else:
                    est_ctx_str = str(est_tokens)
        elif status == "complete" and not model_params_available:
            est_ctx_str = "N/A"

        # TG and score
        tg_str = f"{cfg_stats.get('warm_tg_median', 0):.2f}" if status == "complete" else "—"
        p10_str = f"{cfg_stats.get('warm_tg_p10', 0):.2f}" if status == "complete" else "—"
        score_val = cfg_score_row.get("composite_score")
        score_str = f"{score_val:.3f}" if (status == "complete" and score_val is not None) else "—"

        # Notes
        notes_parts: list[str] = []
        if cfg_id_row == score_winner_id:
            notes_parts.append("★ score winner")
        if diminishing_ngl is not None and ngl_val == diminishing_ngl:
            notes_parts.append("← diminishing returns beyond this point")
        if status == "oom":
            first_line = (failure_detail or "CUDA OOM").splitlines()[0][:100]
            notes_parts.append(f"OOM: {first_line}")
        elif status == "skipped_oom":
            notes_parts.append("skipped (boundary confirmed)")

        notes = " | ".join(notes_parts) if notes_parts else "—"
        sections.append(
            f"| {ngl_val} | {tg_str} | {p10_str} | {peak_str} | {free_str} | {est_ctx_str} | {score_str} | {notes} |"
        )

    sections.append("")

    # Architecture params warning
    if not model_params_available:
        sections.append(
            "> **Note:** Context estimation unavailable — add `n_layers`, `n_kv_heads`, "
            "`d_model` to the `model:` section of `baseline.yaml`.\n"
        )

    # OOM boundary note
    oom_configs = [r for r in config_rows if r[2] == "oom"]
    if not oom_configs:
        sections.append("_No OOM boundary reached — all layer counts are viable on this GPU._\n")

    # Below-table recommendation
    min_ctx = campaign.get("min_context_length")

    if min_ctx is not None:
        sections.append(f"### Context Recommendation (min {min_ctx:,} tokens)\n")
        if not model_params_available:
            sections.append(
                "> Context-based recommendation unavailable — add `n_layers`, `n_kv_heads`, "
                "`d_model` to `baseline.yaml model:` section.\n"
            )
        else:
            candidates = []
            for cfg_id_row, val_json, status, _ in config_rows:
                if status != "complete":
                    continue
                try:
                    ngl_val = int(json.loads(val_json))
                except (TypeError, ValueError):
                    continue
                cfg_vram = vram_data.get(cfg_id_row)
                if not cfg_vram:
                    continue
                peak_mb = cfg_vram.get("peak_mb")
                if total_mb is None or peak_mb is None:
                    continue
                free_mb = total_mb - peak_mb
                bpt = _kv_bytes_per_token(baseline, ngl_val)
                if not bpt or bpt <= 0:
                    continue
                est_tokens = int((free_mb * 1024 * 1024) / bpt)
                if est_tokens >= min_ctx:
                    tg = float(stats.get(cfg_id_row, {}).get("warm_tg_median") or 0.0)
                    free_gb = free_mb / 1024
                    candidates.append((tg, ngl_val, est_tokens, free_gb, cfg_id_row))

            if candidates:
                candidates.sort(reverse=True)
                best_tg, best_ngl, best_ctx, best_free, _ = candidates[0]
                ctx_label = f"{best_ctx // 1000}K" if best_ctx >= 1000 else str(best_ctx)
                min_label = f"{min_ctx // 1000}K" if min_ctx >= 1000 else str(min_ctx)
                sections.append(
                    f"> **For your stated minimum of {min_label} context:** NGL={best_ngl} "
                    f"(TG median {best_tg:.2f} t/s, est. max context {ctx_label}, "
                    f"{best_free:.1f} GB VRAM free). "
                    f"This is the fastest config that meets your context requirement.\n"
                )
            else:
                min_label = f"{min_ctx // 1000}K" if min_ctx >= 1000 else str(min_ctx)
                sections.append(
                    f"> No config in this sweep can sustain {min_label} context — "
                    f"consider a smaller quantization or fewer layers on GPU.\n"
                )
    else:
        sections.append(
            "> No context requirement specified. Set `min_context_length` in your "
            "campaign YAML to get a targeted recommendation, or choose from the "
            "table above based on your workload.\n"
        )

    return sections


def generate_report(
    campaign_id: str,
    db_path: Path,
    baseline: dict[str, Any],
    scores_result: dict[str, Any] | None = None,
    stats: dict[str, dict[str, Any]] | None = None,
    campaign: dict | None = None,
) -> Path:
    """
    Generate Markdown + CSV reports for a completed campaign.

    If scores_result and stats are provided (from score_campaign()), they are
    used directly. Otherwise, analysis is re-run from the database.

    Returns the path to the generated Markdown report.
    """
    if stats is None:
        stats = analyze_campaign(campaign_id, db_path)
    if scores_result is None:
        scores_result = score_campaign(campaign_id, db_path, baseline)

    report_dir = LAB_ROOT / "results" / campaign_id
    report_dir.mkdir(parents=True, exist_ok=True)

    md_path = report_dir / "report.md"
    csv_path = report_dir / "scores.csv"

    # Write scores CSV
    scores_df = scores_result.get("scores_df")
    if scores_df is not None and not scores_df.empty:
        # Full stats table
        rows = []
        for config_id, s in stats.items():
            row = {"config_id": config_id}
            row.update(s)
            if config_id in scores_df.index:
                sr = scores_df.loc[config_id]
                row["composite_score"] = sr.get("composite_score")
                row["rank_overall"] = sr.get("rank_overall")
                row["is_score_winner"] = sr.get("is_score_winner", False)
                row["is_highest_tg"] = sr.get("is_highest_tg", False)
                row["pareto_dominated"] = sr.get("pareto_dominated", False)
                row["warm_tg_vs_baseline_pct"] = sr.get("warm_tg_vs_baseline_pct")
                row["warm_ttft_vs_baseline_pct"] = sr.get("warm_ttft_vs_baseline_pct")
            row["elimination_reason"] = scores_result["eliminated"].get(config_id, "")
            rows.append(row)
        pd.DataFrame(rows).to_csv(csv_path, index=False)
        logger.info("Scores CSV written: %s", csv_path)

    # Generate Markdown
    md = _build_markdown(campaign_id, db_path, baseline, scores_result, stats, campaign=campaign)
    md_path.write_text(md, encoding="utf-8")
    logger.info("Report written: %s", md_path)

    return md_path


def _build_markdown(
    campaign_id: str,
    db_path: Path,
    baseline: dict[str, Any],
    scores_result: dict[str, Any],
    stats: dict[str, dict[str, Any]],
    campaign: dict | None = None,
) -> str:
    """Build the full Markdown report as a string."""
    sections: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Load campaign metadata from DB
    with get_connection(db_path) as conn:
        campaign_row = conn.execute(
            "SELECT * FROM campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        snap_row = conn.execute(
            "SELECT * FROM campaign_start_snapshot WHERE campaign_id=?", (campaign_id,)
        ).fetchone()

    snap = dict(snap_row) if snap_row else {}
    camp = dict(campaign_row) if campaign_row else {}

    # -------------------------------------------------------------------------
    # Title and metadata
    # -------------------------------------------------------------------------
    machine = baseline.get("machine", {})
    runtime = baseline.get("runtime", {})
    bios = baseline.get("bios", {})

    sections.append(f"# QuantMap Campaign Report — {campaign_id}")
    sections.append(f"\nGenerated: {now}\n")

    sections.append("## Campaign Metadata\n")
    sections.append("| Field | Value |")
    sections.append("|-------|-------|")
    sections.append(f"| Campaign ID | `{campaign_id}` |")
    sections.append(f"| Variable | `{camp.get('variable', 'unknown')}` |")
    sections.append(f"| Type | {camp.get('campaign_type', 'unknown')} |")
    sections.append(f"| Status | {camp.get('status', 'unknown')} |")
    sections.append(f"| Started | {camp.get('started_at', 'unknown')} |")
    sections.append(f"| Completed | {camp.get('completed_at', 'unknown')} |")
    sections.append(f"| Machine | {machine.get('name', 'unknown')} |")
    sections.append(f"| CPU | {machine.get('cpu', 'unknown')} |")
    sections.append(f"| GPU | {machine.get('gpu', 'unknown')} |")
    sections.append(f"| RAM | {machine.get('ram', 'unknown')} |")
    sections.append(f"| OS | {snap.get('os_platform', machine.get('os', 'unknown'))} |")
    sections.append(f"| NVIDIA Driver | {snap.get('nvidia_driver', 'unknown')} |")
    sections.append(f"| Build Commit | `{snap.get('build_commit', runtime.get('build_commit', 'unknown'))}` |")
    sections.append(f"| Power Plan | {snap.get('power_plan', 'unknown')} |")
    sections.append(f"| Baseline SHA256 | `{camp.get('baseline_sha256', 'unknown')[:16]}...` |")
    sections.append(f"| Campaign SHA256 | `{camp.get('campaign_sha256', 'unknown')[:16]}...` |")
    sections.append("")

    sections.append("### BIOS Profile at Campaign Start\n")
    sections.append("| Setting | Value |")
    sections.append("|---------|-------|")
    sections.append(f"| PL1 / PL2 | {bios.get('pl1_w', '?')}W / {bios.get('pl2_w', '?')}W |")
    sections.append(f"| Vcore Mode | {bios.get('vcore_mode', '?')} |")
    sections.append(f"| Vcore Offset | {bios.get('vcore_offset_v', '?')}V |")
    sections.append(f"| Gear Mode | {bios.get('gear_mode', '?')} |")
    sections.append(f"| XMP Profile | {bios.get('xmp_profile', '?')} |")
    sections.append(f"| AVX Offset | {bios.get('avx_offset', '?')} |")
    sections.append(f"| CPU Temp at start | {snap.get('cpu_temp_at_start_c', 'unknown')} |")
    sections.append(f"| GPU Temp at start | {snap.get('gpu_temp_at_start_c', 'unknown')} |")
    sections.append("")

    # -------------------------------------------------------------------------
    # S0-new anchor reference
    # -------------------------------------------------------------------------
    ref = baseline.get("reference", {})
    sections.append("## S0-new Baseline Reference (Anchor)\n")
    sections.append("| Metric | Value |")
    sections.append("|--------|-------|")
    sections.append(f"| Warm TG Median | {ref.get('warm_tg_median_ts', '~8.18')} t/s |")
    sections.append(f"| Warm TTFT Median | {ref.get('warm_ttft_median_ms', '~200')} ms |")
    sections.append(f"| Cold TTFT | {ref.get('cold_ttft_ms', '~6100')} ms |")
    sections.append("")

    # -------------------------------------------------------------------------
    # Three required result views
    # -------------------------------------------------------------------------
    winner = scores_result.get("winner")
    highest_tg = scores_result.get("highest_tg")
    pareto_frontier = scores_result.get("pareto_frontier", [])
    passing = scores_result.get("passing", {})
    scores_df = scores_result.get("scores_df")
    speed_medium_flags = scores_result.get("speed_medium_flags", {})

    sections.append("## Results — Three Required Views\n")

    all_same = (winner == highest_tg and winner in pareto_frontier)
    if all_same and winner:
        sections.append(
            f"> **Strong evidence:** All three views agree on the same winner: `{winner}`. "
            "Score winner, Pareto frontier, and highest raw TG are identical."
        )
    elif winner:
        sections.append(
            "> **Views diverge.** See tradeoff explanation in the Winner Declaration section."
        )
    else:
        sections.append("> **WARNING: No configs passed all elimination filters.**")
    sections.append("")

    # View 1: Score winner
    sections.append("### View 1 — Score Winner (Composite Score)\n")
    if winner and winner in passing:
        w_stats = passing[winner]
        sections.append(f"**Winner: `{winner}`**\n")
        sections.append(_config_stats_table(winner, w_stats, scores_df, ref))
        sm_flag = speed_medium_flags.get(winner, False)
        if sm_flag:
            deg = w_stats.get("speed_medium_degradation_pct", 0) or 0
            sections.append(
                f"\n> ⚠️ **speed_medium flag:** This config shows {deg:.1f}% TG degradation "
                "on the 512-token request vs 256-token baseline. Review before using in production."
            )
    else:
        sections.append("*No winner — all configs eliminated.*")
    sections.append("")

    # View 2: Pareto frontier
    sections.append("### View 2 — Pareto Frontier\n")
    sections.append(
        "*Configs not dominated on both warm TG median AND warm TTFT median simultaneously. "
        "Shows full tradeoff space.*\n"
    )
    if pareto_frontier:
        # R3: outlier_count and thermal_events added — Pareto ranking is about
        # the best configs that are ALSO stable. A config that's fast but has 3
        # outliers or a thermal event is a different beast from one with 0.
        sections.append(
            "| Config | Warm TG Median | Warm TTFT Median | vs Baseline TG | Outliers | Thermal | Notes |"
        )
        sections.append("|--------|---------------|-----------------|----------------|----------|---------|-------|")
        for cid in pareto_frontier:
            s = passing.get(cid, {})
            tg = s.get("warm_tg_median") or 0
            ttft = s.get("warm_ttft_median_ms") or 0
            outliers = s.get("outlier_count", 0)
            thermal = s.get("thermal_events", 0)
            tg_pct = s.get("warm_tg_vs_baseline_pct") or (
                (tg - ref.get("warm_tg_median_ts", 8.18)) / ref.get("warm_tg_median_ts", 8.18) * 100
                if tg else None
            )
            if scores_df is not None and cid in scores_df.index:
                tg_pct = scores_df.loc[cid].get("warm_tg_vs_baseline_pct", tg_pct)
            tg_pct_str = f"+{tg_pct:.1f}%" if tg_pct and tg_pct >= 0 else f"{tg_pct:.1f}%"
            notes = ""
            if cid == winner:
                notes = "← score winner"
            elif cid == highest_tg:
                notes = "← highest TG"
            sections.append(
                f"| `{cid}` | {tg:.2f} t/s | {ttft:.0f} ms | {tg_pct_str} | "
                f"{outliers} | {thermal} | {notes} |"
            )
    else:
        sections.append("*No passing configs for Pareto analysis.*")
    sections.append("")

    # View 3: Highest raw TG
    sections.append("### View 3 — Highest Raw TG\n")
    if highest_tg and highest_tg in passing:
        h_stats = passing[highest_tg]
        sections.append(f"**Highest TG Config: `{highest_tg}`**\n")
        if highest_tg == winner:
            sections.append("*Same as score winner.*")
        else:
            sections.append(
                "_Differs from score winner. Useful if generation speed is the only priority "
                "and TTFT is not a concern._"
            )
            sections.append(_config_stats_table(highest_tg, h_stats, scores_df, ref))
    else:
        sections.append("*Same as score winner or no passing configs.*")
    sections.append("")

    # -------------------------------------------------------------------------
    # Full ranking table
    # -------------------------------------------------------------------------
    sections.append("## Full Config Ranking\n")
    sections.append(
        "| Rank | Config | TG Median | TG P10 | TG CV | TTFT Median | TTFT P90 | "
        "Score | Thermal | Outliers | Status |"
    )
    sections.append(
        "|------|--------|-----------|--------|-------|-------------|----------|"
        "-------|---------|----------|--------|"
    )

    # Sort: passing by rank, then eliminated alphabetically
    sorted_passing = []
    if scores_df is not None and not scores_df.empty:
        sorted_passing = [(i + 1, cid) for i, cid in enumerate(scores_df.index)]

    for rank, config_id in sorted_passing:
        s = passing.get(config_id, stats.get(config_id, {}))
        score_val = scores_df.loc[config_id, "composite_score"] if scores_df is not None else None
        sections.append(
            f"| {rank} | `{config_id}` | "
            f"{s.get('warm_tg_median') or 0:.2f} | "
            f"{s.get('warm_tg_p10') or 0:.2f} | "
            f"{s.get('warm_tg_cv') or 0:.3f} | "
            f"{s.get('warm_ttft_median_ms') or 0:.0f}ms | "
            f"{s.get('warm_ttft_p90_ms') or 0:.0f}ms | "
            f"{score_val:.4f} | "
            f"{s.get('thermal_events', 0)} | "
            f"{s.get('outlier_count', 0)} | "
            f"{'✓ PASS' if config_id in passing else 'FAIL'} |"
        )

    for config_id, reason in sorted(scores_result.get("eliminated", {}).items()):
        s = stats.get(config_id, {})
        sections.append(
            f"| — | `{config_id}` | "
            f"{s.get('warm_tg_median') or 0:.2f} | "
            f"{s.get('warm_tg_p10') or 0:.2f} | "
            f"{s.get('warm_tg_cv') or 0:.3f} | "
            f"{s.get('warm_ttft_median_ms') or 0:.0f}ms | "
            f"{s.get('warm_ttft_p90_ms') or 0:.0f}ms | "
            f"— | "
            f"{s.get('thermal_events', 0)} | "
            f"{s.get('outlier_count', 0)} | "
            f"❌ {reason} |"
        )
    sections.append("")

    # -------------------------------------------------------------------------
    # speed_medium flags
    # -------------------------------------------------------------------------
    flagged = [(cid, stats[cid].get("speed_medium_degradation_pct", 0) or 0)
               for cid, flagged in speed_medium_flags.items() if flagged and cid in stats]
    if flagged:
        sections.append("## ⚠️ speed_medium Degradation Flags\n")
        sections.append(
            "Configs with >5% TG degradation on 512-token requests vs 256-token baseline. "
            "Review before advancing to finalist.\n"
        )
        # R4: include S0-new baseline TG so the operator can gauge severity
        # relative to the reference point, not just config-vs-config.
        s0_tg = ref.get("warm_tg_median_ts", "?")
        sections.append("| Config | Degradation | S0-new TG | speed_short TG | speed_medium TG |")
        sections.append("|--------|-------------|-----------|---------------|-----------------|")
        for cid, deg in sorted(flagged, key=lambda x: x[1], reverse=True):
            s = stats[cid]
            sections.append(
                f"| `{cid}` | {deg:.1f}% | "
                f"{s0_tg} t/s | "
                f"{s.get('warm_tg_median') or 0:.2f} t/s | "
                f"{s.get('speed_medium_warm_tg_median') or 0:.2f} t/s |"
            )
        sections.append("")

    # -------------------------------------------------------------------------
    # Telemetry summary per config
    # -------------------------------------------------------------------------
    sections.append("## Telemetry Summary\n")
    # R1: expanded to show GPU/CPU utilization alongside thermals and power.
    # R6: N/A instead of 0 for any missing metric — 0.0 GPU util would otherwise
    #     be indistinguishable from "GPU was idle" vs "sensor was unavailable".
    sections.append(
        "| Config | Avg CPU °C | Max CPU °C | Avg GPU °C | Max GPU °C | "
        "Avg VRAM MB | Avg GPU Util % | Avg CPU Util % | Avg CPU Power W | Throttle Samples | AV Scan Active | Update |"
    )
    sections.append(
        "|--------|-----------|-----------|-----------|-----------|"
        "----------|--------------|--------------|----------------|-----------------|----------|--------|"
    )

    with get_connection(db_path) as conn:
        all_config_ids = [row[0] for row in conn.execute(
            "SELECT id FROM configs WHERE campaign_id=?", (campaign_id,)
        ).fetchall()]

    for config_id in all_config_ids:
        tel = get_telemetry_summary(campaign_id, config_id, db_path)
        bg = get_background_interference_summary(campaign_id, config_id, db_path)

        # AV Scan/Update flags: treat None (no background snapshots at all) as
        # unknown rather than clean — only show ✓ when we have actual data.
        av_count = bg.get("av_scan_count")
        upd_count = bg.get("update_active_count")
        av_flag = "⚠️" if (av_count or 0) > 0 else ("?" if av_count is None else "✓")
        upd_flag = "⚠️" if (upd_count or 0) > 0 else ("?" if upd_count is None else "✓")

        sections.append(
            f"| `{config_id}` | "
            f"{_fmt_tel(tel.get('avg_cpu_temp'), '.1f')} | "
            f"{_fmt_tel(tel.get('max_cpu_temp'), '.1f')} | "
            f"{_fmt_tel(tel.get('avg_gpu_temp'), '.1f')} | "
            f"{_fmt_tel(tel.get('max_gpu_temp'), '.1f')} | "
            f"{_fmt_tel(tel.get('avg_vram_mb'), '.0f')} | "
            f"{_fmt_tel(tel.get('avg_gpu_util'), '.1f')} | "
            f"{_fmt_tel(tel.get('avg_cpu_util'), '.1f')} | "
            f"{_fmt_tel(tel.get('avg_cpu_power'), '.1f')} | "
            f"{tel.get('throttle_samples') or 0} | "
            f"{av_flag} | "
            f"{upd_flag} |"
        )
    sections.append("")

    # -------------------------------------------------------------------------
    # Background Interference Detail  (R2)
    # -------------------------------------------------------------------------
    # The telemetry table shows Defender/Update at-a-glance flags.  This section
    # adds the full picture: AV scan counts, Search Indexer activity, and
    # average/max high-CPU process counts — all fields returned by
    # get_background_interference_summary() but previously not displayed.
    sections.append("## Background Interference Detail\n")
    sections.append(
        "Snapshot counts where each interference source was active during the config run.\n"
    )
    sections.append(
        "| Config | Snapshots | AV Scan Active | Defender Proc | Update | Search Idx | "
        "Avg High-CPU Procs | Max High-CPU Procs |"
    )
    sections.append(
        "|--------|-----------|----------------|---------------|--------|------------|"
        "-------------------|-------------------|"
    )

    for config_id in all_config_ids:
        bg = get_background_interference_summary(campaign_id, config_id, db_path)
        total_snaps = bg.get("total_snapshots") or 0

        def _bg_flag(count: int | None) -> str:
            """⚠️ N  /  ✓  /  ?  depending on count and data availability."""
            if count is None:
                return "?"
            return f"⚠️ {count}" if count > 0 else "✓"

        sections.append(
            f"| `{config_id}` | {total_snaps} | "
            f"{_bg_flag(bg.get('av_scan_count'))} | "
            f"{_bg_flag(bg.get('defender_process_count'))} | "
            f"{_bg_flag(bg.get('update_active_count'))} | "
            f"{_bg_flag(bg.get('search_indexer_count'))} | "
            f"{_fmt_tel(bg.get('avg_high_cpu_procs'), '.1f')} | "
            f"{bg.get('max_high_cpu_procs') if bg.get('max_high_cpu_procs') is not None else 'N/A'} |"
        )
    sections.append("")

    # -------------------------------------------------------------------------
    # Winner Declaration and Confidence Statement
    # -------------------------------------------------------------------------
    sections.append("## Winner Declaration\n")

    if winner and winner in passing:
        w = passing[winner]
        tg = w.get("warm_tg_median") or 0
        tg_p10 = w.get("warm_tg_p10") or 0
        ttft = w.get("warm_ttft_median_ms") or 0
        cv = w.get("warm_tg_cv") or 0
        thermal = w.get("thermal_events", 0)
        outliers = w.get("outlier_count", 0)
        n_warm = w.get("valid_warm_request_count", 0)

        divergence_note = ""
        if highest_tg and highest_tg != winner:
            h = passing[highest_tg]
            divergence_note = (
                f"\n\n**Note:** Score winner (`{winner}`) and highest-TG config (`{highest_tg}`) "
                f"differ. Winner has better TTFT ({ttft:.0f}ms median vs "
                f"{passing[highest_tg].get('warm_ttft_median_ms') or 0:.0f}ms) at the cost of "
                f"slightly lower TG ({tg:.2f} vs {h.get('warm_tg_median') or 0:.2f} t/s). "
                "For pure generation speed, use the highest-TG config."
            )

        snap_bios = (
            f"BIOS: {bios.get('pl1_w','?')}W/−{abs(bios.get('vcore_offset_v',0))*1000:.0f}mV/"
            f"Gear{bios.get('gear_mode','?')}/XMP{bios.get('xmp_profile','?')}"
        )
        machine_str = (
            f"{machine.get('cpu','unknown')} + {machine.get('gpu','unknown').split()[0:4]} "
            f"+ {machine.get('ram','unknown')}"
        )

        # R5: pull model identity and build commit from baseline/snapshot rather
        # than hard-coding.  Fallback to "unknown" (not a specific commit hash)
        # so any misconfigured environment produces an obviously-wrong output
        # rather than silently stamping the wrong build identifier.
        model_cfg = baseline.get("model", {})
        model_label = model_cfg.get("name", "unknown model")
        build_commit = snap.get("build_commit") or runtime.get("build_commit") or "unknown"

        sections.append(
            f'> **Confidence Statement:**\n>\n'
            f'> "On {machine.get("name","DEEP THOUGHT")} '
            f'({machine.get("cpu","unknown")} + {machine.get("gpu","unknown")}, '
            f'{snap_bios}, OS: {machine.get("os","Windows 11 Pro")}) '
            f'running {model_label} via llama.cpp build {build_commit}, '
            f'the validated optimal single-user configuration is `{winner}`, '
            f'delivering **{tg:.2f} t/s** warm TG median (**{tg_p10:.2f} t/s** P10) '
            f'and **{ttft:.0f}ms** warm TTFT median, validated across '
            f'**{n_warm}** warm requests with **{thermal}** thermal events and '
            f'**{outliers}** outliers on {datetime.now(timezone.utc).strftime("%Y-%m-%d")}."'
        )
        sections.append(divergence_note)
        sections.append("")

        # -----------------------------------------------------------------------
        # Production command
        # -----------------------------------------------------------------------
        sections.append("## Production Command\n")
        from src.config import DEFAULT_HOST, PRODUCTION_PORT  # noqa: PLC0415
        sections.append(f"Copy-paste ready. Host {DEFAULT_HOST}, port {PRODUCTION_PORT}.\n")

        with get_connection(db_path) as conn:
            cmd_row = conn.execute(
                "SELECT resolved_command, runtime_env_json FROM configs WHERE id=? AND campaign_id=?",
                (winner, campaign_id),
            ).fetchone()

        server_bin = os.getenv("QUANTMAP_SERVER_BIN")
        if server_bin is None:
            server_bin = "<QUANTMAP_SERVER_BIN not set — copy .env.example to .env>"
        model_path = os.getenv("QUANTMAP_MODEL_PATH")
        if model_path is None:
            model_path = "<QUANTMAP_MODEL_PATH not set — copy .env.example to .env>"
        build_commit = snap.get("build_commit", runtime.get("build_commit", "afa6bfe4f"))

        sections.append("```batch")
        sections.append(f"rem QuantMap — Validated Production Config")
        sections.append(f"rem Campaign: {campaign_id} | Winner: {winner}")
        sections.append(f"rem Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} | Validated: {n_warm} warm requests")
        sections.append(f"rem Warm TG P10: {tg_p10:.2f} t/s | CV: {cv:.3f} | Thermal events: {thermal}")
        sections.append(f"rem Machine: {machine.get('name','DEEP THOUGHT')} ({machine.get('cpu','i9-12900K')} + {machine.get('gpu','RTX 3090')} + {machine.get('ram','128GB DDR4-3200')})")
        sections.append("")

        # Rebuild the winning command with --port 8000
        with get_connection(db_path) as conn:
            cfg_row = conn.execute(
                "SELECT config_values_json FROM configs WHERE id=? AND campaign_id=?",
                (winner, campaign_id),
            ).fetchone()

        if cfg_row:
            import json as _json
            try:
                cfg_vals = _json.loads(cfg_row[0])
                winner_args = _config_to_server_args_for_report(cfg_vals)
                sections.append(f"{server_bin} ^")
                sections.append(f'  -m "{model_path}" ^')
                sections.append(f'  --host {DEFAULT_HOST} --port {PRODUCTION_PORT} ^')
                for i, arg in enumerate(winner_args):
                    separator = " ^" if i < len(winner_args) - 1 else ""
                    sections.append(f"  {arg}{separator}")
            except Exception as exc:
                sections.append(f"rem [Error reconstructing command from config values: {exc}]")
                # Fall back to configs.resolved_command, which is stored as the
                # canonical production command (port 8000, full args) by runner.py.
                if cmd_row and cmd_row[0]:
                    sections.append(cmd_row[0])

        # Append runtime environment required for reproduction.
        # Two sections: MKL DLL injection (required) and GPU device selection
        # (informational — records what was set when the campaign ran).
        import json as _json_env
        runtime_env: dict = {}
        if cmd_row and len(cmd_row) > 1 and cmd_row[1]:
            try:
                runtime_env = _json_env.loads(cmd_row[1])
            except Exception:
                pass

        # -- Injected: Build B / Intel oneAPI MKL DLL resolution --------------
        sections.append("")
        sections.append("rem ── Required environment (Build B / Intel oneAPI MKL) ──")
        injected: dict = runtime_env.get("injected", {})
        # Fallback: old schema stored flat keys at the top level
        if not injected and runtime_env.get("CUDA_PATH"):
            injected = runtime_env
        if injected:
            cuda_path_inj = injected.get("CUDA_PATH", "")
            cmake_prefix = injected.get("CMAKE_PREFIX_PATH", "")
            path_prepend = injected.get("PATH_prepend", [])
            if cuda_path_inj:
                sections.append(f"set CUDA_PATH={cuda_path_inj}")
            if cmake_prefix:
                sections.append(f"set CMAKE_PREFIX_PATH={cmake_prefix}")
            if path_prepend:
                sections.append(f"set PATH={';'.join(path_prepend)};%PATH%")
        else:
            sections.append("rem [runtime_env_json unavailable — set CUDA_PATH, CMAKE_PREFIX_PATH,")
            sections.append("rem  and prepend CUDA/MKL/compiler bin dirs to PATH manually]")

        # -- Ambient: GPU device selection at time of campaign ----------------
        # CUDA_VISIBLE_DEVICES and CUDA_DEVICE_ORDER are recorded so users
        # comparing results across machines can spot invisible GPU mismatches.
        # null = confirmed not set (all GPUs visible, CUDA default ordering).
        ambient: dict = runtime_env.get("ambient", {})
        if ambient:
            sections.append("")
            sections.append("rem ── GPU device selection (recorded at campaign time) ──")
            cvd = ambient.get("CUDA_VISIBLE_DEVICES")
            cdo = ambient.get("CUDA_DEVICE_ORDER")
            sections.append(
                f"rem CUDA_VISIBLE_DEVICES = {_fmt_ambient(cvd)}"
            )
            sections.append(
                f"rem CUDA_DEVICE_ORDER    = {_fmt_ambient(cdo)}"
            )
            # Emit actionable set commands only when a non-default value was
            # present — omitting them when null prevents users from blindly
            # copy-pasting a stale device restriction onto a different machine.
            if cvd is not None:
                sections.append(f"set CUDA_VISIBLE_DEVICES={cvd}")
            if cdo is not None:
                sections.append(f"set CUDA_DEVICE_ORDER={cdo}")

        sections.append("```")
    else:
        sections.append(
            "**No winner declared.** All configs failed elimination filters. "
            "Review the elimination reasons in the Full Config Ranking table.\n"
        )
        sections.append("Possible causes:")
        sections.append("- High CV (>5%): thermal interference, background processes")
        sections.append("- Thermal events: check BIOS settings and cooling")
        sections.append("- Low TG P10 (<7.0 t/s): hardware limitation for these params")
        sections.append("")

    # -------------------------------------------------------------------------
    # Methodology note
    # -------------------------------------------------------------------------
    sections.append("## Methodology\n")
    lab = baseline.get("lab", {})
    # Resolve effective values: campaign YAML overrides baseline defaults
    eff_cycles = lab.get("cycles_per_config", 3)
    eff_reqs = lab.get("requests_per_cycle", 6)
    if campaign:
        if "cycles_per_config" in campaign:
            eff_cycles = campaign["cycles_per_config"]
        if "requests_per_cycle" in campaign:
            eff_reqs = campaign["requests_per_cycle"]
    warm_per_cycle = eff_reqs - 1
    warm_samples = eff_cycles * warm_per_cycle
    last_cycle = eff_cycles

    sections.append(
        f"- **Cycles per config:** {eff_cycles} "
        f"(fresh server restart per cycle)\n"
        f"- **Requests per cycle:** {eff_reqs} "
        f"(1 cold + {warm_per_cycle} warm)\n"
        f"- **Cycle {last_cycle} mix:** {warm_per_cycle - 1} warm speed_short + 1 warm speed_medium\n"
        f"- **Warm samples per config:** {warm_samples}\n"
        f"- **Inter-request delay:** {lab.get('inter_request_delay_s', 20)}s\n"
        f"- **Config cooldown:** {lab.get('cooldown_between_configs_s', 300)}s "
        f"(+ temperature gate <{lab.get('cooldown_temp_target_c', 55)}°C)\n"
        f"- **TTFT definition:** wall-clock ms from first byte sent to first content token\n"
        f"- **Outlier definition:** TG values below Q1 − 1.5×IQR\n"
        f"- **Scoring:** min-max normalized composite across passing configs\n"
        f"- **Seed:** 42 (stabilizes sampling, does not guarantee output identity)\n"
    )
    if warm_samples < 20:
        sections.append(
            f"> **Note:** {warm_samples} warm samples per config — "
            f"detectable difference ~0.4 t/s at 95% confidence. "
            f"For narrower confidence intervals, re-run with `--cycles {max(eff_cycles + 1, 4)}`.\n"
        )

    # NGL sweep section — only for n_gpu_layers campaigns
    if campaign is not None and campaign.get("variable") == "n_gpu_layers":
        ngl_lines = _ngl_sweep_section(
            campaign_id=campaign_id,
            campaign=campaign,
            baseline=baseline,
            scores_result=scores_result,
            stats=stats,
            db_path=db_path,
        )
        sections.extend(ngl_lines)

    return "\n".join(sections)


def _config_stats_table(
    config_id: str,
    s: dict[str, Any],
    scores_df: pd.DataFrame | None,
    ref: dict[str, Any],
) -> str:
    """Generate a compact stats table for one config."""
    lines = []
    lines.append("| Metric | Value | vs S0-new Baseline |")
    lines.append("|--------|-------|--------------------|")

    tg = s.get("warm_tg_median") or 0
    tg_p10 = s.get("warm_tg_p10") or 0
    tg_p90 = s.get("warm_tg_p90") or 0
    cv = s.get("warm_tg_cv") or 0
    ttft_med = s.get("warm_ttft_median_ms") or 0
    ttft_p90 = s.get("warm_ttft_p90_ms") or 0
    cold_ttft = s.get("cold_ttft_median_ms") or 0
    pp = s.get("pp_median") or 0
    thermal = s.get("thermal_events", 0)
    outliers = s.get("outlier_count", 0)

    ref_tg = ref.get("warm_tg_median_ts", 8.18)
    ref_ttft = ref.get("warm_ttft_median_ms", 200.0)

    tg_delta = f"+{(tg - ref_tg) / ref_tg * 100:.1f}%" if ref_tg else "—"
    ttft_delta = f"+{(ref_ttft - ttft_med) / ref_ttft * 100:.1f}%" if ref_ttft else "—"

    score_str = "—"
    if scores_df is not None and config_id in scores_df.index:
        score_str = f"{scores_df.loc[config_id, 'composite_score']:.4f}"

    lines.append(f"| Warm TG Median | **{tg:.2f} t/s** | {tg_delta} |")
    lines.append(f"| Warm TG P10 | {tg_p10:.2f} t/s | — |")
    lines.append(f"| Warm TG P90 | {tg_p90:.2f} t/s | — |")
    lines.append(f"| Warm TG CV | {cv:.4f} | — |")
    lines.append(f"| Warm TTFT Median | {ttft_med:.0f} ms | {ttft_delta} |")
    lines.append(f"| Warm TTFT P90 | {ttft_p90:.0f} ms | — |")
    lines.append(f"| Cold TTFT Median | {cold_ttft:.0f} ms | — |")
    lines.append(f"| PP Median | {pp:.1f} t/s | — |")
    lines.append(f"| Thermal Events | {thermal} | — |")
    lines.append(f"| Outliers | {outliers} | — |")
    lines.append(f"| Composite Score | {score_str} | — |")

    return "\n".join(lines)
