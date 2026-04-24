"""
QuantMap — Unified CLI Dispatcher

Usage:
  python quantmap.py --help
  python quantmap.py run --campaign <ID>
  python quantmap.py doctor
  python quantmap.py rescore <ID>
  python quantmap.py audit <ID1> <ID2>
  python quantmap.py list
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def bootstrap_terminal():
    """Force UTF-8 and handle plain-mode bootstrapping before rich/internals."""
    # 1. UTF-8 Force for Windows
    if sys.platform == "win32":
        # Force the environment variable for subprocesses
        os.environ["PYTHONUTF8"] = "1"
        # Reconfigure sys.stdout/stderr to handle UTF-8 symbols
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass

    # 2. Check for plain mode early (CLI flag or Env)
    # This allows src.ui to detect PLAIN_MODE correctly at import time
    if "--plain" in sys.argv or os.getenv("QUANTMAP_PLAIN") == "1":
        os.environ["QUANTMAP_PLAIN"] = "1"

# Run bootstrap BEFORE any internal imports
bootstrap_terminal()

# 1. Try script directory (standard for repo-local execution)
_SCRIPT_DIR = Path(__file__).parent.resolve()
load_dotenv(_SCRIPT_DIR / ".env")

# 2. Try Current Working Directory (standard for installed CLI tool)
load_dotenv(Path.cwd() / ".env")

# Determine Repo Root for internal path resolution
_REPO_ROOT = _SCRIPT_DIR if (_SCRIPT_DIR / "src").is_dir() else Path.cwd()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Version import is intentionally light enough to happen before dispatch.
try:
    from src.version import __version__, __methodology_version__
except ImportError:
    __version__ = "unknown"
    __methodology_version__ = "methodology unknown"


from src.settings_env import EnvPath, read_env_path, require_env_path  # noqa: E402


TOP_LEVEL_EPILOG = """Primary workflow:
  1. quantmap doctor                    # Verify environment readiness
  2. quantmap run --campaign <ID> --validate  # Pre-flight check
  3. quantmap run --campaign <ID>              # Execute
  4. quantmap list                           # Check results
  5. quantmap explain <ID> --evidence       # Technical briefing

Command family:
  * Health: status (fast pulse), doctor (deep check), self-test (tooling)
  * Campaign: run (execute), run --validate (pre-flight)
  * History: list, explain, compare, export, artifacts
  * ACPM: acpm info, acpm plan, acpm validate, acpm run

Run `quantmap <cmd> --help` for details on a specific command."""

RUN_EPILOG = """Examples:
  quantmap run --campaign B_low_sample --validate    # Pre-flight only
  quantmap run --campaign B_low_sample                 # Full run
  quantmap run --campaign NGL_sweep --mode standard    # Standard depth
  quantmap run --campaign NGL_sweep --values 30,80     # Subset
  quantmap run --campaign NGL_sweep --dry-run          # Dry run

Safety: This command modifies state (creates campaign artifacts).

Note: Redirected output (>) hides live progress.
To monitor redirected output in another terminal:
  Get-Content "<path>" -Tail 80 -Wait"""

DOCTOR_EPILOG = """Checks the current shell and local lab setup.

This command verifies:
  * Server binary and model file presence
  * Baseline YAML validity
  * Request JSON files
  * Lab directory structure
  * Defender and hardware configuration

When to use:
  * Before the first run
  * After path changes
  * When readiness is unclear
  * After `quantmap status` shows degradation"""

STATUS_EPILOG = """Provides a fast operational pulse:
  * Environment readiness (lab, server, model)
  * Campaign count and recent history
  * Database and artifact status

When to use:
  * Quick status check
  * Before `quantmap doctor` for detailed diagnostics
  * Not a substitute for `doctor` or `self-test`

See also: quantmap doctor (deep check), quantmap self-test (tooling)"""

SELFTEST_EPILOG = """Verifies QuantMap's internal tooling:
  * Python package integrity
  * Internal import paths
  * Module version alignment

This is NOT measurement readiness. It only verifies that the tooling itself is functional.
Use `quantmap doctor` to verify model and server readiness.

See also: quantmap doctor (full environment check), quantmap status (operational pulse)"""

LIST_EPILOG = """Shows campaign history, post-run status, and summary paths.

Tip: Full campaign IDs are shown in the footer for easy copying.
Use `quantmap artifacts <ID>` to see exact artifact locations."""

ACPM_EPILOG = """ACPM-guided campaign planning and execution.

This namespace provides ACPM-specific profiles and tiers for structured experimentation.

Examples:
  quantmap acpm info                              # List available profiles
  quantmap acpm plan --campaign NGL_sweep --profile Balanced    # Preview plan
  quantmap acpm validate --campaign NGL_sweep --profile Balanced  # Validate inputs
  quantmap acpm run --campaign NGL_sweep --profile Balanced --tier 1x  # Execute

