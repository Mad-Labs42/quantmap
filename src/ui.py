"""QuantMap — ui.py

Central UI management. Handles:
- Symbol abstraction (UTF-8 vs ASCII fallback)
- Console capability detection (color, encoding, interactivity)
- Unified rich.Console management
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.acpm_planning import ACPMPlannerOutput, ACPMApplicabilityResult

from rich.console import Console
from rich.theme import Theme

from src.artifact_paths import (
    ARTIFACT_CAMPAIGN_SUMMARY,
    ARTIFACT_METADATA,
    ARTIFACT_RAW_TELEMETRY,
    ARTIFACT_RUN_REPORTS,
)
from src.campaign_outcome.contracts import (
    CampaignOutcomeKind,
    FinalReviewMetricsSnapshot,
    FinalReviewReadModel,
)

# Backwards-compatible name for the final-review metrics contract (no second DTO).
PostRunReviewMetrics = FinalReviewMetricsSnapshot

# ---------------------------------------------------------------------------
# Capability Detection Logic
# ---------------------------------------------------------------------------


def _is_plain_mode() -> bool:
    """Check if plain/conservative output is forced."""
    if os.getenv("QUANTMAP_PLAIN") == "1":
        return True
    # Check sys.argv directly for --plain (set by quantmap.py)
    if "--plain" in sys.argv:
        return True
    return False


def _supports_utf8() -> bool:
    """Check if stdout supports UTF-8 characters."""
    if sys.platform != "win32":
        return True
    # On Windows, check console encoding
    encoding = getattr(sys.stdout, "encoding", "") or ""
    return encoding.lower() in ("utf-8", "utf8")


# Force-calculate fallback state
PLAIN_MODE: bool = _is_plain_mode()
UTF8_SUPPORTED: bool = _supports_utf8()
USE_ASCII: bool = PLAIN_MODE or not UTF8_SUPPORTED

# ---------------------------------------------------------------------------
# Symbol Abstraction
# ---------------------------------------------------------------------------

SYM_OK: str = "✓" if not USE_ASCII else "[OK]"
SYM_WARN: str = "⚠️ " if not USE_ASCII else "[!]"
SYM_FAIL: str = "✗" if not USE_ASCII else "[FAIL]"
SYM_INFO: str = "ℹ " if not USE_ASCII else "[i]"
SYM_RETRY: str = "↺" if not USE_ASCII else "[RETRY]"
SYM_DIVIDER: str = "━" if not USE_ASCII else "-"


# ---------------------------------------------------------------------------
# Post-run review presentation (metrics type: PostRunReviewMetrics alias above)
# ---------------------------------------------------------------------------


def render_acpm_plan_preview(
    plan_output: "ACPMPlannerOutput",  # noqa: F821
    target_console: Console | None = None,
) -> None:
    """Render a compact ACPM plan preview for operator review.

    plan_output: an ACPMPlannerOutput from acpm_planning.compile_acpm_plan().
    """
    console = target_console or get_console()
    meta = plan_output.planning_metadata
    scope = plan_output.selected_scope
    coverage = meta.coverage_policy

    console.print("[bold]ACPM Plan Preview[/bold]")
    console.print(f"  Campaign:       {meta.source_campaign_ref}")
    console.print(f"  Profile:        {meta.profile_name}")
    console.print(
        f"  Repeat tier:    {plan_output.repeat_tier} → mode={plan_output.run_mode}"
    )
    console.print(f"  Scope authority: {meta.scope_authority}")
    console.print(f"  Variable:       {scope.variable}")
    console.print(
        f"  Selected:       {len(scope.selected_values)} value(s): {scope.selected_values}"
    )
    console.print(
        f"  Config IDs:     {', '.join(scope.selected_config_ids[:4])}"
        + (
            f" +{len(scope.selected_config_ids) - 4} more"
            if len(scope.selected_config_ids) > 4
            else ""
        )
    )
    cov_class = coverage.get("ngl_coverage_class", "unknown")
    console.print(f"  Coverage class: {cov_class}")
    console.print("")


def _check_scaffold_overlap(
    applicability: "ACPMApplicabilityResult",  # noqa: F821
    repeat_tier: str,
    check_fn: Any,
) -> bool:
    """Check NGL scaffold overlap for 1x repeat-tier campaigns.

    Imports NGL_SCAFFOLD_1X from acpm_planning on demand to avoid pulling
    in the full planning machinery at module level.

    Args:
        applicability: ACPMApplicabilityResult from acpm_planning.
        repeat_tier:   Requested repeat tier string (e.g. '1x').
        check_fn:      The _check callable from render_acpm_validate_result
                       that prints a pass/fail line and returns a bool.

    Returns True if scaffold check passes or is skipped (non-1x tier).
    """
    if repeat_tier != "1x":
        return True
    from src.acpm_planning import NGL_SCAFFOLD_1X  # noqa: PLC0415

    scaffold = [v for v in NGL_SCAFFOLD_1X if v in applicability.all_values]
    if scaffold:
        return check_fn(
            True,
            "scaffold overlap",
            f"{len(scaffold)} scaffold values found: {scaffold}",
        )
    return check_fn(
        False,
        "scaffold overlap",
        "no scaffold values found in campaign",
    )


def _render_applicability_check(
    applicability: "ACPMApplicabilityResult",  # noqa: F821
    repeat_tier: str,
    check_fn: Any,
) -> bool:
    """Render the ACPM applicability check and optional scaffold overlap."""
    if applicability.applicable:
        ok = check_fn(
            True,
            "ACPM-applicable",
            f"variable={applicability.variable}, {len(applicability.all_values)} values",
        )
        ok = _check_scaffold_overlap(applicability, repeat_tier, check_fn) and ok
        return ok

    return check_fn(
        False,
        "ACPM-applicable",
        f"not applicable: {applicability.reason or 'unknown'}",
    )


def _run_acpm_validate_checks(
    *,
    campaign_id: str,
    profile_id: str,
    repeat_tier: str,
    applicability: "ACPMApplicabilityResult",  # noqa: F821
    profile_info: "dict | None",
    tier_ok: bool,
    profile_ok: bool,
    campaign_exists: bool,
    check_fn: "Any",
    console: "Console",
) -> bool:
    """Run all ACPM pre-flight check lines and return True if all pass."""
    ok = True
    ok = check_fn(campaign_exists, "campaign YAML exists", campaign_id) and ok
    ok = check_fn(profile_ok, "profile valid", profile_id) and ok
    if profile_info:
        ok = (
            check_fn(
                True, "profile loads", profile_info.get("display_label", profile_id)
            )
            and ok
        )
    ok = check_fn(tier_ok, "repeat tier valid", repeat_tier) and ok
    ok = _render_applicability_check(applicability, repeat_tier, check_fn) and ok
    console.print("")
    if ok:
        console.print("[green]All ACPM pre-flight checks passed.[/green]")
    else:
        console.print("[red]ACPM pre-flight checks failed — fix errors above.[/red]")
    console.print("")
    return ok


def render_acpm_validate_result(
    campaign_id: str,
    profile_id: str,
    repeat_tier: str,
    applicability: "ACPMApplicabilityResult",  # noqa: F821
    profile_info: dict[str, str] | None = None,
    tier_ok: bool = True,
    profile_ok: bool = True,
    campaign_exists: bool = True,
    target_console: Console | None = None,
) -> bool:
    """Render ACPM validate check results.

    Args:
        campaign_id:    the campaign YAML ID
        profile_id:     the requested profile (e.g. "Balanced")
        repeat_tier:    the requested repeat tier (e.g. "1x")
        applicability:  ACPMApplicabilityResult from acpm_planning
        profile_info:    profile registry entry if profile is valid
        tier_ok:        repeat tier is a known value
        profile_ok:     profile_id is in V1_ACPM_PROFILE_IDS
        campaign_exists: campaign YAML file exists in CONFIGS_DIR/campaigns/
        target_console: console to render to
    """
    console = target_console or get_console()

    def _check(passed: bool, label: str, detail: str = "") -> bool:
        """Print a formatted pass/fail status line and return the pass/fail bool."""
        sym = SYM_OK if passed else SYM_FAIL
        color = "green" if passed else "red"
        msg = f"  [{color}]{sym}[/{color}]  {label}"
        if detail:
            msg += f"  [dim]— {detail}[/dim]"
        console.print(msg)
        return passed

    console.print(f"[bold]ACPM Validate: {campaign_id}[/bold]")
    console.print("=" * 60)
    return _run_acpm_validate_checks(
        campaign_id=campaign_id,
        profile_id=profile_id,
        repeat_tier=repeat_tier,
        applicability=applicability,
        profile_info=profile_info,
        tier_ok=tier_ok,
        profile_ok=profile_ok,
        campaign_exists=campaign_exists,
        check_fn=_check,
        console=console,
    )


# ---------------------------------------------------------------------------
# Unified Console
# ---------------------------------------------------------------------------

# Global theme for consistent coloring
QUANTMAP_THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "red bold",
        "success": "green",
        "dim": "dim",
        "bold": "bold",
        "highlight": "magenta",
    }
)

_GLOBAL_CONSOLE: Console | None = None


def get_console(force_new: bool = False) -> Console:
    """Returns a unified, capability-aware rich.Console.

    Arguments:
        force_new: Always create a fresh instance.
    """
    global _GLOBAL_CONSOLE
    if _GLOBAL_CONSOLE is not None and not force_new:
        return _GLOBAL_CONSOLE

    # Capability detection
    # If stdout is not a TTY, rich usually detects this and disables color/emojis.
    # We respect sys.stdout.isatty() but allow overrides.

    force_terminal = None
    if PLAIN_MODE:
        # plain mode effectively turns off color and special glyphs
        force_terminal = False

    # On Windows, if we reconfigured stdout to UTF-8 in bootstrap,
    # sys.stdout.encoding might already be 'utf-8'.

    console = Console(
        theme=QUANTMAP_THEME,
        force_terminal=force_terminal,
        # fallback to plain text if not a tty and not forced
        no_color=PLAIN_MODE,
        # High-rigor: If we're bootstrapping, we might need a specific color system
        color_system="auto" if not PLAIN_MODE else None,
    )

    if not force_new:
        _GLOBAL_CONSOLE = console
    return console


def print_banner(text: str, style: str = "bold cyan") -> None:
    """Unified banner printer."""
    console = get_console()
    console.print()
    console.print(f"[{style}]{text}[/{style}]")
    if USE_ASCII:
        console.print("-" * len(text))
    else:
        console.print("━" * len(text))
    console.print()


def format_status(label: str, passed: bool, detail: str = "") -> str:
    """Helper for health check style outputs."""
    symbol = SYM_OK if passed else SYM_FAIL
    style = "green" if passed else "red"
    msg = f"  [{style}]{symbol}[/{style}]  {label}"
    if detail:
        msg += f"  [dim]— {detail}[/dim]"
    return msg


def print_next_actions(
    actions: list[str],
    title: str = "Next actions",
    target_console: Console | None = None,
) -> None:
    """Render a compact, consistent next-step block for operator flows."""
    if not actions:
        return

    console = target_console or get_console()
    console.print(f"[bold]{title}[/bold]")
    for action in actions:
        console.print(f"  {SYM_INFO} {action}")
    console.print("")


def render_artifact_block(
    campaign_id: str,
    artifacts: list[dict],
    target_console: Console | None = None,
) -> None:
    """Print a compact artifact path/status block for post-run and discovery use.

    artifacts: list of dicts from artifact_paths.get_campaign_artifact_paths().
    Each entry: artifact_type, filename, path, exists, db_status, sha256.
    """
    _ARTIFACT_LABELS: dict[str, str] = {
        ARTIFACT_CAMPAIGN_SUMMARY: "Campaign Summary",
        ARTIFACT_RUN_REPORTS: "Run Reports",
        ARTIFACT_METADATA: "Metadata",
        ARTIFACT_RAW_TELEMETRY: "Raw Telemetry",
    }

    console = target_console or get_console()
    console.print(f"\n[bold]Artifacts — {campaign_id}[/bold]")
    for a in artifacts:
        atype = a.get("artifact_type", "")
        path = a.get("path")
        exists = a.get("exists", False)
        db_st = a.get("db_status")

        if db_st == "complete":
            sym, color, label = SYM_OK, "green", "complete"
        elif db_st and db_st not in ("missing", "pending"):
            sym, color, label = SYM_WARN, "yellow", db_st
        elif exists:
            sym, color, label = SYM_OK, "green", "present"
        else:
            sym, color, label = SYM_FAIL, "red", "not found"

        from rich.markup import escape

        path_str = escape(str(path)) if path else "[dim]path unknown[/dim]"
        raw_type = escape(atype)
        label_name = _ARTIFACT_LABELS.get(atype)
        if label_name:
            display_name = f"{label_name} [dim]({raw_type})[/dim]"
        else:
            display_name = raw_type
        console.print(
            f"  [{color}]{sym}[/{color}] {display_name}"
            f"\n    {path_str}  [{color}]({label})[/{color}]"
        )
    console.print("")


# --- Post-run review: shared presentation ---------------------------------

_POST_RUN_MODE_LABELS: dict[str, str] = {
    "full": "Full",
    "quick": "Quick",
    "standard": "Standard",
    "custom": "Custom",
}

_OUTCOME_STATUS_STYLE: dict[CampaignOutcomeKind, str] = {
    CampaignOutcomeKind.SUCCESS: "green",
    CampaignOutcomeKind.FAILED: "red",
    CampaignOutcomeKind.ABORTED: "red",
    CampaignOutcomeKind.PARTIAL: "yellow",
    CampaignOutcomeKind.DEGRADED: "yellow",
    CampaignOutcomeKind.INSUFFICIENT_EVIDENCE: "yellow",
}


@dataclass(frozen=True, slots=True)
class _PostRunReviewRenderContext:
    """Presentation-only inputs assembled by each entrypoint — no truth computation.

    ``show_next_actions`` is evaluator/projection-owned. ``PARTIAL`` outcomes
    may still show next actions in the secondary-artifact-only carve-out while
    rendering warning/failure details in parallel.
    """

    campaign_id: str
    yolo_mode: bool
    use_legacy_binary_status: bool
    legacy_report_ok: bool
    read_headline_status: str
    read_headline_color: str
    show_report_generation_subline: bool
    report_generation_ok: bool | None
    metrics: PostRunReviewMetrics | None
    failure_emit: bool
    failure_cause: str | None
    failure_remediation: str | None
    emit_unknown_cause_line: bool
    emit_artifact_block: bool
    artifacts: list[dict] | None
    show_next_actions: bool
    diagnostics_path: str | None
    diagnostics_success_style: bool
    diagnostics_dim_prefer_cause_line: bool


def _norm_sentence_post_run(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    return text if text[-1] in (".", "!", "?") else f"{text}."


def _render_post_run_blocker_detail(
    con: Console,
    failure_cause_stripped: str,
    failure_remediation: str | None,
) -> None:
    from rich.markup import escape as _escape  # noqa: PLC0415

    con.print("The following blocker was identified:\n")
    con.print(f"- Cause: {_norm_sentence_post_run(_escape(failure_cause_stripped))}")
    if failure_remediation and failure_remediation.strip():
        con.print(
            f"  Suggested fix: {_norm_sentence_post_run(_escape(failure_remediation.strip()))}"
        )


def _render_post_run_failure_section(
    con: Console,
    *,
    failure_emit: bool,
    failure_cause_stripped: str,
    failure_remediation: str | None,
    emit_unknown_cause_line: bool,
) -> None:
    if not failure_emit:
        return
    # Suppress the leading blank line when neither the blocker detail nor the
    # unknown-cause line will render. Without this guard, PARTIAL outcomes that
    # still allow next-actions (carve-out path) and carry an empty failure_cause
    # produce an orphan blank section. The renderer must defend the contract
    # surface ``failure_cause: str | None`` rather than rely on evaluator
    # invariants that may shift in future slices.
    if not failure_cause_stripped and not emit_unknown_cause_line:
        return
    con.print("")
    if failure_cause_stripped:
        _render_post_run_blocker_detail(
            con, failure_cause_stripped, failure_remediation
        )
    elif emit_unknown_cause_line:
        con.print("Cause: Unknown.")


def _post_run_has_config_count_block(metrics: PostRunReviewMetrics | None) -> bool:
    return (
        metrics is not None
        and metrics.configs_total is not None
        and metrics.configs_total > 0
    )


def _render_post_run_configs_count_line(
    con: Console, metrics: PostRunReviewMetrics
) -> None:
    _parts: list[str] = [f"{metrics.configs_total} tested"]
    if metrics.configs_valid is not None:
        _parts.append(f"[green]{metrics.configs_valid} valid[/green]")
    if metrics.configs_eliminated is not None and metrics.configs_eliminated > 0:
        _parts.append(f"[yellow]{metrics.configs_eliminated} eliminated[/yellow]")
    con.print(f"Configs:  {' · '.join(_parts)}")


def _render_post_run_winner_lines(con: Console, metrics: PostRunReviewMetrics) -> None:
    if metrics.winner_config_id is not None and metrics.winner_tg is not None:
        con.print(
            f"Best observed config: [bold]{metrics.winner_config_id}[/bold] "
            f"· TG [bold green]{metrics.winner_tg:.2f}[/bold green] t/s"
        )
    elif metrics.winner_config_id is not None:
        con.print(f"Best observed config: [bold]{metrics.winner_config_id}[/bold]")
    elif metrics.configs_valid is not None and metrics.configs_valid == 0:
        con.print("[dim]No valid configs produced a score.[/dim]")


def _post_run_meta_line_parts(metrics: PostRunReviewMetrics | None) -> list[str]:
    _meta_parts: list[str] = []
    if metrics is not None and metrics.run_mode is not None:
        _mode_label = _POST_RUN_MODE_LABELS.get(
            metrics.run_mode, metrics.run_mode.title()
        )
        _meta_parts.append(f"Mode: [dim]{_mode_label}[/dim]")
    if metrics is not None and metrics.elapsed_seconds is not None:
        _elapsed_str = _format_elapsed(metrics.elapsed_seconds)
        _meta_parts.append(f"Elapsed: [dim]{_elapsed_str}[/dim]")
    return _meta_parts


def _render_post_run_config_summary_and_meta(
    con: Console, metrics: PostRunReviewMetrics | None
) -> None:
    has_config_block = _post_run_has_config_count_block(metrics)
    if has_config_block and metrics is not None:
        _render_post_run_configs_count_line(con, metrics)
        _render_post_run_winner_lines(con, metrics)

    _meta_parts = _post_run_meta_line_parts(metrics)
    if _meta_parts:
        con.print("  ".join(_meta_parts))
    elif has_config_block:
        con.print("")


def _render_post_run_header_and_yolo(
    con: Console, campaign_id: str, yolo_mode: bool
) -> None:
    con.print(f"\n[bold]Campaign review — {campaign_id}[/bold]")
    if yolo_mode:
        con.print("[bold yellow]YOLO Mode Active[/bold yellow]")
        con.print(
            "[yellow]Validation requirements were relaxed because the user "
            "chose to continue after a trust warning.[/yellow]"
        )


def _render_post_run_status_line(
    con: Console, ctx: _PostRunReviewRenderContext
) -> None:
    if ctx.use_legacy_binary_status:
        if ctx.legacy_report_ok:
            con.print("Status:  [bold green]Success[/bold green]")
        else:
            con.print("Status:  [bold red]Failed[/bold red]")
        return
    color = ctx.read_headline_color
    con.print(f"Status:  [bold {color}]{ctx.read_headline_status}[/bold {color}]")


def _maybe_render_report_generation_subline(
    con: Console, ctx: _PostRunReviewRenderContext
) -> None:
    if not ctx.show_report_generation_subline or ctx.report_generation_ok is None:
        return
    _rg = "OK" if ctx.report_generation_ok else "FAILED"
    con.print(f"[dim]Report generation: {_rg}[/dim]")


def _render_post_run_diagnostics_block(
    con: Console, ctx: _PostRunReviewRenderContext
) -> None:
    if ctx.diagnostics_path is None:
        return
    from rich.markup import escape  # noqa: PLC0415

    safe_path = escape(str(ctx.diagnostics_path))
    fc_stripped = ctx.failure_cause.strip() if ctx.failure_cause else ""
    dim_use_cause = ctx.diagnostics_dim_prefer_cause_line and bool(fc_stripped)

    if ctx.diagnostics_success_style:
        con.print(
            f"\n[dim]Internal diagnostic files were retained for debugging.\n"
            f"By default, they are not included in the user-facing artifact list.\n"
            f"If you would like to view them, you may do so at:\n"
            f"{safe_path}[/dim]"
        )
        return
    if dim_use_cause:
        con.print(
            f"\n[dim]Internal diagnostics may provide more information: {safe_path}[/dim]"
        )
    else:
        con.print(
            f"\n[dim]Internal diagnostics may help diagnose the issue: {safe_path}[/dim]"
        )


def _render_post_run_review_core(
    con: Console, ctx: _PostRunReviewRenderContext
) -> None:
    """Emit Rich layout for post-run review from a fully built render context.

    Presentation-only: does not evaluate outcomes or touch the DB; ``ctx`` flags
    are already derived from the read model or legacy binary inputs.
    """
    _render_post_run_header_and_yolo(con, ctx.campaign_id, ctx.yolo_mode)
    _render_post_run_status_line(con, ctx)
    _maybe_render_report_generation_subline(con, ctx)
    _render_post_run_config_summary_and_meta(con, ctx.metrics)

    fc_strip = ctx.failure_cause.strip() if ctx.failure_cause else ""
    _render_post_run_failure_section(
        con,
        failure_emit=ctx.failure_emit,
        failure_cause_stripped=fc_strip,
        failure_remediation=ctx.failure_remediation,
        emit_unknown_cause_line=ctx.emit_unknown_cause_line,
    )

    if ctx.emit_artifact_block and ctx.artifacts is not None:
        render_artifact_block(ctx.campaign_id, ctx.artifacts, target_console=con)

    if ctx.show_next_actions:
        print_next_actions(
            [
                f"quantmap explain {ctx.campaign_id} --evidence",
                f"quantmap artifacts {ctx.campaign_id}",
                "quantmap list",
            ],
            title="Next actions",
            target_console=con,
        )

    _render_post_run_diagnostics_block(con, ctx)


def render_post_run_review(
    campaign_id: str,
    report_ok: bool,
    artifacts: list[dict] | None = None,
    diagnostics_path: str | None = None,
    yolo_mode: bool = False,
    failure_cause: str | None = None,
    failure_remediation: str | None = None,
    metrics: PostRunReviewMetrics | None = None,
    target_console: Console | None = None,
) -> None:
    """Render the post-run campaign review screen.

    Presentation-only: no sys.exit, no DB I/O, no filesystem writes.
    All state is passed in by the caller (runner.py).

    Args:
        campaign_id:         Effective campaign ID used for the run.
        report_ok:           True if the primary report was generated successfully.
        artifacts:           Optional list of artifact dicts from
                             artifact_paths.get_campaign_artifact_paths().
                             If provided, render_artifact_block is called.
        diagnostics_path:    Optional path string for the internal diagnostics
                             folder.  None -> diagnostics block is omitted.
        yolo_mode:           If True, show the YOLO active reminder.
        failure_cause:       Optional short failure cause.
        failure_remediation: Optional user-facing remediation guidance.
        metrics:             Optional PostRunReviewMetrics with winner/config/run
                             metadata.  When None the entire config summary,
                             mode, and elapsed sections are silently omitted.
        target_console:      Console to render to (defaults to global console).
    """
    con = target_console or get_console()
    fc = failure_cause.strip() if failure_cause else ""
    ctx = _PostRunReviewRenderContext(
        campaign_id=campaign_id,
        yolo_mode=yolo_mode,
        use_legacy_binary_status=True,
        legacy_report_ok=report_ok,
        read_headline_status="",
        read_headline_color="green",
        show_report_generation_subline=False,
        report_generation_ok=None,
        metrics=metrics,
        failure_emit=not report_ok,
        failure_cause=failure_cause,
        failure_remediation=failure_remediation,
        emit_unknown_cause_line=(not report_ok) and not fc,
        emit_artifact_block=artifacts is not None,
        artifacts=artifacts,
        show_next_actions=report_ok,
        diagnostics_path=diagnostics_path,
        diagnostics_success_style=report_ok,
        diagnostics_dim_prefer_cause_line=bool(fc),
    )
    _render_post_run_review_core(con, ctx)


def render_post_run_review_from_read_model(
    campaign_id: str,
    read_model: FinalReviewReadModel,
    artifacts: list[dict] | None = None,
    diagnostics_path: str | None = None,
    yolo_mode: bool = False,
    target_console: Console | None = None,
) -> None:
    """Render post-run review from ``FinalReviewReadModel`` (Slice 1 seam).

    Maps evaluator/projection fields into layout context only — does not infer
    success vs failure from raw ``report_ok`` or DB state. Uses
    ``read_model.metrics`` (``FinalReviewMetricsSnapshot``) as-is; no DB I/O or
    ``sys.exit``.
    """
    con = target_console or get_console()
    _color = _OUTCOME_STATUS_STYLE.get(read_model.outcome_kind, "red")
    metrics: PostRunReviewMetrics | None = read_model.metrics

    fc = read_model.failure_cause.strip() if read_model.failure_cause else ""
    ctx = _PostRunReviewRenderContext(
        campaign_id=campaign_id,
        yolo_mode=yolo_mode,
        use_legacy_binary_status=False,
        legacy_report_ok=False,
        read_headline_status=read_model.headline_status,
        read_headline_color=_color,
        show_report_generation_subline=(
            read_model.report_generation_ok is not None
            and (
                not read_model.show_next_actions
                or read_model.outcome_kind == CampaignOutcomeKind.PARTIAL
            )
        ),
        report_generation_ok=read_model.report_generation_ok,
        metrics=metrics,
        failure_emit=(
            (not read_model.show_next_actions)
            or read_model.outcome_kind == CampaignOutcomeKind.PARTIAL
        ),
        failure_cause=read_model.failure_cause,
        failure_remediation=read_model.failure_remediation,
        emit_unknown_cause_line=(
            (not read_model.show_next_actions)
            and not fc
            and read_model.outcome_kind != CampaignOutcomeKind.SUCCESS
        ),
        emit_artifact_block=(
            read_model.artifact_block_mode == "full" and artifacts is not None
        ),
        artifacts=artifacts,
        show_next_actions=read_model.show_next_actions,
        diagnostics_path=diagnostics_path,
        diagnostics_success_style=read_model.success_style_diagnostics,
        diagnostics_dim_prefer_cause_line=bool(fc),
    )
    _render_post_run_review_core(con, ctx)


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as a human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"
