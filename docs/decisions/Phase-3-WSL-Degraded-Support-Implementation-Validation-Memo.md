# Phase 3 WSL Degraded Support Implementation Validation Memo

Status: implementation validation  
Date: 2026-04-13  
Scope: bounded WSL degraded support pass

## 1. What Changed

This pass added explicit WSL degraded support without claiming native Linux support.

Code changes:

- Added `src/execution_environment.py`, a stdlib-only execution environment classifier.
- Added persisted execution environment evidence to run-start snapshots through `execution_environment_json`.
- Updated schema to version 12.
- Updated provider evidence construction so `wsl_degraded` runs are degraded rather than blocked solely because CPU thermals are unavailable.
- Updated provider readiness policy:
  - Windows-native behavior remains fail-loud for missing HWiNFO/NVML safety requirements.
  - WSL is detected explicitly and reported as `wsl_degraded`.
  - WSL readiness is `degraded`, not `ready`, and measurement-grade is false.
  - Native Linux remains separate from WSL.
- Updated NVML provider probing to represent `nvidia-smi` GPU visibility when Python `pynvml` is missing.
- Added execution environment evidence to:
  - trust identity
  - report metadata tables
  - compare deltas
  - export manifest/completeness
  - status/doctor output

## 2. Files Changed

Code:

- `quantmap.py`
- `src/compare.py`
- `src/db.py`
- `src/doctor.py`
- `src/execution_environment.py`
- `src/export.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/telemetry.py`
- `src/telemetry_nvml.py`
- `src/telemetry_policy.py`
- `src/telemetry_provider.py`
- `src/trust_identity.py`

Docs:

- `docs/decisions/Current-Phase-Status-and-Roadmap-Alignment.md`
- `docs/decisions/Phase-3-WSL-Degraded-Support-Decision-Memo.md`
- `docs/decisions/Phase-3-WSL-Degraded-Support-Implementation-Validation-Memo.md`
- `docs/system/known_issues_tracker.md`
- `docs/system/TO-DO.md`

## 3. Windows Validation

Validated:

- `python quantmap.py status`
- `python quantmap.py doctor`
- provider readiness reports `windows_native`
- measurement-grade is true when Windows provider readiness is available
- current-run readiness reports `complete` provider evidence on the current Windows host
- Windows HWiNFO/NVML safety behavior was not weakened

Observed local non-provider blocker:

- current methodology remains blocked by missing `pydantic` in the active Windows Python environment. This is separate from provider readiness.

## 4. WSL Validation

Validated from the real WSL Ubuntu distro:

- `wsl -l -v` lists Ubuntu running on WSL 2.
- kernel marker: `microsoft-standard-WSL2`.
- `src.execution_environment.classify_execution_environment()` returns:
  - `execution_platform = linux`
  - `support_tier = wsl_degraded`
  - `boundary_type = wsl2_hypervisor_boundary`
  - `measurement_grade = false`
  - degraded reasons include:
    - `wsl_hypervisor_boundary`
    - `not_linux_native`
    - `missing_linux_cpu_thermal_interfaces`
- `src.telemetry_nvml.probe_nvml_provider()` sees NVIDIA visibility through `nvidia-smi`:
  - RTX 3090
  - driver 591.86
  - status `degraded` when Python `pynvml` is missing
- `src.telemetry_policy.probe_provider_readiness()` returns `degraded` in WSL, not blocked and not ready.
- A bounded startup-policy simulation with WSL degraded classification, missing HWiNFO readings, and unavailable Python NVML returns:
  - support tier `wsl_degraded`
  - provider evidence quality `degraded`
  - `cpu_temp_c = false`
  - no `TelemetryStartupError`

Target evidence also validated:

- `docker run --rm hello-world` succeeds inside Ubuntu.
- `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi --query-gpu=name,driver_version --format=csv,noheader` reports the RTX 3090 and driver.
- direct Ubuntu `nvidia-smi --query-gpu=name,driver_version --format=csv,noheader` reports the RTX 3090 and driver.
- `/sys/class/thermal` has no `thermal_zone*`.
- `/sys/class/hwmon` has no `temp*_input`.

Not fully validated:

- A full QuantMap current run inside WSL was not executed because the WSL Python environment is missing project Python dependencies such as `psutil`.
- This does not change the provider-support decision: the provider/readiness layer now classifies WSL correctly and the startup policy simulation demotes WSL to degraded rather than blocking on CPU thermal absence, but WSL runtime dependency setup remains required before full in-WSL campaign execution.

## 5. Historical Reader Validation

Validated from Windows with current env values blanked:

- explicit-DB `explain` works
- explicit-DB `compare` works
- explicit-DB `export` works
- export manifest includes:
  - `run_execution_environment`
  - `run_telemetry_provider_evidence`
  - `provenance_completeness`

This preserves snapshot-first historical behavior.

## 6. Honest Claims Now Allowed

Allowed:

> QuantMap now has explicit WSL 2 degraded support semantics: WSL is detected as `wsl_degraded`, measurement-grade is false, missing Linux CPU thermal interfaces are persisted as degradation evidence, and downstream trust surfaces can carry that truth.

Not allowed:

- Linux/NVIDIA support complete
- measurement-grade Linux support
- native Linux parity
- WSL treated as `linux_native`

## 7. Remaining Work

- Install/verify the WSL Python dependency environment before a full in-WSL QuantMap campaign run.
- Keep `linux_native` reserved for a later bare-metal Linux compatibility phase.
- If full in-WSL campaign execution is pursued, validate that WSL degraded evidence is persisted by a real run and visible in generated reports.
- Do not implement a Windows-host telemetry bridge unless separately approved.
