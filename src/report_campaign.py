"""
QuantMap — report_campaign.py

Campaign-level report generator following the evidence-first philosophy.

Design principles (non-negotiable):
  1. Data stands on its own — no hidden interpretation in data sections.
  2. Interpretation is always explicitly labeled and placed after its data.
  3. Every interpretive statement references the data it is derived from.
  4. Language conservatism scales with confidence level and run mode.
  5. Report structure enables both human scanning and LLM reasoning.

Section labels used throughout:
    [CONTEXT]       — campaign identity, machine, settings in effect
    [METHODOLOGY]   — test protocol, pre-committed filters/weights, scope
    [DATA]          — measured values and computed statistics only
    [INTERPRETATION]— conclusions drawn from data (always cites basis)
    [IMPLICATIONS]  — what results may mean for downstream decisions
    [LIMITATIONS]   — scope boundaries, confidence caveats, exclusions
    [WARNINGS]      — environment quality issues, data quality problems

Public API:
    generate_campaign_report(campaign_id, db_path, baseline, ...) -> Path
"""

from __future__ import annotations

import json
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.db import get_connection
from src.settings_env import optional_env_path
from src.artifact_paths import (
    ARTIFACT_RUN_REPORTS,
    find_artifact_dir,
    infer_model_identity,
    report_paths,
)

logger = logging.getLogger(__name__)

_STR_NOT_SET_IN_BASELINE = "not set in baseline"
_STR_NOT_RECORDED = "not recorded"
_STR_NOT_CAPTURED = "not captured"
_STR_NOT_IN_METHODOLOGY = "not in methodology snapshot"
_KNOWN_ASSESSMENT_CONFIDENCE = {"high", "medium", "low"}

LAB_ROOT = optional_env_path("QUANTMAP_LAB_ROOT", Path(__file__).resolve().parent.parent)


def _file_sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Semantic labels (Section 5 of Design Memo)
# ---------------------------------------------------------------------------
_L_CONT = "CONTEXT"
_L_METH = "METHODOLOGY"
_L_DATA = "DATA"
_L_INT  = "INTERPRETATION"
_L_IMP  = "IMPLICATIONS"
_L_LIM  = "LIMITATIONS"
_L_WARN = "WARNINGS"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(val: float | int | None, spec: str, missing: str = "—") -> str:
    """Format a numeric value; return `missing` when value is None."""
    if val is None:
        return missing
    try:
        return format(val, spec)
    except (TypeError, ValueError):
        return missing


def _pct(val: float | None, digits: int = 1, missing: str = "—") -> str:
    """Format a fractional value as a percentage string."""
    if val is None:
        return missing
    return f"{val:.{digits}f}%"


def _na(val: Any, missing: str = "N/A") -> str:
    """Return the value's string form, or `missing` explicitly for None.

    Use this instead of `or 0` patterns — returning 'N/A' makes absent data
    visible rather than silently replacing it with a misleading zero.
    """
    if val is None:
        return missing
    return str(val)


def _quality_label(quality: str | None) -> str:
    return {
        "clean":        "clean",
        "mostly_clean": "mostly clean",
        "noisy":        "noisy",
        "distorted":    "distorted",
    }.get(quality or "", quality or "not characterized")


def _confidence_qualifier(assessment_confidence: str | None) -> str:
    """Return a verb qualifier appropriate to the confidence level.

    High confidence → factual language ("measured", "in this sweep").
    Medium → mild hedging ("observed", "under observed conditions").
    Low → explicit uncertainty ("tentative", "limited data indicates").
    """
    return {
        "high":   "in this sweep",
        "medium": "under observed conditions",
        "low":    "tentatively (limited observation)",
    }.get(assessment_confidence or "", "under observed conditions")


# ---------------------------------------------------------------------------
# Section-end summary block
# ---------------------------------------------------------------------------

def _section_end_block(scope_prefix: str, items: dict[str, list[str]]) -> list[str]:
    """
    Build a section-end summary block containing labeled sub-sections.

    Args:
        scope_prefix: The semantic scope to identify these interpretations 
                      (e.g., "METHODOLOGY", "ENVIRONMENT", "PRIMARY_RESULTS").
        items: Ordered dict of label → bullet-point strings.
               e.g. {"INTERPRETATION": [...], "LIMITATIONS": [...]}

    Returns a list of Markdown lines. Empty label lists are omitted.
    """
    populated = {k: v for k, v in items.items() if v}
    if not populated:
        return []
    lines = ["\n---"]
    for label, bullets in populated.items():
        lines.append(f"\n##### [{scope_prefix}:{label}]")
        for b in bullets:
            lines.append(f"- {b}")
    lines.append("\n---\n")
    return lines


def _section_failure_stub(heading: str, exc: Exception) -> list[str]:
    """
    Return a minimal section replacement used when a section builder raises.

    Every major section MUST appear in the report — this stub ensures sections
    are never silently omitted when generation fails.  The stub preserves the
    section heading so the document structure remains navigable.
    """
    return [
        f"\n{heading}\n",
        f"> **[REPORT_RENDER_FAILURE] Localized Section Data Unavailable:** `{type(exc).__name__}: {exc}`",
        ">",
        "> Impact: This section could not be rendered due to an formatting or extraction error.",
        "> The underlying benchmark run completed successfully and all core data is unaffected.",
        "> Review the QuantMap log file for the traceback to identify the missing context.\n",
    ]


# ---------------------------------------------------------------------------
# Run-context JSON loading
# ---------------------------------------------------------------------------

def _load_run_contexts(results_dir: Path) -> list[dict[str, Any]]:
    """
    Load all per-cycle run_context JSON files from the campaign results directory.

    Files follow the naming convention:
        {config_id}_cycle{N:02d}_run_context.json

    Returns a list of dicts, each augmented with:
        _config_id:    str — extracted from filename
        _cycle_number: int | None — extracted from filename
        _filename:     str — original filename for traceability

    Files that fail to load or parse are silently skipped (warning logged).
    """
    contexts: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*_run_context.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_filename"] = path.name
            stem = path.stem   # e.g. "NGL_sweep__30_cycle02_run_context"
            stem = stem.removesuffix("_run_context")
            split_at = stem.rfind("_cycle")
            if split_at != -1:
                data["_config_id"]    = stem[:split_at]
                try:
                    data["_cycle_number"] = int(stem[split_at + 6:])
                except ValueError:
                    data["_cycle_number"] = None
            else:
                data["_config_id"]    = stem
                data["_cycle_number"] = None
            contexts.append(data)
        except Exception as exc:
            logger.warning("Could not load run_context file %s: %s", path, exc)
    return contexts


