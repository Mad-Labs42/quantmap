"""Telemetry provider readiness policy.

This module is the narrow policy seam used by runner, doctor, and status.
Provider helpers probe capability; this module classifies readiness.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.execution_environment import (
    SUPPORT_LINUX_NATIVE,
    SUPPORT_WINDOWS_NATIVE,
    SUPPORT_WSL_DEGRADED,
    classify_execution_environment,
)
from src.telemetry_provider import (
    STATUS_AVAILABLE,
    STATUS_FAILED,
    STATUS_MISSING,
    STATUS_UNSUPPORTED,
)


def enforce_current_run_readiness() -> dict[str, Any]:
    """Run the current measurement readiness policy.

    The implementation delegates to the existing telemetry startup check for
    compatibility, but runner calls this policy seam rather than provider
    internals. Future provider policy changes should land here.
    """
    from src import telemetry

    return telemetry.startup_check()


def probe_provider_readiness() -> dict[str, Any]:
    """Return non-throwing provider readiness for doctor/status surfaces."""
    from src.telemetry_hwinfo import probe_hwinfo_provider
    from src.telemetry_nvml import probe_nvml_provider

    providers = [probe_hwinfo_provider(), probe_nvml_provider()]
    provider_dicts = [asdict(provider) for provider in providers]
    execution_environment = classify_execution_environment()
    support_tier = execution_environment.support_tier

    blocked = []
    warnings = []
    for provider in providers:
        if (
            support_tier == SUPPORT_WINDOWS_NATIVE
            and provider.provider_id == "hwinfo"
            and provider.status == STATUS_MISSING
        ):
            blocked.append("HWiNFO shared memory is unavailable for Windows current-run CPU thermal safety.")
        elif support_tier == SUPPORT_WSL_DEGRADED and provider.provider_id == "hwinfo":
            warnings.append(
                "WSL 2 is explicitly degraded: Linux CPU thermal interfaces are unavailable, "
                "so runs are not measurement-grade."
            )
        elif (
            support_tier == SUPPORT_LINUX_NATIVE
            and provider.provider_id == "hwinfo"
            and provider.status == STATUS_UNSUPPORTED
        ):
            blocked.append(
                "Native Linux current-run CPU thermal safety policy remains validation-pending."
            )
        elif provider.status == STATUS_FAILED:
            warnings.append(f"{provider.provider_label} probe failed: {provider.details.get('reason', 'unknown')}")
        elif (
            support_tier == SUPPORT_WINDOWS_NATIVE
            and provider.provider_id == "nvml"
            and provider.status != STATUS_AVAILABLE
        ):
            blocked.append("NVML is unavailable for current-run GPU VRAM/throttle safety.")
        elif support_tier == SUPPORT_WSL_DEGRADED and provider.provider_id == "nvml" and provider.status == STATUS_MISSING:
            warnings.append("WSL 2 degraded run has no available NVIDIA/NVML provider evidence.")
        elif support_tier == SUPPORT_WSL_DEGRADED and provider.provider_id == "nvml" and provider.status != STATUS_AVAILABLE:
            warnings.append("WSL 2 degraded run has NVIDIA visibility but not full Python NVML sample support.")
        elif support_tier == SUPPORT_LINUX_NATIVE and provider.provider_id == "nvml" and provider.status != STATUS_AVAILABLE:
            blocked.append("Native Linux/NVIDIA support requires NVIDIA/NVML provider validation.")

    if blocked:
        readiness = "blocked"
    elif support_tier == SUPPORT_WSL_DEGRADED:
        readiness = "degraded"
    elif warnings:
        readiness = "warnings"
    else:
        readiness = "ready"

    return {
        "readiness": readiness,
        "providers": provider_dicts,
        "execution_environment": execution_environment.to_dict(),
        "blocked": blocked,
        "warnings": warnings,
        "historical_readers": "unaffected_when_persisted_provider_evidence_exists",
    }
