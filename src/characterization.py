"""
QuantMap — characterization.py

Pre-run environment characterization. Captures a structured, deterministic
snapshot of the system at run start. Attached to every run for debugging,
trust, and reporting.

DATA SOURCES (priority order per metric):
    platform / sys       — OS name, OS version, CPU brand, Python version
    psutil               — CPU core counts, CPU utilization, RAM, process list
    os / pathlib         — model file stats
    pynvml               — GPU name, VRAM total/used, GPU temperature
    importlib.metadata   — installed Python package versions
    subprocess           — Windows power plan (powercfg /getactivescheme)

AVAILABILITY:
    All probes are wrapped in try/except. Failures append to warnings[]; the
    function never raises. Missing data is represented as None, never omitted.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from src.settings_env import read_env_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def characterize_environment(model_path: str | Path | None = None) -> dict[str, Any]:
    """
    Capture a structured snapshot of the system environment at run start.

    Args:
        model_path: Path to the model file. If None, falls back to the
                    QUANTMAP_MODEL_PATH environment variable. Missing or
                    unreadable files produce None values, not errors.

    Returns:
        A JSON-serializable dict matching the characterization schema.
        All probe failures are captured in result["warnings"]. Never raises.
    """
    warnings: list[str] = []

    resolved_model = _resolve_model_path(model_path, warnings)

    # NVML is initialized once so GPU info and GPU temperature share a single
    # driver session instead of init/shutdown-ing twice.
    gpu_info, gpu_temp = _probe_nvml(warnings)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware": _probe_hardware(warnings),
        "system": _probe_system(warnings),
        "runtime": _probe_runtime(warnings),
        "model": _probe_model(resolved_model, warnings),
        "memory": _probe_memory(warnings),
        "gpu": gpu_info,
        "background_load": _probe_background_load(warnings),
        "thermal": {
            "cpu_temp": _probe_cpu_temp(warnings),
            "gpu_temp": gpu_temp,
        },
        "power": _probe_power(warnings),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Model path resolution
# ---------------------------------------------------------------------------

def _resolve_model_path(
    model_path: str | Path | None,
    warnings: list[str],
) -> Path | None:
    if model_path is not None:
        return Path(model_path)
    value = read_env_path("QUANTMAP_MODEL_PATH")
    if value.path is not None:
        return value.path
    warnings.append(f"model_path not provided and {value.message}")
    return None


# ---------------------------------------------------------------------------
# Hardware probe
# ---------------------------------------------------------------------------

def _probe_hardware(warnings: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "cpu":                  None,
        "cpu_architecture":     None,
        "physical_cores":       None,
        "logical_cores":        None,
        "cpu_freq_current_mhz": None,
        "cpu_freq_min_mhz":     None,
        "cpu_freq_max_mhz":     None,
    }

    try:
        result["cpu"] = platform.processor() or platform.machine()
    except Exception as exc:
        warnings.append(f"hardware.cpu: {exc}")

    try:
        result["cpu_architecture"] = platform.machine()
    except Exception as exc:
        warnings.append(f"hardware.cpu_architecture: {exc}")

    try:
        result["physical_cores"] = psutil.cpu_count(logical=False)
    except Exception as exc:
        warnings.append(f"hardware.physical_cores: {exc}")

    try:
        result["logical_cores"] = psutil.cpu_count(logical=True)
    except Exception as exc:
        warnings.append(f"hardware.logical_cores: {exc}")

    try:
        freq = psutil.cpu_freq()
        if freq:
            result["cpu_freq_current_mhz"] = round(freq.current, 1)
            result["cpu_freq_min_mhz"]     = round(freq.min, 1)
            result["cpu_freq_max_mhz"]     = round(freq.max, 1)
    except Exception as exc:
        warnings.append(f"hardware.cpu_freq: {exc}")

    return result


# ---------------------------------------------------------------------------
# System probe
# ---------------------------------------------------------------------------

def _probe_system(warnings: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"os": None, "os_version": None}

    try:
        result["os"] = platform.system()
    except Exception as exc:
        warnings.append(f"system.os: {exc}")

    try:
        result["os_version"] = platform.version()
    except Exception as exc:
        warnings.append(f"system.os_version: {exc}")

    return result


# ---------------------------------------------------------------------------
# Runtime probe
# ---------------------------------------------------------------------------

def _probe_runtime(warnings: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"python_version": None, "llama_cpp_version": None}

    try:
        result["python_version"] = sys.version
    except Exception as exc:
        warnings.append(f"runtime.python_version: {exc}")

    try:
        from importlib.metadata import PackageNotFoundError, version

        for pkg in ("llama-cpp-python", "llama_cpp_python", "llama_cpp"):
            try:
                result["llama_cpp_version"] = version(pkg)
                break
            except PackageNotFoundError:
                continue
    except Exception as exc:
        warnings.append(f"runtime.llama_cpp_version: {exc}")

    return result


# ---------------------------------------------------------------------------
# Model probe
# ---------------------------------------------------------------------------

def _probe_model(model_path: Path | None, warnings: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "model_path": str(model_path) if model_path is not None else None,
        "model_size_bytes": None,
    }
    if model_path is None:
        return result

    try:
        result["model_size_bytes"] = model_path.stat().st_size
    except Exception as exc:
        warnings.append(f"model.model_size_bytes ({model_path}): {exc}")

    return result


# ---------------------------------------------------------------------------
# Memory probe
# ---------------------------------------------------------------------------

def _probe_memory(warnings: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "total_ram":          None,
        "available_ram":      None,
        "ram_percent":        None,
        "swap_total":         None,
        "swap_used":          None,
        "swap_percent":       None,
    }

    try:
        mem = psutil.virtual_memory()
        result["total_ram"]     = mem.total
        result["available_ram"] = mem.available
        result["ram_percent"]   = mem.percent
    except Exception as exc:
        warnings.append(f"memory.ram: {exc}")

    try:
        swap = psutil.swap_memory()
        result["swap_total"]   = swap.total
        result["swap_used"]    = swap.used
        result["swap_percent"] = round(swap.used / swap.total * 100.0, 1) if swap.total else 0.0
    except Exception as exc:
        warnings.append(f"memory.swap: {exc}")

    return result


# ---------------------------------------------------------------------------
# GPU probe (pynvml — single NVML session for both GPU info and temperature)
# ---------------------------------------------------------------------------

def _probe_nvml(warnings: list[str]) -> tuple[dict[str, Any], float | None]:
    """
    Open one NVML session to read baseline GPU state.

    Captures static facts (name, VRAM) and a point-in-time snapshot
    (utilization, power, clocks) so callers can see the GPU's at-rest
    state before any inference starts.

    Returns:
        (gpu_dict, gpu_temp_celsius_or_None)
    """
    gpu: dict[str, Any] = {
        "name":                  None,
        "vram_total":            None,
        "vram_used":             None,
        "gpu_utilization":       None,
        "gpu_mem_utilization":   None,
        "gpu_power_w":           None,
        "gpu_graphics_clock_mhz": None,
        "gpu_mem_clock_mhz":     None,
    }
    gpu_temp: float | None = None

    try:
        import warnings as _w

        with _w.catch_warnings():
            _w.simplefilter("ignore")
            import pynvml  # type: ignore[import]

        pynvml.nvmlInit()
        try:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception as exc:
                warnings.append(f"gpu: no device at index 0 — {exc}")
                return gpu, gpu_temp

            try:
                raw_name = pynvml.nvmlDeviceGetName(handle)
                gpu["name"] = raw_name.decode() if isinstance(raw_name, bytes) else raw_name
            except Exception as exc:
                warnings.append(f"gpu.name: {exc}")

            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpu["vram_total"] = mem.total
                gpu["vram_used"]  = mem.used
            except Exception as exc:
                warnings.append(f"gpu.vram: {exc}")

            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu["gpu_utilization"]     = float(util.gpu)
                gpu["gpu_mem_utilization"] = float(util.memory)
            except Exception as exc:
                warnings.append(f"gpu.utilization: {exc}")

            try:
                gpu["gpu_power_w"] = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
            except Exception as exc:
                warnings.append(f"gpu.power: {exc}")

            try:
                gpu["gpu_graphics_clock_mhz"] = int(
                    pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)
                )
            except Exception as exc:
                warnings.append(f"gpu.graphics_clock: {exc}")

            try:
                gpu["gpu_mem_clock_mhz"] = int(
                    pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM)
                )
            except Exception as exc:
                warnings.append(f"gpu.mem_clock: {exc}")

            try:
                gpu_temp = float(
                    pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                )
            except Exception as exc:
                warnings.append(f"thermal.gpu_temp: {exc}")

        finally:
            pynvml.nvmlShutdown()

    except ImportError:
        warnings.append("gpu: pynvml not installed — GPU info and gpu_temp unavailable")
    except Exception as exc:
        warnings.append(f"gpu: {exc}")

    return gpu, gpu_temp


# ---------------------------------------------------------------------------
# Background load probe
# ---------------------------------------------------------------------------

def _probe_background_load(warnings: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"cpu_percent": None, "top_processes": []}

    try:
        # interval=0.1 gives a real measurement rather than the 0.0 returned
        # by the first non-blocking call. 100 ms is acceptable for startup.
        result["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    except Exception as exc:
        warnings.append(f"background_load.cpu_percent: {exc}")

    try:
        procs: list[tuple[float, str]] = []
        for proc in psutil.process_iter(["name", "cpu_percent"]):
            try:
                pct = proc.info.get("cpu_percent") or 0.0
                name = proc.info.get("name") or "?"
                if pct > 0.0:
                    procs.append((pct, name))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(reverse=True)
        result["top_processes"] = [f"{name} ({pct:.1f}%)" for pct, name in procs[:10]]
    except Exception as exc:
        warnings.append(f"background_load.top_processes: {exc}")

    return result


# ---------------------------------------------------------------------------
# Thermal probe
# ---------------------------------------------------------------------------

def _probe_cpu_temp(warnings: list[str]) -> float | None:
    """
    Read CPU temperature via psutil.sensors_temperatures().

    Available on Linux and macOS. Returns None on Windows without warning —
    the absence is expected and not an error.
    """
    try:
        sensors = psutil.sensors_temperatures()  # type: ignore[attr-defined]
        if not sensors:
            return None
        for key in ("coretemp", "cpu_thermal", "acpitz", "k10temp"):
            entries = sensors.get(key)
            if entries:
                return entries[0].current
    except AttributeError:
        pass  # Windows — sensors_temperatures() is not available
    except Exception as exc:
        warnings.append(f"thermal.cpu_temp: {exc}")
    return None


# ---------------------------------------------------------------------------
# Power probe
# ---------------------------------------------------------------------------

def _probe_power(warnings: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"power_plan": None, "power_plugged": None}

    # Battery / AC status — cross-platform via psutil.
    try:
        batt = psutil.sensors_battery()
        if batt is not None:
            result["power_plugged"] = batt.power_plugged
        # batt is None on desktops with no battery — leave power_plugged as None.
    except Exception as exc:
        warnings.append(f"power.power_plugged: {exc}")

    if platform.system() != "Windows":
        return result

    try:
        proc = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        line = proc.stdout.strip()
        if "(" in line and ")" in line:
            # Extract the friendly name from: "... GUID: ... (Balanced)"
            result["power_plan"] = line.split("(")[1].rstrip(")")
        elif line:
            result["power_plan"] = line
    except Exception as exc:
        warnings.append(f"power.power_plan: {exc}")

    return result


# ===========================================================================
# Sampling layer
# ===========================================================================

# ---------------------------------------------------------------------------
# Known interference categories (process name substring → category label)
# ---------------------------------------------------------------------------

_INTERFERENCE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "browser":       ("chrome", "firefox", "msedge", "opera", "brave", "safari"),
    "ide":           ("code", "pycharm", "idea", "clion", "rider", "webstorm", "devenv"),
    "game_launcher": ("steam", "epicgameslauncher", "goggalaxy", "battlenet", "origin"),
    "sync_tool":     ("onedrive", "dropbox", "googledrivefs", "boxsync"),
    "security":      ("msmpeng", "mpcmdrun", "avast", "avgui", "mbam", "norton", "mcafee",
                      "defender", "clamav", "sophos", "bitdefender", "malwarebytes"),
    # Video conferencing / messaging — heavy CPU+GPU consumers, common on dev machines
    "comms":         ("zoom", "teams", "slack", "discord", "webex", "skype", "lync"),
    # Media playback / capture — GPU encode/decode directly corrupts GPU utilization samples
    "media":         ("vlc", "obs64", "obs32", "obs", "potplayer", "mpchc",
                      "mpc-hc", "foobar2000", "winamp", "streamlabs"),
}

# Process names that are normal/expected — suppress "persistent_cpu_load" flags for these.
# All entries are lowercase without .exe (the _rank_interferers normalizer strips .exe).
_SYSTEM_NAMES: frozenset[str] = frozenset({
    # Windows kernel / session management
    "system", "idle", "system idle process", "registry", "smss", "csrss",
    "wininit", "winlogon", "services", "lsass", "userinit",
    # Core shell + UI
    "svchost", "dwm", "explorer", "taskhostw", "sihost", "runtimebroker",
    "shellexperiencehost", "startmenuexperiencehost", "applicationframehost",
    # Audio, fonts, text input
    "audiodg", "fontdrvhost", "ctfmon",
    # Printing, COM/DCOM
    "spoolsv", "dllhost",
    # Console, search
    "conhost", "searchhost", "searchindexer",
    # WMI (appears during any monitoring — not a benchmark interferer)
    "wmiprvse", "wmiapsrv",
    # Windows update / compatibility telemetry (expected background noise)
    "trustedinstaller", "compattelrunner", "musnotifyicon",
    # Task scheduler
    "taskeng", "taskhost",
    # Error reporting
    "werfault", "werhost",
    # NVML / GPU monitoring infrastructure (not user workloads)
    "nvdisplay.container", "nvspcap64", "nvspcap",
    # QuantMap and llama.cpp server — the tool's own processes
    "python", "python3", "quantmap", "llama-server", "llama_server",
})


# ---------------------------------------------------------------------------
# NVML session helpers (open once for the whole sampling window)
# ---------------------------------------------------------------------------

def _open_nvml_session(warnings: list[str]) -> tuple[Any, Any]:
    """
    Initialize pynvml and return (pynvml_module, gpu0_handle).
    Both are None if pynvml is unavailable or the GPU cannot be opened.
    Caller is responsible for calling _close_nvml_session when done.
    """
    try:
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("ignore")
            import pynvml  # type: ignore[import]
        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception as exc:
            warnings.append(f"sampling: no GPU device at index 0 — {exc}")
            pynvml.nvmlShutdown()
            return None, None
        return pynvml, handle
    except ImportError:
        warnings.append("sampling: pynvml not installed — GPU metrics unavailable")
        return None, None
    except Exception as exc:
        warnings.append(f"sampling: NVML init failed — {exc}")
        return None, None


def _close_nvml_session(pynvml: Any) -> None:
    if pynvml is not None:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Per-sample collection
# ---------------------------------------------------------------------------

def _read_disk_counters() -> Any:
    """Return system-wide disk I/O counters, or None on failure."""
    try:
        return psutil.disk_io_counters()
    except Exception:
        return None


def _take_one_sample(
    pynvml: Any,
    nvml_handle: Any,
    prev_disk: Any,
    warnings: list[str],
) -> tuple[dict[str, Any], Any]:
    """
    Collect one lightweight system snapshot.

    Returns (sample_dict, curr_disk_counters). The caller stores curr_disk
    and passes it back as prev_disk on the next call to produce deltas.
    """
    sample: dict[str, Any] = {
        "timestamp":              datetime.now(timezone.utc).isoformat(),
        "cpu_percent":            None,
        "cpu_freq_current_mhz":  None,
        "available_ram":          None,
        "total_ram":              None,
        "ram_percent":            None,
        "pagefile_used_bytes":    None,
        "pagefile_total_bytes":   None,
        "gpu_utilization":        None,
        "gpu_mem_utilization":    None,
        "vram_used":              None,
        "gpu_temp":               None,
        "gpu_power_w":            None,
        "gpu_graphics_clock_mhz": None,
        "gpu_mem_clock_mhz":      None,
        "disk_read_bytes":        None,
        "disk_write_bytes":       None,
        "top_cpu_processes":      [],
        "top_mem_processes":      [],
        "process_details":        [],
    }

    # CPU — interval=None uses the delta from the previous cpu_percent() call
    try:
        sample["cpu_percent"] = psutil.cpu_percent(interval=None)
    except Exception as exc:
        warnings.append(f"sample.cpu_percent: {exc}")

    # CPU frequency — current observed frequency (may be None on VMs)
    try:
        freq = psutil.cpu_freq()
        if freq is not None:
            sample["cpu_freq_current_mhz"] = freq.current
    except Exception as exc:
        warnings.append(f"sample.cpu_freq: {exc}")

    # RAM — percent alongside the absolute values
    try:
        mem = psutil.virtual_memory()
        sample["available_ram"] = mem.available
        sample["total_ram"]     = mem.total
        sample["ram_percent"]   = mem.percent
    except Exception as exc:
        warnings.append(f"sample.ram: {exc}")

    # Pagefile / swap — proxy for committed-memory pressure
    try:
        swap = psutil.swap_memory()
        sample["pagefile_used_bytes"]  = swap.used
        sample["pagefile_total_bytes"] = swap.total
    except Exception as exc:
        warnings.append(f"sample.pagefile: {exc}")

    # GPU (pynvml session held alive across samples)
    if pynvml is not None and nvml_handle is not None:
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(nvml_handle)
            sample["gpu_utilization"]     = float(util.gpu)
            sample["gpu_mem_utilization"] = float(util.memory)
        except Exception as exc:
            warnings.append(f"sample.gpu_utilization: {exc}")

        try:
            vmem = pynvml.nvmlDeviceGetMemoryInfo(nvml_handle)
            sample["vram_used"] = vmem.used
        except Exception as exc:
            warnings.append(f"sample.vram_used: {exc}")

        try:
            sample["gpu_temp"] = float(
                pynvml.nvmlDeviceGetTemperature(nvml_handle, pynvml.NVML_TEMPERATURE_GPU)
            )
        except Exception as exc:
            warnings.append(f"sample.gpu_temp: {exc}")

        try:
            sample["gpu_power_w"] = pynvml.nvmlDeviceGetPowerUsage(nvml_handle) / 1000.0
        except Exception as exc:
            warnings.append(f"sample.gpu_power_w: {exc}")

        try:
            sample["gpu_graphics_clock_mhz"] = int(
                pynvml.nvmlDeviceGetClockInfo(nvml_handle, pynvml.NVML_CLOCK_GRAPHICS)
            )
        except Exception as exc:
            warnings.append(f"sample.gpu_graphics_clock_mhz: {exc}")

        try:
            sample["gpu_mem_clock_mhz"] = int(
                pynvml.nvmlDeviceGetClockInfo(nvml_handle, pynvml.NVML_CLOCK_MEM)
            )
        except Exception as exc:
            warnings.append(f"sample.gpu_mem_clock_mhz: {exc}")

    # Disk I/O delta since previous sample
    curr_disk = _read_disk_counters()
    if curr_disk is not None and prev_disk is not None:
        sample["disk_read_bytes"]  = curr_disk.read_bytes  - prev_disk.read_bytes
        sample["disk_write_bytes"] = curr_disk.write_bytes - prev_disk.write_bytes

    # Processes — collect all, then produce:
    #   top_cpu_processes / top_mem_processes  (backward-compatible string lists)
    #   process_details                         (structured, for assessment layer)
    try:
        all_procs: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
            try:
                info     = proc.info
                name     = info.get("name") or "?"
                cpu_pct  = info.get("cpu_percent") or 0.0
                mem_info = info.get("memory_info")
                rss      = mem_info.rss if mem_info else 0
                all_procs.append({"name": name, "cpu_pct": cpu_pct, "rss_bytes": rss})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        by_cpu = sorted(all_procs, key=lambda p: p["cpu_pct"], reverse=True)
        by_mem = sorted(all_procs, key=lambda p: p["rss_bytes"], reverse=True)

        sample["top_cpu_processes"] = [
            f"{p['name']} ({p['cpu_pct']:.1f}%)"
            for p in by_cpu[:5] if p["cpu_pct"] > 0.0
        ]
        sample["top_mem_processes"] = [
            f"{p['name']} ({p['rss_bytes'] // (1024 * 1024)} MB)"
            for p in by_mem[:5] if p["rss_bytes"] > 0
        ]
        # Structured details: top 15 by CPU union top 10 by memory, deduped by name.
        # This ensures memory-heavy but CPU-idle processes (e.g. large caches) are visible.
        seen_in_details: set[str] = set()
        details: list[dict[str, Any]] = []
        for p in by_cpu[:15]:
            if p["cpu_pct"] > 0.0 and p["name"] not in seen_in_details:
                details.append(p)
                seen_in_details.add(p["name"])
        for p in by_mem[:10]:
            if p["rss_bytes"] > 0 and p["name"] not in seen_in_details:
                details.append(p)
                seen_in_details.add(p["name"])
        sample["process_details"] = details
    except Exception as exc:
        warnings.append(f"sample.processes: {exc}")

    return sample, curr_disk


# ---------------------------------------------------------------------------
# Public: sample_environment_window
# ---------------------------------------------------------------------------

def sample_environment_window(
    duration_s: float = 5.0,
    interval_s: float = 1.0,
) -> dict[str, Any]:
    """
    Collect lightweight system samples over a time window.

    Samples CPU utilization, RAM, GPU metrics, disk I/O, and top processes
    at each interval. NVML is initialized once and held for the full window
    to avoid per-sample driver overhead.

    Args:
        duration_s:  Total window length in seconds.
        interval_s:  Target time between samples. Actual spacing may be
                     slightly longer if sample collection takes time.

    Returns:
        {
            "samples":  list of per-sample dicts,
            "warnings": list of non-fatal error strings,
        }

    The returned samples list is suitable for passing directly to
    summarize_environment_samples().
    """
    warnings: list[str] = []

    # Prime the system-level CPU counter so that the first in-loop sample
    # reports a real delta rather than 0.0 (psutil returns 0.0 on the very
    # first interval=None call since there is no previous measurement).
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass

    pynvml, nvml_handle = _open_nvml_session(warnings)
    prev_disk = _read_disk_counters()
    samples: list[dict[str, Any]] = []
    deadline = time.monotonic() + duration_s

    try:
        while time.monotonic() < deadline:
            t0 = time.monotonic()

            sample, prev_disk = _take_one_sample(pynvml, nvml_handle, prev_disk, warnings)
            samples.append(sample)

            # Sleep for the remainder of the interval, but never past the deadline
            elapsed   = time.monotonic() - t0
            remaining = deadline - time.monotonic()
            sleep_for = max(0.0, min(interval_s - elapsed, remaining))
            if sleep_for > 0:
                time.sleep(sleep_for)
    finally:
        _close_nvml_session(pynvml)

    return {"samples": samples, "warnings": warnings}


# ===========================================================================
# Summarization layer
# ===========================================================================

# ---------------------------------------------------------------------------
# Math helpers (stdlib only)
# ---------------------------------------------------------------------------

def _mean(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def _std_dev(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    m = sum(vals) / len(vals)
    variance = sum((x - m) ** 2 for x in vals) / len(vals)
    return variance ** 0.5


# ---------------------------------------------------------------------------
# Summary sub-computations
# ---------------------------------------------------------------------------

def _compute_stats(samples: list[dict[str, Any]]) -> dict[str, Any]:
    cpu_vals       = [s["cpu_percent"]          for s in samples if s.get("cpu_percent")          is not None]
    freq_vals      = [s["cpu_freq_current_mhz"] for s in samples if s.get("cpu_freq_current_mhz") is not None]
    ram_vals       = [s["available_ram"]         for s in samples if s.get("available_ram")        is not None]
    ram_pct_vals   = [s["ram_percent"]           for s in samples if s.get("ram_percent")          is not None]
    gpu_util_vals  = [s["gpu_utilization"]       for s in samples if s.get("gpu_utilization")      is not None]
    gpu_temp_vals  = [s["gpu_temp"]              for s in samples if s.get("gpu_temp")             is not None]
    gpu_power_vals = [s["gpu_power_w"]           for s in samples if s.get("gpu_power_w")          is not None]

    # Pagefile percent computed from raw bytes (avoids requiring psutil to expose .percent)
    pf_pct_vals: list[float] = []
    for s in samples:
        pf_used  = s.get("pagefile_used_bytes")
        pf_total = s.get("pagefile_total_bytes")
        if pf_used is not None and pf_total and pf_total > 0:
            pf_pct_vals.append(pf_used / pf_total * 100.0)

    avg_available_ram = _mean(ram_vals)

    return {
        "sample_count":         len(samples),
        "avg_cpu_percent":      _mean(cpu_vals),
        "max_cpu_percent":      max(cpu_vals)       if cpu_vals      else None,
        "min_cpu_percent":      min(cpu_vals)       if cpu_vals      else None,
        "avg_cpu_freq_mhz":     _mean(freq_vals),
        "min_cpu_freq_mhz":     min(freq_vals)      if freq_vals     else None,
        "avg_available_ram":    int(round(avg_available_ram)) if avg_available_ram is not None else None,
        "min_available_ram":    min(ram_vals)       if ram_vals      else None,
        "avg_ram_percent":      _mean(ram_pct_vals),
        "max_ram_percent":      max(ram_pct_vals)   if ram_pct_vals  else None,
        "max_pagefile_percent": max(pf_pct_vals)    if pf_pct_vals   else None,
        "avg_gpu_utilization":  _mean(gpu_util_vals),
        "max_gpu_utilization":  max(gpu_util_vals)  if gpu_util_vals else None,
        "avg_gpu_temp":         _mean(gpu_temp_vals),
        "max_gpu_temp":         max(gpu_temp_vals)  if gpu_temp_vals else None,
        "avg_gpu_power_w":      _mean(gpu_power_vals),
        "max_gpu_power_w":      max(gpu_power_vals) if gpu_power_vals else None,
    }


def _compute_volatility(samples: list[dict[str, Any]]) -> dict[str, Any]:
    cpu_vals      = [s["cpu_percent"]          for s in samples if s.get("cpu_percent")          is not None]
    freq_vals     = [s["cpu_freq_current_mhz"] for s in samples if s.get("cpu_freq_current_mhz") is not None]
    ram_vals      = [s["available_ram"]         for s in samples if s.get("available_ram")        is not None]
    gpu_util_vals = [s["gpu_utilization"]       for s in samples if s.get("gpu_utilization")      is not None]

    ram_variation      = (max(ram_vals)      - min(ram_vals))      if len(ram_vals)      >= 2 else None
    gpu_util_variation = (max(gpu_util_vals) - min(gpu_util_vals)) if len(gpu_util_vals) >= 2 else None
    cpu_freq_variation = (max(freq_vals)     - min(freq_vals))     if len(freq_vals)     >= 2 else None

    return {
        "cpu_std_dev":          _std_dev(cpu_vals),
        "cpu_freq_variation_mhz": cpu_freq_variation,  # MHz swing observed during window
        "ram_variation":        ram_variation,          # bytes — swing in available RAM
        "gpu_util_variation":   gpu_util_variation,     # percentage points
    }


def _compute_process_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    cpu_name_counts: Counter[str] = Counter()
    mem_name_counts: Counter[str] = Counter()

    for sample in samples:
        # Extract the bare process name from "name (12.3%)" or "name (512 MB)"
        for entry in sample.get("top_cpu_processes", []):
            cpu_name_counts[entry.split(" (")[0]] += 1
        for entry in sample.get("top_mem_processes", []):
            mem_name_counts[entry.split(" (")[0]] += 1

    return {
        "most_frequent_cpu_processes":    [n for n, _ in cpu_name_counts.most_common(5)],
        "most_frequent_memory_processes": [n for n, _ in mem_name_counts.most_common(5)],
    }


def _detect_interference(
    samples: list[dict[str, Any]],
    stats: dict[str, Any],
    volatility: dict[str, Any],
    processes: dict[str, Any],
) -> list[str]:
    flags: list[str] = []
    n = len(samples)

    # 1. CPU spike — any sample exceeded threshold
    max_cpu = stats.get("max_cpu_percent")
    if max_cpu is not None and max_cpu > 70.0:
        flags.append(f"cpu_spike: peak {max_cpu:.1f}% (threshold: 70%)")

    # 2. RAM pressure — large swing in available RAM during the window
    ram_variation = volatility.get("ram_variation")
    if ram_variation is not None and ram_variation > 500 * 1024 * 1024:  # 500 MB
        total_ram = next(
            (s["total_ram"] for s in samples if s.get("total_ram") is not None), None
        )
        variation_mb = ram_variation // (1024 * 1024)
        pct_str = (
            f" ({ram_variation / total_ram * 100:.1f}% of total)" if total_ram else ""
        )
        flags.append(f"ram_pressure: available RAM varied by {variation_mb} MB{pct_str}")

    # 3. Persistent non-system CPU load — same process in top CPU for ≥50% of samples
    for name in processes.get("most_frequent_cpu_processes", []):
        name_lower = name.lower().replace(".exe", "")
        if name_lower in _SYSTEM_NAMES:
            continue
        count = sum(
            1 for s in samples
            if any(entry.startswith(name) for entry in s.get("top_cpu_processes", []))
        )
        if count >= max(1, n // 2):
            flags.append(
                f"persistent_cpu_load: '{name}' in top CPU for {count}/{n} samples"
            )

    # 4. Known interference categories — any appearance across the full window
    all_cpu_names = {
        entry.split(" (")[0].lower().replace(".exe", "")
        for s in samples
        for entry in s.get("top_cpu_processes", [])
    }
    for category, keywords in _INTERFERENCE_CATEGORIES.items():
        for kw in keywords:
            if any(kw in name for name in all_cpu_names):
                flags.append(f"interference_category:{category}")
                break  # one flag per category

    return flags


# ---------------------------------------------------------------------------
# Public: summarize_environment_samples
# ---------------------------------------------------------------------------

def summarize_environment_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Reduce a list of environment samples into meaningful signals.

    Args:
        samples: The list returned in sample_environment_window()["samples"].

    Returns:
        {
            "stats":              basic per-metric aggregates,
            "volatility":         spread indicators (std dev, min/max swings),
            "processes":          most frequent processes across the window,
            "interference_flags": list of human-readable interference detections,
            "warnings":           non-fatal issues encountered during summarization,
        }
    """
    if not samples:
        return {
            "stats":              {},
            "volatility":         {},
            "processes":          {},
            "interference_flags": [],
            "warnings":           ["no samples to summarize"],
        }

    warnings: list[str] = []

    try:
        stats = _compute_stats(samples)
    except Exception as exc:
        stats = {}
        warnings.append(f"summarize.stats: {exc}")

    try:
        volatility = _compute_volatility(samples)
    except Exception as exc:
        volatility = {}
        warnings.append(f"summarize.volatility: {exc}")

    try:
        processes = _compute_process_summary(samples)
    except Exception as exc:
        processes = {}
        warnings.append(f"summarize.processes: {exc}")

    try:
        interference_flags = _detect_interference(samples, stats, volatility, processes)
    except Exception as exc:
        interference_flags = []
        warnings.append(f"summarize.interference: {exc}")

    return {
        "stats":              stats,
        "volatility":         volatility,
        "processes":          processes,
        "interference_flags": interference_flags,
        "warnings":           warnings,
    }


