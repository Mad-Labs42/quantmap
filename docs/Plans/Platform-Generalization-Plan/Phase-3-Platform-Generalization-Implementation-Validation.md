# Phase 3 Platform Generalization Implementation Validation Memo

Status: initial implementation pass validation  
Date: 2026-04-13  
Scope: Phase 3 provider-boundary implementation pass 1

## 1. What Changed

This pass implemented the first Phase 3 provider-boundary slice:

- Added a narrow provider-neutral telemetry evidence contract in `src/telemetry_provider.py`.
- Added small flat provider helpers:
  - `src/telemetry_hwinfo.py`
  - `src/telemetry_nvml.py`
- Added `src/telemetry_policy.py` as the current-run readiness/policy seam.
- Fixed the `src.run_context` import-path issue so it imports `src.characterization`.
- Reconciled the run-start snapshot writer with the fields already being passed by `src.runner`.
- Added minimal run-level provider evidence fields to `campaign_start_snapshot`:
  - `telemetry_provider_identity_json`
  - `telemetry_capabilities_json`
  - `telemetry_capture_quality`
- Routed `src.runner` through the readiness policy seam instead of calling telemetry startup policy directly.
- Replaced direct runner NVML VRAM-total probing with the NVML provider helper.
- Routed doctor/status telemetry readiness through provider-readiness summaries.
- Added snapshot-first provider evidence loading to `src.trust_identity`.
- Added persisted provider evidence display/export alignment in:
  - `src.report_campaign`
  - `src.report`
  - `src.compare`
  - `src.export`

## 2. Files Touched

Code:

- `quantmap.py`
- `src/compare.py`
- `src/db.py`
- `src/doctor.py`
- `src/export.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/run_context.py`
- `src/runner.py`
- `src/telemetry.py`
- `src/trust_identity.py`
- `src/telemetry_provider.py`
- `src/telemetry_hwinfo.py`
- `src/telemetry_nvml.py`
- `src/telemetry_policy.py`

Living docs:

- `docs/decisions/Current-Phase-Status-and-Roadmap-Alignment.md`
- `docs/system/known_issues_tracker.md`
- `docs/system/TO-DO.md`

New validation artifact:

- `docs/decisions/Phase-3-Platform-Generalization-Implementation-Validation-Memo.md`

## 3. Validation Run

### Import and Compile Checks

Passed:

- Imported:
  - `src.telemetry_provider`
  - `src.telemetry_hwinfo`
  - `src.telemetry_nvml`
  - `src.telemetry_policy`
  - `src.run_context`
  - `src.telemetry`
  - `src.doctor`
  - `src.trust_identity`
- Ran `python -m py_compile` over the touched code modules.

### Schema and Snapshot Checks

Passed:

- Fresh schema initialization created schema version 11.
- New provider evidence columns exist on `campaign_start_snapshot`.
- Existing `gpu_vram_total_mb` migration column is present on a fresh initialized DB.
- A synthetic campaign start snapshot accepted and persisted:
  - provider evidence JSON
  - telemetry capture quality
  - baseline YAML content
  - QuantMap identity JSON
  - run-plan JSON

Note: a temporary DB cleanup attempt hit a Windows file-lock warning after one schema probe. The schema check itself completed and was rerun successfully in a repo-local temp directory that was cleaned up.

### CLI / Operator Checks

Passed:

- `python quantmap.py --help`
- `python quantmap.py status`
- `python quantmap.py doctor`

Observed current-machine state:

- NVML is available.
- HWiNFO shared memory is missing.
- Current-run telemetry provider readiness is therefore blocked, as expected.
- Historical trust messaging remains separate from current-run readiness.

### Historical Reader Checks

Passed:

- `python quantmap.py explain TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite`
- `python quantmap.py compare C01_threads_batch__quick C01_threads_batch__standard --db D:\Workspaces\QuantMap\db\lab.sqlite --output tmp_phase3_compare.md --force`
- `python quantmap.py export TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite --output tmp_phase3_export.qmap`
- Export manifest contains `run_telemetry_provider_evidence`.
- Export manifest contains updated `provenance_completeness`.

Expected limitation:

- `quantmap audit C01_threads_batch__quick C01_threads_batch__standard --db ...` failed because `C01_threads_batch__quick` has no methodology snapshot. This is legacy data behavior, not a provider-boundary regression.

### Current-Run Safety Check

Passed:

- `src.telemetry_policy.enforce_current_run_readiness()` fails loudly with `TelemetryStartupError` when HWiNFO shared memory is unavailable.
- This preserves current Windows CPU thermal safety behavior and does not silently weaken safety claims.

### Platform Hardening Checks

Partial:

- Windows current-machine readiness was checked.
- HWiNFO missing state is surfaced as a current-run blocker.
- NVML available state is surfaced as provider evidence.
- Historical readers remain usable with explicit DB paths.

Not complete:

- Real Linux/NVIDIA target validation was not run in this environment.
- A synthetic `sys.platform = "linux"` import simulation is not reliable on this Windows host because dependency behavior changes under platform monkeypatching. Do not treat that as Linux validation.

## 4. Phase 3 Decisions Exercised

Exercised:

- Provider boundary before provider variety.
- Minimal JSON fields on the existing run-start authority surface.
- Small flat provider helper modules rather than a plugin framework.
- Historical readers use persisted provider evidence, not live probing.
- Current Windows/HWiNFO safety remains fail-loud when HWiNFO is unavailable.
- Doctor/status consume provider readiness summaries instead of directly making HWiNFO the only readiness authority.

Not exercised fully:

- Real Linux/NVIDIA target validation.
- Final Linux/NVIDIA CPU thermal safety semantics.
- Complete extraction of every HWiNFO acquisition detail from `src.telemetry.py`.

## 5. Remaining Open Work

- Complete the planned Windows/Linux stability and hardening slice.
- Decide Linux/NVIDIA CPU thermal safety behavior before claiming measurement-grade Linux/NVIDIA support.
- Validate on real Linux/NVIDIA hardware or mark target support as validation-pending.
- Continue HWiNFO migration so all provider acquisition is consistently behind provider helpers.
- Consider whether provider evidence summary formatting should move into a tiny shared report helper if additional report surfaces are touched.
- Monitor `src.telemetry.py` and `src.report_campaign.py` for growth during follow-up work.

## 6. Windows + Linux Hardening Status

Status: partial.

Windows:

- Current-machine provider readiness was validated.
- Missing HWiNFO blocks current measurement clearly.
- NVML availability is detected through the provider helper.
- Historical readers continue to operate through explicit DB paths.

Linux:

- Provider boundary was designed for Linux/NVIDIA pathing.
- No real Linux target validation has been run.
- Linux/NVIDIA support must remain validation-pending until target evidence exists.

## 7. Blockers / Approval Questions

No blocker surfaced for the initial provider-boundary pass.

Approval still required before full Linux/NVIDIA measurement support:

> If NVML GPU safety signals are available but CPU package temperature is unavailable on Linux/NVIDIA, should QuantMap block, allow only explicitly labeled degraded runs, or proceed under a Linux-specific provider policy?

Until that decision is approved and target validation runs, Phase 3 should be described as provider-boundary implementation in progress, not complete Linux/NVIDIA support.

