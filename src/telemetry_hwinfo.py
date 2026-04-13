"""Windows/HWiNFO telemetry provider helpers."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import struct
import sys
from typing import Any

from src.telemetry_provider import (
    STATUS_AVAILABLE,
    STATUS_FAILED,
    STATUS_MISSING,
    STATUS_UNSUPPORTED,
    TelemetryProviderIdentity,
)

logger = logging.getLogger(__name__)

_FILE_MAP_READ = 0x0004
_HWINFO_SM_NAMES = ("Global\\HWiNFO_SENS_SM2", "HWiNFO_SENS_SM2")


def _kernel32() -> Any | None:
    if sys.platform != "win32":
        return None
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    try:
        k32 = windll.kernel32
        k32.OpenFileMappingW.restype = ctypes.wintypes.HANDLE
        k32.OpenFileMappingW.argtypes = [
            ctypes.wintypes.DWORD,
            ctypes.wintypes.BOOL,
            ctypes.wintypes.LPCWSTR,
        ]
        k32.MapViewOfFile.restype = ctypes.c_void_p
        k32.MapViewOfFile.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.c_size_t,
        ]
        k32.UnmapViewOfFile.restype = ctypes.wintypes.BOOL
        k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        k32.CloseHandle.restype = ctypes.wintypes.BOOL
        k32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        return k32
    except Exception as exc:
        logger.debug("HWiNFO provider kernel32 setup failed: %s", exc)
        return None


def read_hwinfo_shared_memory_bytes(
    *,
    header_size: int,
    header_fmt: str,
    signature: int,
    max_bytes: int = 32 * 1024 * 1024,
) -> bytes | None:
    """Read HWiNFO shared-memory bytes, or return None when unavailable."""
    k32 = _kernel32()
    if k32 is None:
        return None

    h = None
    for name in _HWINFO_SM_NAMES:
        h = k32.OpenFileMappingW(_FILE_MAP_READ, False, name)
        if h:
            break
    if not h:
        return None

    try:
        addr = k32.MapViewOfFile(h, _FILE_MAP_READ, 0, 0, 0)
        if not addr:
            return None
        try:
            header_raw = ctypes.string_at(addr, header_size)
            if len(header_raw) < header_size:
                return None
            fields = struct.unpack(header_fmt, header_raw)
            if fields[0] != signature:
                logger.debug("HWiNFO signature mismatch: got 0x%08X", fields[0])
                return None
            off_sensor, sz_sensor, num_sensor = fields[4], fields[5], fields[6]
            off_reading, sz_reading, num_reading = fields[7], fields[8], fields[9]
            total_bytes = max(
                header_size,
                (off_sensor + sz_sensor * num_sensor) if num_sensor > 0 else 0,
                (off_reading + sz_reading * num_reading) if num_reading > 0 else 0,
            )
            if total_bytes <= 0 or total_bytes > max_bytes:
                return None
            return ctypes.string_at(addr, total_bytes)
        finally:
            k32.UnmapViewOfFile(ctypes.c_void_p(addr))
    finally:
        k32.CloseHandle(h)


def probe_hwinfo_provider() -> TelemetryProviderIdentity:
    """Return a non-throwing HWiNFO provider identity/status."""
    if sys.platform != "win32":
        return TelemetryProviderIdentity(
            provider_id="hwinfo",
            provider_label="HWiNFO shared memory",
            status=STATUS_UNSUPPORTED,
            source="shared_memory",
            platform=sys.platform,
            details={"reason": "HWiNFO is Windows-only"},
        )

    k32 = _kernel32()
    if k32 is None:
        return TelemetryProviderIdentity(
            provider_id="hwinfo",
            provider_label="HWiNFO shared memory",
            status=STATUS_FAILED,
            source="shared_memory",
            platform=sys.platform,
            details={"reason": "Windows shared-memory API unavailable"},
        )

    for name in _HWINFO_SM_NAMES:
        h = k32.OpenFileMappingW(_FILE_MAP_READ, False, name)
        if h:
            k32.CloseHandle(h)
            return TelemetryProviderIdentity(
                provider_id="hwinfo",
                provider_label="HWiNFO shared memory",
                status=STATUS_AVAILABLE,
                source="shared_memory",
                platform=sys.platform,
                details={"namespace": name},
            )

    return TelemetryProviderIdentity(
        provider_id="hwinfo",
        provider_label="HWiNFO shared memory",
        status=STATUS_MISSING,
        source="shared_memory",
        platform=sys.platform,
        details={"reason": "HWiNFO shared memory not found"},
    )
