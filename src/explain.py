"""
QuantMap — explain.py

Briefing engine for natural language outcome rationales.
Heuristic-driven, deterministic, and evidence-bound.
"""

from __future__ import annotations

import logging
import json
import sqlite3
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from src.db import get_connection
from src import ui

logger = logging.getLogger("explain")

class Confidence(Enum):
    HIGH = "High"
    MODERATE = "Moderate"
    CAUTION = "Caution"

@dataclass
class Briefing:
    title: str
    headline: str
    margin_of_victory: str = ""
    top_constraint: str = ""
    elimination_summary: str = ""
    watchlist: List[str] = field(default_factory=list)
    confidence: Confidence = Confidence.MODERATE
    confidence_rationale: str = ""
    copy_summary: str = ""
    evidence_lines: List[str] = field(default_factory=list)

# Normalized buckets for elimination
REASON_BUCKETS = {
    "fatal_error": "Fatal Error (OOM/Crash)",
    "instrumentation_degraded": "Instrumentation Failure",
    "insufficient_data": "Insufficient Samples",
    "thermal_events": "Thermal Throttling",
    "cv_too_high": "Stability/Variance Failure",
    "cv_uncomputable": "Structural Variance Error",
    "too_many_outliers": "Outlier Excess",
    "warm_ttft_p90_too_high": "Latency Floor (TTFT)",
    "low_success_rate": "Reliability Failure",
    "tg_p10_below_floor": "Performance Floor (TG)",
    "no_complete_cycle_data": "Incomplete Execution",
    "missing_primary_metric": "Data Integrity Failure"
}

def normalize_reason(raw_reason: str) -> str:
    """Map raw elimination string to a stable bucket."""
    for key, label in REASON_BUCKETS.items():
        if raw_reason.startswith(key):
            return label
    return "Unknown Constraint"

