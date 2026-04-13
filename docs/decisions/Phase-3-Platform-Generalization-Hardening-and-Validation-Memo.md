# Phase 3 Platform Generalization Hardening and Validation Memo

Status: hardening and validation pass complete  
Date: 2026-04-13  
Scope: Phase 3 provider-boundary hardening after implementation pass 1

## 1. Opening Assessment

The initial Phase 3 provider-boundary pass proved that QuantMap can introduce a provider-neutral telemetry seam without turning it into a plugin framework or backend abstraction. It added provider identity/evidence vocabulary, HWiNFO/NVML helper modules, a readiness policy seam, run-level provider evidence fields, and persisted-evidence reader surfaces.

What remains weak:

- Real Linux/NVIDIA target validation has not been run.
- Linux/NVIDIA CPU thermal safety semantics remain unresolved.
- `src.telemetry.py` still contains substantial HWiNFO/NVML acquisition logic for live sample collection.
- Windows HWiNFO-present behavior could not be validated because HWiNFO shared memory is not available on this machine.

What is Windows-only but acceptable for now:

- Current Windows/HWiNFO fail-loud safety behavior remains preserved.
- Existing Windows Defender/Search diagnostics remain Windows-specific and are not part of provider generalization.
- `src.server.py` remains llama-server/CUDA/MKL-shaped; backend abstraction is still later work.

What is Linux/NVIDIA-target-critical:

- Real Linux module import and provider readiness validation.
- NVML behavior on a Linux/NVIDIA host.
- CPU thermal policy decision before measurement-grade support.
- Provider evidence persistence from a Linux-generated run.

God-object pressure:

- `src.telemetry.py` remains the highest provider-acquisition concentration risk.
- `src.runner.py` now consumes a policy seam and should not regain direct provider branching.
- `src.report_campaign.py` consumes provider summary lines and should not grow provider aggregation logic.

## 2. Hardening Changes Made

- Tightened `src.telemetry_policy.probe_provider_readiness()` so HWiNFO unsupported on non-Windows does not produce a misleading "warnings only" readiness result. It is now blocked for current-run readiness until Linux/NVIDIA CPU thermal safety policy is approved.
- Revalidated that current-run readiness remains fail-loud through `src.telemetry_policy.enforce_current_run_readiness()`.
- Revalidated that explicit-DB historical readers/export operate without live provider probing for historical truth.

No broad refactor was performed.

## 3. Windows Hardening Results

### HWiNFO Present vs Missing

HWiNFO present could not be validated because HWiNFO shared memory was not available in the current environment.

HWiNFO missing was validated:

- `quantmap doctor` reports `Telemetry Providers` blocked.
- The message states HWiNFO shared memory is unavailable for Windows current-run CPU thermal safety.
- Historical readers remain described as governed by persisted provider evidence when available.

Status: partially passed.

### NVML Present vs Missing

NVML present was validated:

- Provider readiness reports `NVIDIA Management Library: available`.
- NVML provider identity can read the local NVIDIA driver/GPU state.

NVML missing was validated indirectly through bounded policy simulation, not by uninstalling or breaking local NVML:

- Simulated NVML missing classifies current-run readiness as blocked.

Status: partially passed.

### Current-Run Safety Behavior

Validated:

- `enforce_current_run_readiness()` raises `TelemetryStartupError` when HWiNFO shared memory is unavailable.
- This preserves old Windows safety intent and does not silently weaken CPU thermal safety.

Status: passed.

### Historical Readers

Validated:

- `quantmap explain TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite`
- `quantmap compare C01_threads_batch__quick C01_threads_batch__standard --db D:\Workspaces\QuantMap\db\lab.sqlite --output tmp_phase3_compare.md --force`
- `quantmap export TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite --output tmp_phase3_export_emptyenv.qmap`
- Export manifest contains `run_telemetry_provider_evidence`.
- Explicit-DB historical explain/export still work under empty current env values.

Observed limitation:

- `quantmap audit C01_threads_batch__quick C01_threads_batch__standard --db ...` still fails because the quick campaign has no methodology snapshot. This is legacy methodology evidence behavior, not a provider-boundary regression.

Status: passed for provider-boundary trust behavior; legacy methodology limitation remains separate.

## 4. Linux/NVIDIA Target Validation

Real Linux/NVIDIA validation was not possible in this environment.

Evidence:

- `wsl uname -a` reports WSL is not installed.
- `docker --version` is unavailable.
- No Linux/NVIDIA host was available for execution.

Indirect checks performed:

- Provider readiness classification was simulated for:
  - both HWiNFO/NVML available: `ready`
  - HWiNFO missing: `blocked`
  - NVML missing: `blocked`
  - Linux-like HWiNFO unsupported with NVML available: `blocked`
- Provider evidence construction for Linux-like HWiNFO unsupported with NVML available returns `blocked` because CPU thermal evidence is unavailable.

Important limitation:

These indirect checks verify classification logic only. They are not Linux target validation and must not be used to claim Linux/NVIDIA support complete.

## 5. CPU Thermal Safety Evaluation

### Is the current implementation forced to decide Linux/NVIDIA CPU thermal policy?

No. The provider boundary can continue without deciding this. The implementation now blocks current-run readiness for Linux-like HWiNFO-unsupported state until policy is approved.

Status: verified.

### Option A: Block

If CPU package temperature is unavailable, current measurement blocks even if NVML GPU safety signals exist.

