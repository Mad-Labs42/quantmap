"""
QuantMap — telemetry.py

Background telemetry collection for all campaign runs. Samples system metrics
every 2 seconds and records background process activity every 10 seconds.
Writes append-only to telemetry.jsonl and inserts into lab.sqlite.

AVAILABILITY TIERS (MDD §10.2):
    ABORT  — Campaign halts at startup if any of these are unavailable.
             cpu_temp_c, power_limit_throttling, gpu_vram_used_mb, timestamp
    WARN   — Campaign continues with nulls if unavailable. Logged at startup.
             gpu_temp_c, cpu_power_w, ram_used_gb
    SILENT — Absent from output if unavailable. No startup log entry.
             All remaining metrics.

HARDWARE SOURCES (priority order):
    HWiNFO64 shared memory  — PRIMARY for all hardware sensors
        CPU temp, CPU power, CPU core clocks, liquid temp, GPU temp/clocks
        Requires: HWiNFO64 running with Shared Memory Support enabled
        Settings → Shared Memory Support → ON  (free, no license needed)

    pynvml (nvidia-ml-py)   — GPU VRAM + throttle reasons
        More reliable than HWiNFO for VRAM usage and throttle state.
        Required for ABORT-tier gpu_vram_used_mb and power_limit_throttling.

    psutil (stdlib-level)   — RAM, CPU utilization, disk I/O, network I/O,
                              process list, per-process stats

SETUP:
    1. HWiNFO64 → Settings → Shared Memory Support → enable
    2. HWiNFO64 must be running before starting a campaign
    3. No additional Python packages needed (ctypes is stdlib)
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import io
import json
import logging
import os
import sqlite3
import struct
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

try:
    import pynvml  # type: ignore[import]
    _PYNVML_AVAILABLE = True
except ImportError:
    _PYNVML_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# pynvml 13.x compatibility
# pynvml 13.x wraps nvidia-ml-py; some constants moved or were renamed.
# We resolve them at import time with fallbacks to known raw bitmask values.
# ---------------------------------------------------------------------------
_NVML_INITIALIZED = False
_NVML_HANDLE = None

# Throttle reason bitmask constants (from NVML headers, version-stable values)
def _nvml_const(name: str, fallback: int) -> int:
    """Resolve a pynvml constant by name, falling back to a known raw value."""
    if not _PYNVML_AVAILABLE:
        return fallback
    return getattr(pynvml, name, fallback)

_THROTTLE_SW_POWER_CAP  = _nvml_const("NVML_CLOCKS_THROTTLE_REASON_SW_POWER_CAP",  0x0000000000000004)
_THROTTLE_HW_SLOWDOWN   = _nvml_const("NVML_CLOCKS_THROTTLE_REASON_HW_SLOWDOWN",   0x0000000000000008)
_THROTTLE_HW_THERMAL    = _nvml_const("NVML_CLOCKS_THROTTLE_REASON_HW_THERMAL_SLOWDOWN", 0x0000000000000040)
_THROTTLE_HW_POWER_BRAKE= _nvml_const("NVML_CLOCKS_THROTTLE_REASON_HW_POWER_BRAKE_SLOWDOWN", 0x0000000000000080)
_THROTTLE_GPU_IDLE      = _nvml_const("NVML_CLOCKS_THROTTLE_REASON_GPU_IDLE",       0x0000000000000001)
_THROTTLE_APP_CLOCKS    = _nvml_const("NVML_CLOCKS_THROTTLE_REASON_APPLICATIONS_CLOCKS_SETTING", 0x0000000000000002)
_THROTTLE_SW_THERMAL    = _nvml_const("NVML_CLOCKS_THROTTLE_REASON_SW_THERMAL_SLOWDOWN", 0x0000000000000020)
_THROTTLE_SYNC_BOOST    = _nvml_const("NVML_CLOCKS_THROTTLE_REASON_SYNC_BOOST",     0x0000000000000010)

_THROTTLE_REASON_MAP = {
    _THROTTLE_SW_POWER_CAP:   "SW_POWER_CAP",
    _THROTTLE_HW_SLOWDOWN:    "HW_SLOWDOWN",
    _THROTTLE_HW_THERMAL:     "HW_THERMAL",
    _THROTTLE_HW_POWER_BRAKE: "HW_POWER_BRAKE",
    _THROTTLE_GPU_IDLE:       "GPU_IDLE",
    _THROTTLE_APP_CLOCKS:     "APP_CLOCKS",
    _THROTTLE_SW_THERMAL:     "SW_THERMAL",
    _THROTTLE_SYNC_BOOST:     "SYNC_BOOST",
}

# ---------------------------------------------------------------------------
# HWiNFO64 shared memory reader
# ---------------------------------------------------------------------------

_HWINFO_SM_NAME    = "Global\\HWiNFO_SENS_SM2"
_HWINFO_SIGNATURE  = 0x53695748  # 'HWiS' little-endian (H=0x48 W=0x57 i=0x69 S=0x53)
_HWINFO_STR_LEN    = 128

# Reading type enum values
_RTYPE_NONE    = 0
_RTYPE_TEMP    = 1
_RTYPE_VOLT    = 2
_RTYPE_FAN     = 3
_RTYPE_CURRENT = 4
_RTYPE_POWER   = 5
_RTYPE_CLOCK   = 6
_RTYPE_USAGE   = 7
_RTYPE_OTHER   = 8

# Header layout: 10 fields
_HEADER_FMT  = "<IIIqIIIIII"   # DWORD×3, LONGLONG (signed), DWORD×6 (HIGH-7 fix)
# poll_time is a LONGLONG (signed 64-bit) per HWiNFO SDK. Using Q (unsigned)
# would misinterpret negative timestamps (e.g. pre-epoch) but is otherwise
# harmless since poll_time is always positive in practice.
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)

# Sensor element layout
_SENSOR_FMT  = "<II128s128s"
_SENSOR_SIZE = struct.calcsize(_SENSOR_FMT)

# Reading element layout
# HWiNFO SDK: szUnit is HWiNFO_UNIT_STRING_LEN = 16 bytes (not 128).
# Full element: dwReading(4) + dwSensorIndex(4) + dwReadingID(4)
#             + szLabelOrig(128) + szLabelUser(128) + szUnit(16)
#             + Value(8) + ValueMin(8) + ValueMax(8) + ValueAvg(8) = 316 bytes
_READING_FMT  = "<III128s128s16sdddd"
_READING_SIZE = struct.calcsize(_READING_FMT)

# ---------------------------------------------------------------------------
# Windows PERFORMANCE_INFORMATION struct (psapi.GetPerformanceInfo)
# Used by _get_system_commit_charge(). Defined at module level to avoid
# re-creating the class on every call (collect_sample() runs at ~1 Hz).
# ---------------------------------------------------------------------------

class _PERFORMANCE_INFORMATION(ctypes.Structure):
    """Mirrors PERFORMANCE_INFORMATION from psapi.h (winbase.h via SDK)."""
    _fields_ = [
        ("cb",                ctypes.c_uint),    # DWORD — size of this struct
        ("CommitTotal",       ctypes.c_size_t),  # pages currently committed
        ("CommitLimit",       ctypes.c_size_t),  # max pages that can be committed
        ("CommitPeak",        ctypes.c_size_t),  # peak pages committed this boot
        ("PhysicalTotal",     ctypes.c_size_t),  # total physical pages
        ("PhysicalAvailable", ctypes.c_size_t),  # available physical pages
        ("SystemCache",       ctypes.c_size_t),  # system cache pages
        ("KernelTotal",       ctypes.c_size_t),  # kernel + driver pages (paged + NP)
        ("KernelPaged",       ctypes.c_size_t),  # paged kernel pages
        ("KernelNonpaged",    ctypes.c_size_t),  # nonpaged kernel pages
        ("PageSize",          ctypes.c_size_t),  # page size in bytes (typically 4096)
        ("HandleCount",       ctypes.c_uint),    # DWORD — total open handles
        ("ProcessCount",      ctypes.c_uint),    # DWORD — total processes
        ("ThreadCount",       ctypes.c_uint),    # DWORD — total threads
    ]


class HWiNFOUnavailable(RuntimeError):
    """Raised when HWiNFO shared memory cannot be opened."""


# Win32 type setup (done once at module level)
_k32 = ctypes.windll.kernel32
_k32.OpenFileMappingW.restype  = ctypes.wintypes.HANDLE
_k32.OpenFileMappingW.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
_k32.MapViewOfFile.restype     = ctypes.c_void_p
_k32.MapViewOfFile.argtypes    = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD,
                                   ctypes.wintypes.DWORD, ctypes.wintypes.DWORD, ctypes.c_size_t]
_k32.UnmapViewOfFile.restype   = ctypes.wintypes.BOOL
_k32.UnmapViewOfFile.argtypes  = [ctypes.c_void_p]
_k32.CloseHandle.restype       = ctypes.wintypes.BOOL
_k32.CloseHandle.argtypes      = [ctypes.wintypes.HANDLE]

_FILE_MAP_READ = 0x0004


def _read_hwinfo_sm_bytes() -> bytes | None:
    """
    Open HWiNFO64 shared memory read-only and return a snapshot as bytes.

    Uses OpenFileMappingW (open existing) + MapViewOfFile + ctypes.string_at.
    OpenFileMappingW does NOT require elevated privileges or SeCreateGlobalPrivilege
    — only CreateFileMappingW does. This is why mmap(tagname=...) fails for
    unprivileged processes: Python's mmap uses CreateFileMappingW internally.

    Returns None if HWiNFO is not running or shared memory is unavailable.
    """
    h = _k32.OpenFileMappingW(_FILE_MAP_READ, False, _HWINFO_SM_NAME)
    if not h:
        return None

    try:
        addr = _k32.MapViewOfFile(h, _FILE_MAP_READ, 0, 0, 0)
        if not addr:
            return None
        try:
            # Read header to determine how many bytes we actually need
            header_raw = ctypes.string_at(addr, _HEADER_SIZE)
            if len(header_raw) < _HEADER_SIZE:
                return None

            fields = struct.unpack(_HEADER_FMT, header_raw)
            sig = fields[0]
            if sig != _HWINFO_SIGNATURE:
                logger.debug("HWiNFO signature mismatch: got 0x%08X", sig)
                return None

            off_sensor, sz_sensor, num_sensor = fields[4], fields[5], fields[6]
            off_reading, sz_reading, num_reading = fields[7], fields[8], fields[9]

            total_bytes = max(
                _HEADER_SIZE,
                (off_sensor  + sz_sensor  * num_sensor)  if num_sensor  > 0 else 0,
                (off_reading + sz_reading * num_reading) if num_reading > 0 else 0,
            )
            if total_bytes <= 0 or total_bytes > 32 * 1024 * 1024:
                return None

            return ctypes.string_at(addr, total_bytes)
        finally:
            _k32.UnmapViewOfFile(ctypes.c_void_p(addr))
    finally:
        _k32.CloseHandle(h)


def _read_hwinfo_readings(sm: io.BytesIO) -> list[dict[str, Any]]:
    """
    Parse HWiNFO shared memory and return all reading elements as a list of dicts.

    Each dict has keys:
        sensor_name: str    (name of the sensor group, e.g. "CPU [#0]: Intel Core i9-12900K")
        label:       str    (reading label, e.g. "CPU Package")
        label_user:  str    (user-renamed label, same as label if not renamed)
        unit:        str    (e.g. "°C", "W", "MHz", "%")
        rtype:       int    (reading type: 1=temp, 5=power, 6=clock, 7=usage, etc.)
        value:       float  (current value)
        value_min:   float
        value_max:   float
        value_avg:   float

    Returns empty list on any parse error.
    """
    try:
        sm.seek(0)
        raw_header = sm.read(_HEADER_SIZE)
        if len(raw_header) < _HEADER_SIZE:
            return []

        fields = struct.unpack(_HEADER_FMT, raw_header)
        (sig, version, revision, poll_time,
         off_sensor, sz_sensor, num_sensor,
         off_reading, sz_reading, num_reading) = fields

        if sig != _HWINFO_SIGNATURE:
            logger.debug("HWiNFO signature mismatch: got 0x%08X expected 0x%08X", sig, _HWINFO_SIGNATURE)
            return []

        # Read sensor names (for sensor group labels)
        sensors: list[str] = []
        for i in range(num_sensor):
            sm.seek(off_sensor + i * sz_sensor)
            raw = sm.read(sz_sensor)
            if len(raw) < _SENSOR_SIZE:
                break
            # dwSensorID(4) + dwSensorInst(4) + szSensorNameOrig(128) + szSensorNameUser(128)
            _, _, name_orig_b, name_user_b = struct.unpack(_SENSOR_FMT, raw[:_SENSOR_SIZE])
            name_orig = name_orig_b.rstrip(b'\x00').decode('utf-8', errors='replace')
            sensors.append(name_orig)

        # Read all readings
        readings: list[dict[str, Any]] = []
        for i in range(num_reading):
            sm.seek(off_reading + i * sz_reading)
            raw = sm.read(sz_reading)
            if len(raw) < _READING_SIZE:
                break

            (rtype, sensor_idx, reading_id,
             label_orig_b, label_user_b, unit_b,
             val, val_min, val_max, val_avg) = struct.unpack(_READING_FMT, raw[:_READING_SIZE])

            label_orig = label_orig_b.rstrip(b'\x00').decode('utf-8', errors='replace')
            label_user = label_user_b.rstrip(b'\x00').decode('utf-8', errors='replace')
            unit       = unit_b.rstrip(b'\x00').decode('utf-8', errors='replace')
            sensor_name = sensors[sensor_idx] if sensor_idx < len(sensors) else ""

            readings.append({
                "sensor_name": sensor_name,
                "label":       label_orig,
                "label_user":  label_user,
                "unit":        unit,
                "rtype":       rtype,
                "value":       val,
                "value_min":   val_min,
                "value_max":   val_max,
                "value_avg":   val_avg,
            })

        return readings

    except Exception as exc:
        logger.debug("HWiNFO SM parse error: %s", exc)
        return []


def _find_reading(
    readings: list[dict[str, Any]],
    label_substr: str,
    rtype: int | None = None,
    sensor_substr: str | None = None,
) -> float | None:
    """
    Search readings for the first entry matching label_substr (case-insensitive).
    Optionally filter by rtype and/or sensor_substr.
    Returns the current value, or None if not found.
    """
    label_lower  = label_substr.lower()
    sensor_lower = sensor_substr.lower() if sensor_substr else None

    for r in readings:
        if rtype is not None and r["rtype"] != rtype:
            continue
        if sensor_lower and sensor_lower not in r["sensor_name"].lower():
            continue
        if label_lower in r["label"].lower() or label_lower in r["label_user"].lower():
            return r["value"]
    return None


def _find_readings_multi(
    readings: list[dict[str, Any]],
    label_substr: str,
    rtype: int | None = None,
    sensor_substr: str | None = None,
) -> list[float]:
    """Like _find_reading but returns ALL matching values (for per-core averages)."""
    label_lower  = label_substr.lower()
    sensor_lower = sensor_substr.lower() if sensor_substr else None
    results = []

    for r in readings:
        if rtype is not None and r["rtype"] != rtype:
            continue
        if sensor_lower and sensor_lower not in r["sensor_name"].lower():
            continue
        if label_lower in r["label"].lower() or label_lower in r["label_user"].lower():
            results.append(r["value"])
    return results


def _get_hwinfo_readings() -> list[dict[str, Any]]:
    """Read a fresh snapshot from HWiNFO shared memory and return all readings."""
    raw = _read_hwinfo_sm_bytes()
    if raw is None:
        return []
    return _read_hwinfo_readings(io.BytesIO(raw))


# ---------------------------------------------------------------------------
# pynvml helpers
# ---------------------------------------------------------------------------

def _init_nvml() -> bool:
    """Initialize pynvml. Returns True on success."""
    global _NVML_INITIALIZED, _NVML_HANDLE
    if not _PYNVML_AVAILABLE:
        return False
    try:
        pynvml.nvmlInit()
        _NVML_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(0)
        _NVML_INITIALIZED = True
        return True
    except Exception as exc:
        logger.error("pynvml init failed: %s", exc)
        return False


def _nvml_throttle_reasons_str(handle: Any) -> str | None:
    """Return a human-readable comma-separated list of active GPU throttle reasons."""
    if not _NVML_INITIALIZED:
        return None
    try:
        reasons = pynvml.nvmlDeviceGetCurrentClocksThrottleReasons(handle)
        active = [name for flag, name in _THROTTLE_REASON_MAP.items() if reasons & flag]
        return ",".join(active) if active else "NONE"
    except Exception as exc:
        logger.debug("nvml throttle reasons failed: %s", exc)
        return None


def _nvml_pstate_str(handle: Any) -> str | None:
    """Return GPU P-state as string (P0–P8)."""
    if not _NVML_INITIALIZED:
        return None
    try:
        pstate = pynvml.nvmlDeviceGetPerformanceState(handle)
        return f"P{pstate}"
    except Exception as exc:
        logger.debug("nvml pstate failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TelemetrySample:
    """
    One telemetry snapshot (sampled every 2 seconds).
    All fields map to telemetry.jsonl columns (MDD §10.3 + extended metrics).
    None = metric was unavailable for this sample.
    """

    # Identity
    campaign_id: str
    config_id: str
    timestamp: str  # ISO8601 UTC

    # --- ABORT tier ---
    cpu_temp_c: float | None                 # CPU Package temperature (HWiNFO)
    power_limit_throttling: bool | None      # GPU SW power cap throttle (pynvml)
    gpu_vram_used_mb: float | None           # GPU VRAM used (pynvml)

    # --- WARN tier ---
    gpu_temp_c: float | None                 # GPU die temperature
    cpu_power_w: float | None                # CPU Package power (HWiNFO)
    ram_used_gb: float | None                # System RAM in use (psutil)

    # --- SILENT tier (hardware) ---
    cpu_pcore_freq_ghz: float | None = None  # Average P-core frequency (HWiNFO)
    cpu_ecore_freq_ghz: float | None = None  # Average E-core frequency (HWiNFO)
    gpu_util_pct: float | None = None        # GPU compute utilization (pynvml)
    gpu_power_w: float | None = None         # GPU power draw (pynvml)
    gpu_graphics_clock_mhz: float | None = None  # (pynvml)
    gpu_mem_clock_mhz: float | None = None       # (pynvml)
    gpu_pstate: str | None = None                # P0–P8 (pynvml)
    gpu_throttle_reasons: str | None = None      # bitmask description (pynvml)
    liquid_temp_c: float | None = None           # Coolant temp (HWiNFO, NZXT Kraken)
    disk_read_mbps: float | None = None          # System-wide disk read rate
    disk_write_mbps: float | None = None
    page_faults_sec: float | None = None

    # --- SILENT tier (extended — for interference diagnosis) ---
    net_sent_mbps: float | None = None
    net_recv_mbps: float | None = None
    cpu_freq_mhz: float | None = None            # psutil average current freq
    cpu_util_pct: float | None = None            # Overall CPU utilization %
    cpu_util_per_core_json: str | None = None    # Per-core utilization JSON array
    ram_available_gb: float | None = None
    ram_committed_gb: float | None = None
    pagefile_used_gb: float | None = None
    context_switches_sec: float | None = None
    interrupts_sec: float | None = None
    server_cpu_pct: float | None = None          # llama-server CPU %
    server_rss_mb: float | None = None           # Working Set: physical RAM currently in use (mem.rss)
    server_private_bytes_mb: float | None = None # Private Bytes: total committed incl. paged-out (mem.pagefile, Windows only)
    server_vms_mb: float | None = None
    server_thread_count: int | None = None
    server_handle_count: int | None = None
    server_pid: int | None = None

    # --- HWiNFO extended hardware (SILENT) ---
    cpu_core_voltage_v: float | None = None      # CPU VCore (HWiNFO)
    cpu_ia_cores_power_w: float | None = None    # IA Cores power sub-rail (HWiNFO)
    gpu_hotspot_temp_c: float | None = None      # GPU hotspot temperature (HWiNFO)
    gpu_mem_temp_c: float | None = None          # GPU memory temperature (HWiNFO)
    gpu_fan_rpm: float | None = None             # GPU fan speed (HWiNFO)
    cpu_fan_rpm: float | None = None             # CPU fan/pump speed (HWiNFO)


@dataclass
class BackgroundSnapshot:
    """Process and system activity snapshot (taken every 10 seconds)."""

    campaign_id: str
    config_id: str
    timestamp: str

    top_cpu_procs_json: str = "[]"
    top_ram_procs_json: str = "[]"
    top_disk_procs_json: str = "[]"
    all_notable_procs_json: str = "[]"

    windows_defender_active: bool = False
    windows_update_active: bool = False
    search_indexer_active: bool = False
    antivirus_scan_active: bool = False

    network_active_connections: int = 0
    network_established_connections: int = 0
    power_plan: str = ""
    high_cpu_process_count: int = 0


# ---------------------------------------------------------------------------
# Startup availability check
# ---------------------------------------------------------------------------

class TelemetryStartupError(RuntimeError):
    """Raised when ABORT-tier metrics are unavailable at campaign start."""


def startup_check() -> dict[str, Any]:
    """
    Probe all telemetry sources and enforce ABORT/WARN/SILENT tiers.

    Raises TelemetryStartupError if any ABORT-tier metric is unavailable.
    Logs warnings for WARN-tier gaps. SILENT-tier availability recorded silently.

    Returns availability report dict.
    """
    global _NVML_INITIALIZED, _NVML_HANDLE

    report: dict[str, Any] = {
        "abort": {},
        "warn": {},
        "silent": {},
        "source_details": {},
    }

    # ---- HWiNFO (PRIMARY for all hardware temps/power/clocks) ---------------
    readings = _get_hwinfo_readings()
    hwinfo_ok = len(readings) > 0
    report["source_details"]["hwinfo_available"] = hwinfo_ok
    report["source_details"]["hwinfo_reading_count"] = len(readings)

    if not hwinfo_ok:
        raise TelemetryStartupError(
            "ABORT: HWiNFO64 shared memory not accessible.\n\n"
            "To fix:\n"
            "  1. Open HWiNFO64\n"
            "  2. Settings → Shared Memory Support → enable\n"
            "  3. Restart HWiNFO64 (the setting takes effect on next start)\n\n"
            "HWiNFO must be running during all campaigns. "
            "cpu_temp_c (ABORT tier) is sourced from HWiNFO."
        )

    # Confirm CPU Package temp is readable
    cpu_temp = _find_reading(readings, "CPU Package", rtype=_RTYPE_TEMP)
    if cpu_temp is None:
        # Try alternate labels used by HWiNFO on some Intel chips
        for alt_label in ("CPU (Tctl/Tdie)", "CPU Tctl", "CPU Die", "DTS"):
            cpu_temp = _find_reading(readings, alt_label, rtype=_RTYPE_TEMP)
            if cpu_temp is not None:
                report["source_details"]["cpu_temp_label"] = alt_label
                break

    if cpu_temp is None:
        # Log all temp sensor labels for diagnosis
        temp_labels = [r["label"] for r in readings if r["rtype"] == _RTYPE_TEMP]
        raise TelemetryStartupError(
            f"ABORT: HWiNFO is running and shared memory is accessible, but no CPU "
            f"Package temperature sensor was found.\n\n"
            f"Available temperature sensors ({len(temp_labels)}):\n"
            + "\n".join(f"  - {l}" for l in temp_labels[:20])
            + "\n\nCheck HWiNFO sensor list and ensure the CPU sensor is enabled."
        )

    report["abort"]["cpu_temp_c"] = True
    report["source_details"]["cpu_temp_label"] = report["source_details"].get("cpu_temp_label", "CPU Package")
    logger.info("cpu_temp_c (ABORT) available via HWiNFO: %.1f°C", cpu_temp)

    # ---- GPU via pynvml (ABORT for VRAM + throttle, WARN for temp) ----------
    nvml_ok = _init_nvml()
    report["source_details"]["pynvml"] = nvml_ok

    if not nvml_ok:
        raise TelemetryStartupError(
            "ABORT: pynvml unavailable — gpu_vram_used_mb and power_limit_throttling "
            "cannot be collected.\n"
            "Verify nvidia-ml-py is installed: pip install nvidia-ml-py\n"
            "Verify NVIDIA driver is accessible."
        )

    try:
        mem = pynvml.nvmlDeviceGetMemoryInfo(_NVML_HANDLE)
        report["abort"]["gpu_vram_used_mb"] = True
    except Exception as exc:
        raise TelemetryStartupError(
            f"ABORT: pynvml initialized but VRAM read failed: {exc}"
        ) from exc

    try:
        pynvml.nvmlDeviceGetCurrentClocksThrottleReasons(_NVML_HANDLE)
        report["abort"]["power_limit_throttling"] = True
    except Exception as exc:
        raise TelemetryStartupError(
            f"ABORT: pynvml throttle reason query failed: {exc}\n"
            "power_limit_throttling (ABORT tier) requires driver support for this query."
        ) from exc

    # GPU temp (WARN — try HWiNFO first, then pynvml)
    gpu_temp_hwinfo = _find_reading(readings, "GPU Temperature", rtype=_RTYPE_TEMP)
    gpu_temp_nvml: float | None = None
    try:
        gpu_temp_nvml = float(
            pynvml.nvmlDeviceGetTemperature(_NVML_HANDLE, pynvml.NVML_TEMPERATURE_GPU)
        )
    except Exception:
        pass

    report["warn"]["gpu_temp_c"] = (gpu_temp_hwinfo is not None or gpu_temp_nvml is not None)
    if not report["warn"]["gpu_temp_c"]:
        logger.warning("WARN: gpu_temp_c unavailable from both HWiNFO and pynvml")

    # CPU power (WARN)
    cpu_power = _find_reading(readings, "CPU Package Power", rtype=_RTYPE_POWER)
    if cpu_power is None:
        cpu_power = _find_reading(readings, "CPU Package", rtype=_RTYPE_POWER)
    report["warn"]["cpu_power_w"] = cpu_power is not None
    if cpu_power is not None:
        logger.info("cpu_power_w (WARN) available via HWiNFO: %.1fW", cpu_power)
    else:
        logger.warning("WARN: cpu_power_w not found in HWiNFO readings")

    # RAM (WARN via psutil)
    try:
        psutil.virtual_memory()
        report["warn"]["ram_used_gb"] = True
    except Exception:
        report["warn"]["ram_used_gb"] = False
        logger.warning("WARN: ram_used_gb unavailable (psutil failed)")

    # ---- SILENT probes -------------------------------------------------------
    report["silent"]["cpu_pcore_freq"] = len(
        _find_readings_multi(readings, "Core 0 Clock", rtype=_RTYPE_CLOCK)
    ) > 0
    report["silent"]["liquid_temp"] = _find_reading(
        readings, "liquid", rtype=_RTYPE_TEMP
    ) is not None or _find_reading(
        readings, "coolant", rtype=_RTYPE_TEMP
    ) is not None
    report["silent"]["gpu_extended"] = _NVML_INITIALIZED
    report["silent"]["hwinfo_reading_count"] = len(readings)

    report["abort"]["timestamp"] = True

    logger.info(
        "Telemetry startup check passed. "
        "HWiNFO: %d readings | pynvml: %s | "
        "ABORT: all OK | WARN: %s",
        len(readings),
        "ok" if nvml_ok else "FAIL",
        {k: v for k, v in report["warn"].items()},
    )
    return report


# ---------------------------------------------------------------------------
# Delta-counter state for I/O rate calculations
# ---------------------------------------------------------------------------
_prev_disk_counters: Any = None
_prev_net_counters: Any = None
_prev_sample_time: float = 0.0
_prev_cpu_stats: Any = None
_server_process: psutil.Process | None = None


def _get_server_process(pid: int | None) -> psutil.Process | None:
    if pid is None:
        return None
    try:
        p = psutil.Process(pid)
        if p.is_running():
            return p
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return None


# ---------------------------------------------------------------------------
# Platform-isolated memory helper
# ---------------------------------------------------------------------------

def _get_server_private_bytes(mem: Any) -> float | None:
    """
    Return the server process's private committed memory in MB.

    This function is the single point of change for cross-platform support.
    All platform-specific branching for this metric lives here.

    Platform semantics and implementation status
    ─────────────────────────────────────────────
    Windows (current):
        mem.pagefile = "Private Bytes" — virtual memory committed exclusively
        to this process, backed by either RAM or the page file.  This is what
        Task Manager shows as "Memory (Private Working Set)" and what Process
        Explorer shows as "Private Bytes".  Critically distinct from RSS: RSS
        measures pages currently resident in physical RAM; Private Bytes
        measures total commitment including pages currently swapped out.  For
        C12 (mlock campaign) these will diverge significantly under memory
        pressure.

    Linux (NOT YET IMPLEMENTED — planned for cross-platform release):
        No direct equivalent. Closest options, in order of accuracy:
          1. Parse /proc/PID/smaps_rollup → sum Private_Clean + Private_Dirty.
             Most accurate; requires file read per sample (low overhead).
          2. psutil.Process.memory_maps(grouped=True) → sum 'private' field.
             Convenient but slightly slower than direct smaps parse.
        Until implemented, returns None (column will be NULL in telemetry).
        To add: branch on `sys.platform == 'linux'` and implement option 1.

    macOS (NOT YET IMPLEMENTED — planned for cross-platform release):
        psutil exposes mem.private on macOS (maps to task_info TASK_VM_INFO
        → phys_footprint).  Implementation is a one-liner:
            return getattr(mem, 'private', None) / (1024 * 1024)
        To add: branch on `sys.platform == 'darwin'`.
    """
    import sys
    if sys.platform == "win32":
        raw = getattr(mem, "pagefile", None)
        return raw / (1024 * 1024) if raw is not None else None
    # Linux and macOS: see docstring — planned for cross-platform release
    return None


def _get_system_commit_charge() -> float | None:
    """
    Return system-wide virtual memory commit charge in GB.

    Commit charge is the total virtual memory the OS has promised to back
    (with either RAM or page file) across all processes — not what is
    currently resident.  It determines whether the system is approaching its
    commit limit and will start failing VirtualAlloc calls.

    For mmap'd models this is the critical number: RAM used reflects pages
    currently resident; commit charge reflects the full 94 GB the OS has
    reserved, including pages that have never been touched.  The gap between
    the two is exactly the paging pressure diagnostic the C12 (mlock) campaign
    needs.

    This function is the single point of change for cross-platform support.
    All platform-specific branching for this metric lives here.

    Platform semantics and implementation status
    ─────────────────────────────────────────────
    Windows (current):
        GetPerformanceInfo() from psapi.dll returns CommitTotal (pages) and
        PageSize.  CommitTotal × PageSize is the system-wide committed bytes.
        psutil.virtual_memory() does NOT expose this on Windows — vm.used
        measures RAM in use (working set), not commit charge. (HIGH-2 fix)

    Linux (NOT YET IMPLEMENTED — planned for cross-platform release):
        /proc/meminfo "Committed_AS" is the direct equivalent — it is the
        kernel's running total of committed virtual memory across all tasks.
        Implementation: open /proc/meminfo, find the "Committed_AS:" line,
        parse the kB value, convert to GB.  No syscall; cheap file read.
        To add: branch on `sys.platform == 'linux'` and implement above.

    macOS (NOT YET IMPLEMENTED — planned for cross-platform release):
        macOS does not track commit charge in the same sense as Windows or
        Linux — the kernel uses an optimistic overcommit model and does not
        expose a Committed_AS equivalent.  Closest proxy: `vm_stat` output
        (pages active + inactive + speculative + wired + compressor) or
        `sysctl vm.swapusage`.  Neither is a true commit charge.
        To add: branch on `sys.platform == 'darwin'`, return None, and add
        a log.debug() note so users know the column will be NULL on macOS.
    """
    import sys
    if sys.platform == "win32":
        try:
            pi = _PERFORMANCE_INFORMATION()
            pi.cb = ctypes.sizeof(pi)
            ok = ctypes.windll.psapi.GetPerformanceInfo(
                ctypes.byref(pi), ctypes.c_uint(pi.cb)
            )
            if ok:
                return (pi.CommitTotal * pi.PageSize) / (1024 ** 3)
        except Exception:
            pass
        return None
    # Linux and macOS: see docstring — planned for cross-platform release
    return None


# ---------------------------------------------------------------------------
# Core sample collection
# ---------------------------------------------------------------------------

def collect_sample(
    campaign_id: str,
    config_id: str,
    server_pid: int | None = None,
) -> TelemetrySample:
    """
    Collect one telemetry sample. Safe to call from background thread.
    Never raises — all failures produce None for that metric.
    """
    global _prev_disk_counters, _prev_net_counters, _prev_sample_time
    global _prev_cpu_stats, _server_process

    now = time.monotonic()
    ts = datetime.now(timezone.utc).isoformat()
    elapsed = (now - _prev_sample_time) if _prev_sample_time > 0 else None

    # ---- HWiNFO readings (one SM read for all hardware metrics) -------------
    readings = _get_hwinfo_readings()

    # CPU temperature
    cpu_temp_c = _find_reading(readings, "CPU Package", rtype=_RTYPE_TEMP)
    if cpu_temp_c is None:
        for alt in ("CPU (Tctl/Tdie)", "CPU Tctl", "CPU Die", "DTS"):
            cpu_temp_c = _find_reading(readings, alt, rtype=_RTYPE_TEMP)
            if cpu_temp_c is not None:
                break

    # CPU power
    cpu_power_w = _find_reading(readings, "CPU Package Power", rtype=_RTYPE_POWER)
    if cpu_power_w is None:
        cpu_power_w = _find_reading(readings, "CPU Package", rtype=_RTYPE_POWER)

    # CPU IA cores power sub-rail
    cpu_ia_power = _find_reading(readings, "IA Cores Power", rtype=_RTYPE_POWER)
    if cpu_ia_power is None:
        cpu_ia_power = _find_reading(readings, "Core Power", rtype=_RTYPE_POWER)

    # CPU VCore
    cpu_vcore = _find_reading(readings, "CPU Core Voltage", rtype=_RTYPE_VOLT)
    if cpu_vcore is None:
        cpu_vcore = _find_reading(readings, "VCore", rtype=_RTYPE_VOLT)

    # P-core frequencies: i9-12900K P-cores are Core 0–Core 7 (first 8 cores)
    # E-cores are Core 8–Core 15 (labeled differently depending on HWiNFO version)
    all_core_clocks = _find_readings_multi(readings, "Core #", rtype=_RTYPE_CLOCK)
    # Also try "Core 0 Clock" format
    if not all_core_clocks:
        all_core_clocks = _find_readings_multi(readings, "CPU Core Clock", rtype=_RTYPE_CLOCK)

    # Split P-cores (first 8) vs E-cores (remaining) by count
    # i9-12900K: 8 P-cores + 8 E-cores = 16 logical core clock entries
    pcore_freqs = [f / 1000.0 for f in all_core_clocks[:8]]   # MHz → GHz
    ecore_freqs = [f / 1000.0 for f in all_core_clocks[8:16]]

    cpu_pcore_freq_ghz = sum(pcore_freqs) / len(pcore_freqs) if pcore_freqs else None
    cpu_ecore_freq_ghz = sum(ecore_freqs) / len(ecore_freqs) if ecore_freqs else None

    # Liquid temperature (NZXT Kraken / any cooler HWiNFO finds)
    liquid_temp_c = _find_reading(readings, "Liquid Temperature", rtype=_RTYPE_TEMP)
    if liquid_temp_c is None:
        liquid_temp_c = _find_reading(readings, "Coolant Temperature", rtype=_RTYPE_TEMP)
    if liquid_temp_c is None:
        liquid_temp_c = _find_reading(readings, "Kraken", rtype=_RTYPE_TEMP)

    # CPU fan / pump speed
    cpu_fan_rpm = _find_reading(readings, "CPU Fan", rtype=_RTYPE_FAN)
    if cpu_fan_rpm is None:
        cpu_fan_rpm = _find_reading(readings, "Pump", rtype=_RTYPE_FAN)

    # GPU temperature from HWiNFO (more sensor variety than pynvml)
    gpu_temp_c_hwinfo = _find_reading(readings, "GPU Temperature", rtype=_RTYPE_TEMP)
    gpu_hotspot = _find_reading(readings, "GPU Hot Spot", rtype=_RTYPE_TEMP)
    if gpu_hotspot is None:
        gpu_hotspot = _find_reading(readings, "GPU Hotspot", rtype=_RTYPE_TEMP)
    gpu_mem_temp = _find_reading(readings, "GPU Memory Temperature", rtype=_RTYPE_TEMP)
    gpu_fan_rpm = _find_reading(readings, "GPU Fan", rtype=_RTYPE_FAN)

    # ---- GPU metrics (pynvml) -----------------------------------------------
    gpu_vram_used_mb: float | None = None
    gpu_util_pct: float | None = None
    gpu_power_w: float | None = None
    gpu_graphics_clock_mhz: float | None = None
    gpu_mem_clock_mhz: float | None = None
    gpu_pstate: str | None = None
    gpu_throttle_reasons: str | None = None
    power_limit_throttling: bool | None = None
    gpu_temp_nvml: float | None = None

    if _NVML_INITIALIZED and _NVML_HANDLE is not None:
        h = _NVML_HANDLE
        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            gpu_vram_used_mb = mem.used / (1024 * 1024)
        except Exception:
            pass
        try:
            gpu_temp_nvml = float(
                pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
            )
        except Exception:
            pass
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(h)
            gpu_util_pct = float(util.gpu)
        except Exception:
            pass
        try:
            gpu_power_w = pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0
        except Exception:
            pass
        try:
            gpu_graphics_clock_mhz = float(
                pynvml.nvmlDeviceGetClockInfo(h, pynvml.NVML_CLOCK_GRAPHICS)
            )
        except Exception:
            pass
        try:
            gpu_mem_clock_mhz = float(
                pynvml.nvmlDeviceGetClockInfo(h, pynvml.NVML_CLOCK_MEM)
            )
        except Exception:
            pass
        gpu_pstate = _nvml_pstate_str(h)
        gpu_throttle_reasons = _nvml_throttle_reasons_str(h)

        try:
            reasons = pynvml.nvmlDeviceGetCurrentClocksThrottleReasons(h)
            power_limit_throttling = bool(reasons & _THROTTLE_SW_POWER_CAP)
        except Exception:
            power_limit_throttling = None

    # Prefer HWiNFO GPU temp (more sensors); fall back to pynvml
    gpu_temp_c = gpu_temp_c_hwinfo if gpu_temp_c_hwinfo is not None else gpu_temp_nvml

    # ---- RAM, CPU util (psutil) ----------------------------------------------
    ram_used_gb: float | None = None
    ram_available_gb: float | None = None
    ram_committed_gb: float | None = None
    pagefile_used_gb: float | None = None
    cpu_util_pct: float | None = None
    cpu_freq_mhz: float | None = None
    cpu_util_per_core_json: str | None = None

    try:
        vm = psutil.virtual_memory()
        ram_used_gb = vm.used / (1024 ** 3)
        ram_available_gb = vm.available / (1024 ** 3)
    except Exception:
        pass

    # System commit charge — requires platform-specific API (psutil does not
    # expose this on Windows). See _get_system_commit_charge() for details.
    ram_committed_gb = _get_system_commit_charge()

    try:
        sm = psutil.swap_memory()
        pagefile_used_gb = sm.used / (1024 ** 3)
    except Exception:
        pass

    try:
        cpu_util_pct = psutil.cpu_percent(interval=None)
    except Exception:
        pass

    try:
        freq = psutil.cpu_freq()
        if freq:
            cpu_freq_mhz = freq.current
    except Exception:
        pass

    try:
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        cpu_util_per_core_json = json.dumps(per_core)
    except Exception:
        pass

    # ---- CPU stats (context switches, interrupts) ---------------------------
    context_switches_sec: float | None = None
    interrupts_sec: float | None = None

    try:
        stats = psutil.cpu_stats()
        if _prev_cpu_stats is not None and elapsed and elapsed > 0:
            context_switches_sec = (
                stats.ctx_switches - _prev_cpu_stats.ctx_switches
            ) / elapsed
            interrupts_sec = (
                stats.interrupts - _prev_cpu_stats.interrupts
            ) / elapsed
        _prev_cpu_stats = stats
    except Exception:
        pass

    # ---- Disk I/O rates -----------------------------------------------------
    disk_read_mbps: float | None = None
    disk_write_mbps: float | None = None

    try:
        disk = psutil.disk_io_counters()
        if disk and _prev_disk_counters is not None and elapsed and elapsed > 0:
            disk_read_mbps = (
                (disk.read_bytes - _prev_disk_counters.read_bytes) / elapsed / (1024 * 1024)
            )
            disk_write_mbps = (
                (disk.write_bytes - _prev_disk_counters.write_bytes) / elapsed / (1024 * 1024)
            )
        _prev_disk_counters = disk
    except Exception:
        pass

    # ---- Network I/O rates --------------------------------------------------
    net_sent_mbps: float | None = None
    net_recv_mbps: float | None = None

    try:
        net = psutil.net_io_counters()
        if net and _prev_net_counters is not None and elapsed and elapsed > 0:
            net_sent_mbps = (
                (net.bytes_sent - _prev_net_counters.bytes_sent) / elapsed / (1024 * 1024)
            )
            net_recv_mbps = (
                (net.bytes_recv - _prev_net_counters.bytes_recv) / elapsed / (1024 * 1024)
            )
        _prev_net_counters = net
    except Exception:
        pass

    # ---- llama-server process -----------------------------------------------
    _rss_mb: float | None = None           # Working Set (physical RAM in use now)
    _private_bytes_mb: float | None = None # Private Bytes (committed; Windows only)
    server_cpu_pct: float | None = None
    server_vms_mb: float | None = None
    server_thread_count: int | None = None
    server_handle_count: int | None = None

    if server_pid and (
        _server_process is None or _server_process.pid != server_pid
    ):
        _server_process = _get_server_process(server_pid)

    if _server_process is not None:
        try:
            with _server_process.oneshot():
                mem = _server_process.memory_info()
                _rss_mb = mem.rss / (1024 * 1024)
                server_vms_mb = mem.vms / (1024 * 1024)
                _private_bytes_mb = _get_server_private_bytes(mem)
                server_cpu_pct = _server_process.cpu_percent(interval=None)
                server_thread_count = _server_process.num_threads()
                if hasattr(_server_process, "num_handles"):
                    server_handle_count = _server_process.num_handles()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            _server_process = None

    _prev_sample_time = now

    return TelemetrySample(
        campaign_id=campaign_id,
        config_id=config_id,
        timestamp=ts,
        # ABORT
        cpu_temp_c=cpu_temp_c,
        power_limit_throttling=power_limit_throttling,
        gpu_vram_used_mb=gpu_vram_used_mb,
        # WARN
        gpu_temp_c=gpu_temp_c,
        cpu_power_w=cpu_power_w,
        ram_used_gb=ram_used_gb,
        # SILENT hardware
        cpu_pcore_freq_ghz=cpu_pcore_freq_ghz,
        cpu_ecore_freq_ghz=cpu_ecore_freq_ghz,
        gpu_util_pct=gpu_util_pct,
        gpu_power_w=gpu_power_w,
        gpu_graphics_clock_mhz=gpu_graphics_clock_mhz,
        gpu_mem_clock_mhz=gpu_mem_clock_mhz,
        gpu_pstate=gpu_pstate,
        gpu_throttle_reasons=gpu_throttle_reasons,
        liquid_temp_c=liquid_temp_c,
        disk_read_mbps=disk_read_mbps,
        disk_write_mbps=disk_write_mbps,
        page_faults_sec=None,   # requires Windows PerfMon; omitted for now
        # SILENT extended
        net_sent_mbps=net_sent_mbps,
        net_recv_mbps=net_recv_mbps,
        cpu_freq_mhz=cpu_freq_mhz,
        cpu_util_pct=cpu_util_pct,
        cpu_util_per_core_json=cpu_util_per_core_json,
        ram_available_gb=ram_available_gb,
        ram_committed_gb=ram_committed_gb,
        pagefile_used_gb=pagefile_used_gb,
        context_switches_sec=context_switches_sec,
        interrupts_sec=interrupts_sec,
        server_cpu_pct=server_cpu_pct,
        server_rss_mb=_rss_mb,
        server_private_bytes_mb=_private_bytes_mb,
        server_vms_mb=server_vms_mb,
        server_thread_count=server_thread_count,
        server_handle_count=server_handle_count,
        server_pid=server_pid,
        # HWiNFO extended
        cpu_core_voltage_v=cpu_vcore,
        cpu_ia_cores_power_w=cpu_ia_power,
        gpu_hotspot_temp_c=gpu_hotspot,
        gpu_mem_temp_c=gpu_mem_temp,
        gpu_fan_rpm=gpu_fan_rpm,
        cpu_fan_rpm=cpu_fan_rpm,
    )


# ---------------------------------------------------------------------------
# Background activity snapshot
# ---------------------------------------------------------------------------

def _get_active_power_plan() -> str:
    try:
        import subprocess
        result = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True, text=True, timeout=5,
        )
        line = result.stdout.strip()
        if "(" in line and ")" in line:
            return line.split("(")[1].rstrip(")")
        return line
    except Exception:
        return ""


def collect_background_snapshot(
    campaign_id: str,
    config_id: str,
) -> BackgroundSnapshot:
    """
    Collect a background activity snapshot. Records what other processes
    are doing on the machine during inference — essential for interference audit.
    """
    ts = datetime.now(timezone.utc).isoformat()

    windows_defender_active = False
    windows_update_active = False
    search_indexer_active = False
    antivirus_scan_active = False
    proc_data: list[dict] = []

    try:
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_info", "io_counters"]
        ):
            try:
                info = proc.info
                name = info.get("name", "") or ""
                cpu = info.get("cpu_percent") or 0.0
                mem_info = info.get("memory_info")
                rss_mb = mem_info.rss / (1024 * 1024) if mem_info else 0.0
                pid = info.get("pid", 0)
                name_lower = name.lower()

                if "msmpeng" in name_lower or "mpcmdrun" in name_lower:
                    windows_defender_active = True
                    if cpu > 0.5:
                        antivirus_scan_active = True
                elif "tiworker" in name_lower or "wuauclt" in name_lower:
                    windows_update_active = True
                elif "searchindexer" in name_lower or "searchhost" in name_lower:
                    search_indexer_active = True

                if cpu > 0.5 or rss_mb > 100:
                    io = info.get("io_counters")
                    proc_data.append({
                        "name": name,
                        "pid": pid,
                        "cpu_pct": round(cpu, 2),
                        "rss_mb": round(rss_mb, 1),
                        "read_mb": round(io.read_bytes / (1024 * 1024), 2) if io else 0,
                        "write_mb": round(io.write_bytes / (1024 * 1024), 2) if io else 0,
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as exc:
        logger.debug("Process list collection error: %s", exc)

    by_cpu  = sorted(proc_data, key=lambda x: x["cpu_pct"], reverse=True)
    by_ram  = sorted(proc_data, key=lambda x: x["rss_mb"], reverse=True)
    by_disk = sorted(proc_data, key=lambda x: x["read_mb"] + x["write_mb"], reverse=True)
    high_cpu_count = sum(1 for p in proc_data if p["cpu_pct"] > 1.0)

    total_conns = established_conns = 0
    try:
        conns = psutil.net_connections()
        total_conns = len(conns)
        established_conns = sum(1 for c in conns if c.status == "ESTABLISHED")
    except Exception:
        pass

    return BackgroundSnapshot(
        campaign_id=campaign_id,
        config_id=config_id,
        timestamp=ts,
        top_cpu_procs_json=json.dumps(by_cpu[:10]),
        top_ram_procs_json=json.dumps(by_ram[:10]),
        top_disk_procs_json=json.dumps(by_disk[:10]),
        all_notable_procs_json=json.dumps(proc_data),
        windows_defender_active=windows_defender_active,
        windows_update_active=windows_update_active,
        search_indexer_active=search_indexer_active,
        antivirus_scan_active=antivirus_scan_active,
        network_active_connections=total_conns,
        network_established_connections=established_conns,
        power_plan=_get_active_power_plan(),
        high_cpu_process_count=high_cpu_count,
    )


# ---------------------------------------------------------------------------
# TelemetryCollector — background thread
# ---------------------------------------------------------------------------

class TelemetryCollector:
    """
    Background thread collecting telemetry every 2 seconds and process
    snapshots every 10 seconds. Writes to telemetry.jsonl and lab.sqlite.

    Usage:
        collector = TelemetryCollector(db_path, telemetry_jsonl_path)
        collector.start(campaign_id, config_id, server_pid=pid)
        # ... run measurements ...
        samples, snapshots = collector.stop()
    """

    SAMPLE_INTERVAL_S: float = 2.0
    SNAPSHOT_INTERVAL_S: float = 10.0

    def __init__(self, db_path: Path, telemetry_jsonl_path: Path) -> None:
        self._db_path = db_path
        self._jsonl_path = telemetry_jsonl_path
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._samples: list[TelemetrySample] = []
        self._snapshots: list[BackgroundSnapshot] = []
        self._lock = threading.Lock()
        self._campaign_id: str = ""
        self._config_id: str = ""
        self._server_pid: int | None = None

    def start(
        self,
        campaign_id: str,
        config_id: str,
        server_pid: int | None = None,
    ) -> None:
        if self._thread is not None and self._thread.is_alive():
            self.stop()

        self._campaign_id = campaign_id
        self._config_id = config_id
        self._server_pid = server_pid
        self._stop_event.clear()

        with self._lock:
            self._samples = []
            self._snapshots = []

        # Reset delta counters for a fresh collection window
        global _prev_disk_counters, _prev_net_counters, _prev_sample_time, _prev_cpu_stats
        _prev_disk_counters = None
        _prev_net_counters = None
        _prev_sample_time = 0.0
        _prev_cpu_stats = None

        self._thread = threading.Thread(
            target=self._run,
            name="TelemetryCollector",
            daemon=True,
        )
        self._thread.start()
        logger.debug(
            "TelemetryCollector started for %s/%s (server_pid=%s)",
            campaign_id, config_id, server_pid,
        )

    def update_server_pid(self, pid: int) -> None:
        """Update tracked server PID (e.g. after --no-warmup retry)."""
        self._server_pid = pid

    def stop(self) -> tuple[list[TelemetrySample], list[BackgroundSnapshot]]:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                logger.warning("TelemetryCollector thread did not stop within 15s")
        self._thread = None

        with self._lock:
            samples = list(self._samples)
            snapshots = list(self._snapshots)

        logger.debug(
            "TelemetryCollector stopped: %d samples, %d snapshots",
            len(samples), len(snapshots),
        )
        return samples, snapshots

    def _run(self) -> None:
        last_snapshot_time = 0.0

        while not self._stop_event.is_set():
            loop_start = time.monotonic()

            try:
                sample = collect_sample(
                    self._campaign_id,
                    self._config_id,
                    self._server_pid,
                )
                with self._lock:
                    self._samples.append(sample)
                self._write_sample(sample)
            except Exception as exc:
                logger.warning("Telemetry sample error: %s", exc)

            now = time.monotonic()
            if now - last_snapshot_time >= self.SNAPSHOT_INTERVAL_S:
                try:
                    snap = collect_background_snapshot(self._campaign_id, self._config_id)
                    with self._lock:
                        self._snapshots.append(snap)
                    self._write_snapshot(snap)
                    last_snapshot_time = now
                except Exception as exc:
                    logger.warning("Background snapshot error: %s", exc)

            elapsed = time.monotonic() - loop_start
            self._stop_event.wait(timeout=max(0.0, self.SAMPLE_INTERVAL_S - elapsed))

    def _write_sample(self, sample: TelemetrySample) -> None:
        row = asdict(sample)
        try:
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except Exception as exc:
            logger.warning("Failed to write telemetry JSONL: %s", exc)

        try:
            with sqlite3.connect(self._db_path) as conn:
                cols = ", ".join(row.keys())
                placeholders = ", ".join("?" for _ in row)
                conn.execute(
                    f"INSERT INTO telemetry ({cols}) VALUES ({placeholders})",
                    list(row.values()),
                )
                conn.commit()
        except Exception as exc:
            logger.debug("Failed to write telemetry SQLite: %s", exc)

    def _write_snapshot(self, snap: BackgroundSnapshot) -> None:
        row = asdict(snap)
        try:
            with sqlite3.connect(self._db_path) as conn:
                cols = ", ".join(row.keys())
                placeholders = ", ".join("?" for _ in row)
                conn.execute(
                    f"INSERT INTO background_snapshots ({cols}) VALUES ({placeholders})",
                    list(row.values()),
                )
                conn.commit()
        except Exception as exc:
            logger.debug("Failed to write background snapshot: %s", exc)


# ---------------------------------------------------------------------------
# Campaign start snapshot
# ---------------------------------------------------------------------------

def collect_campaign_start_snapshot(
    campaign_id: str,
    server_bin: Path,
    model_path: Path,
    build_commit: str,
    request_files: dict[str, Path],
    campaign_yaml_path: Path,
    baseline_yaml_path: Path,
    sampling_params: dict,
    cpu_affinity_policy: str,
) -> dict[str, Any]:
    """Collect a complete system fingerprint at campaign start (MDD §10.5)."""
    import hashlib
    import platform
    import subprocess
    import sys

    snap: dict[str, Any] = {
        "campaign_id": campaign_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    try:
        h = hashlib.sha256()
        with open(server_bin, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        snap["server_binary_sha256"] = h.hexdigest()
        snap["server_binary_path"] = str(server_bin)
    except Exception as exc:
        snap["server_binary_sha256"] = None
        logger.warning("Could not hash server binary: %s", exc)

    try:
        stat = model_path.stat()
        snap["model_file_size_bytes"] = stat.st_size
        snap["model_mtime_utc"] = datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat()
        snap["model_path"] = str(model_path)
    except Exception as exc:
        snap["model_file_size_bytes"] = None
        snap["model_mtime_utc"] = None

    snap["build_commit"] = build_commit

    prompt_hashes: dict[str, str] = {}
    for name, path in request_files.items():
        try:
            h = hashlib.sha256()
            h.update(path.read_bytes())
            prompt_hashes[name] = h.hexdigest()
        except Exception:
            prompt_hashes[name] = "ERROR"
    snap["prompt_sha256_json"] = json.dumps(prompt_hashes)
    snap["sampling_params_json"] = json.dumps(sampling_params)

    for label, path in [
        ("campaign_yaml", campaign_yaml_path),
        ("baseline_yaml", baseline_yaml_path),
    ]:
        try:
            raw = path.read_bytes()
            h = hashlib.sha256()
            h.update(raw)
            snap[f"{label}_sha256"] = h.hexdigest()
        except Exception:
            snap[f"{label}_sha256"] = None
            raw = None

        # Store verbatim YAML text for the campaign file only.
        # This makes every DB row fully self-contained: if configs/ is modified
        # or deleted after a run, the exact YAML that governed the run is still
        # recoverable from the database. (L1/U6 fix)
        if label == "campaign_yaml":
            try:
                snap["campaign_yaml_content"] = raw.decode("utf-8") if raw is not None else None
            except Exception:
                snap["campaign_yaml_content"] = None

    snap["os_version"] = platform.version()
    snap["os_platform"] = platform.platform()
    snap["python_version"] = sys.version

    try:
        snap["nvidia_driver"] = (
            pynvml.nvmlSystemGetDriverVersion() if _NVML_INITIALIZED else None
        )
    except Exception:
        snap["nvidia_driver"] = None

    try:
        snap["gpu_name"] = (
            pynvml.nvmlDeviceGetName(_NVML_HANDLE) if _NVML_INITIALIZED and _NVML_HANDLE else None
        )
    except Exception:
        snap["gpu_name"] = None

    snap["power_plan"] = _get_active_power_plan()
    snap["cpu_affinity_policy"] = cpu_affinity_policy
    snap["hwm_namespace"] = "HWiNFO64"

    try:
        disk = psutil.disk_usage(str(model_path.drive or "D:\\"))
        snap["model_disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
        snap["model_disk_free_gb"] = round(disk.free / (1024 ** 3), 1)
    except Exception:
        snap["model_disk_total_gb"] = None
        snap["model_disk_free_gb"] = None

    # Current temps at campaign start
    readings = _get_hwinfo_readings()
    snap["cpu_temp_at_start_c"] = _find_reading(readings, "CPU Package", rtype=_RTYPE_TEMP)
    try:
        snap["gpu_temp_at_start_c"] = (
            float(pynvml.nvmlDeviceGetTemperature(_NVML_HANDLE, pynvml.NVML_TEMPERATURE_GPU))
            if _NVML_INITIALIZED and _NVML_HANDLE else None
        )
    except Exception:
        snap["gpu_temp_at_start_c"] = None

    logger.info("Campaign start snapshot collected for %s", campaign_id)
    return snap


# ---------------------------------------------------------------------------
# Thermal checks + cooldown gate
# ---------------------------------------------------------------------------

def check_thermal_event(sample: TelemetrySample, cpu_throttle_temp: float = 100.0) -> bool:
    """
    Return True if this sample represents a thermal disqualification event.
    CPU >= 100°C or GPU SW power cap throttling active.
    """
    if sample.cpu_temp_c is not None and sample.cpu_temp_c >= cpu_throttle_temp:
        logger.warning(
            "THERMAL EVENT: cpu_temp_c=%.1f°C >= %.1f°C",
            sample.cpu_temp_c, cpu_throttle_temp,
        )
        return True
    if sample.power_limit_throttling is True:
        logger.warning("THERMAL EVENT: GPU power_limit_throttling (SW_POWER_CAP) active")
        return True
    return False


def is_machine_cool(target_temp_c: float = 55.0) -> bool:
    """Return True if both CPU and GPU are below target_temp_c."""
    readings = _get_hwinfo_readings()
    cpu_temp = _find_reading(readings, "CPU Package", rtype=_RTYPE_TEMP)
    gpu_temp: float | None = None
    if _NVML_INITIALIZED and _NVML_HANDLE:
        try:
            gpu_temp = float(
                pynvml.nvmlDeviceGetTemperature(_NVML_HANDLE, pynvml.NVML_TEMPERATURE_GPU)
            )
        except Exception:
            pass

    if cpu_temp is not None and cpu_temp >= target_temp_c:
        return False
    if gpu_temp is not None and gpu_temp >= target_temp_c:
        return False
    return True


def shutdown() -> None:
    """Release pynvml resources."""
    global _NVML_INITIALIZED, _NVML_HANDLE
    if _NVML_INITIALIZED:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
        _NVML_INITIALIZED = False
        _NVML_HANDLE = None
