"""
QuantMap — runner.py

Campaign orchestrator. Runs one campaign YAML from start to finish:
  1. Loads baseline.yaml + campaign YAML, validates purity (one variable only)
  2. Performs telemetry startup check (ABORT if ABORT-tier metrics missing)
  3. Records campaign start snapshot
  4. For each config:
       a. Enforces inter-config cooldown (min 300s + temperature gate)
       b. For each cycle (1–5):
            - Starts llama-server via server.py context manager
            - Runs requests_per_cycle requests per cycle.
              Non-final cycles: all speed_short (1 cold + N−1 warm).
              Final cycle only: last request is speed_medium instead of speed_short.
              Quick mode (1 cycle): the only cycle IS the final cycle — it runs
              1 cold speed_short + 4 warm speed_short + 1 warm speed_medium.
            - Telemetry runs in background throughout
            - Writes results to raw.jsonl + lab.sqlite
            - Marks cycle invalid on any crash; resumes from cycle boundary
       c. Checks speed_medium degradation flag (>5% relative)
  5. On completion: writes campaign summary and calls analyze/score/report

CRASH RECOVERY:
    state/progress.json is updated before each cycle starts and after each
    config completes. On restart, completed configs are skipped and the runner
    resumes at cycle boundary. Partial cycles always restart from request 1
    (never mid-cycle).

CAMPAIGN PURITY:
    runner.py raises CampaignPurityViolationError if the campaign YAML changes
    more than one field from baseline.yaml. One variable per campaign — always.

LOGGING:
    Every significant event is logged at INFO level. Full request records,
    all server stdout/stderr, and all telemetry data are written to disk.
    Nothing is discarded.

USAGE:
    python -m src.runner --campaign C01_threads_batch [--dry-run] [--resume]
    python -m src.runner --campaign NGL_sweep --mode quick      # Quick mode (all values, 1 cycle)
    python -m src.runner --campaign NGL_sweep --mode standard   # Standard mode (all values, reduced repetition)
    python -m src.runner --campaign NGL_sweep --values 30,80    # Custom mode (isolated)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv  # type: ignore[import]
from rich.console import Console  # type: ignore[import]
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn  # type: ignore[import]
from rich.table import Table  # type: ignore[import]

load_dotenv()

# Internal modules
from src.config import CONFIGS_DIR, DEFAULT_HOST, LAB_ROOT, REQUESTS_DIR  # noqa: E402
from src.measure import load_request_payload, measure_request_sync, RequestOutcome
from src import telemetry as tele
from src.db import init_db, get_connection, write_request, write_raw_jsonl
from src.run_plan import RunPlan, resolve_run_mode, STANDARD_CYCLES_PER_CONFIG, QUICK_CYCLES_PER_CONFIG  # noqa: E402
from src.score import ELIMINATION_FILTERS  # noqa: E402 — used in dry-run summary

console = Console()
logger = logging.getLogger(__name__)

# Repository root — src/runner.py is one level below the repo root.
# Used to resolve request file paths relative to the repo (not LAB_ROOT).
_REPO_ROOT: Path = Path(__file__).parent.parent

# Runtime outputs always go into LAB_ROOT.
# These module-level constants are the DEFAULT (used when no --baseline override is
# active). Inside run_campaign / _validate_campaign, the effective lab root is
# derived by _derive_lab_root() and local variables shadow these names.
RESULTS_DIR = LAB_ROOT / "results"
LOGS_DIR = LAB_ROOT / "logs"
DB_DIR = LAB_ROOT / "db"
STATE_DIR = LAB_ROOT / "state"
DB_PATH = DB_DIR / "lab.sqlite"
STATE_FILE = STATE_DIR / "progress.json"

BASELINE_YAML = CONFIGS_DIR / "baseline.yaml"
CAMPAIGNS_DIR = CONFIGS_DIR / "campaigns"


# ---------------------------------------------------------------------------
# Per-baseline lab root derivation
# ---------------------------------------------------------------------------

def _derive_lab_root(baseline_path: Path) -> Path:
    """
    Derive the effective lab root for a given baseline file.

    Rules:
      - Default baseline (configs/baseline.yaml): use LAB_ROOT unchanged.
        This is the zero-change path for existing users.
      - Any other --baseline <path>: return
        LAB_ROOT / "profiles" / <baseline_stem>
        e.g. configs/baselines/devstral_small_2507_q5_k_m.yaml
             -> <LAB_ROOT>/profiles/devstral_small_2507_q5_k_m/

    The stem of the baseline filename becomes the namespace so each model
    gets fully isolated DB, logs, results, and state without any manual
    .env edits.
    """
    if baseline_path.resolve() == BASELINE_YAML.resolve():
        return LAB_ROOT
    return LAB_ROOT / "profiles" / baseline_path.stem


# ---------------------------------------------------------------------------
# Effective run identity for targeted executions
# ---------------------------------------------------------------------------

def _derive_effective_campaign_id(
    campaign_id: str,
    values_override: list | None,
    mode_flag: str | None = None,
) -> str:
    """
    Return the stable, scoped run identity for this execution.

    Standard runs get a __standard suffix so their DB rows, progress state,
    and reports are isolated from any Full run of the same campaign.

    When --values is active (Custom mode) a targeted run must be fully
    isolated from the broader parent campaign's DB rows.  Appending the
    canonically-sorted value list creates a deterministic, human-readable key
    that never collides with a real campaign (real IDs never contain
    double-underscore).

    Full runs (no mode_flag, no values_override) return campaign_id unchanged —
    zero behaviour change for all existing callers.

    Examples:
      mode_flag="quick"     values_override=None   → "NGL_sweep__quick"
      mode_flag="standard"  values_override=None   → "NGL_sweep__standard"
      mode_flag=None        values_override=[30]   → "NGL_sweep__v30"
      mode_flag=None        values_override=[30, 80, 999] → "NGL_sweep__v30_80_999"
      mode_flag=None        values_override=None   → "NGL_sweep"
    """
    if mode_flag == "quick":
        return f"{campaign_id}__quick"
    if mode_flag == "standard":
        return f"{campaign_id}__standard"
    if values_override is not None:
        # Sort for canonical order so --values 30,80 ≡ --values 80,30
        val_str = "_".join(str(v) for v in sorted(values_override, key=str))
        return f"{campaign_id}__v{val_str}"
    return campaign_id


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CampaignPurityViolationError(ValueError):
    """
    Raised when a campaign YAML changes more than one field from baseline.yaml.
    One campaign = one variable. This rule is enforced before any measurement
    is taken.
    """


class CampaignAbortError(RuntimeError):
    """Raised when a campaign must be aborted (thermal, telemetry, or fatal error)."""


# ---------------------------------------------------------------------------
# Config loading and validation
# ---------------------------------------------------------------------------

def load_baseline(path: Path = BASELINE_YAML) -> dict[str, Any]:
    """Load and return the baseline YAML."""
    if not path.is_file():
        raise FileNotFoundError(f"baseline.yaml not found: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_campaign(campaign_id: str) -> dict[str, Any]:
    """Load and return the campaign YAML for the given campaign_id."""
    path = CAMPAIGNS_DIR / f"{campaign_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Campaign YAML not found: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_campaign_purity(
    baseline: dict[str, Any],
    campaign: dict[str, Any],
) -> str:
    """
    Verify that the campaign changes exactly one config field from baseline.
    Returns the variable name being swept.
    Raises CampaignPurityViolationError if zero or >1 fields differ.
    """
    variable = campaign.get("variable")
    if not variable or variable == "interaction" or campaign.get("auto_generated"):
        # Interaction and auto-generated campaigns bypass purity check
        return variable or "interaction"

    baseline_config: dict[str, Any] = baseline.get("config", {})
    values = campaign.get("values", [])

    if not values:
        raise CampaignPurityViolationError(
            f"Campaign {campaign['campaign_id']} has no values to sweep."
        )

    # Verify the variable exists in baseline config
    if variable not in baseline_config and variable != "cpu_affinity":
        raise CampaignPurityViolationError(
            f"Campaign variable '{variable}' is not a field in baseline.yaml config section.\n"
            f"Known config fields: {list(baseline_config.keys())}"
        )

    logger.info(
        "Campaign purity check passed: variable='%s', values=%s",
        variable, values,
    )
    return variable


def build_config_list(
    baseline: dict[str, Any],
    campaign: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Build the list of configs to test for this campaign.

    Each entry is a dict containing:
      - config_id: string (e.g., "C01_TB04")
      - variable_name: the field being swept
      - variable_value: the value for this config
      - full_config: merged baseline config + this value
      - server_args: list of --flag value pairs for llama-server

    C08 (interaction) is handled separately — its values must already be
    populated in the campaign YAML by score.py.
    """
    campaign_id = campaign["campaign_id"]
    variable = campaign.get("variable", "")
    values = campaign.get("values", [])
    baseline_config = baseline.get("config", {})

    configs = []
    for value in values:
        # Build a short config ID suffix
        val_str = str(value).replace(".", "p").replace("-", "m").replace(",", "").replace("=", "e")[:12]
        config_id = f"{campaign_id}_{val_str}"

        # Merge baseline + this value
        full_config = dict(baseline_config)
        if variable == "interaction" and isinstance(value, dict):
            # Interaction campaigns: each value is a dict of variable overrides
            config_id = value.get("config_id", f"{campaign_id}_combined")
            full_config.update(value.get("overrides", value))
        elif variable == "cpu_affinity":
            full_config["_cpu_affinity"] = value
        elif variable == "kv_cache_type_k":
            # C03: mirrors K and V
            full_config["kv_cache_type_k"] = value
            if campaign.get("kv_mirror_v", False):
                full_config["kv_cache_type_v"] = value
        else:
            full_config[variable] = value

        # Build server args from full_config
        server_args = _config_to_server_args(full_config, baseline)

        configs.append({
            "config_id": config_id,
            "variable_name": variable,
            "variable_value": value,
            "full_config": full_config,
            "server_args": server_args,
            "cpu_affinity_mask": _get_affinity_mask(full_config, campaign),
        })

    return configs


