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


from src.settings_env import EnvPath, read_env_path, require_env_path


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
            console.print(f"  [bold]Campaigns:[/bold]     0 (DB not found)")
    except Exception:
        console.print(f"  [bold]Campaigns:[/bold]     Unknown")

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
    elif final == Readiness.WARNINGS:
        console.print(f"  [yellow]{ui.SYM_WARN} Ready with Warnings (run 'quantmap doctor' for details)[/yellow]")
    else:
        console.print(f"  [red]{ui.SYM_FAIL} BLOCKED (run 'quantmap doctor' to diagnose)[/red]")

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
        console.print(f"  [red]Campaigns use different anchors or Registry versions.[/red]")
        if not args.force:
            console.print(f"\n[yellow]Comparison blocked for methodological integrity. Use --force to override.[/yellow]")
            sys.exit(1)
        console.print(f"\n[red bold]WARNING: Proceeding with --force despite mismatch. Deltas may be invalid.[/red bold]\n")
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
    if val is None: return missing
    try:
        return format(val, spec)
    except Exception:
        return missing

import argparse
import os
import sys
from pathlib import Path

# ... bootstrap code exists above ...

def main():
    parser = argparse.ArgumentParser(
        prog="quantmap",
        description="QuantMap: LLM Quantization & Inference Benchmarking Governance Tool."
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
    run_parser = subparsers.add_parser("run", help="Execute or validate a benchmark campaign")
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
    doctor_parser = subparsers.add_parser("doctor", help="Perform environment health checks")
    doctor_parser.add_argument("--fix", action="store_true", help="Automate safe environment repairs")
    doctor_parser.set_defaults(func=cmd_doctor)

    # --- INIT ---
    init_parser = subparsers.add_parser("init", help="Interactive lab setup wizard")
    init_parser.set_defaults(func=cmd_init)

    # --- SELF-TEST ---
    selftest_parser = subparsers.add_parser("self-test", help="Verify tool integrity suite")
    selftest_parser.add_argument("--live", action="store_true", help="Include live server/telemetry validation")
    selftest_parser.set_defaults(func=cmd_selftest)

    # --- STATUS ---
    status_parser = subparsers.add_parser("status", help="Display high-level operational status")
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
    list_parser = subparsers.add_parser("list", help="List campaign history and status")
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

    args = parser.parse_args()
    
    # Ensure plain mode is propagated if flag used
    if args.plain:
        os.environ["QUANTMAP_PLAIN"] = "1"
        
    args.func(args)

if __name__ == "__main__":
    main()
