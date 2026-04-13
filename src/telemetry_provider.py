"""Provider-neutral telemetry identity and evidence helpers.

This module defines the small vocabulary shared by telemetry acquisition,
readiness policy, persistence, diagnostics, and historical readers. It does
not probe hardware and should stay free of provider-specific imports.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any


STATUS_AVAILABLE = "available"
STATUS_MISSING = "missing"
STATUS_DEGRADED = "degraded"
STATUS_UNSUPPORTED = "unsupported"
STATUS_FAILED = "failed"
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_UNKNOWN = "unknown"

QUALITY_COMPLETE = "complete"
QUALITY_DEGRADED = "degraded"
QUALITY_BLOCKED = "blocked"
QUALITY_UNSUPPORTED = "unsupported"
QUALITY_LEGACY_INCOMPLETE = "legacy_incomplete"
QUALITY_UNKNOWN = "unknown"

TIER_ABORT = "abort"
TIER_WARN = "warn"
TIER_SILENT = "silent"


@dataclass(frozen=True)
class TelemetryProviderIdentity:
    provider_id: str
    provider_label: str
    status: str
    source: str
    platform: str = field(default_factory=lambda: sys.platform)
    provider_version: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TelemetrySignalStatus:
    signal_name: str
    tier: str
    status: str
    provider_id: str | None = None
    unit: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class TelemetryProviderEvidence:
    provider_identity: list[TelemetryProviderIdentity]
    capabilities: list[TelemetrySignalStatus]
    capture_quality: str
    notes: list[str] = field(default_factory=list)

    def provider_identity_json(self) -> str:
        return json.dumps([asdict(item) for item in self.provider_identity], sort_keys=True)

    def capabilities_json(self) -> str:
        return json.dumps([asdict(item) for item in self.capabilities], sort_keys=True)


def _provider_status(available: bool, *, platform_name: str, provider_id: str) -> str:
    if available:
        return STATUS_AVAILABLE
    if provider_id == "hwinfo" and platform_name != "win32":
        return STATUS_UNSUPPORTED
    return STATUS_MISSING


def build_provider_evidence(
    *,
    hwinfo_available: bool,
    hwinfo_reading_count: int = 0,
    nvml_available: bool,
    nvml_status: str | None = None,
    platform_name: str | None = None,
    nvml_details: dict[str, Any] | None = None,
    cpu_temp_available: bool | None = None,
    gpu_vram_available: bool | None = None,
    power_limit_available: bool | None = None,
    gpu_temp_available: bool | None = None,
    support_tier: str | None = None,
    notes: list[str] | None = None,
) -> TelemetryProviderEvidence:
    """Build a run-level provider evidence summary from observed capability state."""
    platform_value = platform_name or sys.platform
    nvml_details = nvml_details or {}

    providers = [
        TelemetryProviderIdentity(
            provider_id="hwinfo",
            provider_label="HWiNFO shared memory",
            status=_provider_status(hwinfo_available, platform_name=platform_value, provider_id="hwinfo"),
            source="shared_memory",
            platform=platform_value,
            details={"reading_count": hwinfo_reading_count},
        ),
        TelemetryProviderIdentity(
            provider_id="nvml",
            provider_label="NVIDIA Management Library",
            status=nvml_status or (STATUS_AVAILABLE if nvml_available else STATUS_MISSING),
            source="pynvml",
            platform=platform_value,
            provider_version=nvml_details.get("driver_version"),
            details={k: v for k, v in nvml_details.items() if v is not None},
        ),
    ]

    capabilities = [
        TelemetrySignalStatus(
            signal_name="timestamp",
            tier=TIER_ABORT,
            status=STATUS_AVAILABLE,
            provider_id="system_clock",
        ),
        TelemetrySignalStatus(
            signal_name="cpu_temp_c",
            tier=TIER_ABORT,
            status=STATUS_AVAILABLE if cpu_temp_available else (
                STATUS_UNSUPPORTED if platform_value != "win32" and not hwinfo_available else STATUS_MISSING
            ),
            provider_id="hwinfo",
            unit="C",
            message=None if cpu_temp_available else "CPU temperature provider signal unavailable",
        ),
        TelemetrySignalStatus(
            signal_name="gpu_vram_used_mb",
            tier=TIER_ABORT,
            status=STATUS_AVAILABLE if gpu_vram_available else STATUS_MISSING,
            provider_id="nvml",
            unit="MB",
            message=None if gpu_vram_available else "NVML VRAM signal unavailable",
        ),
        TelemetrySignalStatus(
            signal_name="power_limit_throttling",
            tier=TIER_ABORT,
            status=STATUS_AVAILABLE if power_limit_available else STATUS_MISSING,
            provider_id="nvml",
            message=None if power_limit_available else "NVML throttle signal unavailable",
        ),
        TelemetrySignalStatus(
            signal_name="gpu_temp_c",
            tier=TIER_WARN,
            status=STATUS_AVAILABLE if gpu_temp_available else STATUS_MISSING,
            provider_id="hwinfo_or_nvml",
            unit="C",
        ),
    ]

    abort_gaps = []
    for item in capabilities:
        if item.tier != TIER_ABORT:
            continue
        if item.status in (STATUS_AVAILABLE, STATUS_NOT_APPLICABLE):
            continue
        if support_tier == "wsl_degraded" and item.signal_name == "cpu_temp_c":
            continue
        abort_gaps.append(item)
    warn_gaps = [
        item for item in capabilities
        if item.tier == TIER_WARN and item.status != STATUS_AVAILABLE
    ]

    if support_tier == "wsl_degraded":
        quality = QUALITY_DEGRADED
    elif abort_gaps:
        quality = QUALITY_BLOCKED
    elif warn_gaps:
        quality = QUALITY_DEGRADED
    else:
        quality = QUALITY_COMPLETE

    return TelemetryProviderEvidence(
        provider_identity=providers,
        capabilities=capabilities,
        capture_quality=quality,
        notes=notes or [],
    )


def _loads_json_list(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    try:
        parsed = json.loads(str(raw))
    except Exception:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def provider_evidence_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return persisted provider evidence with honest legacy fallback labels."""
    providers = _loads_json_list(snapshot.get("telemetry_provider_identity_json"))
    capabilities = _loads_json_list(snapshot.get("telemetry_capabilities_json"))
    quality = snapshot.get("telemetry_capture_quality")
    source = "snapshot" if providers or capabilities or quality else "legacy_incomplete"

    if source == "legacy_incomplete":
        providers = []
        if snapshot.get("hwm_namespace"):
            providers.append({
                "provider_id": "legacy_hw_monitor",
                "provider_label": str(snapshot.get("hwm_namespace")),
                "status": STATUS_UNKNOWN,
                "source": "legacy_campaign_start_snapshot",
                "platform": snapshot.get("os_platform") or snapshot.get("os_version") or STATUS_UNKNOWN,
                "details": {},
            })
        if snapshot.get("nvidia_driver") or snapshot.get("gpu_name"):
            providers.append({
                "provider_id": "legacy_nvidia_identity",
                "provider_label": "NVIDIA driver/GPU identity",
                "status": STATUS_UNKNOWN,
                "source": "legacy_campaign_start_snapshot",
                "platform": snapshot.get("os_platform") or snapshot.get("os_version") or STATUS_UNKNOWN,
                "provider_version": snapshot.get("nvidia_driver"),
                "details": {"gpu_name": snapshot.get("gpu_name")},
            })
        quality = QUALITY_LEGACY_INCOMPLETE

    return {
        "source": source,
        "provider_identity": providers,
        "capabilities": capabilities,
        "capture_quality": quality or QUALITY_UNKNOWN,
    }


def provider_evidence_label(snapshot: dict[str, Any]) -> str:
    evidence = provider_evidence_from_snapshot(snapshot)
    quality = evidence.get("capture_quality") or QUALITY_UNKNOWN
    source = evidence.get("source")
    if source == "legacy_incomplete":
        return QUALITY_LEGACY_INCOMPLETE
    return str(quality)


def provider_evidence_summary_lines(snapshot: dict[str, Any]) -> list[str]:
    """Format persisted provider evidence for markdown tables."""
    evidence = provider_evidence_from_snapshot(snapshot)
    lines = [
        f"| Telemetry evidence source | `{evidence['source']}` |",
        f"| Telemetry capture quality | `{evidence['capture_quality']}` |",
    ]
    providers = evidence.get("provider_identity") or []
    if not providers:
        lines.append("| Telemetry providers | `unknown` |")
        return lines

    provider_bits = []
    for item in providers:
        label = item.get("provider_label") or item.get("provider_id") or "unknown"
        status = item.get("status") or STATUS_UNKNOWN
        provider_bits.append(f"{label} ({status})")
    lines.append(f"| Telemetry providers | {'; '.join(provider_bits)} |")
    return lines