def get_campaign_briefing(campaign_id: str, db_path: Path, evidence_mode: bool = False) -> Briefing:
    """Generate a technical briefing for a single campaign."""
    methodology_label = "methodology_unknown"
    trust_evidence_lines: list[str] = []
    try:
        from src.trust_identity import (  # noqa: PLC0415
            load_run_identity,
            methodology_source_label,
            recommendation_projection,
        )

        identity = load_run_identity(campaign_id, db_path)
        methodology_label = methodology_source_label(identity.methodology)
        recommendation = recommendation_projection(identity)
        snapshot = identity.start_snapshot

        execution_raw = snapshot.get("execution_environment_json")
        if execution_raw:
            try:
                execution = json.loads(str(execution_raw))
                reasons = execution.get("degraded_reasons") or []
                reason_text = ", ".join(str(item) for item in reasons) if reasons else "none"
                trust_evidence_lines.extend(
                    [
                        f"Execution support tier: {execution.get('support_tier', 'unknown')}",
                        f"Execution boundary: {execution.get('boundary_type', 'unknown')}",
                        f"Measurement-grade platform: {execution.get('measurement_grade', 'unknown')}",
                        f"Platform degradation reasons: {reason_text}",
                    ]
                )
            except Exception as exc:
                logger.debug("Could not parse execution environment evidence: %s", exc)

        provider_raw = snapshot.get("telemetry_provider_identity_json")
        if provider_raw:
            try:
                providers = json.loads(str(provider_raw))
                if isinstance(providers, list):
                    provider_text = "; ".join(
                        f"{provider.get('provider_label', provider.get('provider_id', 'provider'))} "
                        f"({provider.get('status', 'unknown')})"
                        for provider in providers
                        if isinstance(provider, dict)
                    )
                    if provider_text:
                        trust_evidence_lines.append(f"Telemetry providers: {provider_text}")
            except Exception as exc:
                logger.debug("Could not parse telemetry provider evidence: %s", exc)

        capture_quality = snapshot.get("telemetry_capture_quality")
        if capture_quality:
            trust_evidence_lines.append(f"Telemetry capture quality: {capture_quality}")
        if recommendation.get("available"):
            trust_evidence_lines.extend(
                [
                    f"ACPM recommendation status: {recommendation.get('status')}",
                    f"Leading config: {recommendation.get('leading_config_id') or 'none'}",
                    (
                        f"Recommended config: {recommendation.get('recommended_config_id')}"
                        if recommendation.get("recommended_config_id")
                        else "Recommended config: none issued"
                    ),
                    f"Handoff ready: {recommendation.get('handoff_ready')}",
                    f"Caveat codes: {', '.join(recommendation.get('caveat_codes', [])) or 'none'}",
                ]
            )
            if recommendation.get("coverage_class"):
                trust_evidence_lines.append(
                    f"Recommendation coverage class: {recommendation.get('coverage_class')}"
                )
        else:
            trust_evidence_lines.append("ACPM recommendation authority: not recorded")
    except Exception as exc:
        logger.debug("Could not load trust methodology context for briefing: %s", exc)

    def _attach_trust_context(briefing: Briefing) -> Briefing:
        """Attach trust identity context to an explain output dict."""
        briefing.watchlist.append(f"Methodology evidence: {methodology_label}")
        briefing.evidence_lines.extend(trust_evidence_lines)
        if methodology_label != "snapshot_complete":
            briefing.confidence = Confidence.CAUTION
            suffix = (
                f" Methodology evidence is {methodology_label}; historical "
                "interpretation should be treated as weaker evidence."
            )
            briefing.confidence_rationale = (briefing.confidence_rationale or "").rstrip() + suffix
        if briefing.copy_summary:
            briefing.copy_summary += f"\nMethodology evidence: {methodology_label}"
            for line in trust_evidence_lines:
                briefing.copy_summary += f"\n{line}"
        return briefing

    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        
        # 1. Load Winners
        winners = conn.execute(
            "SELECT * FROM scores WHERE campaign_id=? AND is_score_winner=1", 
            (campaign_id,)
        ).fetchall()
        
        # 2. Load Top Passing Candidates (to find runner-up)
        passers = conn.execute(
            "SELECT * FROM scores WHERE campaign_id=? AND passed_filters=1 ORDER BY composite_score DESC LIMIT 5",
            (campaign_id,)
        ).fetchall()
        
        # 3. Load Eliminations
        eliminated = conn.execute(
            "SELECT config_id, elimination_reason FROM scores WHERE campaign_id=? AND passed_filters=0",
            (campaign_id,)
        ).fetchall()

        # 4. Load Metadata
        campaign = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()

    if not campaign:
        return Briefing(campaign_id, f"Campaign {campaign_id} not found in database.")

    # --- NO WINNER Path ---
    if not winners:
        b = Briefing(
            campaign_id, 
            "[bold red]NO VALID WINNER EMERGED[/bold red]", 
            margin_of_victory="No passing configs found.",
            confidence=Confidence.CAUTION,
            confidence_rationale="Campaign produced zero valid candidates meeting quality gates."
        )
        if eliminated:
            counts: dict[str, int] = {}
            for row in eliminated:
                bucket = normalize_reason(row["elimination_reason"])
                counts[bucket] = counts.get(bucket, 0) + 1
            
            summary_parts = [f"{v}x {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1])]
            b.elimination_summary = f"Main failure modes: {'; '.join(summary_parts)}"
            
            # Identify the "Closest Failure"
            # (In a real implementation, we'd query configurations and see which was closest to gates)
            b.top_constraint = "Primary gate rejection: Stability or Latency floors."
        return _attach_trust_context(b)

    # --- WINNER Path ---
    winner = winners[0]
    runner_up = passers[1] if len(passers) > 1 else None
    
    b = Briefing(campaign_id, f"Winner Identification: [bold]{winner['config_id']}[/bold]")
    
    # Margin of Victory
    if runner_up:
        tg_diff = ((winner['warm_tg_median'] - runner_up['warm_tg_median']) / (runner_up['warm_tg_median'] or 1.0)) * 100
        lat_diff = ((winner['warm_ttft_p90_ms'] - runner_up['warm_ttft_p90_ms']) / (runner_up['warm_ttft_p90_ms'] or 1.0)) * 100
        
        b.margin_of_victory = (
            f"Winner outperformed runner-up ({runner_up['config_id']}) by {tg_diff:+.1f}% in throughput "
            f"while Latency (P90) shifted by {lat_diff:+.1f}%."
        )
        
        # Confidence logic
        if tg_diff > 10 and winner['warm_tg_cv'] < 0.03:
            b.confidence = Confidence.HIGH
            b.confidence_rationale = "Double-digit winning margin with low variance (<3% CV)."
        elif tg_diff < 3:
            b.confidence = Confidence.CAUTION
            b.confidence_rationale = "Winning margin is within the typical measurement noise band (<3%)."
        else:
            b.confidence = Confidence.MODERATE
            b.confidence_rationale = "Stable statistical lead outside of noise floor."
    else:
        b.margin_of_victory = "Config won by default (only passing candidate)."
        b.confidence = Confidence.CAUTION
        b.confidence_rationale = "No runner-up available for statistical contrast."

    # Elimination Post-Mortem
    if eliminated:
        winner_counts: dict[str, int] = {}
        for row in eliminated:
            bucket = normalize_reason(row["elimination_reason"])
            winner_counts[bucket] = winner_counts.get(bucket, 0) + 1
        summary_parts = [f"{v}x {k}" for k, v in sorted(winner_counts.items(), key=lambda x: -x[1])]
        b.elimination_summary = f"Out of {len(passers) + len(eliminated)} configs, {len(eliminated)} were rejected: {', '.join(summary_parts)}."
        
        # Top Constraint
        top_bucket = sorted(winner_counts.items(), key=lambda x: -x[1])[0][0]
        b.top_constraint = f"The primary operational constraint was [bold]{top_bucket}[/bold]."

    # 4. Watchlist
    for p in passers:
        cv = p['warm_tg_cv'] or 0
        p90 = p['warm_ttft_p90_ms'] or 0
        if 0.045 < cv < 0.05:
            b.watchlist.append(f"{p['config_id']}: Stability near gate (CV={cv:.1%})")
        if p90 > 450: # Assuming 500ms gate
            b.watchlist.append(f"{p['config_id']}: Latency floor risk (TTFT P90={p90:.0f}ms)")

    # Copy-summary
    b.copy_summary = (
        f"QuantMap Briefing: {campaign_id}\n"
        f"Winner: {winner['config_id']}\n"
        f"Confidence: {b.confidence.value} ({b.confidence_rationale})\n"
        f"Constraint: {b.top_constraint.replace('[bold]', '').replace('[/bold]', '')}"
    )

    return _attach_trust_context(b)

def print_briefing(b: Briefing, evidence_mode: bool = False):
    """Render a briefing to the console."""
    console = ui.get_console()
    ui.print_banner(f"Technical Briefing: {b.title}")
    
    console.print(f"[bold]Outcome:[/bold]           {b.headline}")
    if b.margin_of_victory:
        console.print(f"[bold]Margin of Victory:[/bold] {b.margin_of_victory}")
    if b.top_constraint:
        console.print(f"[bold]Top Constraint:[/bold]    {b.top_constraint}")
    if b.elimination_summary:
        console.print(f"[bold]Eliminations:[/bold]      {b.elimination_summary}")
    
    if b.watchlist:
        console.print("\n[bold]Watchlist (Borderline):[/bold]")
        for item in b.watchlist:
            console.print(f"  {ui.SYM_WARN} {item}")

    color = "green" if b.confidence == Confidence.HIGH else ("yellow" if b.confidence == Confidence.MODERATE else "red")
    console.print(f"\n[bold]Confidence:[/bold]        [{color}]{b.confidence.value}[/{color}]")
    console.print(f"  [dim]Rationale: {b.confidence_rationale}[/dim]")

    if evidence_mode:
        console.print(f"\n{ui.SYM_DIVIDER}" * 30 + " EVIDENCE BASIS " + f"{ui.SYM_DIVIDER}" * 30)
        console.print(f"  [dim]Classification Basis: {b.confidence_rationale}[/dim]")
        if b.margin_of_victory:
            console.print(f"  [dim]Comparative Lead:   {b.margin_of_victory}[/dim]")
        console.print("  [dim]Heuristic Engine: Quantitative Lead Analysis (v1.1) active.[/dim]")
        for line in b.evidence_lines:
            console.print(f"  [dim]{line}[/dim]")
    
    # Copy-paste block
    console.print(f"\n[bold]{ui.SYM_DIVIDER}[/bold] Copy-Paste Summary:")
    console.print(f"[dim]{b.copy_summary}[/dim]")
    console.print("")

def get_compare_briefing(id_a: str, id_b: str, db_path: Path) -> Briefing:
    """Generate a narrative shift briefing between two campaigns."""
    # Simplified implementation for now
    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        winner_a = conn.execute("SELECT config_id, warm_tg_median FROM scores WHERE campaign_id=? AND is_score_winner=1", (id_a,)).fetchone()
        winner_b = conn.execute("SELECT config_id, warm_tg_median FROM scores WHERE campaign_id=? AND is_score_winner=1", (id_b,)).fetchone()

    b = Briefing(f"Shift Analysis: {id_a} vs {id_b}", "Comparative Briefing")
    
    if winner_a and winner_b:
        if winner_a["config_id"] != winner_b["config_id"]:
            b.headline = f"Winner Pivot: [yellow]{winner_a['config_id']} -> {winner_b['config_id']}[/yellow]"
            b.margin_of_victory = f"The champion configuration changed. Subject campaign B favored {winner_b['config_id']}."
        else:
            b.headline = f"Winner Retained: [green]{winner_a['config_id']}[/green]"
            b.margin_of_victory = "The champion configuration remained stable between both runs."
            
        tg_delta = ((winner_b["warm_tg_median"] - winner_a["warm_tg_median"]) / (winner_a["warm_tg_median"] or 1.0)) * 100
        b.top_constraint = f"Observed shared-config throughput shift: [bold]{tg_delta:+.1f}%[/bold]."
        
        b.confidence = Confidence.MODERATE
        b.confidence_rationale = "Heuristic comparison of winner snapshots and median deltas."
    else:
        b.headline = "Comparison incomplete (one or more campaigns lacking winners)"
        b.confidence = Confidence.CAUTION

    b.copy_summary = f"QuantMap Comparison Briefing: {id_a} vs {id_b}\n{b.headline}\n{b.top_constraint}"
    return b
