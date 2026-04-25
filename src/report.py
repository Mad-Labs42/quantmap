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
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.db import get_connection
from src.analyze import get_telemetry_summary, get_background_interference_summary
from src.run_plan import RunPlan
from src.settings_env import optional_env_path, read_env_path
from src.artifact_paths import (
    ARTIFACT_CAMPAIGN_SUMMARY,
    ARTIFACT_METADATA,
    ARTIFACT_RAW_TELEMETRY,
    ARTIFACT_RUN_REPORTS,
    FILENAME_CAMPAIGN_SUMMARY,
    FILENAME_METADATA,
    FILENAME_RAW_TELEMETRY,
    FILENAME_RUN_REPORTS,
    find_artifact_dir,
    infer_model_identity,
    report_paths,
)

_STR_NOT_SET_IN_BASELINE = "not set in baseline"
_STR_NOT_RECORDED = "not recorded"
_STR_NOT_CAPTURED = "not captured"


def render_recommendation_projection(
    projection: dict[str, Any], 
    as_table: bool = False, 
    header: str | None = None
) -> list[str]:
    """Render the compact ACPM recommendation projection."""
    lines: list[str] = []
    if header:
        lines.append(header)
        
    if not projection.get("available"):
        if as_table:
            lines.append(
                f"Recommendation authority not recorded for this campaign (`{projection.get('source', 'unknown')}`).\n"
            )
        else:
            lines.append(
                f"- **Recommendation authority:** not recorded (`{projection.get('source', 'unknown')}`)"
            )
            lines.append("")
        return lines

    if as_table:
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        def add_line(label: str, value: str) -> None:
            lines.append(f"| {label} | {value} |")
    else:
        def add_line(label: str, value: str) -> None:
            lines.append(f"- **{label}:** {value}")

    add_line("Recommendation status", f"`{projection.get('status')}`")
    add_line("Leading config", f"`{projection.get('leading_config_id') or 'none'}`")
    
    recommended_config_id = projection.get("recommended_config_id")
    if recommended_config_id:
        add_line("Recommended config", f"`{recommended_config_id}`")
    else:
        add_line("Recommended config", "No ACPM recommendation issued")
        
    add_line("Handoff ready", f"`{projection.get('handoff_ready')}`")
    add_line("Caveat codes", f"{', '.join(projection.get('caveat_codes', [])) or 'none'}")
    
    if projection.get("coverage_class"):
        add_line("Coverage class", f"`{projection.get('coverage_class')}`")
    if projection.get("scope_authority"):
        add_line("Scope authority", f"`{projection.get('scope_authority')}`")
    if projection.get("selected_ngl_values"):
        values = ", ".join(str(v) for v in projection["selected_ngl_values"])
        add_line("Selected NGL values", values)
        
    add_line("Source", f"`{projection.get('source', 'unknown')}`")
    
    lines.append("")
    return lines


def _file_sha256(path: Path) -> str | None:
    """Compute SHA-256 hex digest of a file; return None on any I/O error."""
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


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

# LAB_ROOT is kept here as a module-level fallback so that tools calling
# generate_report() without a lab_root kwarg (e.g. rescore.py) continue to
# work unchanged. Fallback defaults to this repository root to avoid
# cross-workspace writes when QUANTMAP_LAB_ROOT is unset.
LAB_ROOT = optional_env_path("QUANTMAP_LAB_ROOT", Path(__file__).resolve().parent.parent)


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
    is_custom: bool = False,
    is_standard: bool = False,
    is_quick: bool = False,
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
            ngl_display: int | str = int(json.loads(val_json))
        except (TypeError, ValueError):
            ngl_display = "?"
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
            bpt = _kv_bytes_per_token(baseline, int(ngl_display))
            if bpt and bpt > 0:
                est_tokens = int((free_mb * 1024 * 1024) / bpt)
                if est_tokens >= 1000:
                    est_ctx_str = f"{est_tokens // 1000}K"
                else:
                    est_ctx_str = str(est_tokens)
        elif status == "complete" and not model_params_available:
            est_ctx_str = "N/A"

        # TG and score — use explicit None check so that configs whose
        # warm_tg_median/warm_tg_p10 is stored as None (e.g. a Custom run where
        # the single warm slot was consumed by speed_medium, leaving 0 valid
        # warm speed_short results) render as "—" rather than crashing
        # with "unsupported format string passed to NoneType.__format__".
        _tg_val = cfg_stats.get("warm_tg_median")
        tg_str = f"{_tg_val:.2f}" if (status == "complete" and _tg_val is not None) else "—"
        _p10_val = cfg_stats.get("warm_tg_p10")
        p10_str = f"{_p10_val:.2f}" if (status == "complete" and _p10_val is not None) else "—"
        score_val = cfg_score_row.get("composite_score")
        score_str = f"{score_val:.3f}" if (status == "complete" and score_val is not None) else "—"

        # Notes
        notes_parts: list[str] = []
        if cfg_id_row == score_winner_id:
            if is_custom:
                notes_parts.append("★ best tested")
            elif is_standard or is_quick:
                notes_parts.append("★ top config")
            else:
                notes_parts.append("★ score winner")
        if diminishing_ngl is not None and ngl_display == diminishing_ngl:
            notes_parts.append("← diminishing returns beyond this point")
        if status == "oom":
            first_line = (failure_detail or "CUDA OOM").splitlines()[0][:100]
            notes_parts.append(f"OOM: {first_line}")
        elif status == "skipped_oom":
            notes_parts.append("skipped (boundary confirmed)")

        notes = " | ".join(notes_parts) if notes_parts else "—"
        sections.append(
            f"| {ngl_display} | {tg_str} | {p10_str} | {peak_str} | {free_str} | {est_ctx_str} | {score_str} | {notes} |"
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
                    tg = stats.get(cfg_id_row, {}).get("warm_tg_median")
                    if tg is None:
                        continue  # cannot sort by TG if absent
                    tg = float(tg)
                    free_gb = free_mb / 1024
                    candidates.append((tg, ngl_val, est_tokens, free_gb, cfg_id_row))

            if candidates:
                candidates.sort(reverse=True)
                best_tg, best_ngl, best_ctx, best_free, _ = candidates[0]
                ctx_label = f"{best_ctx // 1000}K" if best_ctx >= 1000 else str(best_ctx)
                min_label = f"{min_ctx // 1000}K" if min_ctx >= 1000 else str(min_ctx)
                if is_custom:
                    _scope_note = " Among tested values only — run Full to confirm across all NGL values."
                elif is_quick:
                    _scope_note = " Quick run (1 cycle, broad but shallow) — run Standard or Full to confirm with higher-confidence statistics."
                elif is_standard:
                    _scope_note = " Standard run (development-grade) — run Full to confirm with higher-confidence statistics."
                else:
                    _scope_note = ""
                sections.append(
                    f"> **For your stated minimum of {min_label} context:** NGL={best_ngl} "
                    f"(TG median {best_tg:.2f} t/s, est. max context {ctx_label}, "
                    f"{best_free:.1f} GB VRAM free). "
                    f"This is the fastest tested config that meets your context requirement."
                    f"{_scope_note}\n"
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
    lab_root: Path | None = None,
    run_plan: RunPlan | None = None,
) -> Path:
    """
    Generate the campaign-summary.md artifact for a completed campaign.

    If scores_result and stats are provided (from score_campaign()), they are
    used directly. Otherwise, analysis is re-run from the database.

    lab_root:  effective lab root to write reports under. If None, falls back to
               the module-level LAB_ROOT (default baseline, backwards-compatible).
    run_plan:  resolved execution plan. When provided, the report reflects the
               run mode, scope, and confidence language correctly. If None (e.g.
               rescore.py), the report is generated without mode-aware sections.

    Returns the path to the generated campaign-summary.md file.
    """
    effective_lab_root = lab_root if lab_root is not None else LAB_ROOT
    from src.trust_identity import load_baseline_for_historical_use  # noqa: PLC0415
    baseline, baseline_source = load_baseline_for_historical_use(
        campaign_id,
        db_path,
        fallback_baseline=baseline,
        allow_current_input=False,
    )
    if scores_result is None:
        from src.score import score_campaign  # noqa: PLC0415

        scores_result = score_campaign(campaign_id, db_path, baseline)
    if stats is None:
        stats = scores_result["stats"]

    model_cfg = baseline.get("model", {}) if isinstance(baseline.get("model", {}), dict) else {}
    model_identity = infer_model_identity(
        model_name=model_cfg.get("name"),
        model_path=model_cfg.get("path"),
    )
    report_artifacts = report_paths(
        effective_lab_root,
        model_identity,
        campaign_id,
        create=True,
    )

    md_path = report_artifacts[ARTIFACT_CAMPAIGN_SUMMARY]

    # scores.csv is no longer written here — its data is folded into metadata.json.
    # The report_artifacts dict retains the deprecated "scores_csv" key for any
    # callers that still reference it, but the file is not generated by this function.

    # Generate Markdown
    md = _build_markdown(
        campaign_id, db_path, baseline, scores_result, stats,
        campaign=campaign, run_plan=run_plan, lab_root=effective_lab_root,
        baseline_source=baseline_source,
    )
    md_path.write_text(md, encoding="utf-8")
    logger.info("Campaign summary written: %s", md_path)

    # Record campaign-summary.md generation in the artifacts table.
    # This provides a DB-level audit trail: when the summary was last regenerated
    # and from what DB path. Non-fatal — a broken artifacts INSERT must never
    # suppress a valid report write.
    _now_utc = datetime.now(timezone.utc).isoformat()
    try:
        with get_connection(db_path) as _art_conn:
            _sha = _file_sha256(md_path)
            _status = "complete" if _sha else "failed"
            _error = None if _sha else "campaign-summary.md missing or unreadable after write"
            _art_conn.execute(
                "DELETE FROM artifacts WHERE campaign_id=? AND artifact_type=?",
                (campaign_id, ARTIFACT_CAMPAIGN_SUMMARY),
            )
            _art_conn.execute(
                "INSERT INTO artifacts (campaign_id, artifact_type, path, sha256, created_at, status, producer, error_message, updated_at, verification_source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    campaign_id,
                    ARTIFACT_CAMPAIGN_SUMMARY,
                    str(md_path),
                    _sha,
                    _now_utc,
                    _status,
                    "src.report.generate_report",
                    _error,
                    _now_utc,
                    "producer_hash" if _sha else "producer_missing",
                ),
            )
            _art_conn.commit()
    except Exception as _art_exc:
        logger.warning("Could not record campaign-summary.md in DB (non-fatal): %s", _art_exc)

    return md_path