Tip: Use `--validate` (validation) before running to catch input errors."""


def _load_lab_root() -> Path:
    return require_env_path(
        "QUANTMAP_LAB_ROOT",
        purpose="QuantMap lab root",
        recommendation="Set QUANTMAP_LAB_ROOT in .env, or pass --db/--output where supported.",
    )


def _env_path(name: str) -> Path | None:
    return read_env_path(name).path


def _env_detail(name: str) -> EnvPath:
    return read_env_path(name)


def _default_db_path() -> Path:
    return _load_lab_root() / "db" / "lab.sqlite"


def _default_results_path(*parts: str) -> Path:
    return _load_lab_root() / "results" / Path(*parts)


def _print_path_resolution_error(context: str, exc: Exception) -> None:
    print(f"error: {context}: {exc}")
    print("hint: pass --db/--output where supported, or run 'quantmap doctor' to diagnose local setup.")


def _blocked_label(value: EnvPath) -> str:
    return f"blocked ({value.message})"

def cmd_run(args):
    """Execute a benchmark campaign."""
    # Maps to src.runner.run_campaign or src.runner.validate_campaign
    try:
        from src import runner  # noqa: PLC0415
    except Exception as exc:
        _print_path_resolution_error("could not initialize run environment", exc)
        sys.exit(1)

    baseline_path = Path(args.baseline) if args.baseline else runner.BASELINE_YAML
    if not baseline_path.is_absolute():
        baseline_path = (_REPO_ROOT / baseline_path).resolve()

    # Parse --values override
    values_override = None
    if args.values:
        values_override = runner._parse_values_arg(args.values)

    # Normalize mode
    mode_flag = args.mode if args.mode not in (None, "full") else None

    if args.validate:
        ok = runner.validate_campaign(
            args.campaign,
            values_override=values_override,
            baseline_path=baseline_path,
            mode_flag=mode_flag
        )
        sys.exit(0 if ok else 1)

    runner.run_campaign(
        campaign_id=args.campaign,
        dry_run=args.dry_run,
        resume=args.resume,
        cycles_override=args.cycles,
        requests_per_cycle_override=args.requests_per_cycle,
        values_override=values_override,
        baseline_path=baseline_path,
        mode_flag=mode_flag
    )

def cmd_doctor(args):
    """Run environment health checks."""
    from src import doctor  # noqa: PLC0415

    env_details = {
        name: _env_detail(name)
        for name in ("QUANTMAP_SERVER_BIN", "QUANTMAP_MODEL_PATH", "QUANTMAP_LAB_ROOT")
    }
    doctor.run_doctor(
        env_details["QUANTMAP_SERVER_BIN"].path,
        env_details["QUANTMAP_MODEL_PATH"].path,
        env_details["QUANTMAP_LAB_ROOT"].path,
        fix=args.fix,
        env_details=env_details,
    )

def cmd_init(args):
    """Run interactive lab setup wizard."""
    from src import init
    init.run_init()

def cmd_selftest(args):
    """Run tool integrity trust suite."""
    from src import selftest
    selftest.run_selftest(live=args.live)

def cmd_status(args):
    """Display high-level operational status (Situation Room)."""
    from src import ui  # noqa: PLC0415
    
    console = ui.get_console()
    ui.print_banner("QuantMap: Operational Status")
    
    # Version/Identity
    console.print(f"  [bold]Versions:[/bold]        {__version__} ({__methodology_version__})")
    lab_detail = _env_detail("QUANTMAP_LAB_ROOT")
    lab_root = lab_detail.path
    if lab_root is not None:
        console.print(f"  [bold]Lab Root:[/bold]        {lab_root}")
    else:
        console.print(f"  [bold]Lab Root:[/bold]        [red]{_blocked_label(lab_detail)}[/red]")
    
    # Active Governance
    methodology_ok = False
    try:
        from src.governance import get_default_profile  # noqa: PLC0415

        profile = get_default_profile()
        methodology_ok = True
        console.print(f"  [bold]Current Methodology:[/bold] {profile.name} (v{profile.version})")
    except Exception as exc:
        console.print(f"  [bold]Current Methodology:[/bold] [red]blocked[/red] ({exc})")
    
    # DB Stats
    try:
        import sqlite3
        db_p = lab_root / "db" / "lab.sqlite" if lab_root is not None else None
        if db_p is not None and db_p.exists():
            conn = sqlite3.connect(db_p)
            count = conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
            conn.close()
            console.print(f"  [bold]Campaigns:[/bold]     {count} in database")
        elif db_p is None:
            console.print("  [bold]Campaigns:[/bold]     unavailable (lab root unavailable)")
        else:
            console.print("  [bold]Campaigns:[/bold]     0 (DB not found)")
    except Exception:
        console.print("  [bold]Campaigns:[/bold]     Unknown")

    if methodology_ok:
        console.print("  [bold]Historical Trust:[/bold] snapshot-complete runs remain DB-authoritative")
    else:
        console.print("  [bold]Historical Trust:[/bold] snapshot-complete runs remain readable from DB evidence")
        console.print("  [dim]Current-run scoring and explicit current-input rescore are blocked until methodology files are fixed.[/dim]")

    try:
        from src.telemetry_policy import probe_provider_readiness  # noqa: PLC0415

        provider_readiness = probe_provider_readiness()
        exec_env = provider_readiness.get("execution_environment") or {}
        support_tier = exec_env.get("support_tier", "unknown")
        measurement_grade = exec_env.get("measurement_grade", "unknown")
        console.print(
            f"  [bold]Execution Support:[/bold] {support_tier} "
            f"(measurement-grade: {measurement_grade})"
        )
        if support_tier == "wsl_degraded":
            reasons = ", ".join(exec_env.get("degraded_reasons") or [])
            console.print(f"  [yellow]WSL degraded:[/yellow] {reasons or 'explicit degraded execution target'}")
    except Exception as exc:
        console.print(f"  [bold]Execution Support:[/bold] unknown ({exc})")
        
    console.print(f"\n[bold]{ui.SYM_DIVIDER}[/bold] Readiness")
    # Quick doctor summary (silent)
    from src import doctor  # noqa: PLC0415
    from src.diagnostics import DiagnosticReport, Readiness  # noqa: PLC0415

    report = DiagnosticReport("Status Pulse")
    server_detail = _env_detail("QUANTMAP_SERVER_BIN")
    model_detail = _env_detail("QUANTMAP_MODEL_PATH")
    report.add(doctor.check_lab_structure(lab_root, detail=lab_detail.message))
    report.add(doctor.check_registry_load())
    report.add(doctor.check_default_profile_load())
    report.add(doctor.check_server_binary(server_detail.path, detail=server_detail.message))
    report.add(doctor.check_model_path(model_detail.path, detail=model_detail.message))
    report.add(doctor.check_telemetry_provider_readiness())
    
    final = report.readiness
    if final == Readiness.READY:
        console.print(f"  [green]{ui.SYM_OK} Environment Ready[/green]")
        ui.print_next_actions([
            "quantmap run --campaign <ID> --validate",
            "quantmap list",
        ])
    elif final == Readiness.WARNINGS:
        console.print(f"  [yellow]{ui.SYM_WARN} Ready with Warnings (run 'quantmap doctor' for details)[/yellow]")
        ui.print_next_actions([
            "quantmap doctor",
            "quantmap run --campaign <ID> --validate",
        ])
    else:
        console.print(f"  [red]{ui.SYM_FAIL} BLOCKED (run 'quantmap doctor' to diagnose)[/red]")
        ui.print_next_actions([
            "quantmap doctor",
            "quantmap run --campaign <ID> --validate",
        ])

    console.print("")

def cmd_rescore(args):
    """Re-play analysis/scoring logic on existing campaign data."""
    import yaml
    try:
        import rescore as rescore_mod  # noqa: PLC0415
    except Exception as exc:
        _print_path_resolution_error("could not initialize rescore environment", exc)
        sys.exit(1)
    
    baseline_path = Path(args.baseline) if args.baseline else rescore_mod.BASELINE_YAML
    if not baseline_path.exists():
        print(f"error: baseline YAML not found: {baseline_path}")
        sys.exit(1)
        
    with open(baseline_path, encoding="utf-8") as f:
        baseline = yaml.safe_load(f)

    if args.all:
        campaign_ids = rescore_mod.get_completed_campaigns()
        if not campaign_ids:
            print("error: no completed campaigns found in database.")
            sys.exit(1)
    else:
        campaign_ids = args.campaigns

    total = len(campaign_ids)
    results = {}
    for idx, cid in enumerate(campaign_ids, start=1):
        print(f"[{idx}/{total}] Re-scoring: {cid}")
        results[cid] = rescore_mod.rescore(
            cid,
            baseline,
            force_new_anchors=args.force_new_anchors,
            current_input=args.current_input,
        )

    failed = [c for c, ok in results.items() if not ok]
    if failed:
        print(f"Failed campaigns: {failed}")
        sys.exit(1)
    print("\nRe-score complete.")

def cmd_audit(args):
    """Verify methodological integrity between two campaigns."""
    from src import audit_methodology  # noqa: PLC0415

    try:
        db_path = args.db or _default_db_path()
    except Exception as exc:
        _print_path_resolution_error("could not resolve audit DB path", exc)
        sys.exit(1)
    m1 = audit_methodology.get_methodology(args.campaign1, db_path)
    m2 = audit_methodology.get_methodology(args.campaign2, db_path)

    if not m1:
        print(f"Error: No methodology snapshot found for {args.campaign1}")
        sys.exit(1)
    if not m2:
        print(f"Error: No methodology snapshot found for {args.campaign2}")
        sys.exit(1)

    ok = audit_methodology.compare_methodologies(args.campaign1, m1, args.campaign2, m2)
    sys.exit(0 if ok else 1)


def cmd_list(args):
    """List all campaigns and their status."""
    try:
        from src import runner  # noqa: PLC0415
    except Exception as exc:
        _print_path_resolution_error("could not resolve campaign list DB path", exc)
        sys.exit(1)

    runner.list_campaigns()


ARTIFACTS_EPILOG = """Examples:
  quantmap artifacts B_low_sample
  quantmap artifacts NGL_sweep --db /path/to/lab.sqlite
