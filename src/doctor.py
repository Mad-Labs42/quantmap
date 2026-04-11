"""
QuantMap — doctor.py

Environment wellness checks and pre-benchmarking diagnostics.
Uses the shared 'diagnostics' readiness model.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import logging
import struct
import subprocess
import sys
import os
from pathlib import Path
from typing import List

from src import ui
from src.diagnostics import Status, CheckResult, DiagnosticReport

logger = logging.getLogger("doctor")

# ---------------------------------------------------------------------------
# Section 1: Configuration & Lab Integrity
# ---------------------------------------------------------------------------

def check_lab_structure(lab_root: Path, apply_fix: bool = False) -> CheckResult:
    """Ensure essential lab directories exist."""
    required_dirs = ["results", "logs", "db", "state"]
    missing = []
    created = []
    
    for d in required_dirs:
        p = lab_root / d
        if not p.is_dir():
            if apply_fix:
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    created.append(d)
                except Exception as e:
                    missing.append(f"{d} (fix failed: {e})")
            else:
                missing.append(d)
                
    if not missing:
        msg = "All lab directories present"
        if created:
            msg += f" (created: {', '.join(created)})"
        return CheckResult("Lab Structure", Status.PASS, msg)
    
    return CheckResult(
        "Lab Structure",
        Status.FAIL,
        f"Missing directories: {', '.join(missing)}",
        "QuantMap requires these folders to store campaign data and logs.",
        "Run 'quantmap doctor --fix' to create them automatically.",
        is_fixable=True
    )

def check_registry_load() -> CheckResult:
    """Verify metrics registry can be loaded."""
    try:
        from src.governance import BUILTIN_REGISTRY
        return CheckResult(
            "Metric Registry", 
            Status.PASS, 
            f"Loaded {len(BUILTIN_REGISTRY)} metrics"
        )
    except Exception as e:
        return CheckResult(
            "Metric Registry",
            Status.FAIL,
            str(e),
            "The Registry defines what metrics QuantMap can measure. Without it, scoring is impossible.",
            "Verify configs/metrics.yaml exists and is valid YAML."
        )

# ---------------------------------------------------------------------------
# Section 2: Runtime Dependencies
# ---------------------------------------------------------------------------

def check_server_binary(server_bin: Path) -> CheckResult:
    """Verify llama-server.exe exists and is executable."""
    if not server_bin.exists():
        return CheckResult(
            "Inference Server",
            Status.FAIL,
            f"Binary not found: {server_bin}",
            "QuantMap needs the inference server to perform measurements.",
            "Set QUANTMAP_SERVER_BIN in .env to the correct path."
        )
    
    try:
        # Quick check if it runs
        subprocess.run([str(server_bin), "--help"], capture_output=True, timeout=5)
        return CheckResult("Inference Server", Status.PASS, "Binary found and callable")
    except Exception as e:
        return CheckResult(
            "Inference Server",
            Status.WARN,
            f"Found but failed to execute: {e}",
            "The binary exists but may have permission issues or missing DLLs.",
            f"Try running '{server_bin} --help' manually."
        )

# ---------------------------------------------------------------------------
# Section 3: System Risks (Defender, Search, etc.)
# ---------------------------------------------------------------------------

def check_defender_exclusions(server_bin: Path, model_path: Path, lab_root: Path) -> List[CheckResult]:
    """Warn if Windows Defender may be scanning benchmark paths."""
    results = []
    if sys.platform != "win32":
        return []

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-MpPreference | Select-Object ExclusionPath, ExclusionProcess, DisableRealtimeMonitoring | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=15
        )
        if res.returncode != 0:
            return [CheckResult("Defender", Status.SKIP, "Could not query Defender (PowerShell error)")]

        data = json.loads(res.stdout.strip()) if res.stdout.strip() else {}
        
        # 1. Real-time protection
        if not data.get("DisableRealtimeMonitoring", False):
            results.append(CheckResult(
                "Defender Real-time",
                Status.WARN,
                "Enabled",
                "Defender can cause 'jitter' in high-frequency measurement cycles.",
                "For clinical-grade benchmarks, consider disabling or using strict path exclusions."
            ))

        # 2. Path exclusions
        excl_raw = data.get("ExclusionPath", [])
        exclusions = [str(e).rstrip("\\/ ").lower() for e in ([excl_raw] if isinstance(excl_raw, str) else list(excl_raw or []))]
        
        paths = [
            ("Binary", server_bin.parent),
            ("Models", model_path.parent),
            ("Lab", lab_root)
        ]
        missing = []
        for label, p in paths:
            p_lower = str(p).rstrip("\\/ ").lower()
            if not any(p_lower.startswith(e) or e.startswith(p_lower) for e in exclusions):
                missing.append(label)
        
        if missing:
            results.append(CheckResult(
                "Defender Exclusions",
                Status.WARN,
                f"Missing exclusions for: {', '.join(missing)}",
                "Scanning benchmark results or model files during execution can throttle I/O performance.",
                "Add these paths to Windows Defender exclusions list."
            ))
        else:
            results.append(CheckResult("Defender Exclusions", Status.PASS, "Paths excluded correctly"))

    except Exception as e:
        results.append(CheckResult("Defender", Status.SKIP, f"Defender check failed: {e}"))
        
    return results

def check_windows_search() -> CheckResult:
    """Check if Indexer is active."""
    if sys.platform != "win32":
        return CheckResult("Windows Search", Status.SKIP, "N/A")

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Service WSearch | Select-Object Status | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=10
        )
        if res.returncode == 0 and "Running" in res.stdout:
            return CheckResult(
                "Windows Search",
                Status.WARN,
                "Running",
                "Indexer spikes can cause outlier 'cold' TTFT values.",
                "Consider pausing Windows Search (WSearch service) during long campaigns."
            )
    except:
        pass
    return CheckResult("Windows Search", Status.PASS, "Not indexed or not interfering")

# ---------------------------------------------------------------------------
# Section 4: Telemetry (HWiNFO)
# ---------------------------------------------------------------------------

def check_hwinfo_shared_memory() -> CheckResult:
    """Check HWiNFO Shared Memory availability."""
    if sys.platform != "win32":
        return CheckResult("HWiNFO Telemetry", Status.SKIP, "N/A")

    try:
        k32 = ctypes.windll.kernel32
        h = k32.OpenFileMappingW(0x0004, False, "Global\\HWiNFO_SENS_SM2")
        if not h:
            h = k32.OpenFileMappingW(0x0004, False, "HWiNFO_SENS_SM2")
            
        if not h:
            return CheckResult(
                "HWiNFO Telemetry",
                Status.WARN,
                "Shared Memory not found",
                "Without HWiNFO, QuantMap cannot monitor thermals or power draw.",
                "Ensure HWiNFO is running with 'Shared Memory Support' enabled."
            )
        
        k32.CloseHandle(h)
        return CheckResult("HWiNFO Telemetry", Status.PASS, "Accessible")
    except:
        return CheckResult("HWiNFO Telemetry", Status.FAIL, "Library access error")

# ---------------------------------------------------------------------------
# Section 5: Terminal & UI
# ---------------------------------------------------------------------------

def check_ui_health() -> CheckResult:
    """Verify terminal capabilities."""
    utf8 = sys.stdout.encoding.lower() == 'utf-8'
    return CheckResult(
        "Terminal Encoding",
        Status.PASS if utf8 else Status.WARN,
        f"Encoding: {utf8}",
        "Non-UTF8 terminals may display broken symbols or truncated lines.",
        "On Windows, use 'chcp 65001' or a modern terminal like Windows Terminal."
    )

# ---------------------------------------------------------------------------
# High-level Entrypoint
# ---------------------------------------------------------------------------

def run_doctor(
    server_bin: Path,
    model_path: Path,
    lab_root: Path,
    fix: bool = False
) -> bool:
    """Execute the full diagnostic suite and return success."""
    report = DiagnosticReport("QuantMap Doctor — Environment Diagnostics")
    
    # 1. Struct/Configs
    report.add(check_lab_structure(lab_root, apply_fix=fix))
    report.add(check_registry_load())
    
    # 2. Runtime
    report.add(check_server_binary(server_bin))
    
    # 3. System
    for r in check_defender_exclusions(server_bin, model_path, lab_root):
        report.add(r)
    report.add(check_windows_search())
    
    # 4. Telemetry
    report.add(check_hwinfo_shared_memory())
    
    # 5. UI
    report.add(check_ui_health())
    
    # Print results
    report.print_summary()
    
    return report.readiness != Status.FAIL # Strictly, any FAIL makes it not successful

if __name__ == "__main__":
    from src.config import LAB_ROOT
    from src.server import SERVER_BIN, MODEL_PATH
    run_doctor(SERVER_BIN, MODEL_PATH, LAB_ROOT)
