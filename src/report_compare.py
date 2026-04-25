"""
QuantMap — report_compare.py

Markdown renderer for cross-campaign comparisons.
Follows the evidence-first philosophy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.compare import CompareResult

# Semantic Labels
_L_CONT = "CONTEXT"
_L_METH = "METHODOLOGY"
_L_ENV  = "ENVIRONMENT"
_L_DATA = "DATA"
_L_INT  = "INTERPRETATION"

def _fmt(val: float | None, spec: str, missing: str = "—") -> str:
    """Format a float value for comparison report display."""
    if val is None:
        return missing
    return format(val, spec)

def _delta_symbol(pct: float, significance: str) -> str:
    """Return an arrow symbol indicating improvement or regression direction."""
    if significance == "inside noise band":
        return "≈"
    if pct > 0.5:
        return "↑"
    if pct < -0.5:
        return "↓"
    return "≈"

def _delta_style(pct: float, significance: str, invert: bool = False) -> str:
    """invert=True means higher is worse (e.g. TTFT)"""
    if significance == "inside noise band":
        return "white"
    
    is_improvement = pct > 0 if not invert else pct < 0
    if abs(pct) < 0.5:
        return "white"
    return "green" if is_improvement else "red"

def render_compare_markdown(result: CompareResult) -> str:
    """Render the full forensic comparison report."""
    res = result.to_dict()
    a = res["campaign_a"]
    b = res["campaign_b"]
    meth = res["methodology"]
    
    lines = []
    lines.append(f"# QuantMap Forensic Comparison: {a['id']} vs {b['id']}")
    lines.append(f"\nGenerated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # --- CONTEXT ---
    lines.append(f"\n## [{_L_CONT}] Comparison Scope")
    lines.append("| Metric | Campaign A (Baseline) | Campaign B (Subject) |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(f"| **ID** | {a['id']} | {b['id']} |")
    lines.append(f"| **Name** | {a['name']} | {b['name']} |")
    lines.append(f"| **Date** | {a['created_at'][:16]} | {b['created_at'][:16]} |")
    lines.append(f"| **Winner** | `{res['winner_a']['config_id'] if res['winner_a'] else '—'}` | `{res['winner_b']['config_id'] if res['winner_b'] else '—'}` |")
    lines.append(f"| **Winner Δ TG** | — | **{_fmt(res['winner_shift_tg_pct'], '+.1f')}%** |")
    lines.append(f"| **Median Shared Δ** | — | **{_fmt(res['median_shared_tg_shift_pct'], '+.1f')}%** |")

    rec_a = res.get("recommendation_a") or {}
    rec_b = res.get("recommendation_b") or {}
    lines.append(f"\n## [{_L_DATA}: RECOMMENDATION] Recommendation Authority")
    lines.append("| Field | Campaign A (Baseline) | Campaign B (Subject) |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(f"| Available | `{rec_a.get('available')}` | `{rec_b.get('available')}` |")
    lines.append(f"| Status | `{rec_a.get('status') or 'not recorded'}` | `{rec_b.get('status') or 'not recorded'}` |")
    lines.append(f"| Leading config | `{rec_a.get('leading_config_id') or 'none'}` | `{rec_b.get('leading_config_id') or 'none'}` |")
    lines.append(f"| Recommended config | `{rec_a.get('recommended_config_id') or 'none issued'}` | `{rec_b.get('recommended_config_id') or 'none issued'}` |")
    lines.append(f"| Handoff ready | `{rec_a.get('handoff_ready')}` | `{rec_b.get('handoff_ready')}` |")
    lines.append(f"| Coverage class | `{rec_a.get('coverage_class') or 'not recorded'}` | `{rec_b.get('coverage_class') or 'not recorded'}` |")
    lines.append(
        f"| Caveat codes | {', '.join(rec_a.get('caveat_codes', [])) or 'none'} | "
        f"{', '.join(rec_b.get('caveat_codes', [])) or 'none'} |"
    )

    # --- METHODOLOGY ---
    grade_map = {
        "compatible": "🟢 COMPATIBLE",
        "warnings":   "🟡 COMPARABLE WITH WARNINGS",
        "mismatch":   "🔴 METHODOLOGY MISMATCH"
    }
    lines.append(f"\n## [{_L_METH}] Compatibility Audit")
    lines.append(f"**Status: {grade_map.get(meth['grade'], meth['grade'])}**")
    
    if meth["warnings"]:
        lines.append("\n> [!WARNING]")
        for w in meth["warnings"]:
            lines.append(f"> - {w}")

    lines.append("\n#### Anchor Drift Analysis")
    lines.append("| Metric | Value A | Value B | Delta | Status |")
    lines.append("| :--- | ---: | ---: | ---: | :--- |")
    for d in meth["anchor_deltas"]:
        delta = (d['val_b'] - d['val_a']) if (d['val_a'] and d['val_b']) else 0
        status = "MATCH" if d['status'] == 'match' else "DRIFTED"
        lines.append(f"| {d['metric']} | {d['val_a']} | {d['val_b']} | {delta:+.2f} | {status} |")

    # --- SYSTEM & ENVIRONMENT ---
    lines.append(f"\n## [{_L_ENV}] System & Environment Deltas")
    if not res["env_deltas"]:
        lines.append("No significant environment or hardware deltas detected between campaign starts.")
    else:
        lines.append("| Category | Component | Baseline (A) | Subject (B) | Trend |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for ed in res["env_deltas"]:
            trend = "REGRESSION" if ed["is_regression"] else "CHANGE" # Simplified
            lines.append(f"| {ed['category'].capitalize()} | {ed['label']} | {ed['val_a']} | {ed['val_b']} | {trend} |")

    # --- DATA: WINNERS ---
    lines.append(f"\n## [{_L_DATA}: WINNERS] Side-by-Side Performance")
    if res["winner_a"] and res["winner_b"]:
        wa = res["winner_a"]
        wb = res["winner_b"]
        lines.append(f"| Metric | Winner A (`{wa['config_id']}`) | Winner B (`{wb['config_id']}`) | Delta (%) |")
        lines.append("| :--- | ---: | ---: | ---: |")
        
        tg_a = wa.get("warm_tg_median")
        tg_b = wb.get("warm_tg_median")
        tg_d = res["winner_shift_tg_pct"]
        lines.append(f"| Throughput (TG) | {_fmt(tg_a, '.2f')} t/s | {_fmt(tg_b, '.2f')} t/s | **{_fmt(tg_d, '+.1f')}%** |")
        
        tt_a = wa.get("warm_ttft_median_ms")
        tt_b = wb.get("warm_ttft_median_ms")
        tt_d = (tt_b - tt_a) / tt_a * 100 if (tt_a and tt_b and tt_a > 0) else None
        lines.append(f"| Latency (TTFT) | {_fmt(tt_a, '.0f')} ms | {_fmt(tt_b, '.0f')} ms | {_fmt(tt_d, '+.1f')}% |")
    else:
        lines.append("Insufficient data to compare campaign winners.")

    # --- DATA: INTERSECTION SET ---
    lines.append(f"\n## [{_L_DATA}: SHARED_CONFIGS] Intersection Set Deltas")
    lines.append("> [!NOTE]")
    lines.append("> Values marked with `~` are inside the measured noise band (CV) and may not represent meaningful performance changes.")
    
    if not res["shared_configs"]:
        lines.append("\nNo identical configurations found between these campaigns.")
    else:
        lines.append("\n| Config ID | Throughput (A) | Throughput (B) | Δ (%) | Significance |")
        lines.append("| :--- | ---: | ---: | ---: | :--- |")
        for sc in res["shared_configs"]:
            sym = _delta_symbol(sc['tg_delta_pct'], sc['significance_label'])
            sig_flag = "~~" if sc['significance_label'] == "inside noise band" else ""
            lines.append(
                f"| `{sc['config_id']}` | {_fmt(sc['tg_a'], '.2f')} | {_fmt(sc['tg_b'], '.2f')} | "
                f"{sig_flag}{sym} {_fmt(sc['tg_delta_pct'], '+.1f')}%{sig_flag} | {sc['significance_label']} |"
            )

    # --- DATA: ELIMINATION ---
    lines.append(f"\n## [{_L_DATA}: REACH] Elimination & Failures")
    lost = len(res["lost_in_b"])
    gained = len(res["gained_in_b"])
    lines.append(f"- **Configs lost in B**: {lost} {'(regression in reach)' if lost > 0 else ''}")
    lines.append(f"- **Configs gained in B**: {gained} {'(improvement in reach)' if gained > 0 else ''}")
    
    if lost > 0:
        lines.append("\n| Lost Config | Potential Reason |")
        lines.append("| :--- | :--- |")
        for cid in res["lost_in_b"][:10]: # Cap at 10
             lines.append(f"| `{cid}` | (Review logs for details) |")

    # --- INTERPRETATION ---
    lines.append(f"\n## [{_L_INT}] Comparison Findings")
    lines.append(f"- **Primary Finding**: {res['primary_finding']}")
    lines.append(f"- **Confidence**: This comparison is graded as **{res['overall_confidence']}-confidence** due to methodology {meth['grade']}.")

    return "\n".join(lines)

def save_compare_report(result: CompareResult, output_path: Path):
    """Render and save the report to disk."""
    content = render_compare_markdown(result)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path