def _aggregate_environment(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute campaign-level environment statistics from per-cycle run_context dicts.

    Returns a summary dict used both for the environment section and for
    scaling interpretation language in other sections.
    """
    if not contexts:
        return {"available": False}

    quality_counts: dict[str, int] = {}
    completeness_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    config_confidence_counts: dict[str, dict[str, int]] = {}
    all_interferers: list[str] = []
    all_reasons: list[str] = []
    coverage_vals: list[float] = []
    failed_probe_names: set[str] = set()
    missing_cap_names: set[str] = set()
    inapplicable_cap_names: set[str] = set()

    for ctx in contexts:
        cid = ctx.get("_config_id")
        assess = ctx.get("assessment") or {}
        conf   = ctx.get("confidence") or {}

        q = assess.get("environment_quality") or "not assessed"
        quality_counts[q] = quality_counts.get(q, 0) + 1

        oc = conf.get("observation_completeness") or "not populated"
        completeness_counts[oc] = completeness_counts.get(oc, 0) + 1

        ac_raw = conf.get("assessment_confidence")
        ac = (
            ac_raw
            if isinstance(ac_raw, str) and ac_raw in _KNOWN_ASSESSMENT_CONFIDENCE
            else "not populated"
        )
        confidence_counts[ac] = confidence_counts.get(ac, 0) + 1

        if cid is not None:
            if cid not in config_confidence_counts:
                config_confidence_counts[cid] = {}
            config_confidence_counts[cid][ac] = config_confidence_counts[cid].get(ac, 0) + 1

        for cand in assess.get("interference_candidates") or []:
            name = cand.get("name") or cand.get("category")
            if name:
                all_interferers.append(name)

        all_reasons.extend(assess.get("reasons") or [])

        cov = conf.get("capability_coverage")
        if cov is not None:
            coverage_vals.append(cov)

        failed_probe_names.update(conf.get("failed_probes") or [])
        missing_cap_names.update(conf.get("missing_capabilities") or [])
        inapplicable_cap_names.update(conf.get("inapplicable_capabilities") or [])

    total = len(contexts)
    n_clean = quality_counts.get("clean", 0) + quality_counts.get("mostly_clean", 0)
    n_noisy = quality_counts.get("noisy", 0)
    n_distorted = quality_counts.get("distorted", 0)

    # Most frequent interferers (by name, ranked by appearance count)
    interferer_freq: dict[str, int] = {}
    for name in all_interferers:
        interferer_freq[name] = interferer_freq.get(name, 0) + 1
    top_interferers = sorted(interferer_freq.items(), key=lambda x: -x[1])

    # Most frequent reason codes across all cycles
    reason_freq: dict[str, int] = {}
    for r in all_reasons:
        reason_freq[r] = reason_freq.get(r, 0) + 1
    top_reasons = sorted(reason_freq.items(), key=lambda x: -x[1])

    # Overall assessment confidence: worst-case of individual cycles
    overall_confidence: str
    known_conf_total = sum(confidence_counts.get(k, 0) for k in _KNOWN_ASSESSMENT_CONFIDENCE)
    if known_conf_total == 0:
        overall_confidence = "not populated"
    elif confidence_counts.get("low", 0) > 0:
        overall_confidence = "low"
    elif confidence_counts.get("medium", 0) > known_conf_total // 2:
        overall_confidence = "medium"
    else:
        overall_confidence = "high"

    # Per-config assessment confidence: worst-case for that config's cycles
    config_confidences: dict[str, str] = {}
    for cid, counts in config_confidence_counts.items():
        known_total_cid = sum(counts.get(k, 0) for k in _KNOWN_ASSESSMENT_CONFIDENCE)
        if known_total_cid == 0:
            config_confidences[cid] = "not populated"
        elif counts.get("low", 0) > 0:
            config_confidences[cid] = "low"
        elif counts.get("medium", 0) > known_total_cid // 2:
            config_confidences[cid] = "medium"
        else:
            config_confidences[cid] = "high"

    avg_coverage = sum(coverage_vals) / len(coverage_vals) if coverage_vals else None

    return {
        "available":               True,
        "total_cycles":            total,
        "quality_counts":          quality_counts,
        "n_clean":                 n_clean,
        "n_noisy":                 n_noisy,
        "n_distorted":             n_distorted,
        "clean_pct":               n_clean / total * 100 if total else 0,
        "top_interferers":         top_interferers[:5],
        "top_reasons":             top_reasons[:8],
        "completeness_counts":     completeness_counts,
        "confidence_counts":       confidence_counts,
        "config_confidences":      config_confidences,
        "overall_confidence":      overall_confidence,
        "avg_capability_coverage": avg_coverage,
        "failed_probe_names":      sorted(failed_probe_names),
        "missing_capability_names": sorted(missing_cap_names),
        "inapplicable_capability_names": sorted(inapplicable_cap_names),
    }

# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_header(
    campaign_id: str,
    camp: dict[str, Any],
    snap: dict[str, Any],
    run_plan: Any,
    baseline: dict[str, Any],
    now: str,
    baseline_source: str | None = None,
    trust_identity: Any = None,
) -> list[str]:
    lines: list[str] = []

    lines.append(f"# QuantMap Campaign Report — {campaign_id}")
    lines.append(f"\nGenerated: {now}\n")

    if run_plan is not None:
        mode_label = getattr(run_plan, "mode_label", run_plan.run_mode.title())
        mode_desc  = getattr(run_plan, "mode_description", "")
        lines.append(f"> **Mode:** {mode_label} — {mode_desc}\n")

    lines.append("## Campaign Identity\n> Type: Context\n")

    machine  = baseline.get("machine", {})
    model_bl = baseline.get("model",   {})

    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Campaign ID | `{campaign_id}` |")
    run_mode = camp.get("run_mode") or (
        getattr(run_plan, "run_mode", None) if run_plan else None
    )
    if run_mode:
        lines.append(f"| Run mode | {run_mode} |")
    lines.append(f"| Variable swept | `{camp.get('variable', '—')}` |")
    lines.append(f"| Campaign type | {camp.get('campaign_type', '—')} |")
    lines.append(f"| Status | {camp.get('status', '—')} |")
    if camp.get("analysis_status") or camp.get("report_status"):
        lines.append(f"| Analysis status | {camp.get('analysis_status', '—')} |")
        lines.append(f"| Report status | {camp.get('report_status', '—')} |")
    lines.append(f"| Started | {camp.get('started_at', '—')} |")
    lines.append(f"| Completed | {camp.get('completed_at', '—')} |")
    lines.append(f"| Machine | {machine.get('name', '—')} |")
    lines.append(f"| CPU | {machine.get('cpu', '—')} |")
    lines.append(f"| GPU | {machine.get('gpu', snap.get('gpu_name', '—'))} |")
    lines.append(f"| RAM | {machine.get('ram', '—')} |")
    lines.append(f"| OS | {snap.get('os_version', machine.get('os', '—'))} |")
    lines.append(f"| NVIDIA Driver | {snap.get('nvidia_driver', '—')} |")
    try:
        from src.execution_environment import execution_environment_summary_lines  # noqa: PLC0415
        lines.extend(execution_environment_summary_lines(snap))
    except Exception:
        lines.append("| Execution support tier | `not assessed` |")
    try:
        from src.telemetry_provider import provider_evidence_summary_lines  # noqa: PLC0415

        lines.extend(provider_evidence_summary_lines(snap))
    except Exception:
        lines.append("| Telemetry provider evidence | `unverifiable` |")
    lines.append(f"| Model | {model_bl.get('name', '—')} |")
    lines.append(f"| Model size | {_na(model_bl.get('size_gb'))} GB |")
    lines.append(f"| Quantization | {model_bl.get('quantization', '—')} |")
    if baseline_source:
        lines.append(f"| Baseline identity source | `{baseline_source}` |")
    if trust_identity is not None:
        qid = getattr(trust_identity, "quantmap", {}) or {}
        qver = qid.get("quantmap_version") or trust_identity.sources.get("quantmap", "legacy_unrecorded")
        qcommit = qid.get("git_commit") or _STR_NOT_CAPTURED
        lines.append(f"| QuantMap identity | {qver} / `{str(qcommit)[:16]}` |")
    lines.append(f"| Power plan | {snap.get('power_plan', '—')} |")
    build_commit = snap.get("build_commit", "—")
    if len(build_commit) > 16:
        build_commit = f"`{build_commit[:16]}...`"
    lines.append(f"| Build commit | {build_commit} |")
    campaign_sha = (camp.get('campaign_sha256') or '—')
    lines.append(f"| Campaign SHA256 | `{campaign_sha[:16]}...` |")
    lines.append("")

    rationale = camp.get("rationale") or ""
    if rationale:
        lines.append(f"**Rationale:** {rationale}\n")

    return lines


def _section_methodology(
    run_plan: Any,
    baseline: dict[str, Any],
    n_tested_configs: int,
    scores_result: dict[str, Any],
    methodology: dict[str, Any] | None = None,
) -> list[str]:
    lines: list[str] = []
    from src.trust_identity import methodology_source_label  # noqa: PLC0415
    methodology = methodology or {}
    methodology_label = methodology_source_label(methodology)
    
    lines.append("> [!NOTE]")
    lines.append("> **QuantMap Governance Methodology v1.0 (Stable)**")
    lines.append("> Methodology: v1.0 (Winsorized Means + LCB + Absolute Anchors)")
    lines.append("")
    
    lines.append(f"## Test Protocol\n> Type: {_L_METH}\n")

    lab_cfg = baseline.get("lab", {})
    cycles  = (
        getattr(run_plan, "cycles_per_config", None)
        or lab_cfg.get("cycles_per_config", 5)
    )
    reqs = (
        getattr(run_plan, "requests_per_cycle", None)
        or lab_cfg.get("requests_per_cycle", 6)
    )
    warm_per_cycle = reqs - 1
    total_warm     = cycles * warm_per_cycle

    lines.append("### Protocol Parameters\n")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| Configs tested | {n_tested_configs} |")
    lines.append(f"| Cycles per config | {cycles} |")
    lines.append(f"| Requests per cycle | {reqs} (1 cold + {warm_per_cycle} warm) |")
    lines.append(f"| Warm samples per config | {total_warm} |")
    if run_plan is not None:
        all_vals  = getattr(run_plan, "all_campaign_values", [])
        sel_vals  = getattr(run_plan, "selected_values",     [])
        untested  = getattr(run_plan, "untested_values",     [])
        coverage  = getattr(run_plan, "coverage_fraction",   1.0)
        tested_str = ", ".join(str(v) for v in sel_vals)
        lines.append(f"| Tested values | {tested_str} |")
        lines.append(f"| Coverage | {len(sel_vals)} of {len(all_vals)} values ({coverage:.0%}) |")
        if untested:
            lines.append(f"| Untested values | {', '.join(str(v) for v in untested)} |")
    lines.append("")

    # Elimination filters — displayed verbatim because they are pre-committed
    lines.append("### Elimination Filters (pre-committed before data collection)\n")
    lines.append(
        "_All thresholds below were fixed prior to data collection based on the Experiment Profile. "
        "Configs failing any filter are excluded from ranking entirely._\n"
    )
    ef = (
        scores_result.get("effective_filters")
        or methodology.get("gates")
        or {}
    )

    lines.append("| Filter | Threshold | Rationale |")
    lines.append("|--------|-----------|-----------|")
    lines.append(f"| Max coefficient of variation | ≤ {ef.get('max_cv', 0.05):.0%} | Inconsistent results are not rankable |")
    lines.append(f"| Max thermal throttle events | ≤ {ef.get('max_thermal_events', 0)} | Throttled configs are not at their rated performance |")
    lines.append(f"| Max statistical outliers (symmetric) | ≤ {ef.get('max_outliers', 3)} | Excessive outliers indicate instability |")
    lines.append(f"| Max warm TTFT P90 | ≤ {ef.get('max_warm_ttft_p90_ms', 500):.0f} ms | Hard latency ceiling for interactive use |")
    lines.append(f"| Min success rate | ≥ {ef.get('min_success_rate', 0.90):.0%} | Unreliable server responses invalidate results |")
    lines.append(f"| Min warm TG P10 | ≥ {ef.get('min_warm_tg_p10', 7.0):.1f} t/s | Floor below which throughput is unusable |")
    lines.append(f"| Min valid warm samples | ≥ {ef.get('min_valid_warm_count', 3)} | Minimum for statistical validity |")
    lines.append("")
    # Scoring Profile
    profile_obj = scores_result.get("scoring_profile")
    profile_name = (
        methodology.get("profile_name")
        or getattr(profile_obj, "name", None)
        or _STR_NOT_IN_METHODOLOGY
    )
    profile_version = (
        methodology.get("profile_version")
        or getattr(profile_obj, "version", None)
        or _STR_NOT_IN_METHODOLOGY
    )
    profile_family = getattr(getattr(profile_obj, "experiment_family", None), "value", _STR_NOT_IN_METHODOLOGY)
    lines.append(
        f"**Experiment Profile:** `{profile_name}` v{profile_version} "
        f"({profile_family})  \n"
        f"**Methodology evidence:** `{methodology_label}`\n"
    )

    # Scoring weights
    lines.append("### Scoring Methodology (Lower Confidence Bound)\n")
    lines.append(
        "_Scoring uses **Winsorized Means** (10% tails) to stabilize point estimates. "
        "The composite score represents the **Lower Confidence Bound (LCB)**, penalizing configs "
        "with high performance variance across cycles. Higher LCB = more stable performance._\n"
    )
    
    # LCB Method Disclosure
    lcb_method: str
    scores_df = scores_result.get("scores_df")
    if scores_df is not None and not scores_df.empty and "lcb_method" in scores_df.columns:
        lcb_method = str(scores_df["lcb_method"].iloc[0])
    else:
        lcb_method = "not computed — minimum warm-sample threshold not met or no ranked configs"

    lines.append(f"> **LCB Computation Method:** {lcb_method}\n")
    
    sw = (
        methodology.get("weights")
        or getattr(profile_obj, "weights", {})
        or {}
    )

    lines.append("| Metric | Weight | Direction |")
    lines.append("|--------|-------:|-----------|")
    lines.append(f"| Throughput median (TG) | {sw.get('warm_tg_median', 0.35):.0%} | higher is better |")
    lines.append(f"| Throughput P10 (consistency floor) | {sw.get('warm_tg_p10', 0.20):.0%} | higher is better |")
    lines.append(f"| Warm TTFT median | {sw.get('warm_ttft_median_ms', 0.20):.0%} | lower is better |")
    lines.append(f"| Warm TTFT P90 (worst-case latency) | {sw.get('warm_ttft_p90_ms', 0.10):.0%} | lower is better |")
    lines.append(f"| Cold TTFT (server startup latency) | {sw.get('cold_ttft_median_ms', 0.10):.0%} | lower is better |")
    lines.append(f"| Prompt processing (PP) | {sw.get('pp_median', 0.05):.0%} | higher is better |")
    lines.append("")

    # Phase 4: Normalization Methodology (Anchor Governance)
    lines.append("### Normalization Methodology (Anchor Governance)\n")
    lines.append(
        "_QuantMap Governance Methodology v1.0 follows absolute fixed-reference normalization to ensure cross-campaign "
        "comparability. Scores are measured against governed hardware or baseline anchors._\n"
    )
    
    governance_snapshot = methodology.get("anchors") or scores_result.get("governance_methodology")
    if governance_snapshot:
        lines.append("| Metric | Anchor Value | Source | Provenance/Version |")
        lines.append("|--------|-------------:|:-------|:-------------------|")
        # Sort metrics for stable reporting
        for m_name in sorted(governance_snapshot.keys()):
            ref = governance_snapshot[m_name]
            val = ref.get("value")
            source = ref.get("source", "no provenance label")
            provenance = ref.get("provenance", "N/A")
            
            val_str = f"{val:.1f}" if val is not None else "BATCH-BEST"
            
            # Format source labels for clarity
            source_label = source
            if source == "baseline_yaml":
                source_label = "**BASELINE OVERRIDE**"
            elif source == "best-in-batch":
                source_label = "FALLBACK (Cohort-Relative) [!CAUTION]"
            
            lines.append(f"| {m_name.replace('_', ' ').title()} | {val_str} | {source_label} | {provenance} |")
        lines.append("")
    else:
        lines.append("> [!WARNING]")
        lines.append("> **Legacy Metadata:** No governance methodology snapshot found. Scores may be cohort-relative.\n")

    # Mode limitations
    limitations: list[str] = []
    if run_plan is not None:
        is_quick    = getattr(run_plan, "is_quick",    False)
        is_standard = getattr(run_plan, "is_standard", False)
        is_custom   = getattr(run_plan, "is_custom",   False)

        if is_quick:
            limitations.append(
                f"Quick run: {cycles} cycle per config. "
                "Broadest coverage, lowest per-config repetition. "
                "Results are directional — running Standard or Full mode would confirm "
                "rankings with higher-confidence statistics."
            )
        elif is_standard:
            limitations.append(
                f"Standard run: {cycles} cycles per config across all campaign values. "
                "Development-grade result. Running Full mode (5 cycles) would provide "
                "the highest-confidence ranking."
            )
        elif is_custom:
            sel_n   = len(getattr(run_plan, "selected_values", []))
            total_n = len(getattr(run_plan, "all_campaign_values", []))
            limitations.append(
                f"Custom run: {sel_n} of {total_n} campaign values tested ({sel_n/total_n:.0%} coverage). "
                "Rankings reflect only the tested subset. "
                "Untested values may produce different performance profiles."
            )

    implications: list[str] = [
        "Pre-committed filters and weights were fixed before data collection began. "
        "Rankings include only configs that cleared all elimination thresholds. "
        "The scoring formula above is the sole basis for composite ranking. "
        "(Basis: filter table and scoring weight table above)"
    ]
    lines.extend(_section_end_block("METHODOLOGY", {"IMPLICATIONS": implications, "LIMITATIONS": limitations}))

    return lines


def _section_recommendation(projection: dict[str, Any]) -> list[str]:
    """Render the compact ACPM recommendation projection for run-reports.md."""
    lines: list[str] = []
    lines.append("## Recommendation Authority\n> Type: INTERPRETATION + LIMITATIONS\n")
    if not projection.get("available"):
        lines.append(
            f"Recommendation authority not recorded for this campaign (`{projection.get('source', 'unknown')}`).\n"
        )
        return lines

    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Recommendation status | `{projection.get('status')}` |")
    lines.append(f"| Leading config | `{projection.get('leading_config_id') or 'none'}` |")
    recommended_config_id = projection.get("recommended_config_id")
    if recommended_config_id:
        lines.append(f"| Recommended config | `{recommended_config_id}` |")
    else:
        lines.append("| Recommended config | No ACPM recommendation issued |")
    lines.append(f"| Handoff ready | `{projection.get('handoff_ready')}` |")
    lines.append(
        f"| Caveat codes | {', '.join(projection.get('caveat_codes', [])) or 'none'} |"
    )
    if projection.get("coverage_class"):
        lines.append(f"| Coverage class | `{projection.get('coverage_class')}` |")
    if projection.get("scope_authority"):
        lines.append(f"| Scope authority | `{projection.get('scope_authority')}` |")
    if projection.get("selected_ngl_values"):
        values = ", ".join(str(v) for v in projection["selected_ngl_values"])
        lines.append(f"| Selected NGL values | {values} |")
    lines.append(f"| Source | `{projection.get('source', 'unknown')}` |")
    lines.append("")
    return lines


def _section_primary_results(
    scores_result:      dict[str, Any],
    stats:              dict[str, dict[str, Any]],
    config_variable_map: dict[str, Any],
    variable_name:      str,
    run_plan:           Any,
    env_agg:            dict[str, Any],
) -> list[str]:
    lines: list[str] = []
    lines.append("## Primary Results\n> Type: Data + Interpretation\n")

    winner          = scores_result.get("winner")
    highest_tg      = scores_result.get("highest_tg")
    pareto_frontier = scores_result.get("pareto_frontier", [])
    passing         = scores_result.get("passing",         {})
    eliminated      = scores_result.get("eliminated",      {})
    unrankable      = scores_result.get("unrankable",      {})
    scores_df       = scores_result.get("scores_df")

    n_passing = len(passing)
    n_total   = len(stats)

    def cfg_s(cid: str) -> dict[str, Any]:
        return stats.get(cid, {})

    def score_field(cid: str, field: str) -> Any:
        if scores_df is None or cid not in scores_df.index:
            return None
        return scores_df.loc[cid].get(field)

    # ── Three required views ─────────────────────────────────────────────────
    lines.append("### Three Required Views\n")
    lines.append(
        "These views provide independent perspectives on the same result set. "
        "Agreement across views strengthens evidence for a particular config. "
        "Disagreement may indicate a tradeoff worth examining, provided the performance "
        "differences exceed the observed run-to-run variability.\n"
    )

    lines.append("| View | Config | TG Median (t/s) | TTFT Median (ms) | Composite Score | Basis |")
    lines.append("|------|--------|----------------:|-----------------:|----------------:|-------|")

    # Score winner row
    if winner:
        var_val = config_variable_map.get(winner, winner)
        tg   = cfg_s(winner).get("warm_tg_median")
        ttft = cfg_s(winner).get("warm_ttft_median_ms")
        sc   = score_field(winner, "composite_score")
        lines.append(
            f"| Score winner | `{winner}` ({variable_name}={var_val}) "
            f"| {_fmt(tg, '.2f')} | {_fmt(ttft, '.0f')} | {_fmt(sc, '.3f')} "
            f"| Highest composite score ({_fmt(sc, '.3f')}) among {n_passing} passing config(s) "
            f"(based on Composite Score column) |"
        )
    else:
        lines.append(
            "| Score winner | — | — | — | — "
            "| No configs passed all pre-committed elimination filters "
            "(based on elimination filter results — see Appendix B) |"
        )

    # Highest TG row
    if highest_tg:
        is_unrank = (highest_tg in unrankable)
        unrank_note = " ⚠ **Unrankable (Evidence Only)**" if is_unrank else ""
        
        var_val = config_variable_map.get(highest_tg, highest_tg)
        tg   = cfg_s(highest_tg).get("warm_tg_median")
        ttft = cfg_s(highest_tg).get("warm_ttft_median_ms")
        sc   = score_field(highest_tg, "composite_score")
        
        if highest_tg == winner:
            lines.append(
                "| Highest raw TG | _(same as score winner)_ | — | — | — "
                "| TG leader and score leader are the same config "
                "(based on TG Median and Composite Score columns) |"
            )
        else:
            lines.append(
                f"| Highest raw TG | `{highest_tg}` ({variable_name}={var_val}){unrank_note} "
                f"| {_fmt(tg, '.2f')} | {_fmt(ttft, '.0f')} | {_fmt(sc, '.3f')} "
                f"| Highest TG median ({_fmt(tg, '.2f')} t/s) among passing configurations "
                f"(based on TG Median column) |"
            )
    else:
        lines.append("| Highest raw TG | — | — | — | — | No passing configs |")

    # Pareto row
    if pareto_frontier:
        def _brand(cid: str) -> str:
            if cid in unrankable:
                return f"`{cid}` (⚠)"
            return f"`{cid}`"
            
        frontier_display = ", ".join(_brand(c) for c in pareto_frontier[:4])
        if len(pareto_frontier) > 4:
            frontier_display += f" +{len(pareto_frontier) - 4} more"
        
        lines.append(
            f"| Pareto frontier | {frontier_display} | — | — | — "
            "| Not dominated on both TG median and TTFT median simultaneously "
            "(based on TG Median and TTFT Median columns). (⚠) = Unrankable evidence |"
        )
    else:
        lines.append("| Pareto frontier | — | — | — | — | No non-dominated configs identified |")

    lines.append("")

    # ── Compact config comparison table ──────────────────────────────────────
    lines.append("### Config Comparison\n")
    lines.append(
        "_Primary decision table. Eliminated configs are shown at the bottom. "
        "See Appendix A for full statistics._\n"
    )

    # Sort: passing by rank, then eliminated
    passing_rows:  list[tuple[int,   str]] = []
    unrankable_rows: list[tuple[str, str]] = []
    elim_rows:     list[tuple[str,   str]] = []

    unrankable = scores_result.get("unrankable", {})

    for cid in stats:
        rank = score_field(cid, "rank_overall")
        if cid in eliminated:
            elim_rows.append((eliminated[cid], cid))
        elif cid in unrankable:
            unrankable_rows.append((", ".join(unrankable[cid]), cid))
        else:
            passing_rows.append((rank if rank is not None else 999, cid))
    passing_rows.sort()
    unrankable_rows.sort()
    elim_rows.sort()

    lines.append(
        f"| Config | {variable_name} | TG Median (t/s) | TTFT Median (ms) | CV | "
        "Thermal Events | Rank | Status |"
    )
    lines.append(
        "|--------|----------|----------------:|-----------------:|----:|"
        "---------------:|-----:|--------|"
    )

    def _row(cid: str, status_str: str) -> str:
        var_val  = config_variable_map.get(cid, "—")
        s        = cfg_s(cid)
        tg       = s.get("warm_tg_median")
        ttft     = s.get("warm_ttft_median_ms")
        cv_frac  = s.get("warm_tg_cv")
        n_warm   = s.get("valid_warm_request_count", 0)
        if n_warm < 3 or cv_frac is None:
            cv_str = "N/A (N<3)"
        else:
            cv_str = f"{cv_frac * 100:.1f}%"
        thermal  = s.get("thermal_events")
        thermal_disp = str(thermal) if thermal is not None else "—"
        rank     = score_field(cid, "rank_overall")

        rank_str = _fmt(rank, "d") if rank is not None else "—"
        badge = ""
        if cid == winner:
            badge = " ★"
        elif cid == highest_tg:
            badge = " ▲"
        if cid in pareto_frontier and cid not in (winner, highest_tg):
            badge += " ◆"

        return (
            f"| `{cid}` | {var_val} "
            f"| {_fmt(tg, '.2f')} "
            f"| {_fmt(ttft, '.0f')} "
            f"| {cv_str} "
            f"| {thermal_disp} "
            f"| {rank_str}{badge} "
            f"| {status_str} |"
        )

    for _, cid in passing_rows:
        lines.append(_row(cid, "✓ passing"))

    if unrankable_rows:
        lines.append(
            "| — | — | — | — | — | — | — | _unrankable configs below_ |"
        )
        for missing, cid in unrankable_rows:
            lines.append(_row(cid, f"⚠ unrankable: missing {missing}"))

    if elim_rows:
        lines.append(
            "| — | — | — | — | — | — | — | _eliminated configs below_ |"
        )
        for reason, cid in elim_rows:
            short_reason = reason[:45] + "..." if len(reason) > 45 else reason
            lines.append(_row(cid, f"eliminated: {short_reason}"))

    lines.append("")
    lines.append(
        "_★ = score winner · ▲ = highest raw TG · ◆ = Pareto frontier · "
        "⚠ = unrankable evidence · CV = coefficient of variation (lower = more stable)_\n"
    )

    # ── Section-end block ────────────────────────────────────────────────────
    interp: list[str] = []
    lims:   list[str] = []

    mode_degrade = False
    if run_plan is not None and getattr(run_plan, "is_quick", False):
        mode_degrade = True

    if winner:
        var_val  = config_variable_map.get(winner, winner)
        tg_w     = cfg_s(winner).get("warm_tg_median")
        cv_w     = cfg_s(winner).get("warm_tg_cv")
        n_w      = cfg_s(winner).get("valid_warm_request_count", 0)
        ttft_w   = cfg_s(winner).get("warm_ttft_median_ms")
        sc_w     = score_field(winner, "composite_score")
        cv_str   = f"{cv_w*100:.1f}%" if (cv_w is not None and n_w >= 3) else "N/A (sparse data)"

        # Confidence qualifier depends on mode AND config-specific environment
        winner_env_conf = "medium"
        if env_agg.get("available"):
            config_confidences = env_agg.get("config_confidences", {})
            winner_env_conf = config_confidences.get(winner, "medium")
            
        if run_plan is not None:
            if getattr(run_plan, "is_quick", False):
                winner_env_conf = "low"
            elif getattr(run_plan, "is_standard", False) and winner_env_conf == "high":
                winner_env_conf = "medium"
                
        qualifier = _confidence_qualifier(winner_env_conf)

        interp.append(
            f"`{winner}` ({variable_name}={var_val}) produced the highest composite score "
            f"{qualifier} ({_fmt(sc_w, '.3f')}). "
            f"Throughput: {_fmt(tg_w, '.2f')} t/s, TTFT: {_fmt(ttft_w, '.0f')} ms, CV: {cv_str}. "
            f"(Basis: TG Median and Composite Score columns in Config Comparison table, "
            f"{n_passing} passing config(s) of {n_total} tested)"
        )

    if highest_tg and highest_tg != winner:
        var_val_h = config_variable_map.get(highest_tg, highest_tg)
        tg_h      = cfg_s(highest_tg).get("warm_tg_median")
        tg_w      = cfg_s(winner).get("warm_tg_median") if winner else None
        cv_h      = cfg_s(highest_tg).get("warm_tg_cv")
        n_h       = cfg_s(highest_tg).get("valid_warm_request_count", 0)
        cv_str    = f"{cv_h*100:.1f}%" if (cv_h is not None and n_h >= 3) else "N/A (sparse data)"
        diff_note = ""
        if tg_w is not None and tg_h is not None:
            diff_pct = abs(tg_h - tg_w) / tg_w * 100 if tg_w else 0
            if tg_h > tg_w:
                diff_note = f" ({diff_pct:.1f}% higher raw TG than score winner)"
            else:
                diff_note = f" ({diff_pct:.1f}% lower raw TG than score winner)"
        
        tradeoff_text = (
            "If this throughput difference exceeds the observed run-to-run variability (CV), "
            "it may represent a throughput/score tradeoff."
        ) if n_h >= 3 else "CV is mathematically unreliable at this sample size, preventing strict stability comparisons."

        interp.append(
            f"`{highest_tg}` ({variable_name}={var_val_h}) showed the highest raw throughput "
            f"({_fmt(tg_h, '.2f')} t/s){diff_note} but did not achieve the highest composite score. "
            f"CV: {cv_str}. {tradeoff_text} "
            f"(Basis: TG Median, Composite Score, and CV columns)"
        )

    if not winner and not highest_tg:
        interp.append(
            "No configs passed all elimination filters. "
            "The ranking tables above show all measured results; no config met all "
            "pre-committed quality thresholds in this sweep. "
            "(Basis: elimination filter results — see Appendix B)"
        )

    # Limitations
    if len(eliminated) > 0:
        elim_reasons = sorted(set(eliminated.values()))[:3]
        lims.append(
            f"{len(eliminated)} of {n_total} config(s) eliminated by pre-committed filters. "
            f"Common reasons: {'; '.join(elim_reasons)}. "
            f"Full detail in Appendix B."
        )
    if mode_degrade:
        lims.append(
            f"Quick run ({getattr(run_plan, 'cycles_per_config', 1)} cycle per config): "
            "results are directional. Running Standard or Full mode would confirm rankings "
            "with higher-confidence statistics."
        )
    elif run_plan is not None and getattr(run_plan, "is_standard", False):
        lims.append(
            f"Standard run ({getattr(run_plan, 'cycles_per_config', 3)} cycles per config): "
            "development-grade result. Running Full mode (5 cycles per config) would provide "
            "the highest-confidence ranking."
        )
    if env_agg.get("available") and env_agg.get("n_noisy", 0) + env_agg.get("n_distorted", 0) > 0:
        n_affected = env_agg["n_noisy"] + env_agg["n_distorted"]
        total_cyc  = env_agg["total_cycles"]
        lims.append(
            f"{n_affected} of {total_cyc} cycles ran in noisy or distorted environment conditions. "
            "Performance measurements from those cycles may reflect some background interference. "
            "See the Environment Quality section for detail."
        )

    lines.extend(_section_end_block("PRIMARY_RESULTS_SUMMARY", {"INTERPRETATION": interp, "LIMITATIONS": lims}))

    return lines


def _section_variability(
    scores_result:       dict[str, Any],
    stats:               dict[str, dict[str, Any]],
    config_variable_map: dict[str, Any],
    variable_name:       str,
) -> list[str]:
    lines: list[str] = []
    lines.append("## Variability & Reliability\n")
    lines.append(
        "_Run-to-run stability is a first-class signal. High variability means "
        "the median is less representative of typical performance._\n"
    )

    eliminated = scores_result.get("eliminated", {})
    scores_df  = scores_result.get("scores_df")

    def score_field(cid: str, field: str) -> Any:
        if scores_df is None or cid not in scores_df.index:
            return None
        return scores_df.loc[cid].get(field)

    # Sort by rank
    rows: list[tuple[int, str]] = []
    for cid in stats:
        rank = score_field(cid, "rank_overall")
        rows.append((rank if rank is not None else 999, cid))
    rows.sort()

    lines.append(
        f"| Config | {variable_name} | TG Median | TG P10 | TG P90 | CV | "
        "Outliers | Thermal Events | Success Rate |"
    )
    lines.append(
        "|--------|----------|----------:|-------:|-------:|----:|"
        "---------:|---------------:|-------------:|"
    )

    for _, cid in rows:
        s = stats.get(cid, {})
        var_val = config_variable_map.get(cid, "—")
        tg      = s.get("warm_tg_median")
        p10     = s.get("warm_tg_p10")
        p90     = s.get("warm_tg_p90")
        cv      = s.get("warm_tg_cv")
        outliers = s.get("outlier_count")
        thermal  = s.get("thermal_events")
        outliers_disp = str(outliers) if outliers is not None else "—"
        thermal_disp  = str(thermal)  if thermal  is not None else "—"
        sr       = s.get("success_rate")
        elim_marker = " ✗" if cid in eliminated else ""
        n_warm  = s.get("valid_warm_request_count", 0)
        cv_disp = f"{cv * 100:.1f}%" if (cv is not None and n_warm >= 3) else "N/A (N<3)"

        lines.append(
            f"| `{cid}`{elim_marker} | {var_val} "
            f"| {_fmt(tg, '.2f')} "
            f"| {_fmt(p10, '.2f')} "
            f"| {_fmt(p90, '.2f')} "
            f"| {cv_disp} "
            f"| {outliers_disp} "
            f"| {thermal_disp} "
            f"| {_pct(sr * 100 if sr is not None else None)} |"
        )

    lines.append("")
    lines.append("_✗ = eliminated from ranking. CV = coefficient of variation._\n")

    # Section-end interpretation
    interp: list[str] = []

    # Find highest and lowest CV among passing configs
    passing_cv = [
        (cid, stats[cid]["warm_tg_cv"])
        for cid in stats
        if cid not in eliminated 
        and stats[cid].get("warm_tg_cv") is not None
        and stats[cid].get("valid_warm_request_count", 0) >= 3
    ]
    if passing_cv:
        passing_cv.sort(key=lambda x: x[1])
        most_stable = passing_cv[0]
        least_stable = passing_cv[-1]
        ms_val = config_variable_map.get(most_stable[0], most_stable[0])
        ls_val = config_variable_map.get(least_stable[0], least_stable[0])
        if most_stable[0] != least_stable[0]:
            interp.append(
                f"Among passing configs, `{most_stable[0]}` ({variable_name}={ms_val}) showed the "
                f"lowest run-to-run variability (CV {most_stable[1]*100:.1f}%) and "
                f"`{least_stable[0]}` ({variable_name}={ls_val}) the highest "
                f"(CV {least_stable[1]*100:.1f}%). "
                f"(Basis: CV column, valid warm speed_short requests)"
            )

    # Thermal event note
    configs_with_thermal = [
        cid for cid in stats if (stats[cid].get("thermal_events") or 0) > 0
    ]
    if configs_with_thermal:
        interp.append(
            f"{len(configs_with_thermal)} config(s) recorded thermal throttle events "
            f"({', '.join(f'`{c}`' for c in configs_with_thermal[:3])}). "
            "Configs with thermal events are excluded from ranking by the pre-committed filter. "
            "(Basis: thermal_events column)"
        )

    lines.extend(_section_end_block("PRIMARY_RESULTS_VARIABILITY", {"INTERPRETATION": interp}))

    return lines


def _section_environment(
    contexts:   list[dict[str, Any]],
    env_agg:    dict[str, Any],
    stats:      dict[str, dict[str, Any]],
) -> list[str]:
    lines: list[str] = []
    lines.append("## Environment Quality\n> Type: Data + Interpretation\n")

    if not env_agg.get("available"):
        lines.append(
            "_No per-cycle environment data available. "
            "Run context files (`*_run_context.json`) were not found in the results directory. "
            "This data is captured when the harness runs with the current version of QuantMap._\n"
        )
        return lines

    total_cyc      = env_agg["total_cycles"]
    n_clean        = env_agg["n_clean"]
    n_noisy        = env_agg["n_noisy"]
    n_distorted    = env_agg["n_distorted"]
    clean_pct      = env_agg["clean_pct"]
    avg_cov        = env_agg.get("avg_capability_coverage")
    failed_names   = env_agg.get("failed_probe_names", [])
    missing_names  = env_agg.get("missing_capability_names", [])
    env_conf_overall = env_agg.get("overall_confidence", "medium")

    # Trust guidance scales with confidence and failure presence
    if env_conf_overall == "high" and not failed_names:
        trust_guidance = (
            "High — environment observations are well-supported by available signals. "
            "Assessment results reflect actual conditions."
        )
    elif env_conf_overall == "medium" or (env_conf_overall == "high" and failed_names):
        trust_guidance = (
            "Medium — some signals were unavailable or failed. "
            "Treat environment assessment as indicative, not definitive."
        )
    else:
        trust_guidance = (
            "Low — limited signals or probe failures present. "
            "Treat environment assessment as tentative."
        )

    # Environment overview (always shown when data is available)
    lines.append("### Environment Overview\n")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Overall assessment confidence | {env_conf_overall.upper()} |")
    lines.append(
        f"| Probe failures (expected but broke at runtime) | "
        f"{', '.join(failed_names) if failed_names else 'none'} |"
    )
    lines.append(
        f"| Missing capabilities (expected but inaccessible) | "
        f"{', '.join(missing_names) if missing_names else 'none'} |"
    )
    lines.append(f"| Measurement trust guidance | {trust_guidance} |")
    lines.append("")

    # Campaign-level summary
    lines.append("### Campaign-Level Environment Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Cycles with run_context data | {total_cyc} |")
    lines.append(f"| Clean / mostly clean cycles | {n_clean} ({clean_pct:.0f}%) |")
    lines.append(f"| Noisy cycles | {n_noisy} ({n_noisy/total_cyc*100:.0f}%) |")
    lines.append(f"| Distorted cycles | {n_distorted} ({n_distorted/total_cyc*100:.0f}%) |")
    lines.append(f"| Overall assessment confidence | {env_conf_overall.upper()} |")
    if avg_cov is not None:
        lines.append(f"| Average capability coverage | {avg_cov:.0%} |")
    lines.append("")

    if env_agg.get("top_interferers"):
        lines.append("**Recurring background interference (by frequency across cycles):**\n")
        lines.append("| Process / Source | Cycles Appeared |")
        lines.append("|------------------|----------------:|")
        for name, count in env_agg["top_interferers"]:
            lines.append(f"| {name} | {count} |")
        lines.append("")

    # Per-cycle detail table
    lines.append("### Per-Cycle Environment Detail\n")
    lines.append(
        "| Config | Cycle | Quality | Obs. Completeness | Confidence | Avg CPU% | Max CPU% | Reasons |"
    )
    lines.append(
        "|--------|------:|---------|:-----------------:|:----------:|---------:|---------:|---------|"
    )

    for ctx in sorted(contexts, key=lambda c: (c.get("_config_id", ""), c.get("_cycle_number", 0) or 0)):
        cid    = ctx.get("_config_id", "—")
        cycle  = ctx.get("_cycle_number")
        assess = ctx.get("assessment") or {}
        conf   = ctx.get("confidence") or {}
        summ   = ctx.get("summary")    or {}
        st     = summ.get("stats")     or {}

        quality      = _quality_label(assess.get("environment_quality"))
        completeness = (conf.get("observation_completeness") or "—").upper()
        confidence   = (conf.get("assessment_confidence")    or "—").upper()
        avg_cpu      = st.get("avg_cpu_percent")
        max_cpu      = st.get("max_cpu_percent")

        # Top reasons (2 most distinctive, skip process_data_present/minimal_warnings)
        _skip_reasons = {
            "process_data_present", "minimal_warnings", "cpu_metrics_complete",
            "memory_metrics_complete", "disk_metrics_available", "sampling_window_populated",
        }
        reasons = [r for r in (assess.get("reasons") or []) if r not in _skip_reasons]
        conf_reasons = [
            r for r in (conf.get("confidence_reasons") or [])
            if r not in _skip_reasons
            and not r.startswith("cpu_metrics_complete")
            and not r.startswith("memory_metrics_complete")
        ]
        all_notable = (reasons + conf_reasons)[:3]
        reason_str = ", ".join(all_notable) if all_notable else "—"

        lines.append(
            f"| `{cid}` | {cycle or '—'} "
            f"| {quality} "
            f"| {completeness} "
            f"| {confidence} "
            f"| {_fmt(avg_cpu, '.1f')} "
            f"| {_fmt(max_cpu, '.1f')} "
            f"| {reason_str} |"
        )

    lines.append("")

    # Probe health — distinguish failed probes from missing capabilities
    if missing_names:
        lines.append(
            f"**Missing capabilities (expected but inaccessible at runtime):** "
            f"{', '.join(missing_names)}. "
            "These probes are implemented in QuantMap but could not be read on this machine. "
            "They reduce capability coverage but do not indicate a code failure — they reflect "
            "a runtime accessibility gap (e.g., OS restrictions, absent hardware interface).\n"
        )
    if failed_names:
        lines.append(
            f"**Probe failures (expected to succeed but raised errors):** "
            f"{', '.join(failed_names)}. "
            "These probes should have worked on this platform but did not. "
            "Affected environment signals are absent or unreliable. "
            "Check QuantMap logs for probe-level error details.\n"
        )

    # ── Section-end block ────────────────────────────────────────────────────
    warnings: list[str] = []
    implications: list[str] = []
    limits: list[str] = []

    if n_distorted > 0:
        warnings.append(
            f"{n_distorted} cycle(s) were classified as **distorted** — significant background interference "
            "was detected during those cycles. Performance measurements from distorted cycles carry "
            "materially higher uncertainty. Distorted-cycle measurements warrant additional scrutiny "
            "if they contributed substantially to config statistics."
        )
    if n_noisy > 0:
        warnings.append(
            f"{n_noisy} cycle(s) were classified as **noisy** — detectable background activity was "
            "present. This does not invalidate results but adds measured uncertainty to those cycles."
        )

    # env_conf_overall already assigned above when building the Overview block
    if env_conf_overall == "high" and n_clean == total_cyc and not failed_names:
        implications.append(
            "All observed cycles ran in clean or mostly-clean environment conditions with high "
            "assessment confidence. Environment noise is unlikely to be a material factor in "
            "differentiating config performance. (Basis: environment quality table above)"
        )
    elif env_conf_overall in ("high", "medium") and n_clean >= total_cyc * 0.75:
        implications.append(
            f"{n_clean} of {total_cyc} cycles ran in clean or mostly-clean conditions. "
            "Environment is likely not a material confounder for most configs, but some cycles "
            "may carry modest additional uncertainty. (Basis: per-cycle quality table above)"
        )
    else:
        implications.append(
            f"Environment conditions were mixed ({n_clean} clean, {n_noisy} noisy, "
            f"{n_distorted} distorted of {total_cyc} cycles). "
            "Readers should cross-reference configs showing high variability (CV) against the per-cycle "
            "environment detail to see if their runs overlapped with noisy or distorted conditions. "
            "Mixed environmental conditions may limit confidence in the interpretation of relative rankings. "
            "(Basis: per-cycle environment quality and variability tables)"
        )

    if avg_cov is not None and avg_cov < 0.70:
        limits.append(
            f"Average capability coverage was {avg_cov:.0%}. "
            "More than 30% of expected probes were missing due to misconfiguration or failure. "
            "The environment quality assessment relies on a significantly degraded signal set."
        )
    if failed_names:
        limits.append(
            f"One or more probes failed at runtime: {', '.join(failed_names)}. "
            "Affected environment metrics are absent. "
            "The quality assessment above may have missed signals that could affect the result tier."
        )

    lines.extend(_section_end_block("ENVIRONMENT", {
        "WARNINGS":     warnings,
        "IMPLICATIONS": implications,
        "LIMITATIONS":  limits,
    }))

    return lines


def _section_concerns_and_warnings(
    env_agg:          dict[str, Any],
    scores_result:    dict[str, Any] | None,
    section_failures: list[tuple[str, str]],
    contexts:         list[dict[str, Any]],
    run_plan:         Any,
) -> list[str]:
    """
    Aggregate all concerns into a single section at the end of the report.

    Items are sorted into High / Moderate / Low severity buckets so readers
    can triage quickly. Every item cites the source data that triggered it.
    """
    lines: list[str] = []
    lines.append("## Aggregated Concerns & Warnings\n> Type: Diagnostics + Limitations\n")
    lines.append(
        "_All quality concerns identified during this campaign are consolidated here. "
        "Items are grouped by estimated impact on result reliability. "
        "If no items appear under a severity level, none were identified for this campaign._\n"
    )

    high:     list[str] = []
    moderate: list[str] = []
    low:      list[str] = []

    # ── Section rendering failures (High — report completeness is compromised) ─
    _label_map = {
        "methodology":     "[METHODOLOGY] Test Protocol",
        "primary_results": "[DATA] Primary Results",
        "variability":     "[DATA] Variability & Reliability",
        "environment":     "[DATA] Environment Quality",
        "appendix_a":      "Appendix A (Full Config Statistics)",
        "appendix_b":      "Appendix B (Elimination Details)",
        "appendix_c":      "Appendix C (Production Commands)",
    }
    for name, err in section_failures:
        label = _label_map.get(name, name)
        high.append(
            f"**Section rendering failure — {label}:** `{err}`. "
            "This section was replaced with a failure stub. Check logs for the full traceback."
        )

    # ── Probe failures (High — probes expected to work did not) ────────────────
    failed_names = env_agg.get("failed_probe_names", []) if env_agg.get("available") else []
    if failed_names:
        high.append(
            f"**Probe failures detected:** {', '.join(failed_names)}. "
            "These probes were expected to succeed on this platform but raised errors at runtime. "
            "Affected environment signals are absent or unreliable. "
            "Check QuantMap logs for probe-level error messages."
        )

    # ── Distorted environment cycles (High) ────────────────────────────────────
    n_distorted  = env_agg.get("n_distorted",   0) if env_agg.get("available") else 0
    total_cyc    = env_agg.get("total_cycles",  1) if env_agg.get("available") else 1
    if n_distorted > 0:
        high.append(
            f"**Distorted environment: {n_distorted} of {total_cyc} cycle(s).** "
            "Significant background interference was detected during those cycles. "
            "Performance measurements from distorted cycles carry materially higher uncertainty. "
            "Rerunning affected configs under controlled conditions would improve "
            "confidence in those measurements. "
            "(Basis: quality column in per-cycle environment table)"
        )

    # ── Overall low assessment confidence (Moderate) ───────────────────────────
    overall_conf = (
        env_agg.get("overall_confidence", "high") if env_agg.get("available") else None
    )
    if overall_conf == "low":
        moderate.append(
            "**Overall assessment confidence is LOW.** "
            "Limited environment signals were available for one or more cycles. "
            "Environment quality assessments should be treated as tentative. "
            "(Basis: confidence column in per-cycle environment table)"
        )

    # ── Noisy cycles (Moderate if ≥ 30 % of cycles, Low otherwise) ────────────
    n_noisy = env_agg.get("n_noisy", 0) if env_agg.get("available") else 0
    if n_noisy > 0:
        noisy_pct = n_noisy / total_cyc * 100
        bucket = moderate if noisy_pct >= 30 else low
        bucket.append(
            f"**Noisy environment: {n_noisy} of {total_cyc} cycle(s) ({noisy_pct:.0f}%).** "
            "Detectable background activity was present. "
            "This adds measured uncertainty but does not invalidate results. "
            "See Environment Quality section for per-cycle detail."
        )

    # ── Low capability coverage (Moderate) ────────────────────────────────────
    avg_cov = env_agg.get("avg_capability_coverage") if env_agg.get("available") else None
    if avg_cov is not None and avg_cov < 0.70:
        moderate.append(
            f"**Capability coverage below threshold: {avg_cov:.0%} average.** "
            "More than 30% of expected environment probes were missing due to misconfiguration or active software failure. "
            "The environment quality assessment is based on a significantly degraded set of signals."
        )
    # ── Missing expected capabilities (Low/Moderate) ───────────────────────────
    missing_names = (
        env_agg.get("missing_capabilities", []) if env_agg.get("available") else []
    )
    if missing_names:
        low.append(
            f"**Expected signals missing:** "
            f"{', '.join(missing_names)}. "
            "These probes experienced missing dependencies or misconfiguration in the OS. "
            "They are not probe software crashes, but reflect a runtime accessibility gap that reduced coverage."
        )

    # ── Inapplicable capabilities (Low) ────────────────────────────────────────
    inapplicable_names = (
        env_agg.get("inapplicable_capabilities", []) if env_agg.get("available") else []
    )
    if inapplicable_names:
        low.append(
            f"**Inapplicable telemetry gracefully absent:** "
            f"{', '.join(inapplicable_names)}. "
            "The system accurately detected that this hardware/config does not support or use these traces. "
            "No action required."
        )

    # ── Quick / Standard mode limitations (Low) ────────────────────────────────
    if run_plan is not None:
        if getattr(run_plan, "is_quick", False):
            cycles = getattr(run_plan, "cycles_per_config", 1)
            low.append(
                f"**Quick run mode ({cycles} cycle per config):** "
                "Results are directional. "
                "Running Standard or Full mode would confirm rankings with "
                "higher-confidence statistics."
            )
        elif getattr(run_plan, "is_standard", False):
            cycles = getattr(run_plan, "cycles_per_config", 3)
            low.append(
                f"**Standard run mode ({cycles} cycles per config):** "
                "Development-grade result. "
                "Running Full mode (5 cycles per config) would provide the "
                "highest-confidence ranking."
            )

    # ── Untested values (Low) ─────────────────────────────────────────────────
    if run_plan is not None:
        untested = getattr(run_plan, "untested_values", [])
        if untested:
            untested_display = ", ".join(str(v) for v in untested[:5])
            if len(untested) > 5:
                untested_display += f" +{len(untested) - 5} more"
            low.append(
                f"**{len(untested)} value(s) not tested in this campaign:** "
                f"{untested_display}. "
                "Rankings reflect only the tested subset. "
                "The optimal value may lie among those not included in this sweep."
            )

    # ── No environment data at all (Low) ──────────────────────────────────────
    if not env_agg.get("available"):
        low.append(
            "**No per-cycle environment data available.** "
            "Run context files (`*_run_context.json`) were not found in the results directory. "
            "Environment quality, probe health, and observation confidence cannot be reported. "
            "This data is captured automatically when the current version of QuantMap is used."
        )

    # ── Render ────────────────────────────────────────────────────────────────
    lines.append("### High Severity\n")
    if high:
        for item in high:
            lines.append(f"- {item}")
    else:
        lines.append("_No high-severity concerns identified._")
    lines.append("")

    lines.append("### Moderate Severity\n")
    if moderate:
        for item in moderate:
            lines.append(f"- {item}")
    else:
        lines.append("_No moderate-severity concerns identified._")
    lines.append("")

    lines.append("### Low Severity\n")
    if low:
        for item in low:
            lines.append(f"- {item}")
    else:
        lines.append("_No low-severity concerns identified._")
    lines.append("")

    return lines


def _appendix_full_stats(
    stats:               dict[str, dict[str, Any]],
    scores_result:       dict[str, Any],
    config_variable_map: dict[str, Any],
    variable_name:       str,
) -> list[str]:
    lines: list[str] = []
    lines.append("## Appendix A: Full Configuration Statistics\n")
    lines.append(
        "This appendix provides exhaustive per-config statistics for all tested configs. "
        "Use this section for detailed metric verification, as the primary report body relies on a compact summary view.\n"
    )

    eliminated = scores_result.get("eliminated", {})
    unrankable = scores_result.get("unrankable", {})
    scores_df  = scores_result.get("scores_df")

    def score_field(cid: str, field: str) -> Any:
        if scores_df is None or cid not in scores_df.index:
            return None
        return scores_df.loc[cid].get(field)

    rows: list[tuple[int, str]] = []
    for cid in stats:
        rank = score_field(cid, "rank_overall")
        rows.append((rank if rank is not None else 999, cid))
    rows.sort()

    lines.append(
        f"| Config | {variable_name} | TG Med | TG P10 | TG P90 | CV | "
        "TTFT Med | TTFT P90 | Cold TTFT | PP Med | Outliers | Thermal | Samples | Score | Rank |"
    )
    lines.append(
        "|--------|----------|-------:|-------:|-------:|----:|"
        "---------:|---------:|----------:|-------:|---------:|--------:|--------:|------:|-----:|"
    )

    for _, cid in rows:
        s       = stats.get(cid, {})
        var_val = config_variable_map.get(cid, "—")
        sc      = score_field(cid, "composite_score")
        rank    = score_field(cid, "rank_overall")
        n_warm  = s.get("valid_warm_request_count", 0)

        elim = ""
        if cid in eliminated:
            elim = "✗ "
        elif cid in unrankable:
            elim = "⚠ "
        cv_frac = s.get("warm_tg_cv")
        cv_disp = f"{cv_frac * 100:.1f}%" if (cv_frac is not None and n_warm >= 3) else "N/A"
        
        lines.append(
            f"| {elim}`{cid}` | {var_val} "
            f"| {_fmt(s.get('warm_tg_median'), '.2f')} "
            f"| {_fmt(s.get('warm_tg_p10'),    '.2f')} "
            f"| {_fmt(s.get('warm_tg_p90'),    '.2f')} "
            f"| {cv_disp} "
            f"| {_fmt(s.get('warm_ttft_median_ms'),  '.0f')} "
            f"| {_fmt(s.get('warm_ttft_p90_ms'),     '.0f')} "
            f"| {_fmt(s.get('cold_ttft_median_ms'),  '.0f')} "
            f"| {_fmt(s.get('pp_median'),             '.1f')} "
            f"| {str(s.get('outlier_count')) if s.get('outlier_count') is not None else '—'} "
            f"| {str(s.get('thermal_events')) if s.get('thermal_events') is not None else '—'} "
            f"| {str(s.get('valid_warm_request_count')) if s.get('valid_warm_request_count') is not None else '—'} "
            f"| {_fmt(sc,   '.3f')} "
            f"| {_fmt(rank, 'd')} |"
        )

    lines.append("")
    lines.append(
        "_✗ = eliminated. ⚠ = unrankable. TG = generation throughput (t/s). TTFT = time to first token (ms). "
        "PP = prompt processing throughput (t/s). CV = coefficient of variation._\n"
    )
    return lines


def _appendix_eliminations(
    scores_result:       dict[str, Any],
    config_variable_map: dict[str, Any],
    variable_name:       str,
) -> list[str]:
    lines: list[str] = []
    lines.append("## Appendix B: Elimination & Forensic Exclusions\n")

    eliminated = scores_result.get("eliminated", {})
    unrankable = scores_result.get("unrankable", {})

    if not eliminated and not unrankable:
        lines.append("_No configs were eliminated or unrankable — all passed the pre-committed filters._\n")
        return lines

    if eliminated:
        lines.append("### Eliminated Configurations\n")
        lines.append(
            "This section details configurations that failed one or more pre-committed elimination filters. "
            "These configurations are categorically excluded from primary rankings. The specific threshold violation that triggered elimination is shown below.\n"
        )
        lines.append(f"| Config | {variable_name} | Elimination Reason |")
        lines.append("|--------|----------|--------------------|")
        for cid, reason in sorted(eliminated.items()):
            var_val = config_variable_map.get(cid, "—")
            lines.append(f"| `{cid}` | {var_val} | {reason} |")
        lines.append("")

    # Forensic Exclusions: Degraded (Severity B) and NaN-Invalid (Hard NaN Guard)
    # These were previously hidden or mixed with filters.
    collapsed = scores_result.get("collapsed_dimensions", [])
    nan_invalid = scores_result.get("nan_invalid_ids", [])
    
    degraded = {cid: s.get("elimination_reason") for cid, s in scores_result.get("stats", {}).items() if s.get("config_status") == "degraded"}
    high_nan_warns = scores_result.get("high_nan_warnings", [])

    if collapsed or high_nan_warns or nan_invalid or degraded:
        lines.append("### Forensic Exclusions & Sensor Collapse\n")
        lines.append(
            "This section details configurations and dimensions that were excluded for truth-integrity reasons "
            "rather than policy filters. These exclusions indicate that the underlying measurements were either "
            "physically impossible to collect (OOM/Degraded) or mathematically invalid for comparison (NaNs).\n"
        )
        
        if collapsed:
            lines.append("#### [WARNING] Sensor Collapse Detected\n")
            lines.append(
                "> **The following scoring dimensions were truth-invalidated across the entire campaign.** "
                "These dimensions produced 100% NaN rates across a valid sample size and were automatically dropped "
                "from the composite solver to prevent ranking corruption:\n"
            )
            for dim in collapsed:
                lines.append(f"- `{dim}`")
            lines.append("")

        if high_nan_warns:
            lines.append("#### [DIAGNOSTIC] High NaN Rate Dimensions\n")
            lines.append(
                "> **The following dimensions exceeded the noise threshold (>50% NaN) but were not fully collapsed.** "
                "These dimensions are still active in the solver, but their information density is low. "
                "Ranking results for these specific metrics should be treated as directional only:\n"
            )
            for dim in high_nan_warns:
                lines.append(f"- `{dim}`")
            lines.append("")

        if nan_invalid or degraded:
            lines.append("#### Excluded Configurations (Truth-Invalidated)\n")
            lines.append(
                "Configurations listed below are **truth-invalidated**. They may have completed cycles, but the "
                "resulting data was either fundamentally missing required metrics (Hard NaN Guard) or marked as "
                "degraded by the instrumentation system (Severity B).\n"
            )
            lines.append(
                "> NOTE: These configs are excluded from all rankings (Winner, Highest TG, Pareto). "
                "Any raw performance observation is provided for diagnostic context only and does not "
                "imply ranking eligibility.\n"
            )
            lines.append(f"| Config | {variable_name} | Exclusion Reason | Basis |")
            lines.append("|--------|----------|------------------|-------|")
            
            # Combine for sorting
            all_exclusions: list[tuple[str, str, str]] = []
            for cid in nan_invalid:
                all_exclusions.append((cid, "composite_nan_exclusion", "Hard NaN Guard (incomplete metric set)"))
            for cid, reason in degraded.items():
                # Use the structured reason from the DB
                all_exclusions.append((cid, "instrumentation_degraded", reason or "degraded"))
                
            for cid, category, reason in sorted(all_exclusions):
                var_val = config_variable_map.get(cid, "—")
                lines.append(f"| `{cid}` | {var_val} | {category} | {reason} |")
            lines.append("")

    return lines


def _appendix_historical_configs(
    scores_result:       dict[str, Any],
    config_variable_map: dict[str, Any],
    variable_name:       str,
) -> list[str]:
    """
    Render Appendix D for configurations found in the DB but missing from the current YAML.
    """
    abandoned = scores_result.get("abandoned", [])
    if not abandoned:
        return []

    lines: list[str] = []
    lines.append("## Appendix D: Historical & Abandoned Configs\n")
    lines.append(
        "The configurations listed below were found in the database for this campaign ID but are missing from the "
        "currently active YAML definition. They are preserved here for forensics and auditability but are "
        "excluded from primary rankings and Pareto evaluations.\n"
    )

    lines.append(f"| Config ID | {variable_name} | Observed Status | Last Reason |")
    lines.append("|:---|:---|:---|:---|")

    stats = scores_result.get("stats", {})
    for cid in sorted(abandoned):
        var_val = config_variable_map.get(cid, "—")
        cfg_stats = stats.get(cid, {})
        status = cfg_stats.get("config_status", "abandoned")
        reason = cfg_stats.get("elimination_reason", "n/a")
        lines.append(f"| `{cid}` | {var_val} | {status} | {reason} |")

    lines.append("")
    return lines



# ---------------------------------------------------------------------------
# Background Process Activity — computation layer
# ---------------------------------------------------------------------------

# Known background interferer categories with their name substrings.
# Checked case-insensitively against process names in all_notable_procs_json.
# Extend this list to add new categories — do NOT use heuristics, only explicit names.
_KNOWN_INTERFERERS: list[tuple[str, list[str]]] = [
    ("Windows Defender",     ["msmpeng", "mpcmdrun", "mpdefendsandbox"]),
    ("Windows Update",       ["tiworker", "wuauclt", "wudfhost", "usoclient"]),
    ("Search Indexer",       ["searchindexer", "searchhost", "searchprotocolhost"]),
    ("Browser (Chrome)",     ["chrome"]),
    ("Browser (Edge)",       ["msedge"]),
    ("Browser (Firefox)",    ["firefox"]),
    ("Steam / Game Client",  ["steam", "epicgameslauncher", "gameoverlayui"]),
    ("Discord / Chat",       ["discord", "slack", "teams"]),
    ("OneDrive / Cloud",     ["onedrive", "googledrivefs", "dropbox"]),
    ("NVIDIA Container",     ["nvcontainer", "nvspcaps", "nvidia web helper"]),
]

# SUMMARY SIGNIFICANCE RULES — explicit, deterministic, v1
#
# Rule R1: Top CPU consumers  — top 5 unique process names by peak_cpu_pct
#          Source: all_notable_procs_json across all snapshots
# Rule R2: Top RAM consumers  — top 5 unique process names by peak_rss_mb
#          Source: all_notable_procs_json; llama-server PID excluded
# Rule R3: Notable CPU spikes — any process with cpu_pct >= 5% in any snapshot
#          Threshold: 5% (conservative — avoids missing short-lived interference)
# Rule R4: Known interferers  — checked against _KNOWN_INTERFERERS list above
#          Reported with presence fraction and peak CPU; absence stated explicitly
# Rule R5: Hardware spikes    — from telemetry table
#          cpu_temp_c >= 90°C OR gpu_temp_c >= 80°C OR power_limit_throttling=1
#
# CAPTURE BOUNDARY (NOT a significance rule):
#   Processes with cpu_pct <= 0.5% AND rss_mb <= 50 MB are NOT captured.
#   This is a collection-time boundary documented in telemetry.py.

_CPU_SPIKE_THRESHOLD_PCT: float = 5.0   # R3
_HW_CPU_TEMP_SPIKE_C: float = 90.0      # R5
_HW_GPU_TEMP_SPIKE_C: float = 80.0      # R5


def _compute_background_interference(
    campaign_id: str,
    db_path: Path,
) -> dict[str, Any]:
    """
    Derive background interference summary from background_snapshots DB records.

    This function applies the explicit significance rules defined above (R1–R5).
    It never modifies or discards stored data — it is a pure read layer.

    Returns a structured dict ready for _section_background_interference().
    Returns {"available": False, "reason": str} if no snapshot data exists.
    """
    try:
        with get_connection(db_path) as conn:
            # R1: Aggregate process activity from snapshots
            # Rule A: Join with cycles to include only data from verified-complete cycles.
            # This naturally excludes legacy NULL cycle_id rows.
            rows = conn.execute(
                "SELECT bs.timestamp, bs.all_notable_procs_json, bs.gpu_proc_vram_json, "
                "       bs.defender_process_running, bs.windows_update_active, "
                "       bs.search_indexer_active, bs.antivirus_scan_active, "
                "       bs.high_cpu_process_count "
                "FROM background_snapshots bs "
                "INNER JOIN cycles c ON bs.cycle_id = c.id "
                "WHERE bs.campaign_id=? AND c.status='complete' "
                "ORDER BY bs.timestamp",
                (campaign_id,),
            ).fetchall()

            # Hardware spikes from telemetry table (R5)
            # Filtered to completed cycles for consistency with Rule A.
            hw_rows = conn.execute(
                "SELECT t.timestamp, t.cpu_temp_c, t.gpu_temp_c, t.power_limit_throttling "
                "FROM telemetry t "
                "INNER JOIN cycles c ON t.cycle_id = c.id "
                "WHERE t.campaign_id=? AND c.status='complete' "
                "ORDER BY t.timestamp",
                (campaign_id,),
            ).fetchall()

            # Get llama-server PID(s) to exclude from RAM rankings
            server_pids: set[int] = set()
            pid_rows = conn.execute(
                "SELECT DISTINCT server_pid FROM telemetry "
                "WHERE campaign_id=? AND server_pid IS NOT NULL",
                (campaign_id,),
            ).fetchall()
            for pr in pid_rows:
                if pr["server_pid"]:
                    server_pids.add(int(pr["server_pid"]))

    except Exception as exc:
        logger.warning("_compute_background_interference: DB query failed: %s", exc)
        return {"available": False, "reason": f"DB query failed: {exc}"}

    if not rows:
        return {"available": False, "reason": "No background_snapshots records found for this campaign."}

    total_snapshots = len(rows)

    # Aggregate per-process stats across all snapshots
    # peak_cpu[name] = max cpu_pct seen in any snapshot
    # peak_rss[name] = max rss_mb seen in any snapshot
    # presence[name] = count of snapshots where process appeared
    peak_cpu:  dict[str, float] = {}
    peak_rss:  dict[str, float] = {}
    presence:  dict[str, int]   = {}
    # Spike events: list of {timestamp, name, cpu_pct} for R3
    spike_events: list[dict[str, Any]] = []

    # Named flag counts (for R4 supplement)
    defender_snapshots = 0
    update_snapshots   = 0
    indexer_snapshots  = 0
    avscan_snapshots   = 0
    total_high_cpu_proc_count = 0
    total_tracked_rss_mb = 0.0
    total_tracked_cpu_pct = 0.0

    for row in rows:
        if row["defender_process_running"]:
            defender_snapshots += 1
        if row["windows_update_active"]:
            update_snapshots += 1
        if row["search_indexer_active"]:
            indexer_snapshots += 1
        if row["antivirus_scan_active"]:
            avscan_snapshots += 1
        total_high_cpu_proc_count += row["high_cpu_process_count"] or 0

        try:
            procs: list[dict] = json.loads(row["all_notable_procs_json"] or "[]")
        except (ValueError, TypeError):
            procs = []

        # Option 6: Per-snapshot aggregation by name
        snapshot_by_name_cpu: dict[str, float] = {}
        snapshot_by_name_rss: dict[str, float] = {}
        snapshot_cpu_total = 0.0
        snapshot_rss_total = 0.0

        # Exclusion logic: llama-server is the test subject, not background interference.
        _SERVER_NAME_SUBSTRINGS = {"llama-server", "llama_server", "llama.server"}

        for p in procs:
            name = p.get("name") or "[unlabeled]"
            
            # Exclude server from all background logic
            if any(sub in name.lower() for sub in _SERVER_NAME_SUBSTRINGS):
                continue
                
            cpu = p.get("cpu_pct") or 0.0
            rss = p.get("rss_mb") or 0.0

            snapshot_by_name_cpu[name] = snapshot_by_name_cpu.get(name, 0.0) + cpu
            snapshot_by_name_rss[name] = snapshot_by_name_rss.get(name, 0.0) + rss
            snapshot_cpu_total += cpu
            snapshot_rss_total += rss

        # Update global peaks from aggregated snapshot data
        for name, cpu in snapshot_by_name_cpu.items():
            if cpu > peak_cpu.get(name, 0.0):
                peak_cpu[name] = cpu
            
            presence[name] = presence.get(name, 0) + 1
            
            if cpu >= _CPU_SPIKE_THRESHOLD_PCT:
                spike_events.append({
                    "timestamp": row["timestamp"],
                    "name":      name,
                    "cpu_pct":   cpu,
                })

        for name, rss in snapshot_by_name_rss.items():
            if rss > peak_rss.get(name, 0.0):
                peak_rss[name] = rss

        if snapshot_cpu_total > total_tracked_cpu_pct:
            total_tracked_cpu_pct = snapshot_cpu_total
        if snapshot_rss_total > total_tracked_rss_mb:
            total_tracked_rss_mb = snapshot_rss_total

    # R1: Top 5 CPU consumers by peak (all processes)
    top_cpu = [
        {"name": n, "peak_cpu_pct": v, "snapshots": presence.get(n, 0)}
        for n, v in sorted(peak_cpu.items(), key=lambda item: -item[1])[:5]
    ]

    # R2: Top 5 RAM consumers by peak
    # (llama-server already excluded in collection loop)
    top_ram = [
        {"name": n, "peak_rss_mb": v, "snapshots": presence.get(n, 0)}
        for n, v in sorted(peak_rss.items(), key=lambda item: -item[1])[:5]
    ]

    # Aggregate RAM pressure from captured processes (excluding llama-server)
    # This surfaces "death by a thousand cuts" — many mid-sized processes together
    # representing significant total load even when no single one is dominant.
    # Computed dynamically per-snapshot above (total_tracked_rss_mb).

    # R3: Deduplicate spike events — keep highest CPU value per process
    spike_by_name: dict[str, dict] = {}
    for ev in spike_events:
        name = ev["name"]
        if name not in spike_by_name or ev["cpu_pct"] > spike_by_name[name]["cpu_pct"]:
            spike_by_name[name] = ev
    notable_spikes = sorted(spike_by_name.values(), key=lambda x: -x["cpu_pct"])

    # R4: Known interferers — check each category against peak_cpu / presence
    known_interferer_results: list[dict[str, Any]] = []
    for category, substrings in _KNOWN_INTERFERERS:
        matched_names = [
            n for n in peak_cpu
            if any(s in n.lower() for s in substrings)
        ]
        detected = len(matched_names) > 0
        entry: dict[str, Any] = {
            "category":      category,
            "detected":      detected,
            "process_names": matched_names,
        }
        if detected:
            entry["peak_cpu_pct"] = max(peak_cpu[n] for n in matched_names)
            entry["snapshots_present"] = max(presence.get(n, 0) for n in matched_names)
            entry["presence_pct"] = round(
                entry["snapshots_present"] / total_snapshots * 100, 1
            )
        known_interferer_results.append(entry)

    # R5: Hardware spikes from telemetry
    hw_cpu_spikes = 0
    hw_gpu_spikes = 0
    hw_throttle_events = 0
    hw_max_cpu_temp: float | None = None
    hw_max_gpu_temp: float | None = None

    for hr in hw_rows:
        cpu_t = hr["cpu_temp_c"]
        gpu_t = hr["gpu_temp_c"]
        throttle = hr["power_limit_throttling"]
        if cpu_t is not None:
            if hw_max_cpu_temp is None or cpu_t > hw_max_cpu_temp:
                hw_max_cpu_temp = cpu_t
            if cpu_t >= _HW_CPU_TEMP_SPIKE_C:
                hw_cpu_spikes += 1
        if gpu_t is not None:
            if hw_max_gpu_temp is None or gpu_t > hw_max_gpu_temp:
                hw_max_gpu_temp = gpu_t
            if gpu_t >= _HW_GPU_TEMP_SPIKE_C:
                hw_gpu_spikes += 1
        if throttle:
            hw_throttle_events += 1

    # VRAM data availability flag
    vram_available = any(
        row["gpu_proc_vram_json"] is not None for row in rows
    )

    return {
        "available":             True,
        "total_snapshots":       total_snapshots,
        "top_cpu":               top_cpu,
        "top_ram":               top_ram,
        "total_tracked_rss_mb":  round(total_tracked_rss_mb, 1),
        "total_tracked_cpu_pct": round(total_tracked_cpu_pct, 1),
        "notable_spikes":        notable_spikes,
        "known_interferers":     known_interferer_results,
        "defender_snapshots":    defender_snapshots,
        "update_snapshots":      update_snapshots,
        "indexer_snapshots":     indexer_snapshots,
        "avscan_snapshots":      avscan_snapshots,
        "hw_max_cpu_temp":       hw_max_cpu_temp,
        "hw_max_gpu_temp":       hw_max_gpu_temp,
        "hw_cpu_spike_samples":  hw_cpu_spikes,
        "hw_gpu_spike_samples":  hw_gpu_spikes,
        "hw_throttle_events":    hw_throttle_events,
        "vram_tracking_available": vram_available,
        # Aggregate interference level (LOW / MODERATE / HIGH) for quick triage.
        # Rules: HIGH if any spike >= CPU_SPIKE_THRESHOLD; MODERATE if any known
        # interferer detected; LOW if neither; NONE if no processes flagged.
        "aggregate_level": (
            "HIGH"     if notable_spikes else
            "MODERATE" if any(r["detected"] for r in known_interferer_results) else
            "LOW"      if any(v > 0 for v in peak_cpu.values()) else
            "NONE"
        ),
    }


def _section_background_interference(
    bg: dict[str, Any],
    results_dir: Path,
    campaign_id: str,
) -> list[str]:
    """
    Render the ## Background Process Activity section.

    This is a top-level section, not a subsection of Environment.
    All content is derived from _compute_background_interference().
    Significance rules R1–R5 are applied in the computation layer;
    this function only renders the result.
    """
    lines: list[str] = []
    lines.append("## Background Process Activity\n> Type: Data\n")

    if not bg.get("available"):
        reason = bg.get("reason", "No background snapshot data found.")
        lines.append(
            f"_No background process data available for this campaign. {reason}_\n"
            "\n"
            "_Background snapshots are collected every 10 seconds during campaign runs. "
            "If this section is empty, the campaign may have been run with an older version "
            "of QuantMap that did not collect this data, or the database was not accessible._\n"
        )
        return lines

    total_snap  = bg["total_snapshots"]
    agg_level   = bg["aggregate_level"]
    agg_emoji   = {"HIGH": "🔴", "MODERATE": "🟡", "LOW": "🟢", "NONE": "✅"}.get(agg_level, "")

    lines.append(
        f"> **Observed interference level:** {agg_emoji} **{agg_level}** "
        f"({total_snap} snapshots across campaign)\n"
    )
    lines.append(
        f"> **Peak concurrent pressure:** "
        f"**{bg['total_tracked_cpu_pct']:.1f}% CPU** | "
        f"**{bg['total_tracked_rss_mb']:.0f} MB RAM**\n"
    )
    lines.append(
        "_Process data is captured every 10 seconds throughout each cycle. "
        "Multiple instances of the same process name are aggregated into a single entry. "
        "**Peak concurrent pressure** reflects the highest total load observed in any single snapshot. "
        "On multi-core systems, total CPU may exceed 100%._\n"
    )
    lines.append(
        "_Capture boundary: processes with CPU ≤ 0.5% AND RAM ≤ 50 MB are not recorded "
        "— this is a collection boundary, not a summary filter. "
        "Absent processes were below both thresholds at every sample point._\n"
    )
    lines.append(
        "_GPU compute % per background process is **not available** via NVML or any "
        "user-space Windows API. Per-process VRAM usage is reported below where available._\n"
    )

    # ── A. Top CPU Consumers (R1) ────────────────────────────────────────────
    lines.append("### A. Top CPU Consumers\n")
    if bg["top_cpu"]:
        lines.append("| Process | Peak CPU % | Snapshots Present |")
        lines.append("|---------|----------:|------------------:|")
        for entry in bg["top_cpu"]:
            lines.append(
                f"| `{entry['name']}` "
                f"| {entry['peak_cpu_pct']:.1f}% "
                f"| {entry['snapshots']} / {total_snap} |"
            )
        lines.append("")
    else:
        lines.append("_No processes exceeded the CPU capture threshold during this campaign._\n")

    # ── B. Top RAM Consumers (R2) (llama-server excluded) ───────────────────
    lines.append("### B. Top RAM Consumers\n")
    lines.append(
        f"_llama-server excluded. "
        f"Peak total RAM across all tracked background processes in any snapshot: "
        f"**{bg['total_tracked_rss_mb']:.0f} MB**. "
        f"Top entries below show peaks for aggregated process names._\n"
    )
    if bg["top_ram"]:
        lines.append("| Process | Peak RSS (MB) | Snapshots Present |")
        lines.append("|---------|-------------:|------------------:|")
        for entry in bg["top_ram"]:
            lines.append(
                f"| `{entry['name']}` "
                f"| {entry['peak_rss_mb']:.0f} MB "
                f"| {entry['snapshots']} / {total_snap} |"
            )
        lines.append("")
    else:
        lines.append("_No background processes exceeded the RAM capture threshold._\n")

    # ── C. GPU VRAM by Process (R2-VRAM) ────────────────────────────────────
    lines.append("### C. GPU VRAM by Process\n")
    if bg["vram_tracking_available"]:
        lines.append(
            "_Per-process VRAM usage captured via `nvmlDeviceGetComputeRunningProcesses()`. "
            "GPU compute % is not attributable per-process (no user-space API exists for this)._\n"
        )
        lines.append(
            "> For full per-process VRAM trace, query: "
            f"`SELECT timestamp, gpu_proc_vram_json FROM background_snapshots "
            f"WHERE campaign_id='{campaign_id}' ORDER BY timestamp;`\n"
        )
    else:
        lines.append(
            "_Per-process VRAM tracking was not available for this campaign. "
            "This requires NVML to be initialized at collection time. "
            "If NVML was available during the run, the data will be present in the database "
            "as `gpu_proc_vram_json` in `background_snapshots`. "
            "If this field is NULL for all rows, NVML was unavailable or the query failed._\n"
        )

    # ── D. Notable CPU Spikes (R3) ───────────────────────────────────────────
    lines.append("### D. Notable CPU Spikes\n")
    lines.append(
        f"_Criterion: any process reaching ≥ {_CPU_SPIKE_THRESHOLD_PCT:.0f}% CPU in any single snapshot. "
        "One row per unique process (highest observed value shown)._\n"
    )
    if bg["notable_spikes"]:
        lines.append("| Process | Peak CPU % | Timestamp of Peak |")
        lines.append("|---------|----------:|-------------------|")
        for ev in bg["notable_spikes"]:
            lines.append(
                f"| `{ev['name']}` "
                f"| {ev['cpu_pct']:.1f}% "
                f"| {ev['timestamp']} |"
            )
        lines.append("")
    else:
        lines.append(
            f"_No processes reached ≥ {_CPU_SPIKE_THRESHOLD_PCT:.0f}% CPU in any snapshot "
            f"during this campaign._\n"
        )

    # ── E. Known Interferers (R4) ────────────────────────────────────────────
    lines.append("### E. Known Background Interferers\n")
    lines.append(
        "_Checked against a fixed list of known interference sources. "
        "Absence is stated explicitly — this is not an omission._\n"
    )
    lines.append("| Category | Detected | Peak CPU % | % of Snapshots |")
    lines.append("|----------|:--------:|-----------:|---------------:|")
    for entry in bg["known_interferers"]:
        detected_str = "✓" if entry["detected"] else "✗"
        if entry["detected"]:
            lines.append(
                f"| {entry['category']} "
                f"| {detected_str} (`{'`, `'.join(entry['process_names'][:2])}`) "
                f"| {entry['peak_cpu_pct']:.1f}% "
                f"| {entry['presence_pct']}% |"
            )
        else:
            lines.append(
                f"| {entry['category']} | {detected_str} | — | 0% |"
            )
    lines.append("")

    # ── F. Hardware Spikes (R5) ──────────────────────────────────────────────
    lines.append("### F. Hardware Conditions\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    cpu_temp_disp = f"{bg['hw_max_cpu_temp']:.1f}°C" if bg["hw_max_cpu_temp"] is not None else "N/A"
    gpu_temp_disp = f"{bg['hw_max_gpu_temp']:.1f}°C" if bg["hw_max_gpu_temp"] is not None else "N/A"
    lines.append(f"| Peak CPU temperature | {cpu_temp_disp} |")
    lines.append(f"| Peak GPU temperature | {gpu_temp_disp} |")
    lines.append(f"| CPU temp ≥ {_HW_CPU_TEMP_SPIKE_C:.0f}°C samples | {bg['hw_cpu_spike_samples']} |")
    lines.append(f"| GPU temp ≥ {_HW_GPU_TEMP_SPIKE_C:.0f}°C samples | {bg['hw_gpu_spike_samples']} |")
    lines.append(f"| GPU power-limit throttle events | {bg['hw_throttle_events']} |")
    lines.append("")

    if bg["hw_throttle_events"] > 0:
        lines.append(
            f"> ⚠️ **{bg['hw_throttle_events']} GPU power-limit throttle event(s) detected.** "
            "GPU SW_POWER_CAP throttling means the GPU was constrained to its TDP limit during "
            "inference. Affected cycles may show artificially lower throughput. "
            "See the `telemetry` table for sample-level timestamps.\n"
        )
    if bg["hw_cpu_spike_samples"] > 0:
        lines.append(
            f"> ⚠️ **{bg['hw_cpu_spike_samples']} sample(s) with CPU ≥ {_HW_CPU_TEMP_SPIKE_C:.0f}°C.** "
            "High CPU temperatures during inference indicate the machine was operating near its "
            "thermal ceiling. Affected samples are in the `telemetry` table.\n"
        )

    lines.append(
        "\n> **Full process trace:** query `background_snapshots WHERE campaign_id='"
        f"{campaign_id}'` for all snapshot rows with per-snapshot process lists.\n"
    )
    lines.append(
        "> **Raw hardware trace:** see the **Campaign Artifacts** section for "
        "the canonical `raw-telemetry.jsonl` path (merged 2-second hardware samples and request records).\n"
    )
    return lines


def _section_supporting_artifacts(
    campaign_id: str,
    reports_dir: Path,
    measurements_dir: Path,
    environment_dir: Path,
    db_path: Path,
    run_contexts: list[dict[str, Any]],
) -> list[str]:
    """
    Render the ## Supporting Evidence section.

    Lists all primary artifacts with their filesystem paths and availability.
    If an artifact is not found, states this explicitly.
    Includes copy-paste SQL queries for power-user inspection.

    This section must appear in every report. Its purpose is to make the
    full evidence chain discoverable without requiring users to know the
    filesystem layout in advance.
    """
    lines: list[str] = []
    lines.append("## Supporting Evidence\n> Type: Artifact Index\n")
    lines.append(
        "_This section lists all primary artifacts that support this report. "
        "They are available for independent inspection and verification of any claim in the report above. "
        "If an artifact is unavailable, this is stated explicitly — nothing is silently omitted._\n"
    )

    def _check(path: Path) -> str:
        return "legacy_file_present" if path.exists() else "missing"

    from src.trust_identity import load_artifact_summaries  # noqa: PLC0415
    artifact_rows = {
        row.get("artifact_type"): row
        for row in load_artifact_summaries(campaign_id, db_path)
    }

    def _artifact_status(artifact_type: str, path: Path) -> str:
        row = artifact_rows.get(artifact_type)
        if not row:
            if path.exists():
                return _check(path)
            # No DB row and file absent. run-reports.md is generated before
            # metadata.json; show "pending" for canonical types rather than
            # "missing" which would be stale once the run completes.
            if artifact_type in _PENDING_TYPES:
                return "pending"
            return _check(path)
        status = row.get("status") or _STR_NOT_RECORDED
        verification = row.get("verification_source") or _STR_NOT_RECORDED
        sha = row.get("sha256")
        error = row.get("error_message")
        parts = [status, f"verification={verification}"]
        if sha:
            parts.append(f"sha256={sha[:12]}")
        if error:
            parts.append(f"error={str(error)[:80]}")
        return "; ".join(parts)
    from src.artifact_paths import (  # noqa: PLC0415
        ARTIFACT_CAMPAIGN_SUMMARY,
        ARTIFACT_RUN_REPORTS,
        ARTIFACT_METADATA,
        ARTIFACT_RAW_TELEMETRY,
        FILENAME_RAW_TELEMETRY,
        FILENAME_CAMPAIGN_SUMMARY,
        FILENAME_RUN_REPORTS,
        FILENAME_METADATA,
    )
    _PENDING_TYPES = {
        ARTIFACT_CAMPAIGN_SUMMARY, ARTIFACT_RUN_REPORTS,
        ARTIFACT_METADATA, ARTIFACT_RAW_TELEMETRY,
    }
    raw_telemetry_jsonl = measurements_dir / FILENAME_RAW_TELEMETRY
    campaign_summary_md = reports_dir / FILENAME_CAMPAIGN_SUMMARY
    run_reports_md      = reports_dir / FILENAME_RUN_REPORTS
    metadata_json       = reports_dir / FILENAME_METADATA

    # Count run context files (internal delivery mechanism, not formal artifacts)
    rc_files = sorted(environment_dir.glob("*_run_context.json"))
    rc_status = f"✓ {len(rc_files)} file(s)" if rc_files else "✗ 0 files found"

    # Find most recent log. Prefer canonical artifacts/logs/... path and retain
    # legacy logs/<campaign> fallback for pre-migration runs.
    lab_root = db_path.parent.parent
    canonical_logs_root = lab_root / "artifacts" / "logs"
    canonical_log_dirs = sorted(canonical_logs_root.glob(f"*/{campaign_id}")) if canonical_logs_root.exists() else []
    canonical_log_files: list[Path] = []
    for d in canonical_log_dirs:
        canonical_log_files.extend(sorted(d.glob("runner_*.log")))
    legacy_log_dir = lab_root / "logs" / campaign_id
    legacy_log_files = sorted(legacy_log_dir.glob("runner_*.log")) if legacy_log_dir.exists() else []

    log_files = canonical_log_files if canonical_log_files else legacy_log_files
    log_dir = canonical_log_dirs[-1] if canonical_log_files and canonical_log_dirs else legacy_log_dir
    log_status = f"✓ {len(log_files)} file(s)" if log_files else "✗ Not found"
    log_latest = f"`{log_files[-1].name}`" if log_files else "—"

    lines.append("### Artifact Index\n")
    lines.append("_Formal campaign artifacts (approved 4-artifact contract):_\n")
    lines.append("| Artifact | Path | Status | Contents |")
    lines.append("|----------|------|:------:|----------|")
    lines.append(
        f"| Campaign Summary | `{campaign_summary_md}` | {_artifact_status('campaign_summary_md', campaign_summary_md)} | "
        "Compact summary — winner, key results, artifact pointers |"
    )
    lines.append(
        f"| Run Reports (this file) | `{run_reports_md}` | {_artifact_status('run_reports_md', run_reports_md)} | "
        "Full readable evidence, rankings, methodology, environment quality |"
    )
    lines.append(
        f"| Measurement Stream | `{raw_telemetry_jsonl}` | {_artifact_status('raw_telemetry_jsonl', raw_telemetry_jsonl)} | "
        "Merged request + telemetry records (distinguished by `_stream` field) |"
    )
    lines.append(
        f"| Provenance + Scores | `{metadata_json}` | {_artifact_status('metadata_json', metadata_json)} | "
        "Campaign YAML, scores, capability inventory, artifact manifest |"
    )
    lines.append(
        f"| Database | `{db_path}` | {_check(db_path)} | "
        "All tables: telemetry, background_snapshots, requests, scores, artifacts |"
    )
    lines.append("\n_Supporting files (not formal artifacts):_\n")
    lines.append(
        f"| Per-cycle environment | `{environment_dir}/*_run_context.json` | {rc_status} | "
        "Internal delivery mechanism — aggregated into run-reports.md and metadata.json |"
    )
    lines.append(
        f"| Run log(s) | `{log_dir}/runner_*.log` | {log_status} | "
        f"Full execution trace. Latest: {log_latest} |"
    )
    lines.append("")


    lines.append("### Database Inspection Queries\n")
    lines.append(
        "_Copy and run against `lab.sqlite` (or the DB path above) in any SQLite client._\n"
    )
    lines.append("```sql\n-- Hardware samples: CPU/GPU temps, VRAM, clocks, server metrics")
    lines.append(f"SELECT * FROM telemetry WHERE campaign_id = '{campaign_id}' ORDER BY timestamp;\n")
    lines.append("-- Background process snapshots: all notable processes every 10 s")
    lines.append(
        f"SELECT timestamp, all_notable_procs_json, gpu_proc_vram_json\n"
        f"FROM background_snapshots WHERE campaign_id = '{campaign_id}' ORDER BY timestamp;\n"
    )
    lines.append("-- Report generation history")
    lines.append(
        f"SELECT artifact_type, path, status, sha256, verification_source, error_message, created_at FROM artifacts\n"
        f"WHERE campaign_id = '{campaign_id}' ORDER BY created_at DESC;\n"
    )
    lines.append("-- Per-config score detail")
    lines.append(
        f"SELECT config_id, composite_score, rank_overall, is_score_winner,\n"
        f"       passed_filters, elimination_reason\n"
        f"FROM scores WHERE campaign_id = '{campaign_id}' ORDER BY rank_overall;\n"
    )
    lines.append("```\n")

    # Explicit note on what is NOT captured
    lines.append("### What Is Not Captured\n")
    lines.append(
        "- **Per-process GPU compute %:** Not available via NVML or any user-space Windows API. "
        "Only per-process VRAM usage is tracked (see `gpu_proc_vram_json` in `background_snapshots`).\n"
        "- **Processes below capture threshold:** Processes with CPU ≤ 0.5% AND RAM ≤ 50 MB are "
        "not recorded in `background_snapshots`. Their aggregate impact can be large but their "
        "individual footprint was below the collection boundary at every sample point.\n"
        "- **Elevated/protected processes:** System processes with PPL (Protected Process Light) "
        "protection may not appear in `all_notable_procs_json` due to OS access restrictions. "
        "Named-process flags (Defender, Windows Update) are set by name-match and are reliable.\n"
    )

    return lines


def _appendix_production_commands(
    scores_result:       dict[str, Any],
    stats:               dict[str, dict[str, Any]],
    db_path:             Path,
    campaign_id:         str,
    config_variable_map: dict[str, Any],
    variable_name:       str,
) -> list[str]:
    lines: list[str] = []
    lines.append("## Appendix C: Resolved Production Commands\n")
    lines.append(
        "This section provides copy-paste ready `llama-server` launch commands for the top-ranked passing configurations. "
        "These commands explicitly embed all parameters evaluated during this campaign. "
        "Note that the binary and model paths reflect the test environment and should be verified before external deployment.\n"
    )

    scores_df = scores_result.get("scores_df")
    eliminated = scores_result.get("eliminated", {})

    # Gather passing configs ordered by rank
    ranked: list[tuple[int, str]] = []
    for cid in stats:
        if cid in eliminated:
            continue
        rank = None
        if scores_df is not None and cid in scores_df.index:
            rank = scores_df.loc[cid].get("rank_overall")
        ranked.append((rank if rank is not None else 999, cid))
    ranked.sort()

    # Fetch resolved_command from DB for top 3
    top_n = ranked[:3]
    if not top_n:
        lines.append("_No passing configs available._\n")
        return lines

    with get_connection(db_path) as conn:
        for rank_pos, cid in top_n:
            row = conn.execute(
                "SELECT resolved_command, variable_value FROM configs WHERE id=? AND campaign_id=?",
                (cid, campaign_id),
            ).fetchone()
            if not row:
                continue
            cmd     = row["resolved_command"] or "—"
            var_val = config_variable_map.get(cid, "—")
            rank_label = f"Rank {rank_pos}" if rank_pos < 999 else "Passing"
            lines.append(f"### {rank_label}: `{cid}` ({variable_name}={var_val})\n")
            lines.append(f"```\n{cmd}\n```\n")

    return lines


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_campaign_report(
    campaign_id:   str,
    db_path:       Path,
    baseline:      dict[str, Any],
    scores_result: dict[str, Any] | None = None,
    stats:         dict[str, dict[str, Any]] | None = None,
    campaign:      dict[str, Any] | None = None,
    run_plan:      Any = None,
    lab_root:      Path | None = None,
) -> Path:
    """
    Generate the run-reports.md artifact (detailed human-readable evidence report).

    If scores_result and stats are not provided, they are computed from
    the database. The report is written to the canonical reports family:
        artifacts/reports/<model_slug>/<campaign_slug>/run-reports.md

    Args:
        campaign_id:   Effective campaign ID (may be mode-scoped, e.g.
                       "NGL_sweep__standard").
        db_path:       Path to lab.sqlite.
        baseline:      Parsed baseline.yaml dict.
        scores_result: Pre-computed scores (from score_campaign()). If None,
                       analysis is re-run from the DB.
        stats:         Pre-computed per-config statistics (from
                       analyze_campaign()). If None, re-run from DB.
        campaign:      Parsed campaign YAML dict. If None, loaded from DB.
        run_plan:      Resolved RunPlan object (optional, for mode awareness).
        lab_root:      Effective lab root. Defaults to LAB_ROOT env var.

    Returns:
        Path to the generated run-reports.md file.

    Never raises — exceptions are logged and the function returns a path
    even if the file was partially written.
    """
    effective_lab_root = lab_root if lab_root is not None else LAB_ROOT
    from src.trust_identity import (  # noqa: PLC0415
        load_baseline_for_historical_use,
        load_run_identity,
        recommendation_projection,
    )
    baseline, baseline_source = load_baseline_for_historical_use(
        campaign_id,
        db_path,
        fallback_baseline=baseline,
        allow_current_input=False,
    )
    trust_identity = load_run_identity(campaign_id, db_path)
    recommendation = recommendation_projection(trust_identity)
    legacy_results_dir = effective_lab_root / "results" / campaign_id
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
    reports_dir = report_artifacts["dir"]
    measurements_dir = find_artifact_dir(
        effective_lab_root,
        "measurements",
        campaign_id,
    ) or legacy_results_dir
    environment_dir = find_artifact_dir(
        effective_lab_root,
        "environment",
        campaign_id,
    ) or legacy_results_dir
    report_path = report_artifacts[ARTIFACT_RUN_REPORTS]

    # Compute analysis if not provided
    if scores_result is None:
        from src.score import score_campaign  # noqa: PLC0415
        scores_result = score_campaign(campaign_id, db_path, baseline)
    if stats is None:
        stats = scores_result["stats"]

    # Load campaign metadata from DB
    with get_connection(db_path) as conn:
        camp_row = conn.execute(
            "SELECT * FROM campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        # Build config → variable_value map for display
        cfg_rows = conn.execute(
            "SELECT id, variable_value FROM configs WHERE campaign_id=?",
            (campaign_id,),
        ).fetchall()

    camp = dict(camp_row) if camp_row else (campaign or {})
    snap = trust_identity.start_snapshot

    # variable_value is JSON-serialized; unwrap it for display
    config_variable_map: dict[str, Any] = {}
    for r in cfg_rows:
        try:
            config_variable_map[r["id"]] = json.loads(r["variable_value"])
        except (TypeError, ValueError):
            config_variable_map[r["id"]] = r["variable_value"]

    variable_name = camp.get("variable") or (
        getattr(run_plan, "variable", None) if run_plan else "value"
    ) or "value"

    # Load per-cycle run-context files, then restrict to configs that are actually
    # present in the current campaign (as recorded in the DB).  If the campaign
    # YAML was edited between runs, or if the same campaign_id was re-run with
    # fewer configs, stale run_context JSON files from removed configs remain on
    # disk.  Including them would inflate the cycle count and skew environment
    # quality percentages, producing a misleading Environment section.
    run_contexts = _load_run_contexts(environment_dir)
    _active_config_ids = set(config_variable_map.keys())
    run_contexts = [
        ctx for ctx in run_contexts
        if ctx.get("_config_id") in _active_config_ids
    ]
    env_agg      = _aggregate_environment(run_contexts)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build sections — every section MUST appear; failures emit stubs not silence
    sections: list[str] = []
    # Track (key, error_string) for each section that failed to render.
    # These are consumed by _section_concerns_and_warnings() which is built last.
    section_failures: list[tuple[str, str]] = []

    # Header (recovery: minimal title — no stub needed, always recoverable)
    try:
        sections.extend(
            _section_header(
                campaign_id, camp, snap, run_plan, baseline, now,
                baseline_source=baseline_source,
                trust_identity=trust_identity,
            )
        )
    except Exception as exc:
        logger.warning("report: header section failed: %s", exc)
        sections.append(f"# QuantMap Run Reports — {campaign_id}\n")

    # Methodology
    try:
        sections.extend(
            _section_methodology(
                run_plan,
                baseline,
                n_tested_configs=len(stats),
                scores_result=scores_result,
                methodology=trust_identity.methodology,
            )
        )
    except Exception as exc:
        logger.warning("report: methodology section failed: %s", exc)
        sections.extend(_section_failure_stub(f"## {_L_METH} Test Protocol", exc))
        section_failures.append(("methodology", str(exc)))

    # Primary Results
    try:
        sections.extend(
            _section_primary_results(
                scores_result, stats, config_variable_map,
                variable_name, run_plan, env_agg,
            )
        )
    except Exception as exc:
        logger.warning("report: primary results section failed: %s", exc)
        sections.extend(_section_failure_stub("## Primary Results", exc))
        section_failures.append(("primary_results", str(exc)))

    try:
        sections.extend(_section_recommendation(recommendation))
    except Exception as exc:
        logger.warning("report: recommendation section failed: %s", exc)
        sections.extend(_section_failure_stub("## Recommendation Authority", exc))
        section_failures.append(("recommendation", str(exc)))

    # Variability & Reliability
    try:
        sections.extend(
            _section_variability(scores_result, stats, config_variable_map, variable_name)
        )
    except Exception as exc:
        logger.warning("report: variability section failed: %s", exc)
        sections.extend(_section_failure_stub("## Variability & Reliability", exc))
        section_failures.append(("variability", str(exc)))

    # Environment Quality
    try:
        sections.extend(_section_environment(run_contexts, env_agg, stats))
    except Exception as exc:
        logger.warning("report: environment section failed: %s", exc)
        sections.extend(_section_failure_stub("## Environment Quality", exc))
        section_failures.append(("environment", str(exc)))

    # Background Process Activity — top-level section, sourced from background_snapshots
    # Computed here (not cached) so the report always reflects the current DB state.
    try:
        bg_data = _compute_background_interference(campaign_id, db_path)
        sections.extend(_section_background_interference(bg_data, reports_dir, campaign_id))
    except Exception as exc:
        logger.warning("report: background interference section failed: %s", exc)
        sections.extend(_section_failure_stub("## Background Process Activity", exc))
        section_failures.append(("background_interference", str(exc)))

    sections.append("\n---\n")

    # Appendices — header note distinguishing them from the main body
    sections.append(
        "## Appendices\n\n"
        "_Appendices contain detailed data for verification and deeper analysis. "
        "They supplement the main body and are not required reading for understanding "
        "the primary results._\n"
    )

    try:
        sections.extend(
            _appendix_full_stats(stats, scores_result, config_variable_map, variable_name)
        )
    except Exception as exc:
        logger.warning("report: appendix A failed: %s", exc)
        sections.extend(_section_failure_stub("## Appendix A — Full Config Statistics", exc))
        section_failures.append(("appendix_a", str(exc)))

    try:
        sections.extend(
            _appendix_eliminations(scores_result, config_variable_map, variable_name)
        )
    except Exception as exc:
        logger.warning("report: appendix B failed: %s", exc)
        sections.extend(_section_failure_stub("## Appendix B — Elimination Details", exc))
        section_failures.append(("appendix_b", str(exc)))

    try:
        sections.extend(
            _appendix_production_commands(
                scores_result, stats, db_path, campaign_id,
                config_variable_map, variable_name,
            )
        )
    except Exception as exc:
        logger.warning("report: appendix C failed: %s", exc)
        sections.extend(_section_failure_stub("## Appendix C — Production Commands", exc))
        section_failures.append(("appendix_c", str(exc)))

    try:
        sections.extend(
            _appendix_historical_configs(scores_result, config_variable_map, variable_name)
        )
    except Exception as exc:
        logger.warning("report: appendix D failed: %s", exc)
        sections.extend(_section_failure_stub("## Appendix D — Historical & Abandoned Configs", exc))
        section_failures.append(("appendix_d", str(exc)))

    # Supporting Evidence — always present; must appear before Concerns so
    # readers can follow artifact links even when other sections have failures.
    try:
        sections.extend(
            _section_supporting_artifacts(
                campaign_id,
                reports_dir,
                measurements_dir,
                environment_dir,
                db_path,
                run_contexts,
            )
        )
    except Exception as exc:
        logger.warning("report: supporting artifacts section failed: %s", exc)
        sections.extend(_section_failure_stub("## Supporting Evidence", exc))
        section_failures.append(("supporting_artifacts", str(exc)))

    # Concerns & Warnings — always last; built after all other sections so it
    # has full visibility of every failure that occurred during rendering.
    sections.append("\n---\n")
    try:
        sections.extend(
            _section_concerns_and_warnings(
                env_agg, scores_result, section_failures, run_contexts, run_plan,
            )
        )
    except Exception as exc:
        # Even the concerns section must not be silently omitted
        logger.warning("report: concerns section failed: %s", exc)
        sections.append(
            "## Aggregated Concerns & Warnings\n"
            "> Type: Diagnostics + Limitations\n\n"
            f"> **[REPORT_RENDER_FAILURE] Concerns section generation failed:** `{exc}`\n"
            "> Check logs for the full traceback.\n"
        )

    # Footer
    sections.append(
        f"\n---\n_Generated by QuantMap · {now} · "
        f"Data source: {db_path.name} · "
        f"Environment data: {len(run_contexts)} run_context file(s) loaded_\n"
    )

    md = "\n".join(sections)
    report_path.write_text(md, encoding="utf-8")
    logger.info("Run reports written: %s", report_path)

    # Record run-reports.md generation in the artifacts table.
    # Consistent with generate_report() — any query against artifacts can now
    # show all report files alongside their generation timestamps.
    _now_utc = datetime.now(timezone.utc).isoformat()
    try:
        with get_connection(db_path) as _art_conn:
            # Canonicalize: Delete previous run_reports_md artifacts for this campaign
            # to prevent DB bloat and ensure Single Source of Truth.
            _art_conn.execute(
                "DELETE FROM artifacts WHERE campaign_id=? AND artifact_type=?",
                (campaign_id, ARTIFACT_RUN_REPORTS)
            )
            _report_sha = _file_sha256(report_path)
            _report_status = "partial" if section_failures else ("complete" if _report_sha else "failed")
            _report_error = "; ".join(f"{k}: {v}" for k, v in section_failures) or None
            if _report_sha is None:
                _report_error = _report_error or "run-reports.md missing or unreadable after generation"
            _art_conn.execute(
                "INSERT INTO artifacts (campaign_id, artifact_type, path, sha256, created_at, status, producer, error_message, updated_at, verification_source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    campaign_id,
                    ARTIFACT_RUN_REPORTS,
                    str(report_path),
                    _report_sha,
                    _now_utc,
                    _report_status,
                    "src.report_campaign.generate_campaign_report",
                    _report_error,
                    _now_utc,
                    "producer_hash" if _report_sha else "producer_missing",
                ),
            )
            _art_conn.commit()
    except Exception as _art_exc:
        logger.warning("Could not record run-reports.md in artifacts table (non-fatal): %s", _art_exc)

    return report_path
