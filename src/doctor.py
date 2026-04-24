"""
QuantMap — doctor.py

Environment wellness checks and pre-benchmarking diagnostics.
Uses the shared 'diagnostics' readiness model.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import List

from src import ui
from src.diagnostics import CheckResult, DiagnosticReport, Readiness, Status

logger = logging.getLogger("doctor")

# ---------------------------------------------------------------------------
# Section 1: Configuration & Lab Integrity
# ---------------------------------------------------------------------------

def check_lab_structure(
    lab_root: Path | None,
    apply_fix: bool = False,
    detail: str | None = None,
) -> CheckResult:
    """Ensure essential lab directories exist."""
    if lab_root is None:
        return CheckResult(
            "Lab Structure",
            Status.FAIL,
            detail or "QUANTMAP_LAB_ROOT is not set",
            "QuantMap needs a lab root for databases, logs, state, and results.",
            "Set QUANTMAP_LAB_ROOT in .env, or run 'quantmap init'."
        )

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
        from src.governance import get_builtin_registry  # noqa: PLC0415

        registry = get_builtin_registry()
        return CheckResult(
            "Metric Registry", 
            Status.PASS, 
            f"Loaded {len(registry)} metrics"
        )
    except Exception as e:
        return CheckResult(
            "Metric Registry",
            Status.FAIL,
            str(e),
            "The Registry defines what metrics QuantMap can measure. Without it, scoring is impossible.",
            "Verify configs/metrics.yaml exists and is valid YAML."
        )


def check_default_profile_load() -> CheckResult:
    """Verify the default current methodology profile can be loaded."""
    try:
        from src.governance import get_default_profile  # noqa: PLC0415

        profile = get_default_profile()
        return CheckResult(
            "Default Profile",
            Status.PASS,
            f"Loaded {profile.name} v{profile.version}"
        )
    except Exception as e:
        return CheckResult(
            "Default Profile",
            Status.FAIL,
            str(e),
            "Current-run scoring and explicit current-input rescoring require a valid Profile.",
            "Fix configs/profiles/default_throughput_v1.yaml, then run 'quantmap doctor' again."
        )

# ---------------------------------------------------------------------------
# Section 2: Runtime Dependencies
# ---------------------------------------------------------------------------

def check_server_binary(server_bin: Path | None, detail: str | None = None) -> CheckResult:
    """Verify llama-server.exe exists and is executable."""
    if server_bin is None:
        return CheckResult(
            "Inference Server",
            Status.FAIL,
            detail or "QUANTMAP_SERVER_BIN is not set",
            "QuantMap needs the inference server to perform measurements.",
            "Set QUANTMAP_SERVER_BIN in .env to the correct path."
        )

    if not server_bin.exists():
        return CheckResult(
            "Inference Server",
            Status.FAIL,
            f"Binary not found: {server_bin}",
            "QuantMap needs the inference server to perform measurements.",
            "Set QUANTMAP_SERVER_BIN in .env to the correct path."
        )

    try:
        from src.backend_execution_policy import (
            assess_backend_execution,  # noqa: PLC0415
        )

        assessment = assess_backend_execution(server_bin)
        if not assessment.allowed:
            return CheckResult(
                "Inference Server",
                Status.SKIP,
                "Backend path exists; callable check skipped by execution policy",
                "QuantMap should not probe a backend across a disallowed execution boundary.",
                assessment.remediation,
            )
    except Exception:
        pass

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


def check_backend_execution_policy(server_bin: Path | None) -> CheckResult:
    """Verify the configured backend does not cross a disallowed platform boundary."""
    if server_bin is None:
        return CheckResult(
            "Backend Execution Policy",
            Status.SKIP,
            "Backend path unavailable",
            recommendation="Set QUANTMAP_SERVER_BIN, then rerun doctor.",
        )

    try:
        from src.backend_execution_policy import (
            assess_backend_execution,  # noqa: PLC0415
        )

        assessment = assess_backend_execution(server_bin)
    except Exception as exc:
        return CheckResult(
            "Backend Execution Policy",
            Status.FAIL,
            f"Policy check failed: {exc}",
            "QuantMap must know whether the backend can run in the current execution environment.",
            "Fix backend path configuration, then rerun doctor.",
        )

    if assessment.allowed:
        return CheckResult(
            "Backend Execution Policy",
            Status.PASS,
            f"{assessment.backend_target_kind} allowed for {assessment.execution_support_tier}",
        )

    return CheckResult(
        "Backend Execution Policy",
        Status.FAIL,
        f"{assessment.reason_code}: {assessment.backend_target_kind} is not allowed for {assessment.execution_support_tier}",
        assessment.diagnostic,
        assessment.remediation,
    )


def check_model_path(model_path: Path | None, detail: str | None = None) -> CheckResult:
    """Verify the configured model shard exists."""
    if model_path is None:
        return CheckResult(
            "Model Path",
            Status.FAIL,
            detail or "QUANTMAP_MODEL_PATH is not set",
            "QuantMap needs a model shard path to perform measurements.",
            "Set QUANTMAP_MODEL_PATH in .env to the first GGUF shard."
        )

    if not model_path.exists():
        return CheckResult(
            "Model Path",
            Status.FAIL,
            f"Model shard not found: {model_path}",
            "QuantMap needs a valid model shard path to perform measurements.",
            "Set QUANTMAP_MODEL_PATH in .env to the first GGUF shard."
        )

    return CheckResult("Model Path", Status.PASS, "Model shard found")

# ---------------------------------------------------------------------------
# Section 3: System Risks (Defender, Search, etc.)
# ---------------------------------------------------------------------------

def check_defender_exclusions(server_bin: Path | None, model_path: Path | None, lab_root: Path | None) -> List[CheckResult]:
    """Warn if Windows Defender may be scanning benchmark paths."""
    results = []
    if sys.platform != "win32":
        return []
    if server_bin is None or model_path is None or lab_root is None:
        return [CheckResult(
            "Defender Exclusions",
            Status.SKIP,
            "Runtime paths unavailable",
            recommendation="Set QUANTMAP_LAB_ROOT, QUANTMAP_SERVER_BIN, and QUANTMAP_MODEL_PATH, then rerun doctor."
        )]

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
    except Exception:  # pragma: no cover
        # Non-fatal: WSearch query failure (service absent, access denied) is
        # acceptable — the check simply reports no interference.
        pass
    return CheckResult("Windows Search", Status.PASS, "Not indexed or not interfering")

# ---------------------------------------------------------------------------
# Section 4: Telemetry (HWiNFO)
# ---------------------------------------------------------------------------

def check_hwinfo_shared_memory() -> CheckResult:
    """Check HWiNFO Shared Memory availability."""
    try:
        from src.telemetry_hwinfo import probe_hwinfo_provider  # noqa: PLC0415

        provider = probe_hwinfo_provider()
    except Exception as exc:
        return CheckResult("HWiNFO Telemetry", Status.FAIL, "Provider probe failed", str(exc))

    if provider.status == "available":
        return CheckResult("HWiNFO Telemetry", Status.PASS, "Accessible")
    if provider.status == "unsupported":
        return CheckResult("HWiNFO Telemetry", Status.SKIP, "N/A")
    if provider.status == "failed":
        return CheckResult("HWiNFO Telemetry", Status.FAIL, "Library access error")
    return CheckResult(
        "HWiNFO Telemetry",
        Status.WARN,
        "Shared Memory not found",
        "Without HWiNFO, QuantMap cannot monitor Windows current-run CPU thermals.",
        "Ensure HWiNFO is running with 'Shared Memory Support' enabled.",
    )


def check_telemetry_provider_readiness() -> CheckResult:
    """Check provider-neutral telemetry readiness for current measurement."""
    try:
        from src.telemetry_policy import probe_provider_readiness  # noqa: PLC0415

        readiness = probe_provider_readiness()
    except Exception as exc:
        return CheckResult(
            "Telemetry Providers",
            Status.FAIL,
            "Provider readiness probe failed",
            str(exc),
        )

    providers = readiness.get("providers") or []
    execution_environment = readiness.get("execution_environment") or {}
    support_tier = execution_environment.get("support_tier", "unknown")
    measurement_grade = execution_environment.get("measurement_grade", "unknown")
    provider_bits = []
    for provider in providers:
        label = provider.get("provider_label") or provider.get("provider_id") or "unknown"
        provider_status = provider.get("status") or "unknown"
        provider_bits.append(f"{label}: {provider_status}")

    detail_lines: list[str] = []
    detail_lines.extend(readiness.get("blocked") or [])
    detail_lines.extend(readiness.get("warnings") or [])
    detail_lines.append(f"Execution support tier: {support_tier}; measurement-grade: {measurement_grade}")
    detail_lines.append(
        "Historical readers remain governed by persisted provider evidence when available."
    )

    state = readiness.get("readiness")
    if state == "blocked":
        status = Status.FAIL
        message = "Current-run telemetry provider readiness is blocked"
    elif state == "degraded":
        status = Status.WARN
        message = "Telemetry provider readiness is degraded"
    elif state == "warnings":
        status = Status.WARN
        message = "Telemetry provider readiness has warnings"
    else:
        status = Status.PASS
        message = "Telemetry provider readiness is available"

    if provider_bits:
        message = f"{message}: " + "; ".join(provider_bits)
    message = f"{message} [{support_tier}]"
    return CheckResult("Telemetry Providers", status, message, "\n".join(detail_lines))

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
    server_bin: Path | None,
    model_path: Path | None,
    lab_root: Path | None,
    fix: bool = False,
    env_details: dict | None = None,
) -> bool:
    """Execute the full diagnostic suite and return success."""
    if env_details is None:
        from src.settings_env import read_env_path  # noqa: PLC0415

        env_details = {
            name: read_env_path(name)
            for name in ("QUANTMAP_LAB_ROOT", "QUANTMAP_SERVER_BIN", "QUANTMAP_MODEL_PATH")
        }
        lab_root = lab_root if lab_root is not None else env_details["QUANTMAP_LAB_ROOT"].path
        server_bin = server_bin if server_bin is not None else env_details["QUANTMAP_SERVER_BIN"].path
        model_path = model_path if model_path is not None else env_details["QUANTMAP_MODEL_PATH"].path

    report = DiagnosticReport("QuantMap Doctor — Environment Diagnostics")
    
    # 1. Struct/Configs
    report.add(
        check_lab_structure(
            lab_root,
            apply_fix=fix,
            detail=env_details["QUANTMAP_LAB_ROOT"].message,
        )
    )
    report.add(check_registry_load())
    report.add(check_default_profile_load())
    
    # 2. Runtime
    report.add(check_server_binary(server_bin, detail=env_details["QUANTMAP_SERVER_BIN"].message))
    report.add(check_backend_execution_policy(server_bin))
    report.add(check_model_path(model_path, detail=env_details["QUANTMAP_MODEL_PATH"].message))
    
    # 3. System
    for r in check_defender_exclusions(server_bin, model_path, lab_root):
        report.add(r)
    report.add(check_windows_search())
    
    # 4. Telemetry
    report.add(check_telemetry_provider_readiness())
    
    # 5. UI
    report.add(check_ui_health())
    
    # Print results
    report.print_summary()
    next_actions = ["quantmap run --campaign <ID> --validate", "quantmap status"]
    if report.readiness != Readiness.READY:
        next_actions.insert(0, "quantmap doctor")
    ui.print_next_actions(next_actions)
    
    return report.readiness != Readiness.BLOCKED # Strictly, any FAIL makes it not successful

if __name__ == "__main__":
    from src.settings_env import read_env_path

    _details = {
        name: read_env_path(name)
        for name in ("QUANTMAP_LAB_ROOT", "QUANTMAP_SERVER_BIN", "QUANTMAP_MODEL_PATH")
    }
    run_doctor(
        _details["QUANTMAP_SERVER_BIN"].path,
        _details["QUANTMAP_MODEL_PATH"].path,
        _details["QUANTMAP_LAB_ROOT"].path,
        env_details=_details,
    )