"""


def cmd_artifacts(args):
    """Discover artifact paths and DB-registered status for a campaign."""
    from src import ui  # noqa: PLC0415
    from src.artifact_paths import get_campaign_artifact_paths  # noqa: PLC0415

    console = ui.get_console()
    try:
        lab_root = _load_lab_root()
        db_path = args.db or _default_db_path()
    except Exception as exc:
        _print_path_resolution_error("could not resolve lab root or DB path", exc)
        sys.exit(1)

    artifacts = get_campaign_artifact_paths(lab_root, args.campaign, db_path=db_path)
    if not artifacts:
        console.print(f"[yellow]No artifact paths resolved for: {args.campaign}[/yellow]")
        sys.exit(1)

    ui.print_banner(f"Artifacts: {args.campaign}")
    ui.render_artifact_block(args.campaign, artifacts, target_console=console)


ACPM_EPILOG = """ACPM-guided campaign planning and execution.

This namespace provides ACPM-specific profiles and tiers for structured experimentation.

Examples:
  quantmap acpm info                              # List available profiles
  quantmap acpm plan --campaign NGL_sweep --profile Balanced    # Preview plan
  quantmap acpm validate --campaign NGL_sweep --profile Balanced  # Validate inputs
  quantmap acpm run --campaign NGL_sweep --profile Balanced --tier 1x  # Execute