def _config_to_server_args(config: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """
    Convert a merged config dict to a llama-server argument list.
    Does not include --host, --port, or --model (added by server.py).
    """
    args: list[str] = []

    # Context
    if "context_size" in config:
        args += ["-c", str(config["context_size"])]

    # GPU layers (locked at 999)
    args += ["-ngl", str(config.get("n_gpu_layers", 999))]

    # Override tensor placement
    ot = config.get("override_tensor")
    if ot:
        args += ["-ot", str(ot)]

    # Flash attention: null = omit flag (server default = auto)
    fa = config.get("flash_attn")
    if fa is False:
        args += ["-fa", "0"]
    elif fa is True:
        args += ["-fa", "1"]
    # null = omit

    # Jinja templating
    if config.get("jinja", True):
        args.append("--jinja")

    # Threads — all three flags are always explicit.
    # threads_http was previously omitted when equal to its default (1), making
    # the resolved_command for C15's threads_http=1 config look identical to a
    # baseline config and hiding which parameter was being tested. (HIGH-5 fix)
    # --threads-http 1 is a no-op on the server; explicit is unambiguous.
    args += ["--threads", str(config.get("threads", 16))]
    args += ["--threads-batch", str(config.get("threads_batch", 16))]
    args += ["--threads-http", str(config.get("threads_http", 1))]

    # Batch sizes
    args += ["-ub", str(config.get("ubatch_size", 512))]
    args += ["-b", str(config.get("batch_size", 2048))]

    # Parallel slots
    n_parallel = config.get("n_parallel", 1)
    if n_parallel != 1:
        args += ["--parallel", str(n_parallel)]

    # KV cache type
    kv_k = config.get("kv_cache_type_k", "f16")
    kv_v = config.get("kv_cache_type_v", "f16")
    if kv_k != "f16":
        args += ["--cache-type-k", kv_k]
    if kv_v != "f16":
        args += ["--cache-type-v", kv_v]

    # mmap
    if not config.get("mmap", True):
        args.append("--no-mmap")

    # mlock
    if config.get("mlock", False):
        args.append("--mlock")

    # Continuous batching
    if not config.get("cont_batching", True):
        args.append("--no-cont-batching")

    # Defrag threshold
    defrag = config.get("defrag_thold", 0.1)
    if defrag != 0.1:
        if defrag < 0:
            # Negative value = disable. llama.cpp uses -1 to disable.
            args += ["--defrag-thold", "-1"]
        else:
            args += ["--defrag-thold", str(defrag)]

    return args


def _get_affinity_mask(config: dict[str, Any], campaign: dict[str, Any]) -> str | None:
    """Return CPU affinity mask string or None for OS default."""
    affinity = config.get("_cpu_affinity")
    if not affinity or affinity == "all_cores":
        return None
    # Get the P-cores-only mask from campaign details
    details = campaign.get("cpu_affinity_details", {})
    if isinstance(details, dict):
        return details.get(affinity)
    return affinity


# ---------------------------------------------------------------------------
# Request scheduling
# ---------------------------------------------------------------------------

def _build_request_schedule(
    cycle_number: int,
    lab_config: dict[str, Any],
    request_files: dict[str, Path],
) -> list[tuple[int, str, Path]]:
    """
    Return the ordered list of (request_index, request_type, payload_path)
    for a given cycle.

    Cycles 1–4: 6 × speed_short (1 cold + 5 warm)
    Cycle 5:    5 × speed_short (1 cold + 4 warm) + 1 × speed_medium (warm)
    """
    schedule = []
    requests_per_cycle = lab_config.get("requests_per_cycle", 6)
    cycles_per_config = lab_config.get("cycles_per_config", 5)

    for req_idx in range(1, requests_per_cycle + 1):
        if cycle_number == cycles_per_config and req_idx == requests_per_cycle:
            # Last request of last cycle: speed_medium
            req_type = "speed_medium"
        else:
            req_type = "speed_short"

        path = request_files.get(req_type)
        if path is None:
            raise ValueError(f"Request file for '{req_type}' not found in request_files map")

        schedule.append((req_idx, req_type, path))

    return schedule


# ---------------------------------------------------------------------------
# Crash recovery state
# ---------------------------------------------------------------------------

def _read_progress(state_file: Path) -> dict[str, Any]:
    """Read crash recovery state. Returns empty dict if none exists."""
    if state_file.is_file():
        try:
            with open(state_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not read progress.json: %s — starting fresh", exc)
    return {}


def _write_progress(state: dict[str, Any], state_dir: Path, state_file: Path) -> None:
    """Write crash recovery state."""
    state_dir.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _clear_progress(state_file: Path) -> None:
    """Clear crash recovery state on clean campaign completion."""
    if state_file.is_file():
        # Overwrite with empty object rather than deleting (per MDD §11.3)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({}, f)


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

def _enforce_cooldown(
    lab_config: dict[str, Any],
    config_label: str,
    console: Console,
) -> None:
    """
    Wait for inter-config cooldown:
      - Minimum: lab_config.cooldown_between_configs_s (300s)
      - Temperature gate: both CPU and GPU below cooldown_temp_target_c
      - Hard cap: lab_config.cooldown_max_s (600s)

    Shows a live Progress spinner with current CPU/GPU temps.
    Logs temperature readings every 30s. (U4 fix)
    """
    min_wait = lab_config.get("cooldown_between_configs_s", 300)
    max_wait = lab_config.get("cooldown_max_s", 600)
    temp_target = lab_config.get("cooldown_temp_target_c", 55.0)

    start_mono = time.monotonic()
    deadline = start_mono + max_wait
    min_deadline = start_mono + min_wait

    logger.info(
        "Cooldown started before %s (min=%ds, max=%ds, temp_target=%.0f°C)",
        config_label, min_wait, max_wait, temp_target,
    )

    check_interval = 10
    last_log = start_mono

    # transient=True — spinner disappears on completion; elapsed time and final
    # temperature are captured in the log.  Using the passed-in console so all
    # output stays on the same Rich console instance. (U4 fix)
    with Progress(
        SpinnerColumn(),
        TextColumn("[dim]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Cooldown before {config_label}: waiting {min_wait}s minimum...",
            total=None,
        )

        while time.monotonic() < deadline:
            now = time.monotonic()
            past_minimum = now >= min_deadline

            # Take a quick telemetry sample for live temp display
            sample = tele.collect_sample("cooldown", config_label, server_pid=None)
            cpu_t = sample.cpu_temp_c or 0.0
            gpu_t = sample.gpu_temp_c or 0.0

            machine_cool = (
                tele.is_machine_cool(target_temp_c=temp_target) if past_minimum else False
            )

            if past_minimum and machine_cool:
                elapsed = now - start_mono
                logger.info(
                    "Cooldown complete after %.0fs — CPU %.1f°C GPU %.1f°C (both below %.0f°C)",
                    elapsed, cpu_t, gpu_t, temp_target,
                )
                break

            # Update spinner description with live temperatures
            min_remaining = max(0.0, min_deadline - now)
            if not past_minimum:
                status = f"min {min_remaining:.0f}s remaining"
            else:
                status = f"waiting for <{temp_target:.0f}°C"
            progress.update(
                task,
                description=(
                    f"Cooldown before {config_label}: "
                    f"CPU {cpu_t:.1f}°C  GPU {gpu_t:.1f}°C  ({status})"
                ),
            )

            # DEBUG: every sample (10s) — captured in log file but not console.
            # INFO: every 30s — less noise for long cooldowns.
            logger.debug(
                "Cooldown sample: cpu=%.1f°C gpu=%.1f°C elapsed=%.0fs",
                cpu_t, gpu_t, now - start_mono,
            )
            if now - last_log >= 30:
                logger.info(
                    "Cooldown: cpu=%.1f°C gpu=%.1f°C elapsed=%.0fs remaining=%.0fs",
                    cpu_t, gpu_t, now - start_mono, deadline - now,
                )
                last_log = now

            time.sleep(check_interval)
        else:
            logger.warning(
                "Cooldown hit max_wait (%ds) without reaching temp target (%.0f°C). Proceeding.",
                max_wait, temp_target,
            )


# ---------------------------------------------------------------------------
# Apply CPU affinity
# ---------------------------------------------------------------------------

def _apply_cpu_affinity(pid: int, mask: str | None) -> bool:
    """
    Set CPU affinity on the given process.
    mask: None = no change (OS default); "0-15" = P-cores only
    Returns True if set successfully.
    """
    if mask is None:
        return True

    try:
        import psutil
        proc = psutil.Process(pid)
        # Parse mask like "0-15" into a list of CPU IDs
        cpus: list[int] = []
        for part in mask.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                cpus.extend(range(int(start), int(end) + 1))
            else:
                cpus.append(int(part))

        proc.cpu_affinity(cpus)
        logger.info("CPU affinity set: pid=%d mask='%s' cpus=%s", pid, mask, cpus)
        return True
    except Exception as exc:
        logger.error("Failed to set CPU affinity pid=%d mask='%s': %s", pid, mask, exc)
        return False


# ---------------------------------------------------------------------------
# Defender pre-flight exclusion check
# ---------------------------------------------------------------------------

def _check_defender_exclusions(
    server_bin: Path,
    model_path: Path,
    lab_root: Path,
    console: Console,
) -> None:
    """
    Warn if Windows Defender may be scanning benchmark paths.  Checks:
      - Whether real-time protection is enabled (DisableRealtimeMonitoring)
      - Whether server binary dir, model dir, results dir, and db dir are
        all in the Defender exclusion list (ExclusionPath)
      - Whether the server binary is in the process exclusion list
        (ExclusionProcess)

    NGL_sweep finding: antivirus_scan_active was True for ~70% of snapshots
    despite D:\\ supposedly being excluded — real-time protection was the cause.

    This is a WARNING only — it never aborts the campaign.  If PowerShell is
    unavailable or the query times out the check is silently skipped.
    """
    if sys.platform != "win32":
        return

    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Get-MpPreference | Select-Object ExclusionPath, ExclusionProcess,"
                " DisableRealtimeMonitoring | ConvertTo-Json -Compress",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            logger.debug(
                "Defender exclusion check skipped — Get-MpPreference failed: %s",
                result.stderr.strip(),
            )
            return

        import json as _json  # noqa: PLC0415 — lazy, only reached on win32

        raw = result.stdout.strip()
        data: dict = _json.loads(raw) if raw and raw.lower() != "null" else {}

        issues = 0

        # --- Real-time protection check ---
        # DisableRealtimeMonitoring=False means real-time IS active (scanning).
        rtm_disabled = data.get("DisableRealtimeMonitoring", False)
        if not rtm_disabled:
            issues += 1
            console.print("[yellow]⚠️  Windows Defender: real-time protection is ENABLED[/yellow]")
            logger.warning(
                "Defender real-time protection is enabled — antivirus_scan_active was True "
                "in ~70%% of NGL_sweep snapshots despite path exclusions being set. "
                "Real-time protection scans file I/O regardless of exclusion list entries "
                "in some Defender policy configurations."
            )
            console.print(
                "[yellow]  Remediation (choose one):\n"
                "    1. Disable real-time protection for benchmarking:\n"
                "       Settings → Windows Security → Virus & threat protection\n"
                "         → Manage settings → Real-time protection → Off\n"
                "    2. Verify exclusions are applied at the policy level, not just\n"
                "       the user-preference level (Group Policy may override).[/yellow]"
            )

        # --- Exclusion path check ---
        excl_raw = data.get("ExclusionPath")
        if excl_raw is None or (isinstance(excl_raw, str) and excl_raw.lower() == "null"):
            exclusions: list[str] = []
        else:
            exclusions = [excl_raw] if isinstance(excl_raw, str) else list(excl_raw or [])

        excl_lower = [str(e).rstrip("\\/ ").lower() for e in exclusions]

        # Check each path: covered if the exclusion is an ancestor or equal
        # (check_lower.startswith(excl)) or a descendant (excl.startswith(check_lower)).
        # The second arm handles "user excluded D:\\ and target is D:\\results".
        paths_to_check = [
            ("server binary dir", server_bin.parent),
            ("model dir",         model_path.parent),
            ("results dir",       lab_root / "results"),
            ("db dir",            lab_root / "db"),
        ]

        not_excluded: list[tuple[str, Path]] = []
        for label, check_path in paths_to_check:
            check_lower = str(check_path).rstrip("\\/ ").lower()
            covered = any(
                check_lower.startswith(excl) or excl.startswith(check_lower)
                for excl in excl_lower
            )
            if not covered:
                not_excluded.append((label, check_path))

        if not_excluded:
            issues += 1
            console.print("[yellow]⚠️  Windows Defender Exclusion Warning[/yellow]")
            logger.warning("Windows Defender: the following paths are NOT in the exclusion list:")
            for label, path in not_excluded:
                console.print(f"  [yellow]• {label}: {path}[/yellow]")
                logger.warning("  Not excluded: %s (%s)", label, path)
            console.print(
                "[yellow]  Defender may scan model loads, MoE dispatch I/O, and result writes,\n"
                "  adding non-deterministic latency across all cycles.\n"
                "  To add exclusions:\n"
                "    Settings → Windows Security → Virus & threat protection\n"
                "      → Manage settings → Exclusions → Add or remove exclusions → Add a folder[/yellow]"
            )
            logger.warning(
                "Recommendation: add to Defender exclusions: '%s', '%s', '%s', '%s'",
                server_bin.parent, model_path.parent, lab_root / "results", lab_root / "db",
            )

        # --- Process exclusion check ---
        # ExclusionProcess entries exempt a process from real-time scanning of
        # its file I/O.  If the server binary isn't listed, every model shard
        # read and mmap page fault triggers a scan.
        proc_excl_raw = data.get("ExclusionProcess")
        if proc_excl_raw is None or (isinstance(proc_excl_raw, str) and proc_excl_raw.lower() == "null"):
            proc_exclusions: list[str] = []
        else:
            proc_exclusions = [proc_excl_raw] if isinstance(proc_excl_raw, str) else list(proc_excl_raw or [])

        proc_excl_lower = [str(e).lower() for e in proc_exclusions]
        bin_name_lower = server_bin.name.lower()
        bin_path_lower = str(server_bin).lower()
        proc_covered = any(
            bin_name_lower == pe or bin_path_lower == pe
            for pe in proc_excl_lower
        )
        if not proc_covered:
            issues += 1
            console.print(f"[yellow]⚠️  Server binary not in Defender process exclusions: {server_bin.name}[/yellow]")
            logger.warning("Server binary '%s' not in ExclusionProcess list.", server_bin.name)
            console.print(
                "[yellow]  Every file read by the server (model shards, mmap pages) may be scanned.\n"
                "  To add a process exclusion:\n"
                "    Settings → Windows Security → Virus & threat protection\n"
                "      → Manage settings → Exclusions → Add or remove exclusions\n"
                f"      → Add an exclusion → Process → enter: {server_bin.name}\n"
                f"  Or via PowerShell:\n"
                f"    Add-MpPreference -ExclusionProcess '{server_bin.name}'[/yellow]"
            )

        if issues == 0:
            logger.info("Defender: real-time off, paths excluded, server process excluded ✓")
            console.print("[green]✓ Defender OK[/green]")

    except FileNotFoundError:
        logger.debug("Defender check skipped — powershell.exe not found")
    except subprocess.TimeoutExpired:
        logger.warning("Defender exclusion check timed out (>15s) — skipping")
    except Exception as exc:
        logger.debug("Defender exclusion check failed: %s — skipping", exc)


# ---------------------------------------------------------------------------
# Windows Search indexer check
# ---------------------------------------------------------------------------

def _check_windows_search(
    lab_root: Path,
    model_path: Path,
    console: Console,
) -> None:
    """
    Warn if the Windows Search indexer (WSearch) service is running.

    NGL_sweep finding: search_indexer_active was True for 100% of snapshots.
    WSearch triggers background file reads on newly-written files under indexed
    paths — results/ and db/ writes during a cycle can pull the indexer's
    I/O onto the same disk as model reads, adding non-deterministic latency.

    This is a WARNING only — it never aborts the campaign.
    """
    if sys.platform != "win32":
        return

    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Get-Service WSearch | Select-Object Status | ConvertTo-Json -Compress",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            logger.debug("WSearch check skipped — Get-Service failed: %s", result.stderr.strip())
            return

        import json as _json  # noqa: PLC0415

        raw = result.stdout.strip()
        if not raw or raw.lower() == "null":
            logger.debug("WSearch service not found on this system")
            return

        data = _json.loads(raw)
        # PS serialises ServiceControllerStatus as an integer: Running=4.
        # Older PS versions may emit the string "Running" instead.
        status = str(data.get("Status", ""))
        if status not in ("4", "Running"):
            logger.info("Windows Search (WSearch): not running ✓")
            console.print("[green]✓ Windows Search not running[/green]")
            return

        console.print("[yellow]⚠️  Windows Search (WSearch) is RUNNING[/yellow]")
        logger.warning(
            "WSearch service is running — it was active in 100%% of NGL_sweep snapshots. "
            "The indexer scans newly-written files under indexed paths; results/ and db/ "
            "writes during cycles may trigger indexer I/O on the same drive as model reads."
        )
        console.print(
            "[yellow]  Paths at risk if indexed:\n"
            f"    • {lab_root / 'results'}\n"
            f"    • {lab_root / 'db'}\n"
            f"    • {model_path.parent}\n"
            "  Remediation options:\n"
            "    Stop for this session (re-enables on reboot):\n"
            "      Stop-Service WSearch\n"
            "    Disable permanently:\n"
            "      Set-Service WSearch -StartupType Disabled\n"
            "    Or exclude paths from indexing:\n"
            "      Settings → Search → Searching Windows → Excluded Folders → Add[/yellow]"
        )
        logger.warning(
            "Recommendation: Stop-Service WSearch before campaigns, or exclude "
            "'%s', '%s', '%s' from Windows Search indexing.",
            lab_root / "results", lab_root / "db", model_path.parent,
        )

    except FileNotFoundError:
        logger.debug("WSearch check skipped — powershell.exe not found")
    except subprocess.TimeoutExpired:
        logger.warning("WSearch check timed out (>15s) — skipping")
    except Exception as exc:
        logger.debug("WSearch check failed: %s — skipping", exc)


# ---------------------------------------------------------------------------
# Single cycle execution
# ---------------------------------------------------------------------------

def _run_cycle(
    config: dict[str, Any],
    cycle_number: int,
    cycle_id: int,
    campaign_id: str,
    lab_config: dict[str, Any],
    request_files: dict[str, Path],
    db_path: Path,
    raw_jsonl_path: Path,
    telemetry_jsonl_path: Path,
    collector: tele.TelemetryCollector,
    console: Console,
    logs_dir: Path | None = None,
) -> tuple[bool, list[dict]]:
    """
    Run one cycle (server start + N requests).
    Returns (thermal_event_occurred, list_of_result_dicts).

    On any crash:
      - Marks all started-but-incomplete requests as cycle_status=invalid
      - Marks cycle as invalid in the database
      - Returns (False, [])

    Thermal event:
      - If detected mid-cycle, returns (True, [])
      - Cycle marked invalid reason=thermal_event
    """
    config_id = config["config_id"]
    server_args = config["server_args"]
    cpu_affinity_mask = config.get("cpu_affinity_mask")

    schedule = _build_request_schedule(cycle_number, lab_config, request_files)
    inter_request_delay = lab_config.get("inter_request_delay_s", 20)
    ready_timeout = lab_config.get("server_ready_timeout_s", 120)
    bind_timeout = lab_config.get("server_bind_timeout_s", 300)

    results: list[dict] = []
    thermal_event = False

    from src.server import start_server  # noqa: PLC0415 — lazy: avoids EnvironmentError on --list/--validate

    try:
        with start_server(
            extra_args=server_args,
            campaign_id=campaign_id,
            config_id=config_id,
            cycle=cycle_number,
            ready_timeout_s=ready_timeout,
            bind_timeout_s=bind_timeout,
            logs_dir=logs_dir,
        ) as srv:
            base_url = srv["base_url"]
            server_pid = srv["pid"]
            server_log = srv["log_file"]
            resolved_cmd = srv["resolved_cmd_str"]

            # Apply CPU affinity if specified (L4: check return value)
            if cpu_affinity_mask:
                affinity_ok = _apply_cpu_affinity(server_pid, cpu_affinity_mask)
                if not affinity_ok:
                    logger.warning(
                        "CPU affinity NOT applied for config %s (pid=%d mask='%s') — "
                        "proceeding without affinity; results may show more variability.",
                        config_id, server_pid, cpu_affinity_mask,
                    )

            # Update telemetry with the new server PID
            collector.start(campaign_id, config_id, server_pid=server_pid)

            # Update cycle record with server details
            with get_connection(db_path) as conn:
                conn.execute(
                    """UPDATE cycles SET status='started', server_pid=?, server_log_path=?,
                       started_at=?, no_warmup=?, attempt_count=?, startup_duration_s=?
                       WHERE id=?""",
                    (
                        server_pid,
                        str(server_log),
                        datetime.now(timezone.utc).isoformat(),
                        int(srv["no_warmup"]),
                        srv["attempt_count"],
                        srv["startup_duration_s"],
                        cycle_id,
                    ),
                )
                conn.commit()

            logger.info(
                "Cycle %d/%s started — server pid=%d port=%s no_warmup=%s",
                cycle_number, config_id, server_pid,
                srv["port"], srv["no_warmup"],
            )

            # --- Execute requests -------------------------------------------
            for req_idx, req_type, payload_path in schedule:
                # Check for thermal event before each request
                # (telemetry has been running since server start)
                with collector._lock:
                    recent_samples = list(collector._samples)[-3:]  # last 6s
                for s in recent_samples:
                    if tele.check_thermal_event(s):
                        thermal_event = True
                        logger.error(
                            "THERMAL EVENT before req %d in cycle %d/%s — aborting cycle",
                            req_idx, cycle_number, config_id,
                        )
                        break

                if thermal_event:
                    break

                # Load payload
                payload = load_request_payload(payload_path)

                console.print(
                    f"  [dim]Cycle {cycle_number}/{lab_config.get('cycles_per_config', 5)}"
                    f"  req {req_idx}/{len(schedule)}"
                    f"  {req_type}  {'(cold)' if req_idx == 1 else '(warm)'}[/dim]"
                )

                result = measure_request_sync(
                    base_url=base_url,
                    payload=payload,
                    request_type=req_type,
                    campaign_id=campaign_id,
                    config_id=config_id,
                    cycle_number=cycle_number,
                    request_index=req_idx,
                    timeout_s=300.0,
                )

                result_dict = result.to_dict()
                result_dict["server_pid"] = server_pid
                result_dict["resolved_command"] = resolved_cmd
                result_dict["resolved_cmd_argv"] = srv["resolved_cmd_argv"]

                # Write to raw.jsonl (immutable)
                write_raw_jsonl(raw_jsonl_path, result_dict)

                # Write to SQLite
                with get_connection(db_path) as conn:
                    write_request(conn, cycle_id, result_dict)
                    conn.commit()

                results.append(result_dict)

                logger.info(
                    "req %d/%d %s outcome=%s ttft=%.1fms tg=%.2ft/s",
                    req_idx, len(schedule), req_type,
                    result.outcome.value,
                    result.ttft_ms or 0,
                    result.predicted_per_second or 0,
                )

                # Inter-request delay (except after last request)
                if req_idx < len(schedule):
                    time.sleep(inter_request_delay)

    except Exception as exc:
        from src.server import ServerOOMError
        
        # Determine if this was an OOM
        is_oom = isinstance(exc, ServerOOMError)
        log_snippet = str(exc)
        
        # Check if the server crashed mid-cycle due to memory (i.e. KV cache exhaustion)
        if not is_oom:
            try:
                server_log = Path(request_files.get("speed_short")).parent.parent.parent / "logs" # approximation or we can just use the config's last srv log 
                # actually srv["log_file"] was defined inside the `with` block, we might not have it.
                # let's just accept the local `server_log` is possibly unbound if `start_server` failed.
                pass
            except Exception:
                pass
            
            # Use `server_log` if it is in locals and exists
            try:
                if 'server_log' in locals() and server_log and server_log.is_file():
                    tail = server_log.read_text(encoding="utf-8", errors="replace")[-3000:].lower()
                    if "out of memory" in tail:
                        is_oom = True
                        log_snippet = tail[-500:]
            except Exception:
                pass

        if is_oom:
            logger.error("Cycle %d/%s OOM detected: %s", cycle_number, config_id, exc)
            _mark_cycle_invalid(db_path, cycle_id, "crash: OOM")
            raise ServerOOMError(
                log_snippet=log_snippet,
                log_path=server_log if 'server_log' in locals() else Path(),
                exit_code=getattr(exc, "exit_code", -1),
            )

        logger.error("Cycle %d/%s crashed: %s", cycle_number, config_id, exc, exc_info=True)
        # Mark existing results as invalid
        _mark_cycle_invalid(db_path, cycle_id, f"crash: {exc}")
        return False, []

    finally:
        # Stop telemetry regardless of outcome
        samples, snapshots = collector.stop()
        logger.debug(
            "Cycle %d/%s telemetry: %d samples, %d snapshots",
            cycle_number, config_id, len(samples), len(snapshots),
        )

    # --- Post-cycle outcome -------------------------------------------------
    if thermal_event:
        _mark_cycle_invalid(db_path, cycle_id, "thermal_event")
        return True, []

    # Mark cycle complete
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE cycles SET status='complete', completed_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), cycle_id),
        )
        conn.commit()

    return False, results