# ===========================================================================
# Assessment layer
# ===========================================================================

# ---------------------------------------------------------------------------
# Assessment thresholds
# ---------------------------------------------------------------------------

_CPU_SPIKE_THRESHOLD       = 70.0                 # % — any single sample above = spike
_CPU_SUSTAINED_THRESHOLD   = 30.0                 # % — average above = sustained load
_CPU_STD_DEV_NOISY         = 5.0                  # % — std dev above = volatile
_RAM_VARIATION_PRESSURE    = 500 * 1024 * 1024    # bytes — 500 MB swing in available RAM
_PAGEFILE_PRESSURE         = 50.0                 # % pagefile used
_GPU_UTIL_PRESSURE         = 80.0                 # % — average GPU compute utilization
_GPU_UTIL_VARIATION_NOISY  = 20.0                 # % points — GPU util swing = noisy
_GPU_TEMP_HIGH             = 85.0                 # °C — above = thermal concern
_DISK_BPS_PRESSURE         = 50 * 1024 * 1024     # 50 MB/s total — sustained disk activity

# Reason → score weight. Higher = worse for benchmark trustworthiness.
_REASON_WEIGHTS: dict[str, int] = {
    "cpu_spike_detected":        3,
    "sustained_cpu_load":        2,
    "cpu_volatile":              1,
    "cpu_freq_throttled":        2,  # frequency drop during window = throttling
    "memory_pressure_detected":  2,
    "pagefile_pressure":         2,
    "memory_volatile":           1,
    "sustained_disk_activity":   1,
    "gpu_thermal_load":          1,
    "gpu_memory_pressure":       2,
    "recurring_browser":         1,
    "recurring_ide":             1,
    "recurring_sync_tool":       1,
    "recurring_security_scan":   1,
    "recurring_game_launcher":   2,
    "recurring_comms":           2,  # Zoom/Teams use heavy CPU+GPU
    "recurring_media":           2,  # OBS/VLC GPU encode corrupts GPU samples
    "persistent_interferer":     2,
    "power_saver_mode":          2,
}

