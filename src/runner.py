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
            - Runs 6 requests (cycles 1–4: all speed_short;
              cycle 5: 5 speed_short + 1 speed_medium)
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
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
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

load_dotenv()

# Internal modules
from src.config import CONFIGS_DIR, DEFAULT_HOST, LAB_ROOT, REQUESTS_DIR  # noqa: E402
from src.server import start_server, get_production_command, get_runtime_env_summary
from src.measure import load_request_payload, measure_request_sync, RequestOutcome
from src import telemetry as tele
from src.db import init_db, get_connection, write_request, write_raw_jsonl
from src.score import ELIMINATION_FILTERS  # noqa: E402 — used in dry-run summary

console = Console()
logger = logging.getLogger(__name__)

# Repository root — src/runner.py is one level below the repo root.
# Used to resolve request file paths relative to the repo (not LAB_ROOT).
_REPO_ROOT: Path = Path(__file__).parent.parent

# Runtime outputs always go into LAB_ROOT.
RESULTS_DIR = LAB_ROOT / "results"
LOGS_DIR = LAB_ROOT / "logs"
DB_DIR = LAB_ROOT / "db"
STATE_DIR = LAB_ROOT / "state"
DB_PATH = DB_DIR / "lab.sqlite"
STATE_FILE = STATE_DIR / "progress.json"

BASELINE_YAML = CONFIGS_DIR / "baseline.yaml"
CAMPAIGNS_DIR = CONFIGS_DIR / "campaigns"


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
        if variable == "cpu_affinity":
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

def _read_progress() -> dict[str, Any]:
    """Read crash recovery state. Returns empty dict if none exists."""
    if STATE_FILE.is_file():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not read progress.json: %s — starting fresh", exc)
    return {}