Trust implication: strongest safety posture.  
Operator UX implication: may block otherwise useful Linux exploratory runs.  
Portability implication: Linux/NVIDIA measurement support remains incomplete until CPU thermal provider evidence is available.

### Option B: Allow Only Explicitly Degraded Runs

Run may proceed only with explicit degraded-state labeling.

Trust implication: acceptable only if every downstream reader and recommendation surface treats the run as degraded.  
Operator UX implication: useful for exploratory validation.  
Portability implication: helps Linux/NVIDIA early testing without claiming parity.

### Option C: Linux-Specific Provider Policy

Define a Linux/NVIDIA provider policy with a different required-signal set.

Trust implication: potentially strong if justified by real target evidence.  
Operator UX implication: cleanest long-term behavior.  
Portability implication: best fit for platform generalization, but not justified without target validation.

Recommendation:

- Keep blocking behavior for now.
- Do not approve measurement-grade Linux/NVIDIA support until real target validation and a safety policy decision exist.
- Create the decision note to preserve the open policy explicitly.

Decision note created:

- `docs/decisions/Phase-3-Linux-NVIDIA-Safety-Decision-Note.md`

## 6. Additional Findings

| Finding | Classification | Status | Notes |
| --- | --- | --- | --- |
| Linux/NVIDIA target validation unavailable locally | Phase 3 follow-up | open | WSL and Docker are unavailable; real target host still required. |
| CPU thermal safety decision unresolved | Phase 3 blocker for measurement-grade Linux/NVIDIA support | open | Boundary work can continue, but support cannot be claimed complete. |
| HWiNFO present path not validated | Phase 3 follow-up | open | HWiNFO shared memory is unavailable on this machine. Missing path is validated. |
| `src.telemetry.py` still contains provider acquisition internals | Phase 3 follow-up | open | Initial boundary exists; continued extraction should stay surgical. |
| Current methodology blocked by missing `pydantic` | not a provider blocker | existing local setup issue | Doctor/status show this separately; explicit-DB historical readers still work. |

## 7. Hardening / Validation Findings Table

| Area | What was validated | Observed result | Status | Why it matters | Required action |
| --- | --- | --- | --- | --- | --- |
| Provider readiness policy | HWiNFO/NVML available/missing/unsupported classifications | Available => ready; missing NVML/HWiNFO => blocked; Linux-like unsupported HWiNFO => blocked | passed | Prevents misleading readiness claims | Keep policy seam central |
| Windows HWiNFO missing | `doctor`, `status`, current-run readiness | Clear blocked state | passed | Preserves CPU thermal safety | None for missing path |
| Windows HWiNFO present | Shared-memory present scenario | Not available locally | not validated | Needed before claiming Windows provider path fully hardened | Validate on machine with HWiNFO running |
| NVML present | Local provider probe | NVML available | passed | Confirms provider helper sees GPU/driver | None |
| NVML missing | Policy classification simulation | Missing NVML blocks current-run readiness | partially passed | Avoids silent GPU safety loss | Validate on machine/env without NVML |
| Current-run safety | `enforce_current_run_readiness()` under missing HWiNFO | Fails loudly with `TelemetryStartupError` | passed | Trust-preserving behavior | None |
| Historical readers | explicit-DB explain/compare/export | Readers work without live provider truth | passed | Preserves snapshot-first trust | Keep persisted-evidence path |
| Export manifest | Provider evidence metadata | `run_telemetry_provider_evidence` present | passed | Supports portable provider provenance | None |
| Empty current env | explicit-DB explain/export | Works with empty env values | passed | Preserves Phase 2.1 reader independence | None |
| Linux target import/readiness | Real Linux/NVIDIA host | No target available | not validated | Required before Linux support claim | Run target validation |
| Linux CPU thermal policy | Boundary behavior without decision | Blocks until approved | passed | Avoids silent safety weakening | Approval decision required |

## 8. Correct Phase 3 State

Recommendation: Option A.

> Phase 3 is still implementation-in-progress and needs another bounded follow-up pass.

Why:

- Provider-boundary implementation exists and is materially hardened on the Windows/missing-provider path.
- Historical trust behavior remains intact.
- Linux/NVIDIA target validation has not run.
- CPU thermal safety semantics remain unresolved.
- HWiNFO present path still needs validation on a machine with HWiNFO shared memory available.

Do not choose "provider-boundary work complete" yet because `src.telemetry.py` still retains significant provider acquisition internals and real Linux/NVIDIA validation is absent.

Do not choose "Linux/NVIDIA support complete" because there is no target evidence.

## 9. Living Docs Updated

Updated:

- `docs/system/known_issues_tracker.md`
- `docs/system/TO-DO.md`
- `docs/decisions/Current-Phase-Status-and-Roadmap-Alignment.md`

Update intent:

- Reflect that Phase 3 provider-boundary implementation is in progress and partially hardened.
- Preserve Linux/NVIDIA support as validation-pending.
- Carry the Windows/Linux hardening slice forward as bounded Phase 3 work.

## 10. Bottom Line

Phase 3 has moved from provider-boundary implementation pass 1 to a partially hardened provider-boundary implementation. It is not complete.

Honest claim now:

> QuantMap has a provider-boundary implementation in progress with Windows missing-provider behavior validated and snapshot-first historical reader behavior preserved. Linux/NVIDIA support remains validation-pending and policy-blocked until real target validation and CPU thermal safety approval.

