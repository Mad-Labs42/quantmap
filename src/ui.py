"""QuantMap — ui.py

Central UI management. Handles:
- Symbol abstraction (UTF-8 vs ASCII fallback)
- Console capability detection (color, encoding, interactivity)
- Unified rich.Console management
"""

from __future__ import annotations

import os
import sys
from typing import Any

from rich.console import Console
from rich.theme import Theme

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
    console.print(f"  Repeat tier:    {plan_output.repeat_tier} → mode={plan_output.run_mode}")
    console.print(f"  Scope authority: {meta.scope_authority}")
    console.print(f"  Variable:       {scope.variable}")
    console.print(
        f"  Selected:       {len(scope.selected_values)} value(s): {scope.selected_values}"
    )
    console.print(
        f"  Config IDs:     {', '.join(scope.selected_config_ids[:4])}"
        + (f" +{len(scope.selected_config_ids) - 4} more" if len(scope.selected_config_ids) > 4 else "")
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
) -> None:
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
    ok = True
    ok = _check(campaign_exists, "campaign YAML exists", campaign_id) and ok
    ok = _check(profile_ok, "profile valid", profile_id) and ok
    if profile_info:
        ok = _check(True, "profile loads", profile_info.get("display_label", profile_id)) and ok
    ok = _check(tier_ok, "repeat tier valid", repeat_tier) and ok
    if applicability.applicable:
        ok = _check(
            True,
            "ACPM-applicable",
            f"variable={applicability.variable}, {len(applicability.all_values)} values",
        ) and ok
        ok = _check_scaffold_overlap(applicability, repeat_tier, _check) and ok
    else:
        ok = _check(
            False,
            "ACPM-applicable",
            f"not applicable: {applicability.reason or 'unknown'}",
        ) and ok
    console.print("")
    if ok:
        console.print("[green]All ACPM pre-flight checks passed.[/green]")
    else:
        console.print("[red]ACPM pre-flight checks failed — fix errors above.[/red]")
    console.print("")

# ---------------------------------------------------------------------------
# Unified Console
# ---------------------------------------------------------------------------

# Global theme for consistent coloring
QUANTMAP_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
    "success": "green",
    "dim": "dim",
    "bold": "bold",
    "highlight": "magenta",
})

_GLOBAL_CONSOLE: Console | None = None

def get_console(force_new: bool = False, force_utf8_if_bootstrap: bool = False) -> Console:
    """Returns a unified, capability-aware rich.Console.
    
    Arguments:
        force_new: Always create a fresh instance.
        force_utf8_if_bootstrap: Internal use for testing bootstrap states.
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
    console = target_console or get_console()
    console.print(f"\n[bold]Artifacts — {campaign_id}[/bold]")
    for a in artifacts:
        atype    = a.get("artifact_type", "")
        path     = a.get("path")
        exists   = a.get("exists", False)
        db_st    = a.get("db_status")

        if db_st == "complete":
            sym, color, label = SYM_OK,   "green",  "complete"
        elif db_st and db_st not in ("missing", "pending"):
            sym, color, label = SYM_WARN, "yellow", db_st
        elif exists:
            sym, color, label = SYM_OK,   "green",  "present"
        else:
            sym, color, label = SYM_FAIL, "red",    "not found"

        path_str = str(path) if path else "[dim]path unknown[/dim]"
        console.print(
            f"  [{color}]{sym}[/{color}] [dim]{atype}[/dim]"
            f"\n    {path_str}  [{color}]({label})[/{color}]"
        )
    console.print("")