# Score → (quality, severity)
_SCORE_TIERS: list[tuple[int, str, str]] = [
    # (max_score_inclusive, quality, severity)
    (0,  "clean",        "low"),
    (2,  "mostly_clean", "low"),
    (4,  "noisy",        "moderate"),
    (6,  "noisy",        "high"),
]
_DISTORTED_QUALITY    = "distorted"
_DISTORTED_SEVERITY   = "high"
_DISTORTED_THRESHOLD  = 7  # score >= this → distorted


# ---------------------------------------------------------------------------
# Disk throughput helper
# ---------------------------------------------------------------------------

def _compute_disk_throughput(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Derive read/write throughput from per-sample byte deltas and timestamps.

    Returns:
        avg_read_bps, avg_write_bps, max_total_bps  (bytes/second, or None)
        sustained_activity                           (bool)
    """
    result: dict[str, Any] = {
        "avg_read_bps":     None,
        "avg_write_bps":    None,
        "max_total_bps":    None,
        "sustained_activity": False,
    }

    disk_samples = [
        s for s in samples
        if s.get("disk_read_bytes") is not None and s.get("disk_write_bytes") is not None
    ]
    if not disk_samples:
        return result

    total_read  = sum(s["disk_read_bytes"]  for s in disk_samples)
    total_write = sum(s["disk_write_bytes"] for s in disk_samples)

    # Elapsed time from first and last sample timestamps
    elapsed_s: float | None = None
    if len(samples) >= 2:
        try:
            t0 = datetime.fromisoformat(samples[0]["timestamp"])
            t1 = datetime.fromisoformat(samples[-1]["timestamp"])
            delta = (t1 - t0).total_seconds()
            if delta > 0:
                elapsed_s = delta
        except Exception:
            pass

    if elapsed_s:
        result["avg_read_bps"]  = total_read  / elapsed_s
        result["avg_write_bps"] = total_write / elapsed_s

        # Per-sample max — approximate per-second rate using avg interval length
        per_interval_s = elapsed_s / len(disk_samples)
        if per_interval_s > 0:
            max_per_interval = max(
                s["disk_read_bytes"] + s["disk_write_bytes"] for s in disk_samples
            )
            result["max_total_bps"] = max_per_interval / per_interval_s

        avg_total_bps = (total_read + total_write) / elapsed_s
        result["sustained_activity"] = avg_total_bps > _DISK_BPS_PRESSURE

    return result


# ---------------------------------------------------------------------------
# Process ranking helpers
# ---------------------------------------------------------------------------

def _categorize_process(name_lower: str) -> str | None:
    """Return the interference category for a normalized process name, or None."""
    for category, keywords in _INTERFERENCE_CATEGORIES.items():
        for kw in keywords:
            if kw in name_lower:
                return category
    return None


def _rank_interferers(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Build a ranked list of non-system processes that appeared in top CPU
    across the sample window.

    Each entry contains: name, category, recurrence, peak_cpu_percent,
    peak_memory_bytes, reason.
    """
    n = len(samples)
    # Aggregate per named process
    agg: dict[str, dict[str, Any]] = {}

    for sample in samples:
        # Track names seen in this sample so multi-instance processes (e.g. chrome
        # spawning several renderer processes) count as one appearance per sample.
        seen_this_sample: set[str] = set()

        for detail in sample.get("process_details", []):
            name    = detail["name"]
            name_lc = name.lower().replace(".exe", "")
            if name_lc in _SYSTEM_NAMES:
                continue

            if name not in agg:
                agg[name] = {
                    "name":              name,
                    "category":          _categorize_process(name_lc),
                    "recurrence":        0,
                    "peak_cpu_percent":  0.0,
                    "peak_memory_bytes": 0,
                }

            # Recurrence = number of samples the process appeared in (not instances)
            if name not in seen_this_sample:
                agg[name]["recurrence"] += 1
                seen_this_sample.add(name)

            # Peak values track across all instances in all samples
            agg[name]["peak_cpu_percent"]  = max(agg[name]["peak_cpu_percent"],  detail["cpu_pct"])
            agg[name]["peak_memory_bytes"] = max(agg[name]["peak_memory_bytes"], detail["rss_bytes"])

    candidates: list[dict[str, Any]] = []
    for data in agg.values():
        reason = (
            "recurring_top_cpu_process"
            if data["recurrence"] >= max(1, n // 2)
            else "appeared_in_top_cpu"
        )
        candidates.append({
            "name":              data["name"],
            "category":          data["category"],
            "recurrence":        data["recurrence"],
            "peak_cpu_percent":  round(data["peak_cpu_percent"], 1),
            "peak_memory_bytes": data["peak_memory_bytes"],
            "reason":            reason,
        })

    # Sort by peak CPU descending, categorized processes first
    candidates.sort(
        key=lambda c: (-c["peak_cpu_percent"], c["category"] is None)
    )
    return candidates[:10]


# ---------------------------------------------------------------------------
# Public: assess_environment_quality
# ---------------------------------------------------------------------------

def assess_environment_quality(
    baseline: dict[str, Any],
    sample_window: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """
    Synthesize the three characterization layers into a structured quality judgment.

    Args:
        baseline:      Output of characterize_environment().
        sample_window: Output of sample_environment_window().
        summary:       Output of summarize_environment_samples().

    Returns:
        {
            "environment_quality":    "clean" | "mostly_clean" | "noisy" | "distorted",
            "severity":               "low" | "moderate" | "high",
            "reasons":                list of short machine-readable reason codes,
            "interference_candidates": ranked list of likely competing workloads,
            "resource_pressure":      compact pressure summary per resource type,
            "stability":              per-metric stability flags,
            "warnings":               non-fatal issues during assessment,
        }

    Never raises. Uses .get() throughout so partial / empty inputs are safe.
    """
    assessment_warnings: list[str] = []
    samples = sample_window.get("samples", [])
    stats   = summary.get("stats", {})
    vol     = summary.get("volatility", {})

    # --- Derived data not in summary ---
    disk: dict[str, Any] = {}
    try:
        disk = _compute_disk_throughput(samples)
    except Exception as exc:
        assessment_warnings.append(f"assess.disk: {exc}")

    interferers: list[dict[str, Any]] = []
    try:
        interferers = _rank_interferers(samples)
    except Exception as exc:
        assessment_warnings.append(f"assess.interferers: {exc}")

    # --- Extract key metrics with safe defaults ---
    max_cpu           = stats.get("max_cpu_percent")
    avg_cpu           = stats.get("avg_cpu_percent")
    cpu_std           = vol.get("cpu_std_dev")
    cpu_freq_var      = vol.get("cpu_freq_variation_mhz")
    ram_variation     = vol.get("ram_variation")
    gpu_util_var      = vol.get("gpu_util_variation")
    max_gpu_util      = stats.get("max_gpu_utilization")
    max_gpu_temp      = stats.get("max_gpu_temp")
    max_pf_pct        = stats.get("max_pagefile_percent")
    power_plan        = (baseline.get("power", {}) or {}).get("power_plan") or ""

    # --- Collect reason codes ---
    reasons: list[str] = []

    # CPU
    if max_cpu is not None and max_cpu > _CPU_SPIKE_THRESHOLD:
        reasons.append("cpu_spike_detected")
    if avg_cpu is not None and avg_cpu > _CPU_SUSTAINED_THRESHOLD:
        reasons.append("sustained_cpu_load")
    if cpu_std is not None and cpu_std > _CPU_STD_DEV_NOISY:
        reasons.append("cpu_volatile")
    # Frequency throttling: large swing indicates thermal/power throttling during window
    if cpu_freq_var is not None and cpu_freq_var > 200.0:
        reasons.append("cpu_freq_throttled")

    # Memory
    if ram_variation is not None and ram_variation > _RAM_VARIATION_PRESSURE:
        reasons.append("memory_pressure_detected")
    if max_pf_pct is not None and max_pf_pct > _PAGEFILE_PRESSURE:
        reasons.append("pagefile_pressure")

    # GPU
    if max_gpu_util is not None and max_gpu_util > _GPU_UTIL_PRESSURE:
        reasons.append("gpu_memory_pressure")
    if max_gpu_temp is not None and max_gpu_temp > _GPU_TEMP_HIGH:
        reasons.append("gpu_thermal_load")

    # Disk
    if disk.get("sustained_activity"):
        reasons.append("sustained_disk_activity")

    # Power plan
    if "saver" in power_plan.lower():
        reasons.append("power_saver_mode")

    # Interference from ranked candidates
    seen_categories: set[str] = set()
    _category_reason_map = {
        "browser":       "recurring_browser",
        "ide":           "recurring_ide",
        "sync_tool":     "recurring_sync_tool",
        "security":      "recurring_security_scan",
        "game_launcher": "recurring_game_launcher",
        "comms":         "recurring_comms",
        "media":         "recurring_media",
    }
    persistent_flagged = False
    for cand in interferers:
        cat = cand.get("category")
        if cat and cat not in seen_categories:
            seen_categories.add(cat)
            reason = _category_reason_map.get(cat)
            if reason:
                reasons.append(reason)

        # Flag persistent high-CPU non-system processes regardless of category
        n_samples = stats.get("sample_count") or 1
        is_persistent  = cand.get("recurrence", 0) >= max(1, n_samples // 2)
        is_meaningful  = cand.get("peak_cpu_percent", 0.0) > 5.0
        if is_persistent and is_meaningful and not persistent_flagged:
            reasons.append("persistent_interferer")
            persistent_flagged = True

    # --- Score → quality + severity ---
    score = sum(_REASON_WEIGHTS.get(r, 1) for r in reasons)

    if score >= _DISTORTED_THRESHOLD:
        quality  = _DISTORTED_QUALITY
        severity = _DISTORTED_SEVERITY
    else:
        quality  = "clean"
        severity = "low"
        for max_score, q, s in _SCORE_TIERS:
            if score <= max_score:
                quality  = q
                severity = s
                break
        else:
            # score > last tier but < distorted threshold
            quality  = "noisy"
            severity = "high"

    # --- Resource pressure ---
    gpu_available  = max_gpu_util is not None
    cpu_pressure   = bool(
        (max_cpu is not None and max_cpu > _CPU_SPIKE_THRESHOLD) or
        (avg_cpu is not None and avg_cpu > _CPU_SUSTAINED_THRESHOLD)
    )
    mem_pressure   = bool(
        (ram_variation is not None and ram_variation > _RAM_VARIATION_PRESSURE) or
        (max_pf_pct is not None and max_pf_pct > _PAGEFILE_PRESSURE)
    )
    gpu_pressure: bool | None = (
        bool(max_gpu_util > _GPU_UTIL_PRESSURE) if gpu_available else None
    )
    disk_pressure  = bool(disk.get("sustained_activity", False))

    resource_pressure: dict[str, Any] = {
        "cpu_pressure":  cpu_pressure,
        "memory_pressure": mem_pressure,
        "gpu_pressure":  gpu_pressure,
        "disk_pressure": disk_pressure,
    }
    # Supporting metrics (always-present, None if unavailable)
    resource_pressure["avg_cpu_percent"]  = round(avg_cpu, 1) if avg_cpu is not None else None
    resource_pressure["ram_variation_mb"] = (
        ram_variation // (1024 * 1024) if ram_variation is not None else None
    )
    avg_disk_bps = (disk.get("avg_read_bps") or 0.0) + (disk.get("avg_write_bps") or 0.0)
    resource_pressure["avg_disk_mbps"] = (
        round(avg_disk_bps / (1024 * 1024), 2) if avg_disk_bps else None
    )
    resource_pressure["max_pagefile_percent"] = (
        round(max_pf_pct, 1) if max_pf_pct is not None else None
    )

    # --- Stability ---
    cpu_stable = cpu_std is None or cpu_std < _CPU_STD_DEV_NOISY
    mem_stable = ram_variation is None or ram_variation < _RAM_VARIATION_PRESSURE
    gpu_stable: bool | None = (
        bool(gpu_util_var < _GPU_UTIL_VARIATION_NOISY)
        if gpu_util_var is not None else None
    )
    overall_stable = cpu_stable and mem_stable and (gpu_stable is not False)

    stability: dict[str, Any] = {
        "cpu_stable":     cpu_stable,
        "memory_stable":  mem_stable,
        "gpu_stable":     gpu_stable,
        "overall_stable": overall_stable,
    }

    return {
        "environment_quality":     quality,
        "severity":                severity,
        "reasons":                 reasons,
        "interference_candidates": interferers,
        "resource_pressure":       resource_pressure,
        "stability":               stability,
        "warnings":                assessment_warnings,
    }


# ===========================================================================
# Capability layer
# ===========================================================================

def _probe_nvml_capabilities() -> dict[str, Any]:
    """
    Probe which NVML metrics are actually available on this GPU.

    Attempts a lightweight NVML init, queries each metric category once,
    then shuts NVML down.  Returns a dict mapping capability names to one of:
        "supported"                — probe succeeded, data available
        "unsupported_on_platform"  — not applicable to this OS/hardware class
        "unavailable_at_runtime"   — pynvml installed but GPU not found
        "probe_failed"             — unexpected error during probe
        "not_implemented"          — intentionally skipped (future work)

    Never raises.
    """
    _S  = "supported"
    _UP = "unsupported_on_platform"
    _EU = "expected_unavailable"
    _IN = "inapplicable"
    _PF = "probe_failed"

    caps: dict[str, Any] = {
        "pynvml_available":        _IN,
        "gpu_name":                _IN,
        "gpu_vram":                _IN,
        "gpu_utilization":         _IN,
        "gpu_mem_utilization":     _IN,
        "gpu_temperature":         _IN,
        "gpu_power":               _IN,
        "gpu_graphics_clock":      _IN,
        "gpu_mem_clock":           _IN,
    }

    try:
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("ignore")
            import pynvml  # type: ignore[import]
    except ImportError:
        # pynvml package not installed — assume no GPU exists (inapplicable)
        return caps

    caps["pynvml_available"] = _S

    try:
        pynvml.nvmlInit()
    except Exception as exc:
        # NVML present but init failed.
        # NVMLError_LibraryNotFound or NVMLError_DriverNotLoaded -> expected driver dependency missing.
        # Any other exception (permission denied, segfault wrapper) -> active probe failure.
        name = type(exc).__name__
        if "NotFound" in name or "NotLoaded" in name:
            state = _EU
        else:
            state = _PF
        caps["pynvml_available"] = state
        for k in caps:
            if k != "pynvml_available":
                caps[k] = state
        return caps

    try:
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            # Init succeeded but 0 devices reported. Strictly inapplicable GPU.
            pynvml.nvmlShutdown()
            caps["pynvml_available"] = _S
            for k in caps:
                if k != "pynvml_available":
                    caps[k] = _IN
            return caps
        
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    except Exception:
        pynvml.nvmlShutdown()
        # Init succeeded, devices exist (or count failed), but API crashed.
        caps["pynvml_available"] = _PF
        for k in caps:
            if k != "pynvml_available":
                caps[k] = _PF
        return caps

    # From here we have a valid handle — probe each metric independently.
    def _try(key: str, fn: Any) -> None:
        try:
            fn()
            caps[key] = _S
        except Exception as e:
            name = type(e).__name__
            # If the specific GPU arch doesn't support this reading (e.g. no power sensor),
            # this is a physical limitation, not a software crash.
            if "NotSupported" in name:
                caps[key] = _IN
            else:
                caps[key] = _PF

    _try("gpu_name",           lambda: pynvml.nvmlDeviceGetName(handle))
    _try("gpu_vram",           lambda: pynvml.nvmlDeviceGetMemoryInfo(handle))
    _try("gpu_utilization",    lambda: pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
    _try("gpu_mem_utilization",lambda: pynvml.nvmlDeviceGetUtilizationRates(handle).memory)
    _try("gpu_temperature",    lambda: pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
    _try("gpu_power",          lambda: pynvml.nvmlDeviceGetPowerUsage(handle))
    _try("gpu_graphics_clock", lambda: pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS))
    _try("gpu_mem_clock",      lambda: pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM))

    try:
        pynvml.nvmlShutdown()
    except Exception:
        pass

    return caps


def get_characterization_capabilities() -> dict[str, Any]:
    """
    Report which characterization probes are available in this environment.

    Returns a flat dict of capability names mapped to one of these states:
        "supported"                — probe is available and expected to work
        "unsupported_on_platform"  — not applicable to this OS/hardware class
        "unavailable_at_runtime"   — dependency missing or not accessible
        "probe_failed"             — unexpected runtime error during probe
        "not_implemented"          — reserved for a planned future probe

    Use this to understand what data ``characterize_environment()`` and
    ``sample_environment_window()`` will actually populate on this machine.
    This function never raises; failures appear as "probe_failed" entries.
    """
    _S  = "supported"
    _UP = "unsupported_on_platform"
    _EU = "expected_unavailable"
    _IN = "inapplicable"
    _PF = "probe_failed"
    _NI = "not_implemented"

    caps: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # CPU
    # ------------------------------------------------------------------
    try:
        caps["cpu_brand"] = _S if platform.processor() else _EU
    except Exception:
        caps["cpu_brand"] = _PF

    try:
        caps["cpu_architecture"] = _S if platform.machine() else _EU
    except Exception:
        caps["cpu_architecture"] = _PF

    try:
        caps["cpu_core_count"] = _S if psutil.cpu_count(logical=False) is not None else _EU
    except Exception:
        caps["cpu_core_count"] = _PF

    try:
        caps["cpu_percent"] = _S  # always available via psutil
    except Exception:
        caps["cpu_percent"] = _PF

    try:
        freq = psutil.cpu_freq()
        caps["cpu_freq"] = _S if freq is not None else _EU
    except Exception:
        caps["cpu_freq"] = _PF

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------
    try:
        psutil.virtual_memory()
        caps["ram_stats"] = _S
    except Exception:
        caps["ram_stats"] = _PF

    try:
        psutil.swap_memory()
        caps["swap_stats"] = _S
    except Exception:
        caps["swap_stats"] = _PF

    # ------------------------------------------------------------------
    # Thermal
    # ------------------------------------------------------------------
    try:
        sensors = psutil.sensors_temperatures()  # type: ignore[attr-defined]
        caps["cpu_temperature"] = _S if sensors else _EU
    except AttributeError:
        caps["cpu_temperature"] = _UP  # Windows — attribute does not exist
    except Exception:
        caps["cpu_temperature"] = _PF

    # ------------------------------------------------------------------
    # GPU (NVML)
    # ------------------------------------------------------------------
    nvml_caps = _probe_nvml_capabilities()
    caps.update(nvml_caps)

    # ------------------------------------------------------------------
    # Power
    # ------------------------------------------------------------------
    try:
        batt = psutil.sensors_battery()
        caps["power_plugged"] = _S if batt is not None else _IN
    except Exception:
        caps["power_plugged"] = _PF

    if platform.system() == "Windows":
        try:
            proc = subprocess.run(
                ["powercfg", "/getactivescheme"],
                capture_output=True, text=True, timeout=5,
            )
            caps["power_plan"] = _S if proc.returncode == 0 else _PF
        except Exception:
            caps["power_plan"] = _PF
    else:
        caps["power_plan"] = _UP

    # ------------------------------------------------------------------
    # Disk I/O
    # ------------------------------------------------------------------
    try:
        io = psutil.disk_io_counters()
        caps["disk_io_counters"] = _S if io is not None else _EU
    except Exception:
        caps["disk_io_counters"] = _PF

    # ------------------------------------------------------------------
    # Model path / size
    # ------------------------------------------------------------------
    try:
        model_path_env = read_env_path("QUANTMAP_MODEL_PATH")
        if model_path_env.path is not None and model_path_env.path.exists():
            caps["model_size"] = _S
        else:
            caps["model_size"] = _EU
    except Exception:
        caps["model_size"] = _PF

    # ------------------------------------------------------------------
    # llama-cpp-python version
    # ------------------------------------------------------------------
    try:
        from importlib.metadata import version as _ver, PackageNotFoundError
        for pkg in ("llama-cpp-python", "llama_cpp_python", "llama_cpp"):
            try:
                _ver(pkg)
                caps["llama_cpp_version"] = _S
                break
            except PackageNotFoundError:
                pass
        else:
            caps["llama_cpp_version"] = _IN
    except Exception:
        caps["llama_cpp_version"] = _PF

    return caps
