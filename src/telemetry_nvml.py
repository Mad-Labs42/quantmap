"""NVIDIA/NVML telemetry provider helpers."""

from __future__ import annotations

import logging
import shutil
import sys
import subprocess
import warnings
from typing import Any

from src.telemetry_provider import (
    STATUS_AVAILABLE,
    STATUS_DEGRADED,
    STATUS_FAILED,
    STATUS_MISSING,
    TelemetryProviderIdentity,
)

logger = logging.getLogger(__name__)

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        import pynvml  # type: ignore[import]
    _PYNVML_AVAILABLE = True
except ImportError:
    pynvml = None  # type: ignore[assignment]
    _PYNVML_AVAILABLE = False


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def open_nvml_handle(index: int = 0) -> Any | None:
    """Initialize NVML and return a device handle, or None when unavailable."""
    if not _PYNVML_AVAILABLE:
        return None
    try:
        pynvml.nvmlInit()
        return pynvml.nvmlDeviceGetHandleByIndex(index)
    except Exception as exc:
        logger.debug("NVML provider init failed: %s", exc)
        return None


def probe_nvml_provider(index: int = 0) -> TelemetryProviderIdentity:
    """Return a non-throwing NVML provider identity/status."""
    if not _PYNVML_AVAILABLE:
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            details: dict[str, Any] = {
                "nvidia_smi_path": nvidia_smi,
                "python_binding": "pynvml_missing",
            }
            try:
                proc = subprocess.run(
                    [
                        nvidia_smi,
                        "--query-gpu=name,driver_version",
                        "--format=csv,noheader",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    first = proc.stdout.strip().splitlines()[0]
                    parts = [part.strip() for part in first.split(",", 1)]
                    if parts:
                        details["gpu_name"] = parts[0]
                    if len(parts) > 1:
                        details["driver_version"] = parts[1]
            except Exception as exc:
                details["nvidia_smi_probe_error"] = str(exc)

            return TelemetryProviderIdentity(
                provider_id="nvml",
                provider_label="NVIDIA Management Library",
                status=STATUS_DEGRADED,
                source="nvidia-smi",
                platform=sys.platform,
                provider_version=details.get("driver_version"),
                details=details,
            )
        return TelemetryProviderIdentity(
            provider_id="nvml",
            provider_label="NVIDIA Management Library",
            status=STATUS_MISSING,
            source="pynvml",
            platform=sys.platform,
            details={"reason": "pynvml is not installed"},
        )

    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(index)
        driver = _decode(pynvml.nvmlSystemGetDriverVersion())
        name = _decode(pynvml.nvmlDeviceGetName(handle))
        return TelemetryProviderIdentity(
            provider_id="nvml",
            provider_label="NVIDIA Management Library",
            status=STATUS_AVAILABLE,
            source="pynvml",
            platform=sys.platform,
            provider_version=driver,
            details={"gpu_name": name, "device_index": index},
        )
    except Exception as exc:
        return TelemetryProviderIdentity(
            provider_id="nvml",
            provider_label="NVIDIA Management Library",
            status=STATUS_FAILED,
            source="pynvml",
            platform=sys.platform,
            details={"reason": str(exc), "device_index": index},
        )


def get_gpu_vram_total_mb(index: int = 0) -> float | None:
    """Return total VRAM in MB for the selected NVIDIA device."""
    handle = open_nvml_handle(index)
    if handle is None:
        return None
    try:
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return mem_info.total / (1024 * 1024)
    except Exception as exc:
        logger.debug("NVML total VRAM read failed: %s", exc)
        return None