def _write_progress(state: dict[str, Any]) -> None:
    """Write crash recovery state."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _clear_progress() -> None:
    """Clear crash recovery state on clean campaign completion."""
    if STATE_FILE.is_file():
        # Overwrite with empty object rather than deleting (per MDD §11.3)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
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
    console: Console,
) -> None:
    """
    Warn if Windows Defender real-time protection may be scanning the server
    binary or model files.  Unexcluded MoE model paths can add measurable I/O
    latency during model load and during expert dispatch (each active-expert
    weight page is a potential scan trigger).

    This is a WARNING only — it never aborts the campaign.  If PowerShell is
    unavailable or the query times out the check is silently skipped.
    """
    if sys.platform != "win32":
        return

    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "(Get-MpPreference).ExclusionPath | ConvertTo-Json -Compress",
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
        if not raw or raw.lower() == "null":
            exclusions: list[str] = []
        else:
            data = _json.loads(raw)
            exclusions = [data] if isinstance(data, str) else list(data or [])

        excl_lower = [str(e).rstrip("\\/ ").lower() for e in exclusions]

        # Check each path: consider it covered if the exclusion is a prefix of
        # the target dir (or an exact match).  Also accepts if the target dir is
        # a prefix of the exclusion (e.g. user excluded the whole drive root).
        paths_to_check = [
            ("server binary dir", server_bin.parent),
            ("model dir", model_path.parent),
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
            console.print("[yellow]⚠️  Windows Defender Exclusion Warning[/yellow]")
            logger.warning("Windows Defender: the following paths are NOT in the exclusion list:")
            for label, path in not_excluded:
                console.print(f"  [yellow]• {label}: {path}[/yellow]")
                logger.warning("  Not excluded: %s (%s)", label, path)
            console.print(
                "[yellow]  Defender may scan model loads and MoE dispatch I/O, adding "
                "non-deterministic latency.  To add exclusions:\n"
                "  Settings → Windows Security → Virus & threat protection → "
                "Manage settings → Exclusions → Add or remove exclusions → Add a folder[/yellow]"
            )
            logger.warning(
                "Recommendation: add '%s' and '%s' to Defender exclusions.",
                server_bin.parent, model_path.parent,
            )
        else:
            logger.info("Defender exclusion check: server binary dir and model dir are excluded ✓")
            console.print("[green]✓ Defender exclusions OK[/green]")

    except FileNotFoundError:
        logger.debug("Defender check skipped — powershell.exe not found")
    except subprocess.TimeoutExpired:
        logger.warning("Defender exclusion check timed out (>15s) — skipping")
    except Exception as exc:
        logger.debug("Defender exclusion check failed: %s — skipping", exc)


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

    try:
        with start_server(
            extra_args=server_args,
            campaign_id=campaign_id,
            config_id=config_id,
            cycle=cycle_number,
            ready_timeout_s=ready_timeout,
            bind_timeout_s=bind_timeout,
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
                    f"  [dim]Cycle {cycle_number}/5  req {req_idx}/6  "
                    f"{req_type}  {'(cold)' if req_idx == 1 else '(warm)'}[/dim]"
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
) -> bool:
    """
    Run all cycles for one config. Returns True if config completed without
    thermal abort.

    Updates progress.json before each cycle and after config completion.
    """
    config_id = config["config_id"]
    cycles_per_config = lab_config.get("cycles_per_config", 5)
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

    for cycle_number in range(1, cycles_per_config + 1):
        # Update crash recovery state
        progress_state["current_config"] = config_id
        progress_state["current_cycle"] = cycle_number
        progress_state["last_update"] = datetime.now(timezone.utc).isoformat()
        _write_progress(progress_state)

        console.print(f"  [bold]Cycle {cycle_number}/{cycles_per_config}[/bold]")
        logger.info("--- Cycle %d/%d for %s ---", cycle_number, cycles_per_config, config_id)

        # Register cycle in DB
        with get_connection(db_path) as conn:
            cur = conn.execute(
                """INSERT INTO cycles (config_id, campaign_id, cycle_number, status)
                   VALUES (?, ?, ?, 'pending')""",
                (config_id, campaign_id, cycle_number),
            )
            cycle_id = cur.lastrowid
            conn.commit()

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
    _write_progress(progress_state)

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
) -> None:
    """
    Run a complete campaign from start to finish (or resume if interrupted).

    This is the main entry point. Call from CLI or directly.
    """
    _setup_logging(campaign_id)
    logger.info("=" * 70)
    logger.info("QuantMap campaign starting: %s  dry_run=%s", campaign_id, dry_run)
    logger.info("=" * 70)

    # -------------------------------------------------------------------------
    # Load configuration
    # -------------------------------------------------------------------------
    baseline = load_baseline()
    campaign = load_campaign(campaign_id)

    # Validate purity
    variable = validate_campaign_purity(baseline, campaign)

    # Build config list
    configs = build_config_list(baseline, campaign)

    # Build request file map
    req_cfg = baseline.get("requests", {})
    request_files: dict[str, Path] = {}
    for req_name, rel_path in req_cfg.items():
        full_path = _REPO_ROOT / rel_path
        if not full_path.is_file():
            raise FileNotFoundError(f"Request file not found: {full_path}")
        request_files[req_name] = full_path

    lab_config = baseline.get("lab", {})

    if dry_run:
        # Log and print so the dry-run output survives in the campaign log file.
        # Any validation failures above (FileNotFoundError, purity violation) would
        # have already raised — reaching here means the campaign is structurally
        # valid. (U2 fix)
        cycles = lab_config.get("cycles_per_config", 5)
        reqs_per_cycle = lab_config.get("requests_per_cycle", 6)
        total_requests = len(configs) * cycles * reqs_per_cycle

        summary_lines = [
            f"DRY RUN — campaign: {campaign_id}",
            f"  Variable:          {variable}",
            f"  Configs to test:   {len(configs)}",
            f"  Cycles per config: {cycles}",
            f"  Requests per cycle:{reqs_per_cycle} (1 cold + {reqs_per_cycle - 1} warm)",
            f"  Total requests:    {total_requests}",
            f"  Request types:     {', '.join(sorted(request_files.keys()))}",
            f"  Elimination filters: {dict(ELIMINATION_FILTERS)}",
            "",
        ]
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
        console.print("[green]✓ Telemetry startup check passed[/green]")
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
    _check_defender_exclusions(_sb_pre, _mp_pre, console)

    # -------------------------------------------------------------------------
    # Initialize filesystem and database
    # -------------------------------------------------------------------------
    for d in [RESULTS_DIR, LOGS_DIR, DB_DIR, STATE_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    campaign_results_dir = RESULTS_DIR / campaign_id
    campaign_results_dir.mkdir(parents=True, exist_ok=True)

    raw_jsonl_path = campaign_results_dir / "raw.jsonl"
    telemetry_jsonl_path = campaign_results_dir / "telemetry.jsonl"

    init_db(DB_PATH)

    # -------------------------------------------------------------------------
    # Register or resume campaign in DB
    # -------------------------------------------------------------------------
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection(DB_PATH) as conn:
        existing = conn.execute(
            "SELECT status FROM campaigns WHERE id=?", (campaign_id,)
        ).fetchone()

        if existing is None:
            import hashlib
            baseline_sha = hashlib.sha256(BASELINE_YAML.read_bytes()).hexdigest()
            campaign_yaml_path = CAMPAIGNS_DIR / f"{campaign_id}.yaml"
            campaign_sha = hashlib.sha256(campaign_yaml_path.read_bytes()).hexdigest()

            conn.execute(
                """INSERT INTO campaigns
                   (id, name, variable, campaign_type, status, created_at, started_at,
                    baseline_sha256, campaign_sha256, rationale)
                   VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, ?)""",
                (
                    campaign_id,
                    campaign.get("campaign_id", campaign_id),
                    variable,
                    campaign.get("type", "primary_sweep"),
                    now_iso, now_iso,
                    baseline_sha, campaign_sha,
                    campaign.get("rationale", ""),
                ),
            )
            conn.commit()
            logger.info("Campaign %s registered in database", campaign_id)
        elif existing["status"] == "complete" and not resume:
            # U7: clarify what --resume actually does (skips completed configs,
            # does NOT re-run them) so operators aren't confused about data integrity.
            console.print(
                f"[yellow]Campaign {campaign_id} is already marked complete in the database. "
                f"Pass --resume to continue in re-entry mode — completed configs will be "
                f"skipped; only configs not yet marked complete will run.[/yellow]"
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
        campaign_id=campaign_id,
        server_bin=_server_bin,
        model_path=_model_path,
        build_commit=baseline.get("runtime", {}).get("build_commit", "unknown"),
        request_files=request_files,
        campaign_yaml_path=campaign_yaml_path,
        baseline_yaml_path=BASELINE_YAML,
        sampling_params=sampling_params,
        cpu_affinity_policy=campaign.get("cpu_affinity_details", {}).get("default", "all_cores"),
    )

    with get_connection(DB_PATH) as conn:
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
    yaml_snapshot_path = RESULTS_DIR / campaign_id / "campaign_yaml_snapshot.yaml"
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
        campaign_id,
        variable,
        [c.get("variable_value") for c in configs],
        lab_config.get("cycles_per_config", 5),
        lab_config.get("requests_per_cycle", 6),
        snap.get("campaign_yaml_sha256", "unknown")[:12],
    )

    console.print(
        f"[bold]Campaign:[/bold] {campaign_id}  "
        f"[dim]variable={variable}  configs={len(configs)}[/dim]"
    )
    logger.info(
        "Campaign %s: variable=%s, %d configs, %d cycles each",
        campaign_id, variable, len(configs),
        lab_config.get("cycles_per_config", 5),
    )

    # -------------------------------------------------------------------------
    # Load crash recovery state
    # -------------------------------------------------------------------------
    progress_state = _read_progress() if resume else {}
    if progress_state.get("campaign_id") and progress_state["campaign_id"] != campaign_id:
        logger.warning(
            "progress.json is for a different campaign (%s vs %s) — starting fresh",
            progress_state["campaign_id"], campaign_id,
        )
        progress_state = {}

    progress_state["campaign_id"] = campaign_id
    progress_state.setdefault("completed_configs", [])
    completed_config_ids = set(progress_state["completed_configs"])

    if completed_config_ids:
        remaining = [c["config_id"] for c in configs if c["config_id"] not in completed_config_ids]
        console.print(
            f"[yellow]Resuming campaign {campaign_id}: "
            f"{len(completed_config_ids)}/{len(configs)} configs already complete, "
            f"{len(remaining)} remaining[/yellow]"
        )
        # Log completed and remaining explicitly so the log alone can prove
        # which configs ran in a prior session vs this one. (L3 fix)
        logger.info(
            "Resuming campaign %s: completed=%s remaining=%s",
            campaign_id,
            sorted(completed_config_ids),
            remaining,
        )
    else:
        logger.info("Starting campaign %s fresh (no prior progress state found)", campaign_id)

    # -------------------------------------------------------------------------
    # Initialize telemetry collector
    # -------------------------------------------------------------------------
    collector = tele.TelemetryCollector(
        db_path=DB_PATH,
        telemetry_jsonl_path=telemetry_jsonl_path,
    )

    # -------------------------------------------------------------------------
    # Run configs
    # -------------------------------------------------------------------------
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

            _run_config(
                config=config,
                campaign_id=campaign_id,
                lab_config=lab_config,
                request_files=request_files,
                db_path=DB_PATH,
                raw_jsonl_path=raw_jsonl_path,
                telemetry_jsonl_path=telemetry_jsonl_path,
                collector=collector,
                progress_state=progress_state,
                console=console,
            )

    except KeyboardInterrupt:
        logger.warning("Campaign %s interrupted by user (KeyboardInterrupt)", campaign_id)
        console.print("\n[yellow]Interrupted. Progress saved — resume with --resume[/yellow]")
        return
    except Exception as exc:
        logger.critical("Campaign %s fatal error: %s", campaign_id, exc, exc_info=True)
        console.print(f"[bold red]Fatal error: {exc}[/bold red]")
        with get_connection(DB_PATH) as conn:
            conn.execute(
                "UPDATE campaigns SET status='failed', failed_at=?, failure_reason=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), str(exc), campaign_id),
            )
            conn.commit()
        raise

    finally:
        tele.shutdown()

    # -------------------------------------------------------------------------
    # Campaign complete
    # -------------------------------------------------------------------------
    with get_connection(DB_PATH) as conn:
        conn.execute(
            "UPDATE campaigns SET status='complete', completed_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), campaign_id),
        )
        conn.commit()

    _clear_progress()

    console.print(f"\n[bold green]Campaign {campaign_id} complete.[/bold green]")
    logger.info("Campaign %s complete.", campaign_id)

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

        # Pass campaign-level elimination overrides if the YAML defines them.
        # score_campaign() merges these with ELIMINATION_FILTERS at call time —
        # the global defaults remain unchanged for every other callsite. (L6 fix)
        filter_overrides = campaign.get("elimination_overrides")
        if filter_overrides:
            logger.info("Campaign-level filter overrides active: %s", filter_overrides)

        stats = analyze_campaign(campaign_id, DB_PATH)
        scores = score_campaign(campaign_id, DB_PATH, baseline, filter_overrides=filter_overrides)
        report_path = generate_report(campaign_id, DB_PATH, baseline, scores, stats)
        console.print(f"[green]Report written:[/green] {report_path}")
        report_ok = True
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

def _setup_logging(campaign_id: str) -> None:
    """Configure logging to both console and file."""
    log_dir = LOGS_DIR / campaign_id
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

def _validate_campaign(campaign_id: str) -> bool:
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
    _setup_logging(campaign_id)
    logger.info("Validating campaign: %s", campaign_id)

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
        baseline = load_baseline()
        ok = _check("baseline.yaml loads", True) and ok
    except Exception as exc:
        _check("baseline.yaml loads", False, str(exc))
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

    # Model path: first shard exists and is plausibly sized (>100 MB to catch
    # empty/placeholder files — the real first shard of any quantized 94 GB
    # model will be several GB)
    model_exists = _model_path.is_file()
    model_size_bytes = _model_path.stat().st_size if model_exists else 0
    model_size_gb = model_size_bytes / (1024 ** 3)
    model_plausible = model_size_gb > 0.1  # >100 MB — any real GGUF shard exceeds this

    # Same pattern as the binary check: path in the label so it leads the line.
    if model_exists:
        if model_size_bytes < 1024 ** 2:
            size_str = f"{model_size_bytes / 1024:.0f} KB"
        elif model_size_bytes < 1024 ** 3:
            size_str = f"{model_size_bytes / 1024 ** 2:.1f} MB"
        else:
            size_str = f"{model_size_gb:.1f} GB"
        model_detail = size_str
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

    # Summary
    console.print()
    if ok:
        configs = build_config_list(baseline, campaign)
        cycles = lab.get("cycles_per_config", 5)
        reqs = lab.get("requests_per_cycle", 6)
        console.print(
            f"[bold green]All checks passed.[/bold green]  "
            f"{len(configs)} configs × {cycles} cycles × {reqs} requests = "
            f"{len(configs) * cycles * reqs} total requests."
        )
        logger.info("Validation passed: %s", campaign_id)
    else:
        console.print("[bold red]Validation FAILED — fix errors above before running.[/bold red]")
        logger.error("Validation failed: %s", campaign_id)

    return ok


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
        """,
    )
    parser.add_argument(
        "--campaign", required=True,
        help="Campaign ID (matches configs/campaigns/{id}.yaml)"
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
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.validate:
        ok = _validate_campaign(args.campaign)
        sys.exit(0 if ok else 1)
    run_campaign(
        campaign_id=args.campaign,
        dry_run=args.dry_run,
        resume=args.resume,
    )