def _mark_cycle_invalid(db_path: Path, cycle_id: int, reason: str) -> None:
    """Mark a cycle as invalid and update all its request records."""
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE cycles SET status='invalid', invalid_reason=? WHERE id=?",
            (reason, cycle_id),
        )
        conn.execute(
            "UPDATE requests SET cycle_status='invalid' WHERE cycle_id=?",
            (cycle_id,),
        )
        conn.commit()
    logger.warning("Cycle id=%d marked invalid: %s", cycle_id, reason)


# ---------------------------------------------------------------------------
# Single config execution
# ---------------------------------------------------------------------------

def _run_config(
    config: dict[str, Any],
    campaign_id: str,
    lab_config: dict[str, Any],
    request_files: dict[str, Path],
    db_path: Path,
    raw_jsonl_path: Path,
    telemetry_jsonl_path: Path,
    collector: tele.TelemetryCollector,
    progress_state: dict[str, Any],
    console: Console,
    oom_boundary_sweep: bool = False,
    state_dir: Path | None = None,
    state_file: Path | None = None,
    logs_dir: Path | None = None,
) -> bool | str:
    """
    Run all cycles for one config. Returns True if config completed without
    thermal abort.

    When oom_boundary_sweep=True: returns "oom" if the server startup fails
    with a confirmed CUDA OOM on any cycle. Returns True on clean completion.
    When oom_boundary_sweep=False: behavior is unchanged; returns True/False.

    Updates progress.json before each cycle and after config completion.
    state_dir / state_file: effective locations for crash recovery state
    (derived from the active lab root; fall back to module-level defaults).
    logs_dir: effective server log directory (namespaced when --baseline used).
    """
    _eff_state_dir  = state_dir  if state_dir  is not None else STATE_DIR
    _eff_state_file = state_file if state_file is not None else STATE_FILE
    _eff_logs_dir   = logs_dir  if logs_dir   is not None else LOGS_DIR
    config_id = config["config_id"]
    cycles_per_config = lab_config.get("cycles_per_config", 5)
    
    with get_connection(db_path) as conn:
        try:
            thermal_events_total = conn.execute(
                "SELECT COUNT(*) FROM telemetry WHERE config_id=? AND campaign_id=? AND (power_limit_throttling=1 OR cpu_temp_c >= 100.0)",
                (config_id, campaign_id)
            ).fetchone()[0]
        except Exception:
            thermal_events_total = 0
    
    all_results: list[dict] = []

    console.print(
        f"\n[bold cyan]Config:[/bold cyan] {config_id}  "
        f"[dim]({config['variable_name']}={config['variable_value']})[/dim]"
    )
    logger.info("=== Starting config %s (%s=%s) ===",
                config_id, config['variable_name'], config['variable_value'])

    # Register config in DB
    with get_connection(db_path) as conn:
        full_config_json = json.dumps(config["full_config"])
        # Build the canonical reproduction command for this config.
        # get_production_command() lives in server.py alongside SERVER_BIN and
        # MODEL_PATH — the binary and model path are backend-specific details
        # that runner.py has no need to know directly.
        # NOTE: --no-warmup is intentionally excluded here — it is a startup
        # workaround tracked per-cycle in the cycles table, not a performance
        # config variable.  The report flags configs that required it.
        from src.server import get_production_command, get_runtime_env_summary  # noqa: PLC0415
        resolved_cmd = get_production_command(config["server_args"])
        runtime_env_json = json.dumps(get_runtime_env_summary())
        conn.execute(
            """INSERT OR IGNORE INTO configs
               (id, campaign_id, variable_name, variable_value, config_values_json,
                resolved_command, runtime_env_json, cpu_affinity_mask, status, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)""",
            (
                config_id, campaign_id,
                config["variable_name"],
                json.dumps(config["variable_value"]),
                full_config_json,
                resolved_cmd,
                runtime_env_json,
                config.get("cpu_affinity_mask"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()

    def _run_cycles() -> None:
        """Inner loop shared by both OOM-boundary and standard paths."""
        nonlocal thermal_events_total
        for cycle_number in range(1, cycles_per_config + 1):
            # Update crash recovery state
            progress_state["current_config"] = config_id
            progress_state["current_cycle"] = cycle_number
            progress_state["last_update"] = datetime.now(timezone.utc).isoformat()
            _write_progress(progress_state, _eff_state_dir, _eff_state_file)

            console.print(f"  [bold]Cycle {cycle_number}/{cycles_per_config}[/bold]")
            logger.info("--- Cycle %d/%d for %s ---", cycle_number, cycles_per_config, config_id)

            # Register cycle in DB.
            # On resume, this cycle row may already exist from an interrupted run:
            #   terminal (complete/invalid)  — skip; data already recorded
            #   non-terminal (pending/started) — stale; delete and restart clean
            with get_connection(db_path) as conn:
                existing = conn.execute(
                    """SELECT id, status FROM cycles
                       WHERE config_id=? AND campaign_id=? AND cycle_number=?""",
                    (config_id, campaign_id, cycle_number),
                ).fetchone()

                if existing is not None:
                    existing_status = existing["status"]
                    if existing_status in ("complete", "invalid"):
                        logger.info(
                            "Cycle %d/%s already %s — skipping",
                            cycle_number, config_id, existing_status,
                        )
                        console.print(
                            f"  [dim]Cycle {cycle_number}/{cycles_per_config} "
                            f"already {existing_status} — skipping[/dim]"
                        )
                        continue
                    # Non-terminal: interrupted mid-run. Discard and restart.
                    logger.info(
                        "Cycle %d/%s found in state '%s' — discarding partial data and restarting",
                        cycle_number, config_id, existing_status,
                    )
                    conn.execute("DELETE FROM requests WHERE cycle_id=?", (existing["id"],))
                    conn.execute("DELETE FROM cycles WHERE id=?", (existing["id"],))
                    conn.commit()

                cur = conn.execute(
                    """INSERT INTO cycles (config_id, campaign_id, cycle_number, status)
                       VALUES (?, ?, ?, 'pending')""",
                    (config_id, campaign_id, cycle_number),
                )
                cycle_id = cur.lastrowid
                conn.commit()

            # Capture run context before cycle execution begins (one per cycle).
            # Failure is non-fatal: log it and let the cycle proceed.
            _ctx_path = (
                raw_jsonl_path.parent
                / f"{config_id}_cycle{cycle_number:02d}_run_context.json"
            )
            try:
                from src.run_context import create_run_context  # noqa: PLC0415
                from src.server import MODEL_PATH as _ctx_model_path  # noqa: PLC0415
                logger.info(
                    "Capturing run context for cycle %d/%s ...",
                    cycle_number, config_id,
                )
                _ctx = create_run_context(model_path=str(_ctx_model_path))
                _ctx_path.write_text(json.dumps(_ctx, indent=2), encoding="utf-8")
                logger.info("Run context persisted: %s", _ctx_path)
            except Exception as _ctx_exc:
                logger.warning(
                    "Run context capture failed — cycle %d/%s will proceed without it: %s",
                    cycle_number, config_id, _ctx_exc,
                )

            thermal_event, results = _run_cycle(
                config=config,
                cycle_number=cycle_number,
                cycle_id=cycle_id,
                campaign_id=campaign_id,
                lab_config=lab_config,
                request_files=request_files,
                db_path=db_path,
                raw_jsonl_path=raw_jsonl_path,
                telemetry_jsonl_path=telemetry_jsonl_path,
                collector=collector,
                console=console,
                logs_dir=_eff_logs_dir,
            )

            if thermal_event:
                thermal_events_total += 1
                logger.warning(
                    "Thermal event in cycle %d/%s (total events this config: %d)",
                    cycle_number, config_id, thermal_events_total,
                )
                # Continue to next cycle — thermal events are recorded but don't abort
                # the config (they disqualify the cycle and affect scoring)

            all_results.extend(results)

    from src.server import ServerOOMError  # noqa: PLC0415
    try:
        _run_cycles()
    except ServerOOMError as exc:
        logger.error("Config %s: OOM during server startup — %s", config_id, exc)
        with get_connection(db_path) as conn:
            conn.execute(
                "UPDATE configs SET status='oom', failure_detail=? "
                "WHERE id=? AND campaign_id=?",
                (exc.log_snippet[:500], config_id, campaign_id),
            )
            conn.commit()
        console.print(
            f"  [bold red]OOM:[/bold red] {config_id} — server ran out of GPU memory\n"
            f"  [dim]{exc.log_snippet.splitlines()[0][:120]}[/dim]"
        )
        completed = progress_state.get("completed_configs", [])
        if config_id not in completed:
            completed.append(config_id)
        progress_state["completed_configs"] = completed
        _write_progress(progress_state, _eff_state_dir, _eff_state_file)
        if oom_boundary_sweep:
            return "oom"
        return True

    # Mark config complete
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE configs SET status='complete', completed_at=? WHERE id=? AND campaign_id=?",
            (datetime.now(timezone.utc).isoformat(), config_id, campaign_id),
        )
        conn.commit()

    # Update progress state
    completed = progress_state.get("completed_configs", [])
    if config_id not in completed:
        completed.append(config_id)
    progress_state["completed_configs"] = completed
    progress_state["current_config"] = None
    progress_state["current_cycle"] = None
    _write_progress(progress_state, _eff_state_dir, _eff_state_file)

    # Summary log
    warm_tgs = [
        r["predicted_per_second"]
        for r in all_results
        if r.get("is_cold") is False
        and r.get("outcome") == RequestOutcome.SUCCESS.value
        and r.get("predicted_per_second") is not None
        and r.get("request_type") == "speed_short"
        and r.get("cycle_status") == "complete"
    ]
    if warm_tgs:
        # statistics.median() averages the two middle values for even N.
        # The previous floor-index formula returned the lower-middle element
        # for even-length lists (e.g. N=4 → index 2, not avg of [1],[2]). (LOW-3 fix)
        median_tg = statistics.median(warm_tgs)
        logger.info(
            "Config %s complete: %d warm speed_short results, median TG=%.2f t/s, "
            "thermal_events=%d",
            config_id, len(warm_tgs), median_tg, thermal_events_total,
        )
        console.print(
            f"  [green]Done:[/green] {len(warm_tgs)} warm results, "
            f"median TG=[bold]{median_tg:.2f}[/bold] t/s, "
            f"thermal_events={thermal_events_total}"
        )
    else:
        logger.warning("Config %s: no valid warm speed_short results", config_id)
        console.print(f"  [yellow]Warning:[/yellow] No valid warm results for {config_id}")

    return True


# ---------------------------------------------------------------------------
# Main campaign runner
# ---------------------------------------------------------------------------

def run_campaign(
    campaign_id: str,
    dry_run: bool = False,
    resume: bool = True,
    cycles_override: int | None = None,
    requests_per_cycle_override: int | None = None,
    values_override: list | None = None,
    baseline_path: Path = BASELINE_YAML,
    mode_flag: str | None = None,
) -> None:
    """
    Run a complete campaign from start to finish (or resume if interrupted).

    This is the main entry point. Call from CLI or directly.

    Override resolution order (highest priority wins):
      1. CLI flags (--cycles, --requests-per-cycle)
      2. Mode-specific default (QUICK/STANDARD_CYCLES_PER_CONFIG) — only if no --cycles
      3. Campaign YAML (cycles_per_config, requests_per_cycle keys)
      4. baseline.yaml lab section (global defaults)
    """
    _effective_lab_root = _derive_lab_root(baseline_path)
    _eff_results_dir = _effective_lab_root / "results"
    _eff_logs_dir    = _effective_lab_root / "logs"
    _eff_db_dir      = _effective_lab_root / "db"
    _eff_state_dir   = _effective_lab_root / "state"
    _eff_db_path     = _eff_db_dir / "lab.sqlite"
    _eff_state_file  = _eff_state_dir / "progress.json"

    effective_campaign_id = _derive_effective_campaign_id(campaign_id, values_override, mode_flag)

    _setup_logging(effective_campaign_id, logs_dir=_eff_logs_dir)
    logger.info("=" * 70)
    logger.info(
        "QuantMap campaign starting: %s  dry_run=%s  baseline=%s",
        effective_campaign_id, dry_run, baseline_path,
    )
    if effective_campaign_id != campaign_id:
        if mode_flag == "quick":
            _scope_reason = "--mode quick"
        elif mode_flag == "standard":
            _scope_reason = "--mode standard"
        else:
            _scope_reason = "--values scope"
        logger.info(
            "Effective run ID (%s): %s  (parent campaign: %s)",
            _scope_reason, effective_campaign_id, campaign_id,
        )
        console.print(
            f"[yellow]Effective run ID:[/yellow] {effective_campaign_id}  "
            f"[dim](parent campaign: {campaign_id})[/dim]"
        )
    if _effective_lab_root != LAB_ROOT:
        logger.info(
            "Lab root (namespaced): %s", _effective_lab_root,
        )
        console.print(
            f"[dim]Lab root (namespaced): {_effective_lab_root}[/dim]"
        )
    else:
        logger.info("Lab root (default): %s", _effective_lab_root)
    logger.info("=" * 70)

    # -------------------------------------------------------------------------
    # Load configuration
    # -------------------------------------------------------------------------
    if baseline_path != BASELINE_YAML:
        logger.info("INFO: --baseline override active: %s", baseline_path)
    baseline = load_baseline(baseline_path)
    campaign = load_campaign(campaign_id)

    # Validate purity
    variable = validate_campaign_purity(baseline, campaign)

    # Build config list
    configs = build_config_list(baseline, campaign)

    # Apply values override (Custom mode — targeted subset run)
    if values_override is not None:
        if not values_override:
            raise ValueError("--values is empty — provide at least one value")
        campaign_values = campaign.get("values", [])
        bad = [v for v in values_override if v not in campaign_values]
        if bad:
            raise ValueError(
                f"--values contains values not present in campaign '{campaign_id}':\n"
                f"  invalid: {bad}\n"
                f"  valid:   {campaign_values}"
            )
        original_count = len(configs)
        configs = [c for c in configs if c["variable_value"] in values_override]
        logger.info(
            "--values override: using %d/%d configs (values=%s)",
            len(configs), original_count, values_override,
        )
        console.print(
            f"[yellow]--values override:[/yellow] {len(configs)} of "
            f"{original_count} configs  [dim](values={values_override})[/dim]"
        )

    # Build request file map
    req_cfg = baseline.get("requests", {})
    request_files: dict[str, Path] = {}
    for req_name, rel_path in req_cfg.items():
        full_path = _REPO_ROOT / rel_path
        if not full_path.is_file():
            raise FileNotFoundError(f"Request file not found: {full_path}")
        request_files[req_name] = full_path

    lab_config = baseline.get("lab", {})

    # -------------------------------------------------------------------------
    # Apply cycles / requests overrides (campaign YAML → CLI flags)
    # -------------------------------------------------------------------------
    # Layer 2: campaign YAML overrides baseline defaults
    if "cycles_per_config" in campaign:
        logger.info(
            "Campaign YAML overrides cycles_per_config: %d → %d",
            lab_config.get("cycles_per_config", 3), campaign["cycles_per_config"],
        )
        lab_config["cycles_per_config"] = campaign["cycles_per_config"]
    if "requests_per_cycle" in campaign:
        logger.info(
            "Campaign YAML overrides requests_per_cycle: %d → %d",
            lab_config.get("requests_per_cycle", 6), campaign["requests_per_cycle"],
        )
        lab_config["requests_per_cycle"] = campaign["requests_per_cycle"]

    # Layer 2.5: Mode-specific cycle defaults — applied after campaign YAML,
    # before CLI --cycles so the explicit override always wins.
    if mode_flag == "standard" and cycles_override is None:
        _before = lab_config.get("cycles_per_config", 5)
        lab_config["cycles_per_config"] = STANDARD_CYCLES_PER_CONFIG
        logger.info(
            "--mode standard: overriding cycles_per_config %d → %d (STANDARD_CYCLES_PER_CONFIG)",
            _before, STANDARD_CYCLES_PER_CONFIG,
        )
    elif mode_flag == "quick" and cycles_override is None:
        _before = lab_config.get("cycles_per_config", 5)
        lab_config["cycles_per_config"] = QUICK_CYCLES_PER_CONFIG
        logger.info(
            "--mode quick: overriding cycles_per_config %d -> %d (QUICK_CYCLES_PER_CONFIG)",
            _before, QUICK_CYCLES_PER_CONFIG,
        )

    # Layer 3: CLI flags override everything
    if cycles_override is not None:
        logger.info(
            "CLI --cycles overrides cycles_per_config: %d → %d",
            lab_config.get("cycles_per_config", 3), cycles_override,
        )
        lab_config["cycles_per_config"] = cycles_override
    if requests_per_cycle_override is not None:
        logger.info(
            "CLI --requests-per-cycle overrides requests_per_cycle: %d → %d",
            lab_config.get("requests_per_cycle", 6), requests_per_cycle_override,
        )
        lab_config["requests_per_cycle"] = requests_per_cycle_override

    # -------------------------------------------------------------------------
    # Resolve run mode and build execution plan
    # -------------------------------------------------------------------------
    # RunPlan is the single authoritative description of this execution:
    # what mode, which identity, which values, what schedule, which paths.
    # Validate / dry-run / execution / reporting all read from it.
    _run_mode = resolve_run_mode(values_override, mode_flag)

    # Mode-specific filter overrides:
    # - Custom: relax min_valid_warm_count to 1 (intentionally sparse targeted run)
    # - Quick: relax min_valid_warm_count to 3.
    #          Why 3: Quick's only cycle uses requests [cold, warm×4, warm speed_medium].
    #          analyze.py counts warm speed_short only → 4 valid warm samples per config.
    #          min=3 allows exactly 1 request failure (4−3=1) before eliminating a config.
    #          The default of 10 would eliminate every Quick config (4 < 10).
    # - Standard and Full: use ELIMINATION_FILTERS defaults unchanged
    # Campaign-level elimination_overrides (from YAML) are merged at call time.
    _mode_filter_overrides: dict | None = None
    if _run_mode == "custom":
        _mode_filter_overrides = {"min_valid_warm_count": 1}
    elif _run_mode == "quick":
        _mode_filter_overrides = {"min_valid_warm_count": 3}

    run_plan = RunPlan(
        parent_campaign_id=campaign_id,
        effective_campaign_id=effective_campaign_id,
        run_mode=_run_mode,
        variable=variable,
        all_campaign_values=campaign.get("values", []),
        selected_values=[c["variable_value"] for c in configs],
        selected_configs=configs,
        cycles_per_config=lab_config.get("cycles_per_config", 5),
        requests_per_cycle=lab_config.get("requests_per_cycle", 6),
        baseline_path=baseline_path,
        effective_lab_root=_effective_lab_root,
        db_path=_eff_db_path,
        state_file=_eff_state_file,
        results_dir=_eff_results_dir / effective_campaign_id,
        filter_overrides=_mode_filter_overrides,
        mode_flag=mode_flag,
        values_override=values_override,
        cycles_override=cycles_override,
        requests_per_cycle_override=requests_per_cycle_override,
    )
    logger.info(
        "Run plan: mode=%s  effective_id=%s  configs=%d  cycles=%d  reqs=%d",
        run_plan.run_mode, run_plan.effective_campaign_id,
        len(run_plan.selected_configs), run_plan.cycles_per_config,
        run_plan.requests_per_cycle,
    )

    if dry_run:
        # Log and print so the dry-run output survives in the campaign log file.
        # Any validation failures above (FileNotFoundError, purity violation) would
        # have already raised — reaching here means the campaign is structurally
        # valid. (U2 fix)
        cycles = lab_config.get("cycles_per_config", 3)
        reqs_per_cycle = lab_config.get("requests_per_cycle", 6)
        total_requests = len(configs) * cycles * reqs_per_cycle
        warm_per_cycle = reqs_per_cycle - 1
        warm_samples = cycles * warm_per_cycle

        # Annotate override sources
        cycles_src = ""
        if cycles_override is not None:
            cycles_src = " (CLI override)"
        elif run_plan.is_quick and cycles_override is None:
            cycles_src = " (Quick mode default — 1 cycle, fastest complete-pass)"
        elif run_plan.is_standard and cycles_override is None:
            cycles_src = " (Standard mode default — reduced repetition)"
        elif "cycles_per_config" in campaign:
            cycles_src = " (campaign YAML)"
        reqs_src = ""
        if requests_per_cycle_override is not None:
            reqs_src = " (CLI override)"
        elif "requests_per_cycle" in campaign:
            reqs_src = " (campaign YAML)"

        _mode_label = run_plan.mode_label
        _mode_desc  = run_plan.mode_description
        summary_lines = [
            f"DRY RUN — {campaign_id}",
            f"  Mode:              {_mode_label} — {_mode_desc}",
            f"  Baseline:          {baseline_path}",
            f"  Lab root:          {_effective_lab_root}" + (
                "  [namespaced]" if _effective_lab_root != LAB_ROOT else "  [default]"
            ),
        ]
        if effective_campaign_id != campaign_id:
            summary_lines.append(
                f"  Effective run ID:  {effective_campaign_id}"
            )
            summary_lines.append(
                f"  Parent campaign:   {campaign_id}"
            )
        _all_vals = run_plan.all_campaign_values
        _sel_vals = run_plan.selected_values
        _untested = run_plan.untested_values
        summary_lines += [
            f"  Variable:          {variable}",
            f"  Tested values:     {_sel_vals}  ({len(_sel_vals)} of {len(_all_vals)} total)",
        ]
        if _untested:
            summary_lines.append(
                f"  Skipped values:    {_untested}  (not in this run)"
            )
        if run_plan.filter_overrides:
            summary_lines.append(
                f"  Filter overrides:  {run_plan.filter_overrides}  [{_mode_label} mode]"
            )
        summary_lines += [
            f"  Configs to test:   {len(configs)}",
            f"  Cycles per config: {cycles}{cycles_src}",
            f"  Requests per cycle:{reqs_per_cycle} (1 cold + {warm_per_cycle} warm){reqs_src}",
            f"  Warm samples/cfg:  {warm_samples}",
            f"  Total requests:    {total_requests}",
            f"  Request types:     {', '.join(sorted(request_files.keys()))}",
            f"  Elimination filters: {dict(ELIMINATION_FILTERS)}",
            "",
        ]
        if warm_samples < 20:
            if run_plan.is_custom:
                summary_lines.append(
                    f"  Note: {warm_samples} warm samples — Custom run, sparse data is intentional. "
                    f"Results are valid for comparison within the tested subset only."
                )
            elif run_plan.is_quick:
                summary_lines.append(
                    f"  Note: {warm_samples} warm samples — Quick run (1 cycle, complete coverage). "
                    f"Broad but shallow. Lowest-confidence full-coverage result. "
                    f"Use Standard or Full for deeper confirmation."
                )
            elif run_plan.is_standard:
                summary_lines.append(
                    f"  Note: {warm_samples} warm samples — Standard run (reduced repetition). "
                    f"Development-grade result. Run Full for higher-confidence results."
                )
            else:
                summary_lines.append(
                    f"  Note: {warm_samples} warm samples — detectable difference ~0.4 t/s "
                    f"at 95% confidence"
                )
        if campaign.get("oom_boundary_sweep", False):
            summary_lines.append(
                "  OOM boundary detection: enabled (early termination after 2 consecutive OOMs)"
            )
        for cfg in configs:
            summary_lines.append(
                f"  Config: {cfg['config_id']:<35}  args: {cfg['server_args']}"
            )

        for line in summary_lines:
            console.print(line)
            logger.info(line)
        return

    # -------------------------------------------------------------------------
    # Telemetry startup check (ABORT if ABORT-tier metrics unavailable)
    # -------------------------------------------------------------------------
    console.print("[bold]Running telemetry startup check...[/bold]")
    try:
        availability = tele.startup_check()
        console.print("[green]OK Telemetry startup check passed[/green]")
    except tele.TelemetryStartupError as exc:
        console.print(f"[bold red]CAMPAIGN ABORTED — Telemetry startup check failed:[/bold red]\n{exc}")
        logger.critical("Campaign aborted: %s", exc)
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Defender pre-flight (warning only — never aborts)
    # -------------------------------------------------------------------------
    # Import the resolved paths from server.py so we check the same binary and
    # model that will actually be used, respecting .env overrides.
    from src.server import SERVER_BIN as _sb_pre, MODEL_PATH as _mp_pre  # noqa: PLC0415
    _check_defender_exclusions(_sb_pre, _mp_pre, _effective_lab_root, console)
    _check_windows_search(_effective_lab_root, _mp_pre, console)

    # -------------------------------------------------------------------------
    # Initialize filesystem and database
    # -------------------------------------------------------------------------
    for d in [_eff_results_dir, _eff_logs_dir, _eff_db_dir, _eff_state_dir]:
        d.mkdir(parents=True, exist_ok=True)

    campaign_results_dir = _eff_results_dir / effective_campaign_id
    campaign_results_dir.mkdir(parents=True, exist_ok=True)

    raw_jsonl_path = campaign_results_dir / "raw.jsonl"
    telemetry_jsonl_path = campaign_results_dir / "telemetry.jsonl"

    init_db(_eff_db_path)

    # -------------------------------------------------------------------------
    # Register or resume campaign in DB
    # -------------------------------------------------------------------------
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection(_eff_db_path) as conn:
        existing = conn.execute(
            "SELECT status FROM campaigns WHERE id=?", (effective_campaign_id,)
        ).fetchone()

        if existing is None:
            import hashlib
            baseline_sha = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
            campaign_yaml_path = CAMPAIGNS_DIR / f"{campaign_id}.yaml"
            campaign_sha = hashlib.sha256(campaign_yaml_path.read_bytes()).hexdigest()

            conn.execute(
                """INSERT INTO campaigns
                   (id, name, variable, campaign_type, run_mode, status, created_at, started_at,
                    baseline_sha256, campaign_sha256, rationale)
                   VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?)""",
                (
                    effective_campaign_id,
                    campaign_id,  # human-readable name = parent campaign YAML id
                    variable,
                    campaign.get("type", "primary_sweep"),
                    run_plan.run_mode,
                    now_iso, now_iso,
                    baseline_sha, campaign_sha,
                    campaign.get("rationale", ""),
                ),
            )
            conn.commit()
            logger.info("Campaign %s registered in database", effective_campaign_id)
        elif existing["status"] == "complete" and not resume:
            # U7: clarify what --resume actually does (skips completed configs,
            # does NOT re-run them) so operators aren't confused about data integrity.
            console.print(
                f"[yellow]Campaign {effective_campaign_id} is already marked complete in the "
                f"database. Pass --resume to continue in re-entry mode — completed configs will "
                f"be skipped; only configs not yet marked complete will run.[/yellow]"
            )
            return

    # -------------------------------------------------------------------------
    # Campaign start snapshot
    # -------------------------------------------------------------------------
    # Use SERVER_BIN and MODEL_PATH from server.py — they are the llama.cpp
    # backend constants and the authoritative source for these paths.
    from src.server import SERVER_BIN as _server_bin, MODEL_PATH as _model_path  # noqa: PLC0415

    campaign_yaml_path = CAMPAIGNS_DIR / f"{campaign_id}.yaml"
    sampling_params = baseline.get("sampling", {})

    snap = tele.collect_campaign_start_snapshot(
        campaign_id=effective_campaign_id,
        server_bin=_server_bin,
        model_path=_model_path,
        build_commit=baseline.get("runtime", {}).get("build_commit", "unknown"),
        request_files=request_files,
        campaign_yaml_path=campaign_yaml_path,
        baseline_yaml_path=baseline_path,
        sampling_params=sampling_params,
        cpu_affinity_policy=campaign.get("cpu_affinity_details", {}).get("default", "all_cores"),
    )

    # Add gpu_vram_total_mb for NGL sweep VRAM headroom reporting.
    # Uses pynvml directly — same device index as telemetry.py.
    try:
        import pynvml  # noqa: PLC0415
        pynvml.nvmlInit()
        _handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(_handle)
        snap["gpu_vram_total_mb"] = mem_info.total / (1024 * 1024)
        logger.info("gpu_vram_total_mb captured: %.0f MB", snap["gpu_vram_total_mb"])
    except Exception as _exc:  # noqa: BLE001
        snap["gpu_vram_total_mb"] = None
        logger.warning("Could not capture gpu_vram_total_mb: %s", _exc)

    with get_connection(_eff_db_path) as conn:
        cols = ", ".join(snap.keys())
        placeholders = ", ".join("?" for _ in snap)
        conn.execute(
            f"INSERT OR REPLACE INTO campaign_start_snapshot ({cols}) VALUES ({placeholders})",
            list(snap.values()),
        )
        conn.commit()

    # Write a parallel human-readable YAML snapshot alongside the report.
    # The DB row is the authoritative record; this file is a convenience copy
    # that can be inspected or diffed without opening SQLite. (L1/U6 fix)
    yaml_snapshot_path = _eff_results_dir / effective_campaign_id / "campaign_yaml_snapshot.yaml"
    try:
        yaml_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_snapshot_path.write_text(
            snap.get("campaign_yaml_content") or "",
            encoding="utf-8",
        )
        logger.info("Campaign YAML snapshot written: %s", yaml_snapshot_path)
    except Exception as exc:
        logger.warning("Could not write campaign YAML snapshot file: %s", exc)

    # Log campaign structure so the log file alone is sufficient to reconstruct
    # what was tested. If the YAML is later modified, the log proves what ran.
    logger.info(
        "Campaign %s loaded: variable=%s, values=%s, cycles_per_config=%d, "
        "requests_per_cycle=%d, yaml_sha256=%s",
        effective_campaign_id,
        variable,
        [c.get("variable_value") for c in configs],
        lab_config.get("cycles_per_config", 5),
        lab_config.get("requests_per_cycle", 6),
        snap.get("campaign_yaml_sha256", "unknown")[:12],
    )

    console.print(
        f"[bold]Campaign:[/bold] {effective_campaign_id}  "
        f"[dim]variable={variable}  configs={len(configs)}[/dim]"
    )
    logger.info(
        "Campaign %s: variable=%s, %d configs, %d cycles each",
        effective_campaign_id, variable, len(configs),
        lab_config.get("cycles_per_config", 5),
    )

    # -------------------------------------------------------------------------
    # Load crash recovery state
    # -------------------------------------------------------------------------
    progress_state = _read_progress(_eff_state_file) if resume else {}
    if progress_state.get("campaign_id") and progress_state["campaign_id"] != effective_campaign_id:
        logger.warning(
            "progress.json is for a different campaign (%s vs %s) — starting fresh",
            progress_state["campaign_id"], effective_campaign_id,
        )
        progress_state = {}

    progress_state["campaign_id"] = effective_campaign_id
    progress_state.setdefault("completed_configs", [])
    completed_config_ids = set(progress_state["completed_configs"])

    if completed_config_ids:
        remaining = [c["config_id"] for c in configs if c["config_id"] not in completed_config_ids]
        console.print(
            f"[yellow]Resuming campaign {effective_campaign_id}: "
            f"{len(completed_config_ids)}/{len(configs)} configs already complete, "
            f"{len(remaining)} remaining[/yellow]"
        )
        # Log completed and remaining explicitly so the log alone can prove
        # which configs ran in a prior session vs this one. (L3 fix)
        logger.info(
            "Resuming campaign %s: completed=%s remaining=%s",
            effective_campaign_id,
            sorted(completed_config_ids),
            remaining,
        )
    else:
        logger.info("Starting campaign %s fresh (no prior progress state found)", effective_campaign_id)

    # -------------------------------------------------------------------------
    # Initialize telemetry collector
    # -------------------------------------------------------------------------
    collector = tele.TelemetryCollector(
        db_path=_eff_db_path,
        telemetry_jsonl_path=telemetry_jsonl_path,
    )

    # -------------------------------------------------------------------------
    # Run configs
    # -------------------------------------------------------------------------
    oom_boundary_sweep = campaign.get("oom_boundary_sweep", False)
    if oom_boundary_sweep:
        # Belt-and-suspenders sort check (--validate should have caught this).
        raw_values = campaign.get("values", [])
        if raw_values != sorted(raw_values):
            logger.warning(
                "oom_boundary_sweep: values not sorted ascending in campaign YAML — "
                "auto-sorting. Run --validate to catch this before next run."
            )
        consecutive_ooms = 0

    first_config = True
    try:
        for i, config in enumerate(configs):
            config_id = config["config_id"]

            if config_id in completed_config_ids:
                console.print(f"[dim]Skipping {config_id} (already complete)[/dim]")
                continue

            # U3: show overall campaign progress so the operator can track
            # time-to-completion at a glance.  Printed before cooldown so the
            # "Config X/Y" header anchors each section of the log.
            console.print(
                f"\n[bold cyan]Config {i + 1}/{len(configs)}: {config_id}[/bold cyan]"
            )
            logger.info(
                "Starting config %d/%d: %s (variable=%s, value=%s)",
                i + 1, len(configs), config_id,
                config.get("variable_name"), config.get("variable_value"),
            )

            # Cooldown between configs (skip before very first)
            if not first_config:
                _enforce_cooldown(lab_config, config_id, console)
            first_config = False

            result = _run_config(
                config=config,
                campaign_id=effective_campaign_id,
                lab_config=lab_config,
                request_files=request_files,
                db_path=_eff_db_path,
                raw_jsonl_path=raw_jsonl_path,
                telemetry_jsonl_path=telemetry_jsonl_path,
                collector=collector,
                progress_state=progress_state,
                console=console,
                oom_boundary_sweep=oom_boundary_sweep,
                state_dir=_eff_state_dir,
                state_file=_eff_state_file,
                logs_dir=_eff_logs_dir,
            )

            if oom_boundary_sweep:
                if result == "oom":
                    consecutive_ooms += 1
                    if consecutive_ooms == 1:
                        logger.warning(
                            "OOM on config %s (consecutive=%d) — "
                            "continuing to next config to confirm boundary",
                            config_id, consecutive_ooms,
                        )
                        console.print(
                            f"  [yellow]OOM ({consecutive_ooms}/2) — "
                            f"continuing to confirm boundary[/yellow]"
                        )
                    elif consecutive_ooms >= 2:
                        logger.error(
                            "OOM confirmed on config %s (consecutive=%d) — "
                            "VRAM ceiling established; terminating sweep",
                            config_id, consecutive_ooms,
                        )
                        console.print(
                            f"\n[bold red]OOM boundary confirmed[/bold red] "
                            f"(2 consecutive OOM failures). Terminating sweep.\n"
                            f"All remaining configs will be marked skipped_oom."
                        )
                        # Mark all remaining configs skipped_oom in DB + progress
                        # BEFORE break, so crash recovery skips them on resume.
                        remaining_configs = configs[i + 1:]
                        if remaining_configs:
                            detail = "boundary confirmed by 2 consecutive OOM failures"
                            with get_connection(_eff_db_path) as conn:
                                for rc in remaining_configs:
                                    conn.execute(
                                        """INSERT OR IGNORE INTO configs
                                           (id, campaign_id, variable_name, variable_value,
                                            config_values_json, status, failure_detail, started_at)
                                           VALUES (?, ?, ?, ?, ?, 'skipped_oom', ?, ?)""",
                                        (
                                            rc["config_id"], effective_campaign_id,
                                            rc["variable_name"],
                                            json.dumps(rc["variable_value"]),
                                            json.dumps(rc["full_config"]),
                                            detail,
                                            datetime.now(timezone.utc).isoformat(),
                                        ),
                                    )
                                conn.commit()
                            skipped_ids = [rc["config_id"] for rc in remaining_configs]
                            completed = progress_state.get("completed_configs", [])
                            for sid in skipped_ids:
                                if sid not in completed:
                                    completed.append(sid)
                            progress_state["completed_configs"] = completed
                            _write_progress(progress_state, _eff_state_dir, _eff_state_file)
                            logger.info(
                                "Marked %d configs as skipped_oom: %s",
                                len(skipped_ids), skipped_ids,
                            )
                        break
                else:
                    if oom_boundary_sweep and consecutive_ooms > 0:
                        logger.info(
                            "Config %s succeeded after %d OOM(s) — prior OOM was transient; "
                            "resetting consecutive_ooms counter",
                            config_id, consecutive_ooms,
                        )
                    consecutive_ooms = 0

    except KeyboardInterrupt:
        logger.warning("Campaign %s interrupted by user (KeyboardInterrupt)", effective_campaign_id)
        console.print("\n[yellow]Interrupted. Progress saved — resume with --resume[/yellow]")
        return
    except Exception as exc:
        logger.critical("Campaign %s fatal error: %s", effective_campaign_id, exc, exc_info=True)
        console.print(f"[bold red]Fatal error: {exc}[/bold red]")
        with get_connection(_eff_db_path) as conn:
            conn.execute(
                "UPDATE campaigns SET status='failed', failed_at=?, failure_reason=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), str(exc), effective_campaign_id),
            )
            conn.commit()
        raise

    finally:
        tele.shutdown()

    # -------------------------------------------------------------------------
    # Campaign complete
    # -------------------------------------------------------------------------
    with get_connection(_eff_db_path) as conn:
        conn.execute(
            "UPDATE campaigns SET status='complete', completed_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), effective_campaign_id),
        )
        conn.commit()

    _clear_progress(_eff_state_file)

    console.print(f"\n[bold green]Campaign {effective_campaign_id} complete.[/bold green]")
    logger.info("Campaign %s complete.", effective_campaign_id)

    # Run analysis + scoring + report
    # Failure here does NOT mean data was lost — raw.jsonl and lab.sqlite are
    # intact and rescore.py can replay the pipeline at any time. However, the
    # runner MUST exit non-zero so automation (CI pipelines, batch scripts) can
    # detect the failure. Exiting 0 when the report failed to generate is data
    # falsification from the caller's perspective. (L5 fix)
    console.print("[bold]Running analysis and scoring...[/bold]")
    report_ok = False
    try:
        from src.analyze import analyze_campaign
        from src.score import score_campaign
        from src.report import generate_report

        # Build the effective filter_overrides for scoring:
        #   1. Start with mode-level overrides (from RunPlan — e.g. Custom relaxes
        #      min_valid_warm_count so sparse-but-intentional runs aren't rejected).
        #   2. Merge campaign YAML elimination_overrides on top (YAML wins on conflict
        #      so explicit campaign-level decisions always take precedence).
        yaml_filter_overrides = campaign.get("elimination_overrides") or {}
        effective_filter_overrides: dict | None = None
        if run_plan.filter_overrides or yaml_filter_overrides:
            effective_filter_overrides = {**(run_plan.filter_overrides or {}), **yaml_filter_overrides}
            logger.info(
                "Effective filter overrides (mode=%s + campaign YAML): %s",
                run_plan.run_mode, effective_filter_overrides,
            )

        # effective_campaign_id is the DB key for this run.  For full runs it
        # equals campaign_id; for Custom runs it is the scoped identity
        # (e.g. "NGL_sweep__v30"), so analyze/score/report operate only on the
        # rows this run actually inserted — no cross-contamination from prior
        # broader runs.
        scores = score_campaign(
            effective_campaign_id, _eff_db_path, baseline,
            filter_overrides=effective_filter_overrides,
        )
        stats = scores["stats"]

        report_path = generate_report(
            effective_campaign_id, _eff_db_path, baseline, scores, stats,
            campaign=campaign,
            lab_root=_effective_lab_root,
            run_plan=run_plan,
        )
        console.print(f"[green]Report written:[/green] {report_path}")
        report_ok = True

        # Generate the evidence-first campaign report (new philosophy).
        # Failure here is non-fatal — the primary report above is the critical path.
        try:
            from src.report_campaign import generate_campaign_report  # noqa: PLC0415
            v2_path = generate_campaign_report(
                effective_campaign_id, _eff_db_path, baseline, scores, stats,
                campaign=campaign,
                run_plan=run_plan,
                lab_root=_effective_lab_root,
            )
            console.print(f"[green]Evidence report written:[/green] {v2_path}")
        except Exception as _v2_exc:
            logger.warning(
                "Evidence-first report generation failed (non-fatal): %s", _v2_exc
            )

    except Exception as exc:
        logger.error("Post-campaign analysis failed: %s", exc, exc_info=True)
        console.print(
            f"[bold red]Analysis failed (raw data is safe — run rescore.py to retry):[/bold red]\n{exc}"
        )

    if not report_ok:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(campaign_id: str, logs_dir: Path | None = None) -> None:
    """Configure logging to both console and file."""
    # Allow callers to supply an effective logs_dir derived from the active
    # lab root; fall back to the module-level default for default-baseline runs.
    effective_logs_dir = logs_dir if logs_dir is not None else LOGS_DIR
    log_dir = effective_logs_dir / campaign_id
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_file = log_dir / f"runner_{ts}.log"

    fmt = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%SZ"

    # Root logger — captures everything from all modules
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # File handler — full DEBUG detail
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(fh)

    # Console handler — INFO and above only
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(fmt, datefmt))
    root.addHandler(ch)

    logger.info("Log file: %s", log_file)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _validate_campaign(
    campaign_id: str,
    values_override: list | None = None,
    baseline_path: Path = BASELINE_YAML,
    mode_flag: str | None = None,
) -> bool:
    """
    Validate a campaign YAML without running any measurements.

    Checks (in order — stops reporting after first structural failure):
      1. baseline.yaml exists and loads cleanly
      2. campaign YAML exists and loads cleanly
      3. Campaign purity (exactly one variable vs baseline)
      4. All request files referenced in baseline.yaml exist on disk
      5. Runtime binaries: SERVER_BIN exists, is non-empty, and is executable;
         MODEL_PATH first shard exists and has plausible file size
      6. Baseline completeness (lab section, reference section)
      7. Campaign-level elimination_overrides keys are valid filter names

    The server binary check (5) covers the most common "why didn't it start"
    failure: a stale build path after rebuilding llama.cpp in a new directory.
    Override paths via QUANTMAP_SERVER_BIN / QUANTMAP_MODEL_PATH env vars.

    Prints a structured report to console AND the log file.
    Returns True if all checks pass, False if any fail.
    (U1 fix)
    """
    # Derive effective lab root FIRST — _setup_logging must receive the
    # correct logs_dir or the runner log file lands in the wrong directory.
    _eff_lab_root_val = _derive_lab_root(baseline_path)
    _eff_logs_dir_val = _eff_lab_root_val / "logs"

    # Effective campaign identity — same logic as run_campaign.
    # values_override is not yet validated here (check 3.5 does that), but the
    # helper is safe to call with any list; it only formats the string.
    _eff_cid_val = _derive_effective_campaign_id(campaign_id, values_override, mode_flag)

    _setup_logging(_eff_cid_val, logs_dir=_eff_logs_dir_val)
    logger.info("Validating campaign: %s  (baseline=%s)", _eff_cid_val, baseline_path)
    if baseline_path != BASELINE_YAML:
        logger.info("INFO: --baseline override active: %s", baseline_path)
        console.print(f"[dim]Active baseline: {baseline_path}[/dim]")

    if _eff_cid_val != campaign_id:
        if mode_flag == "quick":
            _val_scope_reason = "--mode quick"
        elif mode_flag == "standard":
            _val_scope_reason = "--mode standard"
        else:
            _val_scope_reason = "--values scope"
        logger.info(
            "Effective run ID (%s): %s  (parent campaign: %s)",
            _val_scope_reason, _eff_cid_val, campaign_id,
        )
        console.print(
            f"[yellow]Effective run ID:[/yellow] {_eff_cid_val}  "
            f"[dim](parent campaign: {campaign_id})[/dim]"
        )
    if _eff_lab_root_val != LAB_ROOT:
        logger.info("Lab root (namespaced): %s", _eff_lab_root_val)
        console.print(f"[dim]Lab root (namespaced): {_eff_lab_root_val}[/dim]")
    else:
        logger.info("Lab root (default): %s", _eff_lab_root_val)

    ok = True

    def _check(label: str, passed: bool, detail: str = "") -> bool:
        status = "[green]PASS[/green]" if passed else "[bold red]FAIL[/bold red]"
        msg = f"  {status}  {label}" + (f"  — {detail}" if detail else "")
        console.print(msg)
        log_msg = f"  {'PASS' if passed else 'FAIL'}  {label}" + (f"  — {detail}" if detail else "")
        (logger.info if passed else logger.error)(log_msg)
        return passed

    console.print(f"\n[bold]Validating campaign: {campaign_id}[/bold]")

    # 1. baseline.yaml
    try:
        baseline = load_baseline(baseline_path)
        ok = _check(f"baseline YAML loads: {baseline_path}", True) and ok
    except Exception as exc:
        _check(f"baseline YAML loads: {baseline_path}", False, str(exc))
        return False  # can't continue without baseline

    # 2. campaign YAML
    try:
        campaign = load_campaign(campaign_id)
        ok = _check("campaign YAML loads", True, str(CAMPAIGNS_DIR / f"{campaign_id}.yaml")) and ok
    except Exception as exc:
        _check("campaign YAML loads", False, str(exc))
        return False  # can't continue without campaign

    # 3. Purity check
    try:
        variable = validate_campaign_purity(baseline, campaign)
        values = campaign.get("values", [])
        ok = _check("campaign purity (one variable)", True,
                    f"variable={variable!r}, {len(values)} values: {values}") and ok
    except CampaignPurityViolationError as exc:
        ok = _check("campaign purity (one variable)", False, str(exc)) and ok

    # 3.5 Values override validation (if --values used)
    if values_override is not None:
        campaign_values_all = campaign.get("values", [])
        bad_vals = [v for v in values_override if v not in campaign_values_all]
        ok = _check(
            "--values override: all values present in campaign",
            len(bad_vals) == 0,
            (
                f"using {len(values_override)} of {len(campaign_values_all)} values: {values_override}"
                if not bad_vals
                else f"invalid: {bad_vals}; campaign has: {campaign_values_all}"
            ),
        ) and ok
        _check(
            "effective run ID",
            True,
            f"{_eff_cid_val}",
        )

    # 3.6 Mode identity checks (if --mode quick or --mode standard used)
    if mode_flag == "quick":
        _check(
            "effective run ID (--mode quick)",
            True,
            f"{_eff_cid_val}  (isolated from Full/Standard run of same campaign)",
        )
        _check(
            "--mode quick cycles",
            True,
            f"{QUICK_CYCLES_PER_CONFIG} cycle per config (broad but shallow — lowest-confidence full-coverage)",
        )
    elif mode_flag == "standard":
        _check(
            "effective run ID (--mode standard)",
            True,
            f"{_eff_cid_val}  (isolated from Full run of same campaign)",
        )
        _check(
            "--mode standard cycles",
            True,
            f"{STANDARD_CYCLES_PER_CONFIG} cycles per config (reduced repetition — development-grade)",
        )

    # 4. Request files
    req_cfg = baseline.get("requests", {})
    if not req_cfg:
        ok = _check("request files defined in baseline.yaml", False,
                    "baseline.yaml has no 'requests:' section") and ok
    else:
        for req_name, rel_path in req_cfg.items():
            full_path = _REPO_ROOT / rel_path
            ok = _check(
                f"request file: {req_name}",
                full_path.is_file(),
                str(full_path),
            ) and ok

    # 5. Runtime binaries — server binary and first model shard
    #
    # These are the two most common silent-failure points:
    #   a) SERVER_BIN: stale path after rebuilding llama.cpp in a new directory
    #   b) MODEL_PATH: incomplete shard download or wrong first-shard filename
    #
    # Import here (not at module top) to avoid import-time side effects when
    # src.server is loaded — it reads env vars and resolves paths at import.
    from src.server import SERVER_BIN as _server_bin, MODEL_PATH as _model_path  # noqa: PLC0415

    # Server binary: exists, is a file, non-zero (zero-byte = failed/incomplete build)
    bin_exists = _server_bin.is_file()
    bin_size = _server_bin.stat().st_size if bin_exists else 0
    bin_nonempty = bin_size > 0
    bin_executable = bin_exists and os.access(_server_bin, os.X_OK)

    # Path goes in the label — not the detail — so the resolved path is the
    # first thing the user reads on both PASS and FAIL.  This makes it
    # immediately obvious whether the env var was picked up or not.
    if bin_exists:
        bin_detail = f"{bin_size / 1024:.0f} KB"
        bin_detail += ", executable" if bin_executable else ", NOT executable — missing chmod +x?"
    else:
        bin_detail = f"QUANTMAP_SERVER_BIN env = {os.environ.get('QUANTMAP_SERVER_BIN', '<not set>')}"

    ok = _check(
        f"server binary: {_server_bin}",
        bin_exists and bin_nonempty,
        bin_detail,
    ) and ok
    if bin_exists and bin_nonempty and not bin_executable:
        # Non-fatal on Windows (X_OK is extension-based and always true for .exe),
        # but a genuine warning on Linux/macOS where chmod +x may have been forgotten.
        _check(f"server binary executable: {_server_bin}", bin_executable, "")

    # Model path: first shard exists and the model set is plausibly real.
    #
    # Some multi-shard models (e.g. unsloth/MiniMax-M2.5-GGUF UD-Q3_K_XL) use
    # a small header/index file as shard 1 (~8 MB) with the actual weights in
    # shards 2-4 (~49 GB each).  Requiring shard 1 to be >100 MB incorrectly
    # rejects these layouts.
    #
    # Acceptance rule:
    #   (a) shard 1 is >100 MB  (single-file or standard multi-shard layout), OR
    #   (b) shard 1 is small AND shard 2 (00002-of-NNNNN) exists and is >100 MB
    #       (header-shard layout — confirms weight files are present)
    model_exists = _model_path.is_file()
    model_size_bytes = _model_path.stat().st_size if model_exists else 0
    model_size_gb = model_size_bytes / (1024 ** 3)
    model_plausible = model_size_gb > 0.1  # >100 MB — standard layout

    shard2_detail = ""
    if model_exists and not model_plausible:
        # Check for header-shard layout: look for 00002-of-NNNNN adjacent shard.
        shard2_name = _model_path.name.replace("00001-of-", "00002-of-", 1)
        if shard2_name != _model_path.name:
            shard2_path = _model_path.parent / shard2_name
            if shard2_path.is_file():
                shard2_bytes = shard2_path.stat().st_size
                if shard2_bytes > 100 * 1024 * 1024:  # >100 MB
                    model_plausible = True
                    shard2_gb = shard2_bytes / (1024 ** 3)
                    shard2_detail = f"; shard 2 present ({shard2_gb:.1f} GB) — header-shard layout"

    # Same pattern as the binary check: path in the label so it leads the line.
    if model_exists:
        if model_size_bytes < 1024 ** 2:
            size_str = f"{model_size_bytes / 1024:.0f} KB"
        elif model_size_bytes < 1024 ** 3:
            size_str = f"{model_size_bytes / 1024 ** 2:.1f} MB"
        else:
            size_str = f"{model_size_gb:.1f} GB"
        model_detail = size_str + shard2_detail
        if not model_plausible:
            model_detail += " — expected >100 MB for a real GGUF shard; set QUANTMAP_MODEL_PATH"
    else:
        model_detail = f"QUANTMAP_MODEL_PATH env = {os.environ.get('QUANTMAP_MODEL_PATH', '<not set>')}"

    ok = _check(
        f"model shard 1: {_model_path}",
        model_exists and model_plausible,
        model_detail,
    ) and ok

    # 6. Baseline completeness
    lab = baseline.get("lab", {})
    for key in ("cycles_per_config", "requests_per_cycle", "cooldown_between_configs_s"):
        ok = _check(
            f"baseline.yaml lab.{key} present",
            key in lab,
            f"value={lab.get(key, '<MISSING>')!r}",
        ) and ok

    ref = baseline.get("reference", {})
    for key in ("warm_tg_median_ts", "warm_ttft_median_ms", "cold_ttft_ms"):
        ok = _check(
            f"baseline.yaml reference.{key} present",
            key in ref,
            f"value={ref.get(key, '<MISSING>')!r}",
        ) and ok

    # 7. elimination_overrides keys (if present)
    overrides = campaign.get("elimination_overrides", {})
    if overrides:
        valid_keys = set(ELIMINATION_FILTERS.keys())
        for key in overrides:
            ok = _check(
                f"elimination_overrides.{key} is a known filter",
                key in valid_keys,
                f"valid keys: {sorted(valid_keys)}" if key not in valid_keys else "",
            ) and ok

    # 8. oom_boundary_sweep: values must be ascending
    if campaign.get("oom_boundary_sweep", False):
        values = campaign.get("values", [])
        is_sorted = values == sorted(values)
        ok = _check(
            "oom_boundary_sweep: values ascending",
            is_sorted,
            f"values must be in ascending order for early termination to be correct; "
            f"got {values}" if not is_sorted else f"{values}",
        ) and ok

    # 9. Environment warnings (advisory — do not affect the ok flag)
    #    Run the same Defender and WSearch checks as campaign startup so users
    #    see interference risks before committing to a multi-hour run.
    if sys.platform == "win32":
        console.print("\n[bold]Environment warnings (advisory — do not block validation):[/bold]")
        _check_defender_exclusions(_server_bin, _model_path, _eff_lab_root_val, console)
        _check_windows_search(_eff_lab_root_val, _model_path, console)

    # Summary
    console.print()
    if ok:
        configs = build_config_list(baseline, campaign)
        if values_override is not None:
            all_count = len(configs)
            configs = [c for c in configs if c["variable_value"] in values_override]
            console.print(
                f"[dim]--values override: {len(configs)} of {all_count} campaign configs "
                f"(values={values_override})[/dim]"
            )
        # Resolve effective cycles/requests using the same layer ordering as run_campaign:
        # baseline → campaign YAML → mode-specific default → (CLI --cycles not available here)
        cycles = campaign.get("cycles_per_config", lab.get("cycles_per_config", 5))
        reqs = campaign.get("requests_per_cycle", lab.get("requests_per_cycle", 6))
        source_parts: list[str] = []
        if "cycles_per_config" in campaign:
            source_parts.append(f"cycles from campaign YAML ({cycles})")
        if mode_flag == "quick":
            # Quick mode override applied here to match run_campaign Layer 2.5 behavior.
            # CLI --cycles is not available in validate; if user passes --cycles it will
            # take precedence at actual run time.
            cycles = QUICK_CYCLES_PER_CONFIG
            source_parts.append(f"cycles from Quick mode default ({cycles})")
        elif mode_flag == "standard":
            cycles = STANDARD_CYCLES_PER_CONFIG
            source_parts.append(f"cycles from Standard mode default ({cycles})")
        if "requests_per_cycle" in campaign:
            source_parts.append(f"requests from campaign YAML ({reqs})")
        source_note = f"  [dim]({'; '.join(source_parts)})[/dim]" if source_parts else ""

        warm_per_cycle = reqs - 1  # first request each cycle is cold
        warm_samples = len(configs) and (cycles * warm_per_cycle)

        console.print(
            f"[bold green]All checks passed.[/bold green]  "
            f"{len(configs)} configs × {cycles} cycles × {reqs} requests = "
            f"{len(configs) * cycles * reqs} total requests.{source_note}"
        )
        _validate_run_mode = resolve_run_mode(values_override, mode_flag)
        if warm_samples < 20:
            if _validate_run_mode == "custom":
                console.print(
                    f"  [dim]Note: {warm_samples} warm samples per config — "
                    f"Custom run, sparse data is intentional. "
                    f"Results are valid for comparison within the tested subset only.[/dim]"
                )
            elif _validate_run_mode == "quick":
                console.print(
                    f"  [dim]Note: {warm_samples} warm samples per config — "
                    f"Quick run (1 cycle, complete coverage). Broad but shallow. "
                    f"Lowest-confidence full-coverage result. "
                    f"Use Standard or Full for deeper confirmation.[/dim]"
                )
            elif _validate_run_mode == "standard":
                console.print(
                    f"  [dim]Note: {warm_samples} warm samples per config — "
                    f"Standard run (reduced repetition). Development-grade result. "
                    f"Run Full for higher-confidence statistics.[/dim]"
                )
            else:
                console.print(
                    f"  [dim]Note: {warm_samples} warm samples per config — "
                    f"detectable difference ~0.4 t/s at 95% confidence. "
                    f"Use --cycles {max(cycles + 1, 4)} for narrower confidence interval.[/dim]"
                )
        logger.info("Validation passed: %s", campaign_id)
    else:
        console.print("[bold red]Validation FAILED — fix errors above before running.[/bold red]")
        logger.error("Validation failed: %s", campaign_id)

    return ok


def _list_campaigns() -> None:
    """
    Print a summary table of all campaigns recorded in the lab database.

    Columns: campaign ID, status, config count, winner (if scored), completed/started
    timestamp, report path.  Exits cleanly if no db exists yet.
    """
    db_path = DB_PATH
    if not db_path.exists():
        console.print("[yellow]No database found.[/yellow] Run a campaign first.")
        return

    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.run_mode,
                c.status,
                (SELECT COUNT(*) FROM configs cf WHERE cf.campaign_id = c.id) AS cfg_count,
                (SELECT s.config_id FROM scores s
                 WHERE s.campaign_id = c.id AND s.is_score_winner = 1
                 LIMIT 1) AS winner,
                (SELECT ROUND(s.warm_tg_median, 2) FROM scores s
                 WHERE s.campaign_id = c.id AND s.is_score_winner = 1
                 LIMIT 1) AS winner_tg,
                COALESCE(c.completed_at, c.started_at, c.created_at) AS ts,
                (SELECT a.path FROM artifacts a
                 WHERE a.campaign_id = c.id AND a.artifact_type = 'report_md'
                 LIMIT 1) AS report_path
            FROM campaigns c
            ORDER BY ts DESC
            """,
        ).fetchall()

    if not rows:
        console.print("[yellow]No campaigns in database yet.[/yellow]")
        return

    from src.run_plan import MODE_LABELS as _ML  # noqa: PLC0415

    tbl = Table(show_header=True, header_style="bold", box=None, pad_edge=False, min_width=80)
    tbl.add_column("Campaign", style="cyan", no_wrap=True)
    tbl.add_column("Mode", no_wrap=True)
    tbl.add_column("Status", no_wrap=True)
    tbl.add_column("Cfgs", justify="right")
    tbl.add_column("Winner", no_wrap=True)
    tbl.add_column("TG (t/s)", justify="right")
    tbl.add_column("Timestamp (UTC)", no_wrap=True)
    tbl.add_column("Report")

    status_styles = {
        "complete": "green",
        "running": "yellow",
        "failed": "red",
        "aborted": "red",
        "pending": "dim",
    }

    for campaign_id, run_mode, status, cfg_count, winner, winner_tg, ts, report_path in rows:
        style = status_styles.get(status, "")
        ts_short = (ts or "")[:16].replace("T", " ")  # "2026-03-31 14:22"
        report_display = str(report_path) if report_path else "—"
        mode_label = _ML.get(run_mode, run_mode.title()) if run_mode else "—"
        tbl.add_row(
            campaign_id,
            mode_label,
            f"[{style}]{status}[/{style}]" if style else status,
            str(cfg_count),
            winner or "—",
            f"{winner_tg:.2f}" if winner_tg is not None else "—",
            ts_short,
            report_display,
        )

    console.print()
    console.print(tbl)
    console.print()


def _parse_values_arg(raw: str) -> list:
    """
    Parse the --values string into a typed list.

    Tries int conversion first; keeps original string on failure.
    Example: "30,80,999" → [30, 80, 999]
    """
    result = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            result.append(part)
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QuantMap campaign runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.runner --campaign C01_threads_batch
  python -m src.runner --campaign C01_threads_batch --resume
  python -m src.runner --campaign C01_threads_batch --dry-run
  python -m src.runner --campaign C01_threads_batch --validate
  python -m src.runner --campaign C01_threads_batch --baseline configs/minimax_baseline.yaml
  python -m src.runner --campaign NGL_sweep --mode standard     (Standard mode — all values, reduced repetition)
  python -m src.runner --campaign NGL_sweep --mode quick        (Quick mode — all values, 1 cycle, fastest complete-pass)
  python -m src.runner --campaign NGL_sweep --values 30         (Custom mode — single value)
  python -m src.runner --campaign NGL_sweep --values 30,80,999  (Custom mode — subset)
        """,
    )
    parser.add_argument(
        "--campaign",
        help="Campaign ID (matches configs/campaigns/{id}.yaml); required unless --list is used"
    )
    parser.add_argument(
        "--baseline", default=None, metavar="PATH",
        help=(
            "Path to a baseline YAML file (default: configs/baseline.yaml). "
            "Overrides the default for this run only — useful when benchmarking "
            "multiple models without touching the committed baseline."
        ),
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Show all campaigns in the lab database (completed, running, pending) and exit"
    )
    parser.add_argument(
        "--validate", action="store_true",
        help="Check campaign YAML, request files, and baseline completeness without running"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be run without executing measurements"
    )
    parser.add_argument(
        "--resume", action="store_true", default=True,
        help="Resume from crash recovery state (default: True)"
    )
    parser.add_argument(
        "--no-resume", action="store_false", dest="resume",
        help="Start fresh, ignoring crash recovery state"
    )
    parser.add_argument(
        "--cycles", type=int, default=None, metavar="N",
        help="Override cycles_per_config (baseline.yaml and campaign YAML) for this run"
    )
    parser.add_argument(
        "--requests-per-cycle", type=int, default=None, metavar="N",
        help="Override requests_per_cycle (baseline.yaml and campaign YAML) for this run"
    )
    parser.add_argument(
        "--mode", default=None, choices=["full", "standard", "quick"],
        metavar="MODE",
        help=(
            "Run mode: 'full' (default), 'standard', or 'quick'. "
            "full: complete campaign, all values, full schedule — highest-confidence, recommendation-grade. "
            "standard: complete campaign, all values, reduced repetition (3 cycles) — development-grade. "
            "quick: complete campaign, all values, 1 cycle — fastest complete-pass, broad but shallow. "
            "Each non-full mode gets its own DB identity (e.g. NGL_sweep__quick, NGL_sweep__standard) "
            "and report, isolated from any Full run of the same campaign. "
            "Cannot be combined with --values."
        ),
    )
    parser.add_argument(
        "--values", default=None, metavar="VALUE_LIST",
        help=(
            "Comma-separated list of campaign variable values to test (e.g. 30 or 30,80,999). "
            "Triggers Custom mode: an isolated run scoped to exactly these values. "
            "The run gets its own DB identity (e.g. NGL_sweep__v30), results directory, "
            "and report — fully isolated from any Full run of the same campaign. "
            "Values must exist in the campaign's values list. "
            "Cannot be combined with --mode. "
            "If omitted and --mode is not set, all campaign values are used (Full mode)."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    # Resolve --baseline to an absolute Path, defaulting to the repo's
    # configs/baseline.yaml.  Validated here so the error is reported before
    # any logging is set up (cleaner UX than a FileNotFoundError from deep inside).
    if args.baseline is not None:
        _active_baseline = Path(args.baseline)
        if not _active_baseline.is_absolute():
            _active_baseline = (_REPO_ROOT / _active_baseline).resolve()
        if not _active_baseline.is_file():
            console.print(
                f"[bold red]error:[/bold red] --baseline path not found: {_active_baseline}"
            )
            sys.exit(2)
        console.print(f"[dim]Active baseline: {_active_baseline}[/dim]")
    else:
        _active_baseline = BASELINE_YAML

    # Parse --values override (if supplied)
    _values_override: list | None = None
    if args.values is not None:
        _values_override = _parse_values_arg(args.values)
        if not _values_override:
            console.print("[bold red]error:[/bold red] --values is empty — provide at least one value")
            sys.exit(2)

    # Resolve mode flag — None means Full (default); "full" is explicitly the default
    # and normalized to None so existing callers are unaffected.
    _mode_flag: str | None = args.mode if args.mode not in (None, "full") else None

    # --mode and --values are mutually exclusive regardless of the mode value.
    # "full" is the default, so --mode full --values 30 is ambiguous: the user said
    # "full mode" but --values would trigger Custom isolation. Reject explicitly.
    if args.mode is not None and _values_override is not None:
        console.print(
            "[bold red]error:[/bold red] --mode and --values cannot be combined. "
            "--mode selects a run mode for the full campaign value list; "
            "--values triggers Custom mode for a specific value subset. "
            "Omit --mode to let --values alone trigger Custom mode."
        )
        sys.exit(2)

    if args.list:
        _list_campaigns()
        sys.exit(0)
    if not args.campaign:
        console.print("[bold red]error:[/bold red] --campaign is required (or use --list to see campaigns)")
        sys.exit(2)
    if args.validate:
        ok = _validate_campaign(
            args.campaign,
            values_override=_values_override,
            baseline_path=_active_baseline,
            mode_flag=_mode_flag,
        )
        sys.exit(0 if ok else 1)
    run_campaign(
        campaign_id=args.campaign,
        dry_run=args.dry_run,
        resume=args.resume,
        cycles_override=args.cycles,
        requests_per_cycle_override=args.requests_per_cycle,
        values_override=_values_override,
        baseline_path=_active_baseline,
        mode_flag=_mode_flag,
    )
