# Phase 3 WSL Backend Execution Policy Validation Memo

Status: bounded policy pass complete  
Date: 2026-04-13  
Scope: WSL degraded backend execution boundary only

## 1. Purpose

This pass makes the next WSL blocker explicit. WSL degraded telemetry/readiness is working, but real measurement execution must not silently rely on a Windows `llama-server.exe` backend launched through WSL interop.

This is not native Linux support, backend abstraction, interop support mode, or a Windows-host telemetry bridge. It is a bounded platform-policy safeguard.

## 2. Decision Implemented

When QuantMap runs under WSL:

- Windows `.exe` backends are classified as Windows-native backend targets.
- Windows-native backend execution through WSL interop is disallowed for in-WSL measurement execution.
- The run blocks before backend startup and HTTP readiness polling.
- The diagnostic distinguishes backend/platform policy from WSL degraded telemetry readiness.
- Windows-native QuantMap runs with Windows `.exe` backends remain allowed.

## 3. Code Changes

- Added `src/backend_execution_policy.py`.
- Updated `src/server.py` to assert the backend execution policy before subprocess launch.
- Updated `src/runner.py` to run the policy after run-start snapshot persistence and before config/cycle/server launch. On policy block it marks the campaign failed, skips analysis/report phases, and writes JSONL policy markers.
- Updated `src/doctor.py` to show a dedicated `Backend Execution Policy` check and skip backend callability probing when the execution boundary is already disallowed.
- Updated runner preflight output to surface backend execution policy issues before the persisted campaign abort.

## 4. Diagnostic Text

The WSL policy block emits:

```text
Backend execution blocked by WSL boundary policy.

QuantMap is running under WSL (`wsl_degraded`), but QUANTMAP_SERVER_BIN points to a Windows-native backend: /mnt/d/.store/tools/llama.cpp/build-B/bin/llama-server.exe

Windows `.exe` backend execution through WSL interop is not accepted as valid in-WSL measurement execution in this pass. The run is blocked before backend startup and HTTP readiness polling.

This is a backend/platform policy issue, not a failure of WSL degraded telemetry readiness. Use a Linux-native backend path inside WSL, or run the campaign from Windows when using a Windows backend.
```

Reason code:

```text
wsl_windows_backend_interop_disallowed
```

## 5. Validation

| Scenario | Result | Evidence |
|---|---|---|
| WSL policy classification | passed | `/mnt/d/.../llama-server.exe` and `D:/.../llama-server.exe` classify as `windows_native_executable` and are disallowed under `wsl_degraded`; `/usr/local/bin/llama-server` is allowed as a Linux-shaped target. |
| WSL doctor diagnostic | passed | `quantmap doctor` under WSL reports `Backend Execution Policy` as failed with `wsl_windows_backend_interop_disallowed` while telemetry remains `wsl_degraded`. |
| WSL campaign run with Windows `.exe` backend | passed | `quantmap run --campaign C02_n_parallel --mode quick --values 1 --cycles 1 --requests-per-cycle 1` exits non-zero and aborts before config/cycle/server launch. |
| Persisted failure evidence | passed | `campaigns.status='failed'`, `failure_reason` contains the policy reason, `analysis_status='skipped'`, `report_status='skipped'`, and raw/telemetry JSONL markers include `_backend_execution_policy_block=true`. |
| Run-start WSL degraded evidence preserved | passed | `campaign_start_snapshot.execution_environment_json` still records `support_tier=wsl_degraded`, `measurement_grade=false`, and the WSL degradation reasons. |
| No late HTTP readiness ambiguity | passed | The policy-blocked run created zero config rows and zero cycle rows; the runner log contains no backend HTTP-readiness failure. |
| Windows-native policy behavior | passed | A Windows `.exe` backend is `allowed` under `windows_native`; Windows `doctor` reports `Backend Execution Policy` as passing. |

## 6. Current Boundary

WSL degraded support now has two separate truths:

- Telemetry/readiness can proceed as explicitly degraded and non-measurement-grade.
- Measurement execution requires a Linux-native backend path inside WSL; Windows `.exe` interop is rejected until an explicit future policy approves otherwise.

This preserves trust by preventing an ambiguous late backend crash from looking like a telemetry failure or a weak native Linux claim.

## 7. Remaining Work

Still future work:

- provide or validate a Linux-native backend path inside WSL
- decide whether a future explicit WSL interop mode is ever worth supporting
- measurement-grade bare-metal `linux_native` support
- native Linux CPU thermal provider validation
- backend adapter design beyond this narrow policy check

## 8. Current-State Sentence

QuantMap now supports WSL 2 as an explicit degraded telemetry/readiness tier and rejects Windows `.exe` backend execution through WSL interop before measurement startup; real in-WSL measurement requires a Linux-native backend path, and measurement-grade bare-metal `linux_native` support remains future work.