Tip: Use `--validate` (validation) before running to catch input errors."""


def cmd_acpm_info(args):
    """Show available ACPM profiles or details for a specific profile."""
    from src import ui  # noqa: PLC0415
    from src.acpm_planning import V1_ACPM_PROFILE_IDS, get_acpm_profile_info  # noqa: PLC0415

    console = ui.get_console()

    if args.profile:
        try:
            info = get_acpm_profile_info(args.profile)
        except ValueError:
            console.print(f"[red]Unknown profile: {args.profile}[/red]")
            console.print(f"Valid profiles: {', '.join(sorted(V1_ACPM_PROFILE_IDS))}")
            sys.exit(1)
        ui.print_banner(f"ACPM Profile: {info['display_label']}")
        console.print(f"  Profile ID:     {args.profile}")
        console.print(f"  Display name:   {info['display_name']}")
        console.print(f"  Lens:           {info['lens_description']}")
        console.print(f"  Scoring profile: {info['scoring_profile_name']}")
        console.print("")
        return

    ui.print_banner("ACPM Profiles")
    console.print("  Available profiles for ACPM planning:\n")
    for pid in sorted(V1_ACPM_PROFILE_IDS):
        info = get_acpm_profile_info(pid)
        console.print(f"  [bold]{info['display_label']}[/bold] — {info['lens_description']}")
    console.print("")
    console.print("  Use --profile <name> to see details for a specific profile.")
    console.print("")


def cmd_acpm_plan(args):
    """Preview an ACPM run plan without executing."""
    from src import ui  # noqa: PLC0415
    from src.acpm_planning import (  # noqa: PLC0415
        V1_ACPM_PROFILE_IDS,
        compile_acpm_plan,
    )
    from src.runner import CAMPAIGNS_DIR

    console = ui.get_console()

    campaign_path = CAMPAIGNS_DIR / f"{args.campaign}.yaml"
    if not campaign_path.is_file():
        console.print(f"[red]Campaign not found: {args.campaign}[/red]")
        console.print("Hint: use `quantmap list` to see available campaign IDs.")
        sys.exit(1)

    import yaml
    with open(campaign_path, encoding="utf-8") as f:
        campaign = yaml.safe_load(f)

    if args.profile not in V1_ACPM_PROFILE_IDS:
        console.print(f"[red]Unknown profile: {args.profile}[/red]")
        console.print(f"Valid profiles: {', '.join(sorted(V1_ACPM_PROFILE_IDS))}")
        sys.exit(1)

    try:
        plan_output = compile_acpm_plan(
            campaign,
            profile_name=args.profile,
            repeat_tier=args.tier,
        )
    except Exception as exc:
        console.print(f"[red]Plan compilation failed: {exc}[/red]")
        sys.exit(1)

    ui.print_banner(f"ACPM Plan Preview: {args.campaign}")
    ui.render_acpm_plan_preview(plan_output, target_console=console)


def cmd_acpm_validate(args):
    """Validate ACPM inputs without executing."""
    from src import ui  # noqa: PLC0415
    from src.acpm_planning import (  # noqa: PLC0415
        V1_ACPM_PROFILE_IDS,
        REPEAT_TIER_1X,
        REPEAT_TIER_3X,
        REPEAT_TIER_5X,
        check_campaign_applicability,
        get_acpm_profile_info,
    )
    from src.runner import CAMPAIGNS_DIR

    console = ui.get_console()
    _ALL_TIERS = {REPEAT_TIER_1X, REPEAT_TIER_3X, REPEAT_TIER_5X}

    campaign_path = CAMPAIGNS_DIR / f"{args.campaign}.yaml"
    campaign_exists = campaign_path.is_file()

    profile_ok = args.profile in V1_ACPM_PROFILE_IDS
    tier_ok = args.tier in _ALL_TIERS

    profile_info = None
    if profile_ok:
        try:
            profile_info = get_acpm_profile_info(args.profile)
        except ValueError:
            profile_ok = False

    applicability = check_campaign_applicability({})
    if campaign_exists:
        import yaml
        with open(campaign_path, encoding="utf-8") as f:
            campaign = yaml.safe_load(f)
        applicability = check_campaign_applicability(campaign)

    ui.render_acpm_validate_result(
        args.campaign,
        args.profile,
        args.tier,
        applicability,
        profile_info=profile_info,
        tier_ok=tier_ok,
        profile_ok=profile_ok,
        campaign_exists=campaign_exists,
        target_console=console,
    )
    sys.exit(0 if (campaign_exists and profile_ok and tier_ok and applicability.applicable) else 1)


def cmd_acpm_run(args):
    """Execute an ACPM-guided campaign."""
    from src import ui  # noqa: PLC0415
    from src.acpm_planning import (  # noqa: PLC0415
        V1_ACPM_PROFILE_IDS,
        REPEAT_TIER_1X,
        REPEAT_TIER_3X,
        REPEAT_TIER_5X,
        compile_acpm_plan,
        check_campaign_applicability,
    )
    from src import runner  # noqa: PLC0415
    from src.runner import CAMPAIGNS_DIR

    console = ui.get_console()
    _ALL_TIERS = {REPEAT_TIER_1X, REPEAT_TIER_3X, REPEAT_TIER_5X}

    campaign_path = CAMPAIGNS_DIR / f"{args.campaign}.yaml"
    if not campaign_path.is_file():
        console.print(f"[red]Campaign not found: {args.campaign}[/red]")
        console.print("Hint: use `quantmap list` to see available campaign IDs.")
        sys.exit(1)

    if args.profile not in V1_ACPM_PROFILE_IDS:
        console.print(f"[red]Unknown profile: {args.profile}[/red]")
        console.print(f"Valid profiles: {', '.join(sorted(V1_ACPM_PROFILE_IDS))}")
        sys.exit(1)

    if args.tier not in _ALL_TIERS:
        console.print(f"[red]Unknown tier: {args.tier}[/red]")
        console.print(f"Valid tiers: {', '.join(sorted(_ALL_TIERS))}")
        sys.exit(1)

    import yaml
    with open(campaign_path, encoding="utf-8") as f:
        campaign = yaml.safe_load(f)

    applicability = check_campaign_applicability(campaign)
    if not applicability.applicable:
        console.print(f"[red]Campaign '{args.campaign}' is not ACPM-applicable: {applicability.reason}[/red]")
        console.print("Hint: ACPM only supports campaigns with supported variables.")
        sys.exit(1)

    plan_compiled = compile_acpm_plan(campaign, args.profile, args.tier)

    execution_inputs = plan_compiled.to_execution_inputs()
    run_values = execution_inputs.get("selected_values")
    scope_authority = execution_inputs.get("scope_authority")
    scoring_profile_name = execution_inputs.get("scoring_profile_name")
    planning_metadata = plan_compiled.to_planning_metadata_snapshot()
    selected_config_ids = execution_inputs.get("selected_config_ids", [])

    n_runs = len(selected_config_ids) if selected_config_ids else 1
    cycles_override = n_runs
    requests_per_cycle_override = None

    if args.validate:
        console.print("[bold]Running pre-flight validation...[/bold]")
        ok = runner.validate_campaign(
            args.campaign,
            values_override=run_values,
            baseline_path=runner.BASELINE_YAML,
            mode_flag=None,
        )
        sys.exit(0 if ok else 1)

    if args.dry_run:
        ui.print_banner(f"ACPM Dry Run: {args.campaign}")
        console.print(f"  Campaign:   {args.campaign}")
        console.print(f"  Profile:     {args.profile}")
        console.print(f"  Tier:       {args.tier}")
        console.print(f"  Scope:      {scope_authority}")
        console.print(f"  Values:     {run_values}")
        console.print(f"  Cycles:     {cycles_override}")
        console.print(f"  Scoring:    {scoring_profile_name}")
        sys.exit(0)

    console.print("[bold]Executing ACPM campaign...[/bold]")
    runner.run_campaign(
        campaign_id=args.campaign,
        dry_run=False,
        resume=True,
        cycles_override=cycles_override,
        requests_per_cycle_override=requests_per_cycle_override,
        values_override=run_values,
        baseline_path=runner.BASELINE_YAML,
        mode_flag=None,
        scope_authority=scope_authority,
        acpm_planning_metadata=planning_metadata,
    )
    sys.exit(0)


def cmd_explain(args):
    """Generate a technical briefing explaining a campaign outcome."""
    from src import explain  # noqa: PLC0415

    try:
        db_p = args.db or _default_db_path()
    except Exception as exc:
        _print_path_resolution_error("could not resolve explain DB path", exc)
        sys.exit(1)
    briefing = explain.get_campaign_briefing(args.campaign, db_p, evidence_mode=args.evidence)
    explain.print_briefing(briefing, evidence_mode=args.evidence)

def cmd_explain_compare(args):
    """Generate a technical briefing explaining narrative shifts between two campaigns."""
    from src import explain  # noqa: PLC0415

    try:
        db_p = args.db or _default_db_path()
    except Exception as exc:
        _print_path_resolution_error("could not resolve explain DB path", exc)
        sys.exit(1)
    briefing = explain.get_compare_briefing(args.campaign1, args.campaign2, db_p)
    explain.print_briefing(briefing)

def cmd_export(args):
    """Export a campaign to a portable .qmap case file."""
    from src import export as export_mod  # noqa: PLC0415

    try:
        db_p = args.db or _default_db_path()
        output_path = Path(args.output) if args.output else _default_results_path(f"{args.campaign}.qmap")
    except Exception as exc:
        _print_path_resolution_error("could not resolve export paths", exc)
        sys.exit(1)
    
    ok = export_mod.run_export(
        args.campaign, 
        db_p, 
        output_path, 
        lite=args.lite, 
        strip_env=args.strip_env,
        redaction_root=_env_path("QUANTMAP_LAB_ROOT") if args.strip_env else None,
    )
    if not ok:
        sys.exit(1)

def cmd_about(args):
    """Display rich system and provenance information."""
    from src import ui  # noqa: PLC0415
    
    console = ui.get_console()
    ui.print_banner("QuantMap: About & Provenance")
    
    console.print(f"  [bold]Software Version:[/bold]      {__version__}")
    console.print(f"  [bold]Methodology Version:[/bold]   {__methodology_version__}")
    try:
        from src.governance import get_builtin_registry, get_default_profile  # noqa: PLC0415

        profile = get_default_profile()
        registry = get_builtin_registry()
        console.print(f"  [bold]Current Profile:[/bold]       {profile.name} (v{profile.version})")
        console.print(f"  [bold]Registry Metrics:[/bold]      {len(registry)} defined")
    except Exception as exc:
        console.print(f"  [bold]Current Methodology:[/bold]   [red]blocked[/red] ({exc})")

    lab_root = _env_path("QUANTMAP_LAB_ROOT")
    console.print(f"  [bold]Lab Root:[/bold]              {lab_root or 'unavailable'}")
    console.print(f"  [bold]DB Path:[/bold]               {(lab_root / 'db' / 'lab.sqlite') if lab_root else 'unavailable'}")

    console.print(f"\n[green]{ui.SYM_OK} Software identity available.[/green]\n")

def cmd_compare(args):
    """Forensic comparison between two campaigns."""
    from src import compare
    from src import report_compare
    from src import ui

    console = ui.get_console()
    
    # 1. Generate Structured Analysis
    try:
        db_p = args.db or _default_db_path()
        result = compare.generate_compare_result(args.campaign1, args.campaign2, db_p)
    except Exception as e:
        console.print(f"[bold red]{ui.SYM_FAIL} Comparison Analysis Failed:[/bold red] {e}")
        # import traceback; traceback.print_exc()
        sys.exit(1)

    # 2. Methodology Gate
    if result.methodology["grade"] == "mismatch":
        console.print(f"\n[bold red]{ui.SYM_FAIL} METHODOLOGY MISMATCH DETECTED[/bold red]")
        console.print("  [red]Campaigns use different anchors or Registry versions.[/red]")
        if not args.force:
            console.print("\n[yellow]Comparison blocked for methodological integrity. Use --force to override.[/yellow]")
            sys.exit(1)
        console.print("\n[red bold]WARNING: Proceeding with --force despite mismatch. Deltas may be invalid.[/red bold]\n")
    elif result.methodology["grade"] == "warnings":
        console.print(f"\n[bold yellow]{ui.SYM_WARN} METHODOLOGY WARNING: Minor anchor drift detected.[/bold yellow]\n")

    # 3. Print Console Summary
    ui.print_banner(f"Comparison Summary: {args.campaign1} vs {args.campaign2}")
    console.print(f"  Winner Shift:      [bold]{_fmt(result.winner_shift_tg_pct, '+.1f')}%[/bold] TG")
    console.print(f"  Median Shared Δ:   [bold]{_fmt(result.median_shared_tg_shift_pct, '+.1f')}%[/bold] TG")
    console.print(f"  Reach Delta:       [bold]{len(result.gained_in_b) - len(result.lost_in_b):+d}[/bold] configs")
    
    # 4. Render and Save Persistent Report
    output_path = args.output
    if not output_path:
        # Default: artifacts/reports/comparisons/<pair>/compare.md
        try:
            from src.artifact_paths import compare_default_report_path  # noqa: PLC0415

            output_path = compare_default_report_path(
                _load_lab_root(),
                args.campaign1,
                args.campaign2,
            )
        except Exception as exc:
            _print_path_resolution_error("could not resolve comparison output path", exc)
            sys.exit(1)
    else:
        output_path = Path(output_path)

    report_compare.save_compare_report(result, output_path)
    console.print(f"\n[green]{ui.SYM_OK} Forensic comparison report written to:[/green]")
    console.print(f"  [cyan]{output_path}[/cyan]\n")

def _fmt(val, spec, missing="—"):
    if val is None:
        return missing
    try:
        return format(val, spec)
    except Exception:
        return missing

def main():
    parser = argparse.ArgumentParser(
        prog="quantmap",
        description="QuantMap: LLM Quantization and inference benchmarking governance tool.",
        epilog=TOP_LEVEL_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    # Global flags
    parser.add_argument("--plain", action="store_true", help="Use plain ASCII output and disable emojis")
    parser.add_argument(
        "--version", 
        action="version", 
        version=f"QuantMap Software {__version__}\n{__methodology_version__}"
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands")

    # --- RUN ---
    run_parser = subparsers.add_parser(
        "run",
        help="Execute or validate a benchmark campaign",
        description="Validate or run a campaign on the existing QuantMap shell.",
        epilog=RUN_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    run_parser.add_argument("--campaign", required=True, help="Campaign ID (e.g. C01_threads_batch)")
    run_parser.add_argument("--baseline", help="Path to baseline.yaml override")
    run_parser.add_argument("--validate", action="store_true", help="Perform pre-flight checks and exit")
    run_parser.add_argument("--dry-run", action="store_true", help="Simulate campaign flow without measurements")
    run_parser.add_argument("--resume", action="store_true", help="Resume an interrupted campaign")
    run_parser.add_argument("--cycles", type=int, help="Override cycles_per_config")
    run_parser.add_argument("--requests-per-cycle", type=int, help="Override requests_per_cycle")
    run_parser.add_argument("--mode", choices=["full", "standard", "quick"], help="Run mode depth")
    run_parser.add_argument("--values", help="Comma-separated subset of values to test")
    run_parser.set_defaults(func=cmd_run)

    # --- DOCTOR ---
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Perform environment health checks",
        description="Check local shell, lab, backend, and telemetry readiness.",
        epilog=DOCTOR_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    doctor_parser.add_argument("--fix", action="store_true", help="Automate safe environment repairs")
    doctor_parser.set_defaults(func=cmd_doctor)

    # --- INIT ---
    init_parser = subparsers.add_parser("init", help="Interactive lab setup wizard")
    init_parser.set_defaults(func=cmd_init)

    # --- SELF-TEST ---
    selftest_parser = subparsers.add_parser(
        "self-test",
        help="Verify QuantMap tooling integrity",
        description="Run internal QuantMap tooling checks without a campaign run.",
        epilog=SELFTEST_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    selftest_parser.add_argument("--live", action="store_true", help="Include live server/telemetry validation")
    selftest_parser.set_defaults(func=cmd_selftest)

    # --- STATUS ---
    status_parser = subparsers.add_parser(
        "status",
        help="Display high-level operational status",
        description="Show a quick readiness pulse, current methodology, and campaign count.",
        epilog=STATUS_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    status_parser.set_defaults(func=cmd_status)

    # --- RESCORE ---
    rescore_parser = subparsers.add_parser("rescore", help="Re-process data for existing campaigns")
    rescore_parser.add_argument("campaigns", nargs="*", help="Campaign ID(s) to rescore")
    rescore_parser.add_argument("--all", action="store_true", help="Rescore all completed campaigns")
    rescore_parser.add_argument("--baseline", help="Path to baseline.yaml override")
    rescore_parser.add_argument("--force-new-anchors", action="store_true", help="Force re-anchoring to current Registry values")
    rescore_parser.add_argument("--current-input", action="store_true", help="Explicitly use current files when a complete historical snapshot is unavailable")
    rescore_parser.set_defaults(func=cmd_rescore)

    # --- AUDIT ---
    audit_parser = subparsers.add_parser("audit", help="Audit methodological integrity between two campaigns")
    audit_parser.add_argument("campaign1", help="First campaign ID")
    audit_parser.add_argument("campaign2", help="Second campaign ID")
    audit_parser.add_argument("--db", type=Path, help="Path to lab.sqlite override")
    audit_parser.set_defaults(func=cmd_audit)

    # --- LIST ---
    list_parser = subparsers.add_parser(
        "list",
        help="List campaign history and status",
        description="List prior campaigns and surface the key follow-up commands.",
        epilog=LIST_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    list_parser.set_defaults(func=cmd_list)

    # --- ABOUT ---
    about_parser = subparsers.add_parser("about", help="Display version and system provenance")
    about_parser.set_defaults(func=cmd_about)

    # --- COMPARE ---
    compare_parser = subparsers.add_parser("compare", help="Perform forensic comparison between two campaigns")
    compare_parser.add_argument("campaign1", help="Baseline campaign ID")
    compare_parser.add_argument("campaign2", help="Subject campaign ID")
    compare_parser.add_argument("--db", type=Path, help="Path to lab.sqlite override")
    compare_parser.add_argument("--output", help="Path to save comparison Markdown report")
    compare_parser.add_argument("--force", action="store_true", help="Proceed despite methodology mismatch")
    compare_parser.set_defaults(func=cmd_compare)

    # --- EXPLAIN ---
    explain_parser = subparsers.add_parser("explain", help="Technical briefing for a campaign outcome")
    explain_parser.add_argument("campaign", help="Campaign ID to explain")
    explain_parser.add_argument("--db", type=Path, help="Path to lab.sqlite override")
    explain_parser.add_argument("--evidence", action="store_true", help="Include denser factual audit basis")
    explain_parser.set_defaults(func=cmd_explain)

    # --- EXPLAIN-COMPARE ---
    explain_compare_parser = subparsers.add_parser("explain-compare", help="Technical briefing for comparative shifts")
    explain_compare_parser.add_argument("campaign1", help="Baseline campaign ID")
    explain_compare_parser.add_argument("campaign2", help="Subject campaign ID")
    explain_compare_parser.add_argument("--db", type=Path, help="Path to lab.sqlite override")
    explain_compare_parser.set_defaults(func=cmd_explain_compare)

    # --- EXPORT ---
    export_parser = subparsers.add_parser("export", help="Export a campaign to a portable .qmap case file")
    export_parser.add_argument("campaign", help="Campaign ID to export")
    export_parser.add_argument("--output", help="Output path (e.g. bundle.qmap)")
    export_parser.add_argument("--lite", action="store_true", help="Exclude raw telemetry for smaller bundle")
    export_parser.add_argument("--strip-env", action="store_true", help="Redact local paths and environment info")
    export_parser.add_argument("--db", type=Path, help="Path to lab.sqlite override")
    export_parser.set_defaults(func=cmd_export)

    # --- ARTIFACTS ---
    artifacts_parser = subparsers.add_parser(
        "artifacts",
        help="Discover artifact paths and status for a campaign",
        description="Show the disk location and DB-registered status of all four canonical artifacts.",
        epilog=ARTIFACTS_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    artifacts_parser.add_argument("campaign", help="Campaign ID")
    artifacts_parser.add_argument("--db", type=Path, help="Path to lab.sqlite override")
    artifacts_parser.set_defaults(func=cmd_artifacts)

    # --- ACPM ---
    acpm_parser = subparsers.add_parser(
        "acpm",
        help="ACPM planner entry: plan, validate, and profile discovery",
        description="ACPM-guided campaign planning. Preview a plan, validate inputs, or explore available profiles.",
        epilog=ACPM_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    acpm_subparsers = acpm_parser.add_subparsers(dest="acpm_command", required=True, help="ACPM subcommands")

    acpm_info_parser = acpm_subparsers.add_parser(
        "info",
        help="List available ACPM profiles or show details for a specific profile",
        description="List all available ACPM profiles, or show details for a named profile.",
    )
    acpm_info_parser.add_argument("--profile", help="Specific profile ID (e.g. Balanced, T/S, TTFT)")
    acpm_info_parser.set_defaults(func=cmd_acpm_info)

    acpm_plan_parser = acpm_subparsers.add_parser(
        "plan",
        help="Preview an ACPM run plan without executing",
        description="Compile and preview the effective ACPM plan for a campaign/profile/tier combination without running it.",
    )
    acpm_plan_parser.add_argument("--campaign", required=True, help="Campaign ID")
    acpm_plan_parser.add_argument("--profile", required=True, help="ACPM profile (Balanced, T/S, TTFT)")
    acpm_plan_parser.add_argument(
        "--tier",
        default="1x",
        help="Repeat tier (1x, 3x, 5x). 1x=scaffolded quick, 3x=standard, 5x=full. Default: 1x",
    )
    acpm_plan_parser.set_defaults(func=cmd_acpm_plan)

    acpm_validate_parser = acpm_subparsers.add_parser(
        "validate",
        help="Validate ACPM inputs without executing",
        description="Check that a campaign, profile, and repeat tier combination is valid for ACPM planning.",
    )
    acpm_validate_parser.add_argument("--campaign", required=True, help="Campaign ID")
    acpm_validate_parser.add_argument("--profile", required=True, help="ACPM profile (Balanced, T/S, TTFT)")
    acpm_validate_parser.add_argument(
        "--tier",
        default="1x",
        help="Repeat tier (1x, 3x, 5x). Default: 1x",
    )
    acpm_validate_parser.set_defaults(func=cmd_acpm_validate)

    acpm_run_parser = acpm_subparsers.add_parser(
        "run",
        help="Execute an ACPM-guided campaign",
        description="Compile an ACPM plan and execute it via the runner.",
    )
    acpm_run_parser.add_argument("--campaign", required=True, help="Campaign ID")
    acpm_run_parser.add_argument("--profile", required=True, help="ACPM profile (Balanced, T/S, TTFT)")
    acpm_run_parser.add_argument(
        "--tier",
        default="1x",
        help="Repeat tier (1x, 3x, 5x). Default: 1x",
    )
    acpm_run_parser.add_argument(
        "--validate",
        action="store_true",
        help="Run pre-flight validation only, skip execution",
    )
    acpm_run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show plan without executing",
    )
    acpm_run_parser.set_defaults(func=cmd_acpm_run)

    args = parser.parse_args()

    # Ensure plain mode is propagated if flag used
    if args.plain:
        os.environ["QUANTMAP_PLAIN"] = "1"

    args.func(args)

if __name__ == "__main__":
    main()
