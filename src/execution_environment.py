"""Execution environment classification for platform support tiers.

This module is intentionally small and stdlib-only. It distinguishes WSL from
native Linux so degraded WSL support cannot be mistaken for measurement-grade
Linux support.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SUPPORT_WINDOWS_NATIVE = "windows_native"
SUPPORT_WSL_DEGRADED = "wsl_degraded"
SUPPORT_LINUX_NATIVE = "linux_native"
SUPPORT_UNSUPPORTED = "unsupported"

BOUNDARY_NATIVE_PROCESS = "native_process"
BOUNDARY_WSL2_HYPERVISOR = "wsl2_hypervisor_boundary"
BOUNDARY_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExecutionEnvironment:
    execution_platform: str
    support_tier: str
    boundary_type: str
    measurement_grade: bool
    degraded_reasons: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def is_wsl_environment() -> bool:
    """Return True only when stable WSL kernel markers are present."""
    if sys.platform != "linux":
        return False
    osrelease = _read_text("/proc/sys/kernel/osrelease").lower()
    version = _read_text("/proc/version").lower()
    return "microsoft" in osrelease or "wsl" in osrelease or "microsoft" in version


def linux_cpu_thermal_interfaces_available() -> bool:
    """Return whether normal Linux CPU thermal interfaces are visible."""
    if sys.platform != "linux":
        return False

    thermal = Path("/sys/class/thermal")
    try:
        if any(thermal.glob("thermal_zone*")):
            return True
    except Exception:
        pass

    hwmon = Path("/sys/class/hwmon")
    try:
        for path in hwmon.glob("hwmon*/temp*_input"):
            if path.is_file():
                return True
    except Exception:
        pass

    return shutil.which("sensors") is not None


def classify_execution_environment() -> ExecutionEnvironment:
    """Classify the current execution environment into QuantMap support tiers."""
    platform_value = sys.platform
    evidence: dict[str, Any] = {
        "sys_platform": platform_value,
    }

    if platform_value == "win32":
        return ExecutionEnvironment(
            execution_platform="windows",
            support_tier=SUPPORT_WINDOWS_NATIVE,
            boundary_type=BOUNDARY_NATIVE_PROCESS,
            measurement_grade=True,
            evidence=evidence,
        )

    if platform_value == "linux":
        osrelease = _read_text("/proc/sys/kernel/osrelease").strip()
        proc_version = _read_text("/proc/version").strip()
        cpu_thermal = linux_cpu_thermal_interfaces_available()
        evidence.update(
            {
                "osrelease": osrelease,
                "proc_version_contains_wsl": "wsl" in proc_version.lower()
                or "microsoft" in proc_version.lower(),
                "cpu_thermal_interfaces_available": cpu_thermal,
                "nvidia_smi_available": shutil.which("nvidia-smi") is not None,
            }
        )

        if is_wsl_environment():
            reasons = [
                "wsl_hypervisor_boundary",
                "not_linux_native",
            ]
            if not cpu_thermal:
                reasons.append("missing_linux_cpu_thermal_interfaces")
            return ExecutionEnvironment(
                execution_platform="linux",
                support_tier=SUPPORT_WSL_DEGRADED,
                boundary_type=BOUNDARY_WSL2_HYPERVISOR,
                measurement_grade=False,
                degraded_reasons=reasons,
                evidence=evidence,
            )

        return ExecutionEnvironment(
            execution_platform="linux",
            support_tier=SUPPORT_LINUX_NATIVE,
            boundary_type=BOUNDARY_NATIVE_PROCESS,
            measurement_grade=cpu_thermal,
            degraded_reasons=[] if cpu_thermal else ["missing_linux_cpu_thermal_interfaces"],
            evidence=evidence,
        )

    return ExecutionEnvironment(
        execution_platform=platform_value,
        support_tier=SUPPORT_UNSUPPORTED,
        boundary_type=BOUNDARY_UNKNOWN,
        measurement_grade=False,
        degraded_reasons=["unsupported_execution_platform"],
        evidence=evidence,
    )


def execution_environment_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw = snapshot.get("execution_environment_json")
    if raw:
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, dict):
                parsed.setdefault("source", "snapshot")
                return parsed
        except Exception:
            pass
    return {
        "source": "legacy_incomplete",
        "execution_platform": snapshot.get("os_platform") or "unknown",
        "support_tier": "legacy_unrecorded",
        "boundary_type": "legacy_unrecorded",
        "measurement_grade": None,
        "degraded_reasons": [],
        "evidence": {},
    }


def execution_environment_summary_lines(snapshot: dict[str, Any]) -> list[str]:
    env = execution_environment_from_snapshot(snapshot)
    reasons = env.get("degraded_reasons") or []
    reason_text = ", ".join(str(item) for item in reasons) if reasons else "none"
    return [
        f"| Execution support tier | `{env.get('support_tier', 'unknown')}` |",
        f"| Execution boundary | `{env.get('boundary_type', 'unknown')}` |",
        f"| Measurement-grade platform | `{env.get('measurement_grade', 'unknown')}` |",
        f"| Platform degradation reasons | `{reason_text}` |",
    ]