def _build_markdown(
    campaign_id: str,
    db_path: Path,
    baseline: dict[str, Any],
    scores_result: dict[str, Any],
    stats: dict[str, dict[str, Any]],
    campaign: dict | None = None,
    run_plan: RunPlan | None = None,
    lab_root: Path | None = None,
    baseline_source: str | None = None,
) -> str:
    """Build the full Markdown report as a string."""
    effective_lab_root = lab_root if lab_root is not None else LAB_ROOT
    sections: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Load campaign metadata from DB
    with get_connection(db_path) as conn:
        campaign_row = conn.execute(
            "SELECT * FROM campaigns WHERE id=?", (campaign_id,)
        ).fetchone()

    camp = dict(campaign_row) if campaign_row else {}
    from src.trust_identity import (  # noqa: PLC0415
        load_run_identity,
        methodology_source_label,
        recommendation_projection,
    )
    trust_identity = load_run_identity(campaign_id, db_path)
    snap = trust_identity.start_snapshot
    recommendation = recommendation_projection(trust_identity)

    # -------------------------------------------------------------------------
    # Title and metadata
    # -------------------------------------------------------------------------
    machine = baseline.get("machine", {})
    runtime = baseline.get("runtime", {})
    bios = baseline.get("bios", {})

    sections.append(f"# QuantMap Campaign Summary — {campaign_id}")
    sections.append(f"\nGenerated: {now}\n")

    # ── Mode badge ────────────────────────────────────────────────────────────
    if run_plan is not None:
        sections.append(
            f"> **Mode:** {run_plan.mode_label} — {run_plan.mode_description}"
        )
        sections.append("")

    sections.append("## Campaign Metadata\n")
    sections.append("| Field | Value |")
    sections.append("|-------|-------|")
    sections.append(f"| Campaign ID | `{campaign_id}` |")
    _db_run_mode = camp.get("run_mode") or (run_plan.run_mode if run_plan else None)
    if _db_run_mode:
        from src.run_plan import MODE_LABELS as _ML  # noqa: PLC0415
        sections.append(f"| Run mode | {_ML.get(_db_run_mode, _db_run_mode.title())} |")
    sections.append(f"| Variable | `{camp.get('variable', 'unspecified sweep')}` |")
    sections.append(f"| Type | {camp.get('campaign_type', 'type not recorded')} |")
    sections.append(f"| Status | {camp.get('status', 'status not recorded')} |")
    if camp.get("analysis_status") or camp.get("report_status"):
        sections.append(f"| Analysis status | {camp.get('analysis_status', 'unassessed')} |")
        sections.append(f"| Report status | {camp.get('report_status', 'unassessed')} |")
    sections.append(f"| Started | {camp.get('started_at', 'timing unavailable')} |")
    sections.append(f"| Completed | {camp.get('completed_at', 'timing unavailable')} |")
    sections.append(f"| Machine | {machine.get('name', 'unidentified machine')} |")
    sections.append(f"| CPU | {machine.get('cpu', 'unidentified CPU')} |")
    sections.append(f"| GPU | {machine.get('gpu', 'unidentified GPU')} |")
    sections.append(f"| RAM | {machine.get('ram', 'RAM capacity unmeasured')} |")
    sections.append(f"| OS | {snap.get('os_platform', machine.get('os', 'OS platform unmeasured'))} |")
    sections.append(f"| NVIDIA Driver | {snap.get('nvidia_driver', 'driver probe failed')} |")
    try:
        from src.execution_environment import execution_environment_summary_lines  # noqa: PLC0415

        sections.extend(execution_environment_summary_lines(snap))
    except Exception:
        sections.append("| Execution support tier | `unknown` |")
    try:
        from src.telemetry_provider import provider_evidence_summary_lines  # noqa: PLC0415

        sections.extend(provider_evidence_summary_lines(snap))
    except Exception:
        sections.append("| Telemetry provider evidence | not available \u2014 provider probe failed |")
    sections.append(f"| Build Commit | `{snap.get('build_commit', runtime.get('build_commit', 'not captured'))}` |")
    qid = trust_identity.quantmap
    qver = qid.get("quantmap_version") or trust_identity.sources.get("quantmap", "legacy_unrecorded")
    qcommit = qid.get("git_commit") or _STR_NOT_CAPTURED
    sections.append(f"| QuantMap identity | {qver} / `{str(qcommit)[:16]}` |")
    if baseline_source:
        sections.append(f"| Baseline identity source | `{baseline_source}` |")
    sections.append(f"| Power Plan | {snap.get('power_plan') or 'not recorded'} |")
    baseline_sha = (camp.get('baseline_sha256') or 'not recorded')
    campaign_sha = (camp.get('campaign_sha256') or 'not recorded')
    sections.append(f"| Baseline SHA256 | `{baseline_sha[:16]}...` |")
    sections.append(f"| Campaign SHA256 | `{campaign_sha[:16]}...` |")
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
    # Run Scope — shown for all modes; essential for Custom
    # -------------------------------------------------------------------------
    if run_plan is not None:
        sections.append("## Run Scope\n")
        sections.append("| Field | Value |")
        sections.append("|-------|-------|")
        sections.append(f"| Mode | {run_plan.mode_label} — {run_plan.mode_description} |")
        if run_plan.effective_campaign_id != run_plan.parent_campaign_id:
            sections.append(f"| Parent campaign | `{run_plan.parent_campaign_id}` |")
            sections.append(f"| Effective run ID | `{run_plan.effective_campaign_id}` |")
        sections.append(f"| Variable | `{run_plan.variable}` |")
        _tested_str = ", ".join(str(v) for v in run_plan.selected_values)
        _total = len(run_plan.all_campaign_values)
        _tested_n = len(run_plan.selected_values)
        sections.append(f"| Tested values | {_tested_str} |")
        sections.append(f"| Coverage | {_tested_n} of {_total} campaign values ({run_plan.coverage_fraction:.0%}) |")
        if run_plan.untested_values:
            _skip_str = ", ".join(str(v) for v in run_plan.untested_values)
            sections.append(f"| Skipped values | {_skip_str} |")
        sections.append(f"| Configs tested | {len(run_plan.selected_configs)} |")
        sections.append(f"| Cycles per config | {run_plan.cycles_per_config} |")
        sections.append(f"| Requests per cycle | {run_plan.requests_per_cycle} (1 cold + {run_plan.requests_per_cycle - 1} warm) |")
        sections.append(f"| Warm samples per config | {run_plan.warm_samples_per_config} |")
        if run_plan.filter_overrides:
            sections.append(f"| Filter overrides | {run_plan.filter_overrides} |")
        sections.append("")

        if run_plan.is_custom:
            sections.append(
                "> ⚠️ **Custom run** — user-directed scope. "
                f"Only {_tested_n} of {_total} campaign values were tested. "
                "Results reflect the best among tested configs only. "
                "Untested values may outperform this result. "
                "Do not treat this as a full campaign recommendation."
            )
            sections.append("")
        elif run_plan.is_standard:
            sections.append(
                "> ℹ️ **Standard run** — complete value coverage, reduced repetition. "
                f"All {_total} campaign values tested with {run_plan.cycles_per_config} cycles per config. "
                "Development-grade result. Run Full for highest-confidence recommendation."
            )
            sections.append("")
        elif run_plan.is_quick:
            _q_cycles = run_plan.cycles_per_config
            _q_cycle_word = "cycle" if _q_cycles == 1 else "cycles"
            sections.append(
                f"> ⚡ **Quick run** — complete value coverage, {_q_cycles} {_q_cycle_word} per config. "
                f"All {_total} campaign values tested — broad but shallow. "
                "Lowest-confidence full-coverage result. Use Standard or Full for deeper confirmation."
            )
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

    _is_custom = run_plan is not None and run_plan.is_custom
    _is_standard = run_plan is not None and run_plan.is_standard
    _is_quick = run_plan is not None and run_plan.is_quick

    all_same = (winner == highest_tg and winner in pareto_frontier)
    if all_same and winner:
        if len(passing) == 1:
            sections.append(
                f"> **Single Valid Result:** Only `{winner}` passed all elimination filters. "
                "There is no competitive field to compare against."
            )
        elif _is_custom:
            sections.append(
                f"> **Best tested config:** All three views agree on `{winner}` "
                "as the top result among the tested subset."
            )
        elif _is_quick:
            sections.append(
                f"> **Consistent result:** All three views agree on `{winner}` "
                "across all campaign values. Quick run — broad but shallow, lowest-confidence full-coverage."
            )
        elif _is_standard:
            sections.append(
                f"> **Consistent result:** All three views agree on `{winner}` "
                "across all campaign values. Standard run — development-grade confidence."
            )
        else:
            sections.append(
                f"> **Strong evidence:** All three views agree on the same winner: `{winner}`. "
                "Score winner, Pareto frontier, and highest raw TG are identical."
            )
    elif winner:
        if _is_custom:
            _decl_section = "Custom Run Summary"
        elif _is_quick:
            _decl_section = "Quick Run Summary"
        elif _is_standard:
            _decl_section = "Standard Run Summary"
        else:
            _decl_section = "Winner Declaration"
        sections.append(
            f"> **Views diverge.** See tradeoff explanation in the {_decl_section} section."
        )
    else:
        sections.append("> **WARNING: No configs passed all elimination filters.**")
    sections.append("")

    # View 1: Score winner (or best-tested-config for Custom)
    _v1_header = "### View 1 — Best Tested Config (Composite Score)\n" if _is_custom else "### View 1 — Score Winner (Composite Score)\n"
    sections.append(_v1_header)
    if winner and winner in passing:
        w_stats = passing[winner]
        _winner_label = "Best tested config" if _is_custom else ("Top config" if (_is_standard or _is_quick) else "Winner")
        sections.append(f"**{_winner_label}: `{winner}`**\n")
        sections.append(_config_stats_table(winner, w_stats, scores_df, ref))
        sm_flag = speed_medium_flags.get(winner, False)
        if sm_flag:
            deg = w_stats.get("speed_medium_degradation_pct")
            deg_disp = f"{deg:.1f}%" if deg is not None else "—"
            sections.append(
                f"\n> ⚠️ **speed_medium flag:** This config shows "
                f"{deg_disp} TG degradation "
                "on the 512-token request vs 256-token baseline. Review before using in production."
            )
    else:
        if _is_custom:
            sections.append("*No best tested config — all tested configs eliminated.*")
        elif _is_quick or _is_standard:
            sections.append("*No top config — all configs eliminated.*")
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
            tg   = s.get("warm_tg_median")      # guaranteed non-None (rankable)
            ttft = s.get("warm_ttft_median_ms")  # guaranteed non-None (rankable)
            outliers = s.get("outlier_count")
            thermal  = s.get("thermal_events")
            tg_pct = None
            if scores_df is not None and cid in scores_df.index:
                tg_pct = scores_df.loc[cid].get("warm_tg_vs_baseline_pct")
            tg_pct_str = (
                (f"+{tg_pct:.1f}%" if tg_pct >= 0 else f"{tg_pct:.1f}%")
                if tg_pct is not None else "—"
            )
            tg_disp   = f"{tg:.2f} t/s"  if tg   is not None else "—"
            ttft_disp = f"{ttft:.0f} ms" if ttft is not None else "—"
            outliers_disp = str(outliers) if outliers is not None else "—"
            thermal_disp  = str(thermal)  if thermal  is not None else "—"
            notes = ""
            if cid == winner:
                if _is_custom:
                    notes = "← best tested"
                elif _is_quick or _is_standard:
                    notes = "← top config"
                else:
                    notes = "← score winner"
            elif cid == highest_tg:
                notes = "← highest TG"
            sections.append(
                f"| `{cid}` | {tg_disp} | {ttft_disp} | {tg_pct_str} | "
                f"{outliers_disp} | {thermal_disp} | {notes} |"
            )
    else:
        sections.append("*No passing configs for Pareto analysis.*")
    sections.append("")

    # View 3: Highest raw TG
    unrankable = scores_result.get("unrankable", {})
    sections.append("### View 3 — Highest Raw TG\n")
    if highest_tg:
        # highest_tg can now be one of the rankable configs (in stats) or an unrankable config
        # stats includes all configs returned by analyze_campaign.
        h_stats = stats.get(highest_tg)
        is_unrank = (highest_tg in unrankable)
        unrank_note = " ⚠ **Unrankable (Evidence Only)**" if is_unrank else ""

        sections.append(f"**Highest TG Config: `{highest_tg}`**{unrank_note}\n")
        if _is_custom:
            _best_label = "best tested config"
        elif _is_quick or _is_standard:
            _best_label = "top config"
        else:
            _best_label = "score winner"
            
        if highest_tg == winner:
            sections.append(f"*Same as {_best_label}.*")
        else:
            if is_unrank:
                sections.append(
                    "_This configuration is the absolute performance leader for throughput, "
                    "but is excluded from the primary ranking because one or more secondary "
                    "metrics (e.g. latency or efficiency) could not be recorded._"
                )
            else:
                sections.append(
                    f"_Differs from {_best_label}. Useful if generation speed is the only priority "
                    "and TTFT is not a concern._"
                )
            
            if h_stats:
                sections.append(_config_stats_table(highest_tg, h_stats, scores_df, ref))
    else:
        if _is_custom:
            sections.append("*Same as best tested config or no passing configs.*")
        elif _is_quick or _is_standard:
            sections.append("*Same as top config or no passing configs.*")
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
        cv_val = s.get('warm_tg_cv')
        cv_disp = f"{cv_val:.3f}" if (cv_val is not None and s.get("valid_warm_request_count", 0) >= 3) else "N/A"
        tg_disp   = f"{s.get('warm_tg_median'):.2f}"    if s.get('warm_tg_median')    is not None else "—"
        tgp10_disp= f"{s.get('warm_tg_p10'):.2f}"      if s.get('warm_tg_p10')        is not None else "—"
        ttft_disp = f"{s.get('warm_ttft_median_ms'):.0f}ms" if s.get('warm_ttft_median_ms') is not None else "—"
        ttftp_disp= f"{s.get('warm_ttft_p90_ms'):.0f}ms"   if s.get('warm_ttft_p90_ms')    is not None else "—"
        thermal_disp  = str(s.get('thermal_events'))  if s.get('thermal_events')  is not None else "—"
        outlier_disp  = str(s.get('outlier_count'))   if s.get('outlier_count')   is not None else "—"

        sections.append(
            f"| {rank} | `{config_id}` | "
            f"{tg_disp} | "
            f"{tgp10_disp} | "
            f"{cv_disp} | "
            f"{ttft_disp} | "
            f"{ttftp_disp} | "
            f"{score_val:.4f} | "
            f"{thermal_disp} | "
            f"{outlier_disp} | "
            f"{'✓ PASS' if config_id in passing else 'FAIL'} |"
        )

    unrankable = scores_result.get("unrankable", {})
    if unrankable:
        sections.append("| | **Unrankable Configs** | | | | | | | | | |")
    for config_id, missing in sorted(unrankable.items()):
        s = stats.get(config_id, {})
        cv_val = s.get('warm_tg_cv')
        cv_disp = f"{cv_val:.3f}" if (cv_val is not None and s.get("valid_warm_request_count", 0) >= 3) else "N/A"
        tg_disp   = f"{s.get('warm_tg_median'):.2f}"    if s.get('warm_tg_median')    is not None else "—"
        tgp10_disp= f"{s.get('warm_tg_p10'):.2f}"      if s.get('warm_tg_p10')        is not None else "—"
        ttft_disp = f"{s.get('warm_ttft_median_ms'):.0f}ms" if s.get('warm_ttft_median_ms') is not None else "—"
        ttftp_disp= f"{s.get('warm_ttft_p90_ms'):.0f}ms"   if s.get('warm_ttft_p90_ms')    is not None else "—"
        thermal_disp  = str(s.get('thermal_events'))  if s.get('thermal_events')  is not None else "—"
        outlier_disp  = str(s.get('outlier_count'))   if s.get('outlier_count')   is not None else "—"

        missing_str = ", ".join(missing)
        sections.append(
            f"| — | `{config_id}` | "
            f"{tg_disp} | "
            f"{tgp10_disp} | "
            f"{cv_disp} | "
            f"{ttft_disp} | "
            f"{ttftp_disp} | "
            f"— | "
            f"{thermal_disp} | "
            f"{outlier_disp} | "
            f"❌ unrankable: missing {missing_str} |"
        )

    eliminated = scores_result.get("eliminated", {})
    if eliminated:
        sections.append("| | **Eliminated Configs** | | | | | | | | | |")
    for config_id, reason in sorted(eliminated.items()):
        s = stats.get(config_id, {})
        cv_val = s.get('warm_tg_cv')
        cv_disp = f"{cv_val:.3f}" if (cv_val is not None and s.get("valid_warm_request_count", 0) >= 3) else "N/A"
        tg_disp   = f"{s.get('warm_tg_median'):.2f}"    if s.get('warm_tg_median')    is not None else "—"
        tgp10_disp= f"{s.get('warm_tg_p10'):.2f}"      if s.get('warm_tg_p10')        is not None else "—"
        ttft_disp = f"{s.get('warm_ttft_median_ms'):.0f}ms" if s.get('warm_ttft_median_ms') is not None else "—"
        ttftp_disp= f"{s.get('warm_ttft_p90_ms'):.0f}ms"   if s.get('warm_ttft_p90_ms')    is not None else "—"
        thermal_disp  = str(s.get('thermal_events'))  if s.get('thermal_events')  is not None else "—"
        outlier_disp  = str(s.get('outlier_count'))   if s.get('outlier_count')   is not None else "—"

        sections.append(
            f"| — | `{config_id}` | "
            f"{tg_disp} | "
            f"{tgp10_disp} | "
            f"{cv_disp} | "
            f"{ttft_disp} | "
            f"{ttftp_disp} | "
            f"— | "
            f"{thermal_disp} | "
            f"{outlier_disp} | "
            f"❌ {reason} |"
        )
    sections.append("")

    # -------------------------------------------------------------------------
    # speed_medium flags
    # -------------------------------------------------------------------------
    flagged = [(cid, stats[cid].get("speed_medium_degradation_pct"))
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
        for cid, deg in sorted(flagged, key=lambda x: x[1] if x[1] is not None else -999, reverse=True):
            s = stats[cid]
            tg_val   = s.get('warm_tg_median')
            med_val  = s.get('speed_medium_warm_tg_median')
            deg_disp = f"{deg:.1f}%" if deg is not None else "—"
            sections.append(
                f"| `{cid}` | {deg_disp} | "
                f"{s0_tg} t/s | "
                f"{f'{tg_val:.2f} t/s' if tg_val is not None else '—'} | "
                f"{f'{med_val:.2f} t/s' if med_val is not None else '—'} |"
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
            f"{_fmt_tel(tel.get('throttle_samples'), 'd')} | "
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
        total_snaps = bg.get("total_snapshots")
        total_snaps_disp = str(total_snaps) if total_snaps is not None else "—"

        def _bg_flag(count: int | None) -> str:
            """⚠️ N  /  ✓  /  ?  depending on count and data availability."""
            if count is None:
                return "?"
            return f"⚠️ {count}" if count > 0 else "✓"

        sections.append(
            f"| `{config_id}` | {total_snaps_disp} | "
            f"{_bg_flag(bg.get('av_scan_count'))} | "
            f"{_bg_flag(bg.get('defender_process_count'))} | "
            f"{_bg_flag(bg.get('update_active_count'))} | "
            f"{_bg_flag(bg.get('search_indexer_count'))} | "
            f"{_fmt_tel(bg.get('avg_high_cpu_procs'), '.1f')} | "
            f"{bg.get('max_high_cpu_procs') if bg.get('max_high_cpu_procs') is not None else 'N/A'} |"
        )
    sections.append("")

    # -------------------------------------------------------------------------
    # Winner Declaration / Quick Run Summary / Standard Run Summary / Custom Run Summary
    # -------------------------------------------------------------------------
    if _is_custom:
        _decl_header = "## Custom Run Summary\n"
    elif _is_quick:
        _decl_header = "## Quick Run Summary\n"
    elif _is_standard:
        _decl_header = "## Standard Run Summary\n"
    else:
        _decl_header = "## Winner Declaration\n"
    sections.append(_decl_header)

    if winner and winner in passing:
        w = passing[winner]
        # All metrics are guaranteed non-None for ranked (passing) configs.
        tg     = w.get("warm_tg_median")
        tg_p10 = w.get("warm_tg_p10")
        ttft   = w.get("warm_ttft_median_ms")
        cv     = w.get("warm_tg_cv")
        thermal  = w.get("thermal_events")  # may be None if no telemetry data
        outliers = w.get("outlier_count")   # same
        n_warm   = w.get("valid_warm_request_count", 0)
        thermal_disp  = str(thermal)  if thermal  is not None else "N/A"
        outliers_disp = str(outliers) if outliers is not None else "N/A"

        divergence_note = ""
        if highest_tg and highest_tg != winner:
            h = passing[highest_tg]
            h_ttft = passing[highest_tg].get('warm_ttft_median_ms')
            h_tg   = h.get('warm_tg_median')
            ttft_disp   = f"{ttft:.0f}ms"  if ttft   is not None else "N/A"
            h_ttft_disp = f"{h_ttft:.0f}ms" if h_ttft is not None else "N/A"
            h_tg_disp   = f"{h_tg:.2f}"    if h_tg   is not None else "N/A"
            tg_disp_w   = f"{tg:.2f}"      if tg     is not None else "N/A"
            divergence_note = (
                f"\n\n**Note:** Best-scoring config (`{winner}`) and highest-TG config "
                f"(`{highest_tg}`) differ. Best-scoring has better TTFT ({ttft_disp} median vs "
                f"{h_ttft_disp}) at the cost of "
                f"slightly lower TG ({tg_disp_w} vs {h_tg_disp} t/s). "
                "For pure generation speed, use the highest-TG config."
            )

        snap_bios = (
            f"BIOS: {bios.get('pl1_w','?')}W/−{abs(bios.get('vcore_offset_v',0))*1000:.0f}mV/"
            f"Gear{bios.get('gear_mode','?')}/XMP{bios.get('xmp_profile','?')}"
        )

        # R5: pull model identity and build commit from baseline/snapshot rather
        # than hard-coding.  Fallback to "unknown" (not a specific commit hash)
        # so any misconfigured environment produces an obviously-wrong output
        # rather than silently stamping the wrong build identifier.
        model_cfg = baseline.get("model", {})
        model_label = model_cfg.get("name", "unknown model")
        build_commit = snap.get("build_commit") or runtime.get("build_commit") or _STR_NOT_CAPTURED

        tg_str    = f"{tg:.2f} t/s"   if tg     is not None else "N/A"
        tg_p10_str= f"{tg_p10:.2f} t/s" if tg_p10 is not None else "N/A"
        ttft_str  = f"{ttft:.0f}ms"    if ttft   is not None else "N/A"

        if _is_custom and run_plan is not None:
            # Custom mode: honest scope-limited language.
            # Never claims "validated optimal" — only "best among tested".
            _rp = run_plan
            _tested_n = len(_rp.selected_values)
            _total_n  = len(_rp.all_campaign_values)
            _untested  = _rp.untested_values
            sections.append(
                f'> **Custom Run — Scope Notice:**\n>\n'
                f'> "On {machine.get("name","DEEP THOUGHT")} '
                f'({machine.get("cpu", _STR_NOT_SET_IN_BASELINE)} + {machine.get("gpu", _STR_NOT_SET_IN_BASELINE)}, '
                f'{snap_bios}, OS: {machine.get("os","Windows 11 Pro")}) '
                f'running {model_label} via llama.cpp build {build_commit}, '
                f'the best-performing config among the {_tested_n} tested value(s) '
                f'is `{winner}`, delivering **{tg_str}** warm TG median '
                f'(**{tg_p10_str}** P10) and **{ttft_str}** warm TTFT median '
                f'across **{n_warm}** warm request(s) with **{thermal_disp}** thermal events '
                f'and **{outliers_disp}** outlier(s) on '
                f'{datetime.now(timezone.utc).strftime("%Y-%m-%d")}."'
            )
            if _untested:
                sections.append(
                    f'>\n> ⚠️ **Untested values:** {", ".join(str(v) for v in _untested)}. '
                    "These were not measured in this run. The true optimum may lie "
                    "elsewhere. Run Full to measure all campaign values."
                )
        elif _is_quick and run_plan is not None:
            # Quick mode: complete coverage, 1 cycle, broad but shallow.
            # Not "validated optimal" — lowest-confidence full-coverage result.
            _rp = run_plan
            _total_vals = len(_rp.all_campaign_values)
            _q_c = _rp.cycles_per_config
            _q_cw = "cycle" if _q_c == 1 else "cycles"
            sections.append(
                f'> **Quick Run — Broad Coverage Result:**\n>\n'
                f'> "On {machine.get("name","DEEP THOUGHT")} '
                f'({machine.get("cpu", _STR_NOT_SET_IN_BASELINE)} + {machine.get("gpu", _STR_NOT_SET_IN_BASELINE)}, '
                f'{snap_bios}, OS: {machine.get("os","Windows 11 Pro")}) '
                f'running {model_label} via llama.cpp build {build_commit}, '
                f'the top-performing config across all {_total_vals} campaign values '
                f'under {_q_c} {_q_cw} (broad but shallow) '
                f'is `{winner}`, delivering **{tg_str}** warm TG median '
                f'(**{tg_p10_str}** P10) and **{ttft_str}** warm TTFT median '
                f'across **{n_warm}** warm request(s) with **{thermal_disp}** thermal events '
                f'and **{outliers_disp}** outlier(s) on '
                f'{datetime.now(timezone.utc).strftime("%Y-%m-%d")}."'
            )
            sections.append(
                f'>\n> ⚡ **Broad but shallow:** Quick mode uses {_q_c} {_q_cw} per config '
                f'({_rp.warm_samples_per_config} warm request slots). '
                'Useful for plumbing checks, bug-finding, and first-look identification. '
                'Run Standard or Full to confirm with higher-confidence statistics before '
                'treating this as a production recommendation.'
            )
        elif _is_standard and run_plan is not None:
            # Standard mode: complete coverage, reduced repetition, development-grade.
            # Not "validated optimal" — development-grade, confirm with Full.
            _rp = run_plan
            _total_vals = len(_rp.all_campaign_values)
            sections.append(
                f'> **Standard Run — Development-Grade Result:**\n>\n'
                f'> "On {machine.get("name","DEEP THOUGHT")} '
                f'({machine.get("cpu", _STR_NOT_SET_IN_BASELINE)} + {machine.get("gpu", _STR_NOT_SET_IN_BASELINE)}, '
                f'{snap_bios}, OS: {machine.get("os","Windows 11 Pro")}) '
                f'running {model_label} via llama.cpp build {build_commit}, '
                f'the top-performing config across all {_total_vals} campaign values '
                f'under reduced repetition ({_rp.cycles_per_config} cycles) '
                f'is `{winner}`, delivering **{tg_str}** warm TG median '
                f'(**{tg_p10_str}** P10) and **{ttft_str}** warm TTFT median '
                f'across **{n_warm}** warm request(s) with **{thermal_disp}** thermal events '
                f'and **{outliers_disp}** outlier(s) on '
                f'{datetime.now(timezone.utc).strftime("%Y-%m-%d")}."'
            )
            sections.append(
                f'>\n> ℹ️ **Development-grade:** Standard mode uses {_rp.cycles_per_config} cycles per config '
                '(reduced repetition). This result identifies the leading config across the full '
                'value space. Run Full to confirm with highest-confidence statistics before '
                'treating this as a production recommendation.'
            )
        else:
            sections.append(
                f'> **Confidence Statement:**\n>\n'
                f'> "On {machine.get("name","DEEP THOUGHT")} '
                f'({machine.get("cpu", _STR_NOT_SET_IN_BASELINE)} + {machine.get("gpu", _STR_NOT_SET_IN_BASELINE)}, '
                f'{snap_bios}, OS: {machine.get("os","Windows 11 Pro")}) '
                f'running {model_label} via llama.cpp build {build_commit}, '
                f'the validated optimal single-user configuration is `{winner}`, '
                f'delivering **{tg_str}** warm TG median (**{tg_p10_str}** P10) '
                f'and **{ttft_str}** warm TTFT median, validated across '
                f'**{n_warm}** warm requests with **{thermal_disp}** thermal events and '
                f'**{outliers_disp}** outliers on {datetime.now(timezone.utc).strftime("%Y-%m-%d")}."'
            )
        sections.append(divergence_note)
        sections.append("")

        # -----------------------------------------------------------------------
        # Production command
        # -----------------------------------------------------------------------
        sections.append("## Production Command\n")
        from src.config import DEFAULT_HOST, PRODUCTION_PORT  # noqa: PLC0415
        if _is_custom:
            sections.append(
                f"Command for `{winner}` — best tested config in this Custom run. "
                f"Host {DEFAULT_HOST}, port {PRODUCTION_PORT}. "
                "Validate with a Full run before deploying as a permanent config.\n"
            )
        elif _is_quick:
            sections.append(
                f"Command for `{winner}` — top config in this Quick run. "
                f"Host {DEFAULT_HOST}, port {PRODUCTION_PORT}. "
                "Quick run (1 cycle, broad but shallow) — run Standard or Full to confirm before deploying.\n"
            )
        elif _is_standard:
            sections.append(
                f"Command for `{winner}` — top config in this Standard run. "
                f"Host {DEFAULT_HOST}, port {PRODUCTION_PORT}. "
                "Development-grade — run Full for highest-confidence confirmation before deploying.\n"
            )
        else:
            sections.append(f"Copy-paste ready. Host {DEFAULT_HOST}, port {PRODUCTION_PORT}.\n")

        with get_connection(db_path) as conn:
            cmd_row = conn.execute(
                "SELECT resolved_command, runtime_env_json FROM configs WHERE id=? AND campaign_id=?",
                (winner, campaign_id),
            ).fetchone()

        server_bin_env = read_env_path("QUANTMAP_SERVER_BIN")
        server_bin = (
            str(server_bin_env.path)
            if server_bin_env.path is not None
            else f"<{server_bin_env.message} — copy .env.example to .env>"
        )
        model_path_env = read_env_path("QUANTMAP_MODEL_PATH")
        model_path = (
            str(model_path_env.path)
            if model_path_env.path is not None
            else f"<{model_path_env.message} — copy .env.example to .env>"
        )
        build_commit = snap.get("build_commit") or runtime.get("build_commit") or _STR_NOT_CAPTURED

        if _is_custom:
            _cmd_label = "QuantMap — Custom Run — Best Tested Config"
        elif _is_standard:
            _cmd_label = "QuantMap — Standard Run — Development-Grade"
        else:
            _cmd_label = "QuantMap — Validated Production Config"
        sections.append("```batch")
        sections.append(f"rem {_cmd_label}")
        sections.append(f"rem Campaign: {campaign_id} | Config: {winner}")
        sections.append(f"rem Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} | Warm requests: {n_warm}")
        sections.append(f"rem Warm TG P10: {tg_p10:.2f} t/s | CV: {cv:.3f} | Thermal events: {thermal}")
        sections.append(f"rem Machine: {machine.get('name','DEEP THOUGHT')} ({machine.get('cpu','i9-12900K')} + {machine.get('gpu','RTX 3090')} + {machine.get('ram','128GB DDR4-3200')})")
        if _is_custom and run_plan is not None:
            sections.append(f"rem Mode: Custom | Tested: {len(run_plan.selected_values)} of {len(run_plan.all_campaign_values)} values")
        elif _is_quick and run_plan is not None:
            sections.append(f"rem Mode: Quick | All {len(run_plan.all_campaign_values)} values | {run_plan.cycles_per_config} cycle per config (broad but shallow)")
        elif _is_standard and run_plan is not None:
            sections.append(f"rem Mode: Standard | All {len(run_plan.all_campaign_values)} values | {run_plan.cycles_per_config} cycles per config")
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
        if _is_custom:
            sections.append(
                "**No result declared.** All tested configs failed elimination filters. "
                "Check the Full Config Ranking table for the specific elimination reason per config.\n"
            )
            sections.append("Possible causes:")
            sections.append("- High CV (>5%): thermal interference or background processes during the run")
            sections.append("- Thermal events: check GPU/CPU thermals and BIOS power limits")
            sections.append("- Low TG P10 (<7.0 t/s): hardware limitation for these parameter values")
            sections.append("- Low sample count: if fewer cycles than usual, add `--cycles N` and re-run")
        elif _is_quick:
            sections.append(
                "**No result declared.** All configs failed elimination filters. "
                "Check the Full Config Ranking table for the specific elimination reason per config.\n"
            )
            sections.append("Possible causes:")
            sections.append("- High CV (>5%): thermal interference or background processes during the run")
            sections.append("- Thermal events: check GPU/CPU thermals and BIOS power limits")
            sections.append("- Low TG P10 (<7.0 t/s): hardware limitation for these parameter values")
            _q_c_nw = run_plan.cycles_per_config if run_plan is not None else 1
            _q_cw_nw = "cycle" if _q_c_nw == 1 else "cycles"
            sections.append(
                f"- Low sample count: Quick uses {_q_c_nw} {_q_cw_nw} per config (lowest-confidence). "
                "Re-run with `--mode standard` or `--mode full` for higher-confidence results."
            )
        elif _is_standard:
            sections.append(
                "**No result declared.** All configs failed elimination filters. "
                "Check the Full Config Ranking table for the specific elimination reason per config.\n"
            )
            sections.append("Possible causes:")
            sections.append("- High CV (>5%): thermal interference or background processes during the run")
            sections.append("- Thermal events: check GPU/CPU thermals and BIOS power limits")
            sections.append("- Low TG P10 (<7.0 t/s): hardware limitation for these parameter values")
            sections.append(
                "- Low sample count: Standard uses reduced repetition. "
                "Add `--cycles N` to increase or re-run with `--mode full` for higher confidence."
            )
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

    sections.extend(
        render_recommendation_projection(
            recommendation, 
            as_table=False, 
            header="## ACPM Recommendation\n"
        )
    )

    # -------------------------------------------------------------------------
    # Methodology note
    # -------------------------------------------------------------------------
    sections.append("## Methodology\n")
    methodology = trust_identity.methodology
    methodology_label = methodology_source_label(methodology)
    sections.append(f"- **Methodology evidence:** `{methodology_label}`")
    if methodology.get("profile_name") or methodology.get("profile_version"):
        sections.append(
            f"- **Experiment profile:** `{methodology.get('profile_name') or 'unspecified profile'}` "
            f"v{methodology.get('profile_version') or 'unspecified version'}"
        )
    if methodology.get("id") is not None:
        sections.append(f"- **Methodology snapshot ID:** `{methodology.get('id')}`")
    if methodology_label == "legacy_partial_methodology":
        sections.append(
            "- **Legacy note:** partial methodology evidence is displayed for "
            "context only and is not complete historical scoring authority."
        )
    sections.append("")
    lab = baseline.get("lab", {})
    # RunPlan has the authoritative resolved schedule when available;
    # fall back to campaign YAML → baseline for backwards-compat (rescore.py).
    if run_plan is not None:
        eff_cycles = run_plan.cycles_per_config
        eff_reqs   = run_plan.requests_per_cycle
    else:
        eff_cycles = lab.get("cycles_per_config", 3)
        eff_reqs   = lab.get("requests_per_cycle", 6)
        if campaign:
            if "cycles_per_config" in campaign:
                eff_cycles = campaign["cycles_per_config"]
            if "requests_per_cycle" in campaign:
                eff_reqs = campaign["requests_per_cycle"]
    warm_per_cycle = eff_reqs - 1
    warm_samples = eff_cycles * warm_per_cycle
    last_cycle = eff_cycles

    if _is_custom and run_plan is not None:
        _rp = run_plan
        sections.append(
            f"**Run mode:** Custom — user-directed. "
            f"{len(_rp.selected_values)} of {len(_rp.all_campaign_values)} campaign values tested deliberately. "
            "Sparse data is intentional; results are valid for comparison within the tested subset only.\n"
        )
    elif _is_quick and run_plan is not None:
        _rp = run_plan
        _q_c = _rp.cycles_per_config
        _q_cw = "cycle" if _q_c == 1 else "cycles"
        sections.append(
            f"**Run mode:** Quick — complete value coverage, {_q_c} {_q_cw} per config. "
            f"All {len(_rp.all_campaign_values)} campaign values tested — broad but shallow. "
            "Lowest-confidence full-coverage mode; run Standard or Full for higher-confidence confirmation.\n"
        )
    elif _is_standard and run_plan is not None:
        _rp = run_plan
        sections.append(
            f"**Run mode:** Standard — complete value coverage, reduced repetition. "
            f"All {len(_rp.all_campaign_values)} campaign values tested with {_rp.cycles_per_config} cycles per config. "
            "Development-grade result; run Full for highest-confidence confirmation.\n"
        )

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
        if _is_custom:
            sections.append(
                f"> **Note:** {warm_samples} warm sample(s) per config — intentionally sparse "
                f"(Custom run). Results are statistically valid within the tested scope. "
                f"Run Full to measure all campaign values and extend coverage.\n"
            )
        elif _is_quick:
            sections.append(
                f"> **Note:** {warm_samples} warm request slot(s) per config — Quick run "
                f"({eff_cycles} cycle, broad but shallow). Lowest-confidence full-coverage result. "
                f"Run Standard or Full for higher-confidence statistics.\n"
            )
        elif _is_standard:
            sections.append(
                f"> **Note:** {warm_samples} warm sample(s) per config — Standard run "
                f"(reduced repetition). Development-grade result across all campaign values. "
                f"Run Full for higher-confidence statistics.\n"
            )
        else:
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
            is_custom=_is_custom,
            is_standard=_is_standard,
            is_quick=_is_quick,
        )
        sections.extend(ngl_lines)

    # ─── Artifact Index ───────────────────────────────────────────────────────
    # Compact index of the four formal campaign artifacts.
    # Full evidence and methodology details are in run-reports.md.
    # Missing artifacts are stated explicitly — never silently omitted.
    report_dir = find_artifact_dir(
        effective_lab_root,
        "reports",
        campaign_id,
    ) or (effective_lab_root / "results" / campaign_id)
    measurements_dir = find_artifact_dir(
        effective_lab_root,
        "measurements",
        campaign_id,
    ) or report_dir

    _raw_telemetry_jsonl = measurements_dir / FILENAME_RAW_TELEMETRY
    _run_reports_md      = report_dir / FILENAME_RUN_REPORTS
    _metadata_json       = report_dir / FILENAME_METADATA

    from src.trust_identity import load_artifact_summaries  # noqa: PLC0415
    _artifact_rows = {
        row.get("artifact_type"): row
        for row in load_artifact_summaries(campaign_id, db_path)
    }

    def _artifact_status(artifact_type: str, p: "Path") -> str:  # noqa: F821
        """Return a display label for an artifact status string."""
        row = _artifact_rows.get(artifact_type)
        if row:
            status = row.get("status") or _STR_NOT_RECORDED
            sha = row.get("sha256")
            verification = row.get("verification_source") or _STR_NOT_RECORDED
            err = row.get("error_message")
            parts = [status, f"verification={verification}"]
            if sha:
                parts.append(f"sha256={sha[:12]}")
            if err:
                parts.append(f"error={str(err)[:80]}")
            return "; ".join(parts)
        if p.exists():
            return "file_present"
        # No DB row and file absent. campaign-summary.md is written first; peer
        # artifacts may not yet exist at generation time. Use "pending" for
        # canonical types so the file does not permanently claim "not generated"
        # for artifacts that will be present moments after this report is written.
        _CANONICAL = {ARTIFACT_CAMPAIGN_SUMMARY, ARTIFACT_RUN_REPORTS,
                      ARTIFACT_METADATA, ARTIFACT_RAW_TELEMETRY}
        return "pending" if artifact_type in _CANONICAL else "not generated"

    sections.append("\n---\n")
    sections.append("## Campaign Artifacts\n")
    sections.append(
        "_This summary is one of four formal campaign artifacts. "
        "See `run-reports.md` for full evidence, methodology, and detailed rankings._\n"
    )
    sections.append("| Artifact | Path | Status |")
    sections.append("|----------|------|:------:|")
    sections.append(
        f"| Campaign Summary (this file) | `{report_dir / FILENAME_CAMPAIGN_SUMMARY}` | "
        f"{_artifact_status(ARTIFACT_CAMPAIGN_SUMMARY, report_dir / FILENAME_CAMPAIGN_SUMMARY)} |"
    )
    sections.append(
        f"| Detailed Report | `{_run_reports_md}` | {_artifact_status(ARTIFACT_RUN_REPORTS, _run_reports_md)} |"
    )
    sections.append(
        f"| Measurement Stream | `{_raw_telemetry_jsonl}` | "
        f"{_artifact_status(ARTIFACT_RAW_TELEMETRY, _raw_telemetry_jsonl)} |"
    )
    sections.append(
        f"| Provenance + Scores | `{_metadata_json}` | {_artifact_status(ARTIFACT_METADATA, _metadata_json)} |"
    )
    sections.append(
        f"| Full database | `{db_path}` | {'file_present' if db_path.exists() else 'not found'} |"
    )
    sections.append(
        "\n_Background process data, per-cycle environment quality, and ranked scores are in"
        " `run-reports.md` and `metadata.json`. Raw measurements are queryable from the"
        " `requests` and `telemetry` tables in `lab.sqlite`._\n"
    )

    return "\n".join(sections)


def _config_stats_table(
    config_id: str,
    s: dict[str, Any],
    scores_df: pd.DataFrame | None,
    ref: dict[str, Any],
) -> str:
    """Generate a compact stats table for one config.

    All metrics are rendered as '—' when None — absent data must never
    appear as '0.00' or '0 ms' in the report.
    """
    lines = []
    lines.append("| Metric | Value | vs S0-new Baseline |")
    lines.append("|--------|-------|--------------------|")

    tg     = s.get("warm_tg_median")
    tg_p10 = s.get("warm_tg_p10")
    tg_p90 = s.get("warm_tg_p90")
    n_warm = s.get("valid_warm_request_count", 0)
    cv     = s.get("warm_tg_cv")
    cv_disp = f"{cv:.4f}" if (cv is not None and n_warm >= 3) else "N/A (N<3)"

    ttft_med   = s.get("warm_ttft_median_ms")
    ttft_p90   = s.get("warm_ttft_p90_ms")
    cold_ttft  = s.get("cold_ttft_median_ms")
    pp         = s.get("pp_median")
    thermal    = s.get("thermal_events")
    outliers   = s.get("outlier_count")

    # Baseline-relative deltas — only computed when reference values exist
    # and the measured metric is present. Never fabricates a comparison.
    ref_tg   = ref.get("warm_tg_median_ts")
    ref_ttft = ref.get("warm_ttft_median_ms")
    tg_delta   = (
        f"+{(tg - ref_tg) / ref_tg * 100:.1f}%"
        if (tg is not None and ref_tg)
        else "—"
    )
    ttft_delta = (
        f"+{(ref_ttft - ttft_med) / ref_ttft * 100:.1f}%"
        if (ttft_med is not None and ref_ttft)
        else "—"
    )

    score_str = "—"
    if scores_df is not None and config_id in scores_df.index:
        score_str = f"{scores_df.loc[config_id, 'composite_score']:.4f}"

    def _m(val: float | None, fmt: str) -> str:
        """Format optional metric; return '—' for None."""
        return format(val, fmt) if val is not None else "—"

    lines.append(f"| Warm TG Median   | **{_m(tg, '.2f')} t/s** | {tg_delta} |")
    lines.append(f"| Warm TG P10      | {_m(tg_p10, '.2f')} t/s | — |")
    lines.append(f"| Warm TG P90      | {_m(tg_p90, '.2f')} t/s | — |")
    lines.append(f"| Warm TG CV       | {cv_disp} | — |")
    lines.append(f"| Warm TTFT Median | {_m(ttft_med, '.0f')} ms | {ttft_delta} |")
    lines.append(f"| Warm TTFT P90    | {_m(ttft_p90, '.0f')} ms | — |")
    lines.append(f"| Cold TTFT Median | {_m(cold_ttft, '.0f')} ms | — |")
    lines.append(f"| PP Median        | {_m(pp, '.1f')} t/s | — |")
    lines.append(f"| Thermal Events   | {thermal  if thermal  is not None else '—'} | — |")
    lines.append(f"| Outliers         | {outliers if outliers is not None else '—'} | — |")
    lines.append(f"| Composite Score  | {score_str} | — |")

    return "\n".join(lines)
