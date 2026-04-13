# Phase 3 Platform Generalization Interrogation

Status: pre-implementation interrogation and design-resolution artifact  
Date: 2026-04-12  
Scope: Phase 3 Platform Generalization only  
Primary center: boundary-aware telemetry/provider design, Linux/NVIDIA-first target, trust-preserving portability groundwork

## 1. Purpose

This document interrogates the real Phase 3 problem space before implementation planning. It is not an implementation pass and not a broad re-audit. Its job is to determine what QuantMap should generalize now, what should remain later work, and what boundary rules are needed so provider work does not enlarge existing high-blast-radius modules.

The central Phase 3 rule is:

> Telemetry/provider abstraction must build on the completed Phase 2.1 settings/environment boundary, not replace it and not bypass it.

The central trust rule remains:

> Do not weaken trust in the name of generalization.

The central architecture rule is:

> Do not let Phase 3 enlarge the God objects.

## 2. Evidence Base

### Grounding Documents Reviewed

| Source | Relevant evidence |
| --- | --- |
| `docs/decisions/Current-Phase-Status-and-Roadmap-Alignment.md` | Phase 3 is active; starts with telemetry/provider boundary design; provider work must not add branches directly to `runner.py`, `telemetry.py`, `doctor.py`, or report modules. |
| `docs/AUDITS/4-11/Post-Audit-Synthesis-Memo.md` | Phase 3 is Platform Generalization with telemetry provider abstraction and Linux/NVIDIA-first target support. |
| `docs/AUDITS/4-11/Responses-4-11/Audit-5-RE` | Audit 5 accepts the HWiNFO wall, Linux/NVIDIA-first target, runner responsibility fusion, and backend coupling as distinct remediation families. |
| `docs/decisions/Phase-2.1-Settings-Environment-Bridge-Interrogation.md` | Defines missing vs empty env semantics and the minimum settings/environment contract needed before provider work. |
| `docs/decisions/Phase-2.1-Settings-Environment-Bridge-Pre-Implementation-Plan.md` | Explicitly defers telemetry provider implementation to Phase 3. |
| `docs/decisions/Phase-2.1-Settings-Environment-Bridge-Implementation-Validation-Memo.md` | Confirms Phase 2.1 implemented `src/settings_env.py`, explicit-DB reader independence, and safe redaction-root semantics. |
| `docs/system/known_issues_tracker.md` | QM-018 is the active Phase 3 provider-boundary issue; QM-017 tracks runner responsibility risk; QM-019 keeps backend adapter work later. |
| `docs/system/TO-DO.md` | TODO-018 asks for telemetry provider interface boundaries; TODO-022 asks for Linux/NVIDIA-first scope; TODO-023 asks for HWiNFO migration strategy after provider boundary design. |
| `docs/system/architecture.md` | Current architecture focus is Phase 3; boundary discipline is a standing rule. |

### Code Reviewed

The inspection covered `src/telemetry.py`, `src/doctor.py`, `src/diagnostics.py`, `src/config.py`, `src/settings_env.py`, `src/server.py`, `src/runner.py`, `src/report.py`, `src/report_campaign.py`, `src/report_compare.py`, `src/compare.py`, `src/export.py`, `src/explain.py`, `src/trust_identity.py`, `src/code_identity.py`, `src/run_plan.py`, `src/run_context.py`, `src/characterization.py`, `src/score.py`, `src/db.py`, `src/governance.py`, and `quantmap.py`.

## 3. Interrogation

### A. Define What Phase 3 Actually Is

#### Question A1: What should "Platform Generalization" mean for QuantMap right now?

Answer: Platform Generalization should mean extracting the Windows/HWiNFO-shaped telemetry assumptions behind a provider-neutral boundary, preserving the current Windows path, and creating a Linux/NVIDIA-first path or staged implementation plan. It should not mean universal portability, backend abstraction, report redesign, packaging, or optimization.

Evidence:

- `docs/AUDITS/4-11/Post-Audit-Synthesis-Memo.md` names Phase 3 as Platform Generalization with telemetry provider abstraction and Linux/NVIDIA-first target support.
- `docs/decisions/Current-Phase-Status-and-Roadmap-Alignment.md` says Phase 3 starts with telemetry/provider boundary design and must not add providers directly to `runner.py`, `telemetry.py`, `doctor.py`, or report modules.
- `docs/system/known_issues_tracker.md` QM-018 lists provider-neutral telemetry policy, Windows/HWiNFO preservation, Linux/NVIDIA-capable provider path, degraded provider signals, and doctor/readiness explanation as acceptance criteria.

Status: verified.

#### Question A2: Which known problems belong in Phase 3 now?

Answer: The Phase 3-now problem set is:

- Telemetry policy is fused to Windows/HWiNFO and pynvml internals.
- Doctor/readiness surfaces are HWiNFO-specific rather than provider-aware.
- Campaign start snapshots record provider-adjacent facts as HWiNFO/NVIDIA-specific fields rather than provider identity/evidence quality.
- Runner calls telemetry startup policy and imports NVML directly, which would become worse if new providers are added there.
- Reports and comparisons show NVIDIA/HWiNFO-shaped evidence without a provider identity model.
- Run-context/characterization already has useful capability/evidence vocabulary, but is not yet integrated as the provider authority.

Evidence:

- `src/telemetry.py` has module-level `ctypes.windll` access, HWiNFO shared-memory code, `_init_nvml()`, `startup_check()`, `collect_sample()`, `TelemetryCollector`, and campaign start snapshot collection in one file.
- `src/telemetry.py` `startup_check()` enforces HWiNFO CPU temp and pynvml VRAM/throttle as ABORT-tier requirements.
- `src/doctor.py` has `check_hwinfo_shared_memory()` as the telemetry readiness check.
- `src/runner.py` imports `src.telemetry` at module load, calls `tele.startup_check()`, starts `tele.TelemetryCollector`, and imports `pynvml` directly for VRAM total capture.
- `src/db.py` `campaign_start_snapshot` has `nvidia_driver`, `gpu_name`, and `hwm_namespace`; the telemetry table has fixed HWiNFO/NVML-shaped sample columns.
- `src/run_context.py` and `src/characterization.py` contain capability states such as `supported`, `expected_unavailable`, `probe_failed`, `unsupported_on_platform`, and `not_implemented`.

Status: verified.

#### Question A3: Which tempting items are later work?

Answer: Backend adapter design, universal hardware support, cloud packaging, report consolidation, optimization/recommendation semantics, broad runner decomposition, and broad server lifecycle redesign are later work. Phase 3 may create small seams where provider work naturally touches crowded modules, but it should not absorb those larger efforts.

Evidence:

- `docs/system/known_issues_tracker.md` QM-019 keeps backend coupling planned after settings and telemetry groundwork.
- `docs/system/TO-DO.md` TODO-019 tracks runner decomposition as a future staged boundary plan after provider groundwork.
- `docs/AUDITS/4-11/Post-Audit-Synthesis-Memo.md` separates telemetry abstraction, runner decomposition, and backend modularization as distinct remediation layers.

Status: verified.

### B. Telemetry / Provider Problem Definition

#### Question B1: What is the current telemetry model?

Answer: The current model is a single fused telemetry module that performs provider acquisition, runtime safety policy, sample normalization, persistence support, startup checks, and campaign start hardware fingerprinting. It assumes HWiNFO shared memory is the primary source for CPU/environment hardware signals and pynvml is the GPU source.

Evidence:

- `src/telemetry.py` has module-level `ctypes.windll.kernel32` access around line 169.
- `src/telemetry.py` defines `TelemetrySample`, `startup_check()`, `collect_sample()`, `TelemetryCollector`, and `collect_campaign_start_snapshot()`.
- `src/telemetry.py` writes `hwm_namespace = "HWiNFO64"` in the campaign start snapshot.
- `src/db.py` telemetry schema stores ABORT/WARN/SILENT sample columns directly rather than provider-specific evidence records.

Status: verified.

#### Question B2: What assumptions make it Windows/HWiNFO-shaped?

Answer: The strongest Windows/HWiNFO assumptions are import-time Windows API access through `ctypes.windll`, embedded HWiNFO shared-memory parsing, HWiNFO CPU temperature as an ABORT-tier requirement, `hwm_namespace = "HWiNFO64"` as the only monitor identity, and a doctor readiness check named "HWiNFO Telemetry."

Evidence:

- `src/telemetry.py` uses `ctypes.windll`, `_get_hwinfo_readings()`, and HWiNFO labels inside startup and sample collection.
- `src/doctor.py` `check_hwinfo_shared_memory()` checks `Global\\HWiNFO_SENS_SM2` and `HWiNFO_SENS_SM2`.
- `src/db.py` comments `hwm_namespace TEXT -- HWiNFO64`.

Status: verified.

#### Question B3: What is provider-specific, policy-specific, report/evidence-specific, and runtime-control-specific today?

Answer:

| Category | Current location | Current behavior |
| --- | --- | --- |
| Provider-specific acquisition | `src/telemetry.py`, `src/doctor.py`, `src/characterization.py` | HWiNFO shared memory, NVML, psutil, and Windows checks are mixed into operational modules. |
| Policy-specific decisions | `src/telemetry.py startup_check()` | HWiNFO CPU temp and NVML VRAM/throttle are ABORT-tier requirements. |
| Evidence-specific persistence | `src/db.py`, `src/telemetry.py`, `src/runner.py` | Snapshot and telemetry tables store provider-shaped facts without provider identity. |
| Runtime control | `src/runner.py` | Runner invokes startup policy, collector lifecycle, and direct NVML capture. |
| Operator UX | `src/doctor.py`, `quantmap.py status` | Readiness is HWiNFO-specific, not provider-aware. |
| Report/export surface | `src/report_campaign.py`, `src/report.py`, `src/compare.py`, `src/export.py` | Readers consume existing tables but do not surface provider identity or provider quality consistently. |

Status: verified.

#### Question B4: What exactly must change to support a provider-aware model?

Answer: QuantMap needs a narrow provider contract that separates provider identity, provider capability/status, telemetry signal identity, signal evidence quality, acquisition details, safety/readiness policy, and persistence/report summaries. The first implementation should keep current sample tables compatible and add provider identity/evidence quality at run-level and report/export surfaces.

Evidence:

- QM-018 acceptance criteria require provider-neutral evidence/state, missing/degraded signals, doctor readiness explanation, and Windows/HWiNFO preservation.
- Existing `src/diagnostics.py` already offers generic status/readiness types.
- Existing `src/run_context.py` and `src/characterization.py` already model capability states, but they are not yet the telemetry provider contract.

Status: verified.

#### Question B5: What is reusable?

Answer:

- `src/settings_env.py` is reusable for env/path availability semantics.
- `src/diagnostics.py` is reusable for readiness/status reporting.
- `src/characterization.py` has useful probe and capability vocabulary.
- `src/run_context.py` has evidence-confidence logic and domain coverage concepts, but needs an import-path fix before it can be relied on.
- `src/trust_identity.py` is reusable for snapshot-first historical reader behavior.
- Current HWiNFO and NVML acquisition code can be preserved as provider implementations, not as the core model.

Status: verified.

#### Question B6: What is too fused to keep as-is?

Answer: `src/telemetry.py` cannot remain the home for all new provider branches. `src/doctor.py` cannot remain HWiNFO-only for telemetry readiness. `src/runner.py` should not gain provider-selection branches or direct provider imports. `src/report_campaign.py` should not become the place where provider evidence quality is assembled.

Evidence:

- `src/telemetry.py` is about 1668 lines and already carries provider acquisition, policy, sampling, and snapshots.
- `src/runner.py` is about 2802 lines and already imports telemetry, doctor, server, scoring, persistence, UI, progress, and direct NVML behavior.
- `src/report_campaign.py` is about 2628 lines and already aggregates environment, artifacts, interpretation, and rendering.

Status: verified.

### C. Linux/NVIDIA-First Target Clarification

#### Question C1: What does Linux/NVIDIA-first mean in practice?

Answer: It means the first non-Windows target should be a Linux environment with NVIDIA GPUs where QuantMap can identify available telemetry providers without HWiNFO, use NVML and psutil-style data where available, mark Windows/HWiNFO-only signals as unsupported or unavailable instead of silently treating them as equivalent, surface provider identity and degraded evidence quality in doctor/status/reports, and preserve Windows/HWiNFO support.

It does not yet mean Apple Silicon, ROCm, CPU-only parity, universal hardware coverage, cloud orchestration, packaging, or backend adapter support.

Evidence:

- Audit 5 response accepts Linux/NVIDIA-first and explicitly defers Apple Silicon, ROCm, CPU-only parity, and universal backend parity.
- `docs/AUDITS/4-11/Post-Audit-Synthesis-Memo.md` warns against provider overreach and says not to support all hardware at once.

Status: verified.

#### Question C2: Which Windows/HWiNFO assumptions block Linux/NVIDIA?

Answer:

- Import-time `ctypes.windll` in `src/telemetry.py` is Windows-only.
- HWiNFO CPU package temperature is currently an ABORT-tier requirement.
- Doctor telemetry readiness checks only HWiNFO shared memory.
- Campaign snapshots record `hwm_namespace` rather than generic provider identity.
- Reports and compare fields assume NVIDIA driver/GPU but not provider identity.
- `src/server.py` still contains Windows/CUDA/MKL path injection assumptions, though backend abstraction is later.

Status: verified.

#### Question C3: Can Phase 3 enable Linux/NVIDIA measurement immediately?

Answer: Not safely without one policy decision: how ABORT-tier safety should behave when CPU package temperature is unavailable on Linux but NVML GPU safety signals are available. The provider boundary can be implemented before this decision, but claiming Linux/NVIDIA measurement support requires deciding whether missing CPU package temp blocks the run, permits a degraded run, or is acceptable under a Linux-specific provider policy.

Evidence:

- `src/telemetry.py startup_check()` blocks campaigns if HWiNFO CPU package temp is unavailable.
- `src/run_context.py` treats CPU temperature states differently by platform but is not currently the telemetry startup policy authority.
- Audit and tracker docs require missing/degraded provider signals to be surfaced honestly rather than silently treated as clean.

Status: decision required.

### D. Settings / Environment Dependency Review

#### Question D1: Which settings/environment surfaces are now clean enough for provider work?

Answer: The narrow env/path availability contract is clean enough for provider work. Required env values treat missing, empty, whitespace, and `Path('.')` as unavailable; explicit-DB readers are protected; export redaction root semantics are safe.

Evidence:

- `src/settings_env.py` implements `read_env_path()` and `require_env_path()`.
- `src/config.py` uses `require_env_path()` for `QUANTMAP_LAB_ROOT`.
- `src/server.py` uses `require_env_path()` for `QUANTMAP_SERVER_BIN` and `QUANTMAP_MODEL_PATH`.
- Phase 2.1 validation confirms empty env no longer becomes `Path('.')`, explicit-DB readers work under missing/empty env, and export redaction hard-fails without a trustworthy root.

Status: verified.

#### Question D2: What provider code must not import directly?

Answer: Provider discovery/readiness code must not import `src.server` as a general dependency because `src.server` still represents the llama-server runtime lifecycle, required backend paths, log directory setup, and CUDA/MKL PATH injection. Provider code should use `src.settings_env` and provider-specific probes instead.

Evidence:

- `src/server.py` imports `LAB_ROOT`, `SERVER_BIN`, and `MODEL_PATH`, creates lab/log directories, and owns llama-server command construction.
- `src/server.py` still owns backend-specific runtime env injection through CUDA/MKL/compiler paths.

Status: verified.

#### Question D3: What remains partially generalized after Phase 2.1?

Answer: Phase 2.1 generalized env/path availability semantics, not provider discovery, backend identity, model-store portability, CUDA/MKL environment policy, or telemetry source selection. Those remain Phase 3 or later concerns.

Evidence:

- Phase 2.1 plan explicitly excluded telemetry provider implementation and backend abstraction.
- QM-005 remains open for broader path portability and local assumptions, while QM-018 is active for provider boundary work.

Status: verified.

### E. Requested vs Resolved Runtime Reality

#### Question E1: What resolved runtime reality is already captured?

Answer: QuantMap already captures substantial resolved runtime data: resolved server command, runtime env deltas, server pid, server log path, startup duration, request-level timing/token/server pid data, campaign start model/server binary identity, OS/GPU metadata, and run-context/environment characterization artifacts where available.

Evidence:

- `src/db.py` `configs` table includes `resolved_command` and `runtime_env_json`.
- `src/db.py` `cycles` table includes `startup_duration_s`, `server_pid`, and `server_log_path`.
- `src/db.py` `requests` table stores request timings, tokens, server pid, and resolved command.
- `src/db.py` `campaign_start_snapshot` includes binary/model identity and OS/GPU fields.

Status: verified.

#### Question E2: What is still only requested intent or backend-specific reality?

Answer: Backend-specific runtime reality remains mostly llama-server-shaped. Provider reality is not captured as a first-class identity. The difference between requested telemetry requirements and resolved provider capability is not yet persisted as an authority model.

Evidence:

- Phase 1 fields persist intended runtime shape, but provider identity is absent from snapshot schema.
- `src/server.py` owns llama-server command/env, but no backend-neutral resolved-runtime surface exists.
- `src/db.py` has no provider identity JSON fields in `campaign_start_snapshot` or telemetry rows.

Status: verified.

#### Question E3: What can Phase 3 improve without backend abstraction?

Answer: Phase 3 can add provider identity, provider capability status, and telemetry evidence quality to resolved runtime evidence without changing backend launch architecture. It can also remove direct provider probes from runner and doctor into a provider boundary. It should not design a backend adapter.

Evidence:

- QM-018 is unblocked and active.
- QM-019 remains planned but blocked behind settings and telemetry groundwork.

Status: verified.

### F. Report / Artifact / Evidence Implications

#### Question F1: What report/export/explain surfaces need to change?

Answer: Reports should show provider identity and evidence quality where telemetry evidence is interpreted. Exports should carry persisted provider identity and completeness labels. Compare should be able to show provider identity deltas if provider state differs across campaigns. Explain should not infer provider quality from live state; if it references instrumentation degradation, it should use persisted evidence.

Evidence:

- `src/report_campaign.py` renders environment quality, telemetry artifact availability, and concerns, but does not show provider identity.
- `src/report.py` renders NVIDIA driver and telemetry summaries but not provider identity.
- `src/compare.py` compares `nvidia_driver` and `gpu_name`, but not telemetry provider identity.
- `src/export.py` exports schema/tables and manifest completeness but has no provider-specific trust summary beyond what is currently persisted.
- `src/explain.py` uses persisted trust identity but has no provider-specific reader path.

Status: verified.

#### Question F2: What should be deferred until report consolidation?

Answer: Phase 3 should not consolidate `report.py` and `report_campaign.py`, redesign report layout, build an artifact browser, or rewrite scoring explanation. It should add provider evidence display through a small shared summary helper or persisted fields so the reports remain honest without becoming a redesign project.

Evidence:

- Architecture docs warn against enlarging report modules.
- `src/report_campaign.py` is already a high-blast-radius renderer/aggregator.

Status: verified.

### G. Doctor / Diagnostics / UX Implications

#### Question G1: How should doctor and diagnostics evolve?

Answer: Doctor should consume a provider-neutral readiness summary instead of checking only HWiNFO shared memory. It should be able to say provider active, missing, degraded, unsupported, or failed; identify whether missing signals block measurement; and point to remediation.

Evidence:

- `src/diagnostics.py` already has generic `Status`, `Readiness`, `CheckResult`, and `DiagnosticReport`.
- `src/doctor.py` currently checks HWiNFO directly and returns "HWiNFO Telemetry" as the readiness surface.
- QM-018 acceptance criteria require doctor/readiness to explain active/missing/degraded/unsupported provider state.

Status: verified.

#### Question G2: What should be blocked vs warned vs degraded?

Answer: Current measurement must block if required safety signals for the active provider policy are missing. Historical readers must not perform live provider probes when persisted evidence is sufficient. Missing optional telemetry signals should be visible as degraded or incomplete evidence, not silently ignored. Unsupported platform/provider states should be labeled, not treated as failures unless they block the requested operation.

Evidence:

- Phase 1/1.1 trust docs require historical evidence to outrank live convenience.
- Phase 2 docs require historical readers to survive malformed current state where snapshot evidence is complete.
- Current telemetry startup policy already distinguishes ABORT/WARN/SILENT, but it does so inside provider-specific code.

Status: inferred.

### H. Anti-God-Object / Boundary-Enforcement Analysis

#### Question H1: Which modules are most at risk of growing during Phase 3?

Answer:

| Module | Current size/role | Phase 3 growth risk |
| --- | --- | --- |
| `src/runner.py` | About 2802 lines; campaign policy, execution, persistence, UI, telemetry lifecycle, scoring/reporting coordination | Provider selection, provider startup policy, provider-specific runtime capture, Linux branches. |
| `src/telemetry.py` | About 1668 lines; acquisition, policy, samples, collector, snapshots | More provider branches, Linux paths, degraded-policy code, provider identity persistence. |
| `src/report_campaign.py` | About 2628 lines; aggregation plus rendering | Provider evidence formatting, capability summaries, platform-specific explanations. |
| `src/doctor.py` | About 380 lines; diagnostics/readiness | Provider discovery tree and platform branching. |
| `src/server.py` | About 859 lines; llama-server lifecycle/env | Backend/provider discovery confusion, runtime observation expansion. |
| `src/characterization.py` | About 1636 lines; environment probes | More provider probes without a clear ownership boundary. |

Status: verified.

#### Question H2: What small extractions or seam definitions should happen instead?

Answer:

- Add a provider contract module instead of adding provider branches directly to `telemetry.py`.
- Move HWiNFO/NVML acquisition behind provider-specific helpers.
- Add a provider policy/readiness function so runner gets one startup assessment rather than provider internals.
- Add a provider diagnostics helper so doctor consumes readiness summaries.
- Add a provider evidence summary helper so reports display persisted provider identity without aggregating provider logic.
- Keep backend runtime observation separate from telemetry provider work.

Status: inferred; ready as a design direction.

### I. Modification / Replacement / Creation Map

#### Modified

| File/module | Modification direction |
| --- | --- |
| `src/telemetry.py` | Demote to collector/persistence compatibility layer; call provider and policy helpers; avoid new direct provider branches. |
| `src/runner.py` | Replace direct telemetry/provider internals with one readiness/policy seam; remove or quarantine direct NVML use where naturally touched. |
| `src/doctor.py` | Consume provider-neutral readiness results; keep platform checks but stop making HWiNFO the telemetry authority. |
| `quantmap.py` | Surface provider-aware status through doctor/status without top-level heavy imports. |
| `src/db.py` | Add minimal provider identity/evidence fields if required; preserve existing telemetry table compatibility. |
| `src/report_campaign.py` | Display persisted provider identity/evidence quality through a shared summary helper; no broad renderer redesign. |
| `src/report.py` | Minimal provider identity/evidence display where it currently shows telemetry/hardware identity. |
| `src/compare.py` and `src/report_compare.py` | Use persisted provider identity for environment/provider deltas if fields are added. |
| `src/export.py` | Include provider evidence/completeness in export manifest without changing export into a case-file redesign. |
| `src/characterization.py` | Reuse capability vocabulary; align provider states if needed. |
| `src/run_context.py` | Fix import-path defect before relying on it for provider confidence evidence. |

#### Replaced or Demoted

| Current mechanism | Disposition |
| --- | --- |
| HWiNFO shared memory as telemetry readiness authority | Demote to Windows/HWiNFO provider implementation. |
| `src.telemetry.startup_check()` as mixed provider-plus-policy authority | Replace with provider-neutral policy boundary while preserving external behavior initially. |
| `hwm_namespace = "HWiNFO64"` as the only provider identity | Replace with explicit provider identity/evidence fields; keep legacy field for compatibility. |
| Direct `pynvml` import in `src/runner.py` | Replace with provider/runtime evidence helper when naturally touched. |
| Report text that frames telemetry absence only through NVML/Windows API | Demote to provider-specific language or shared provider evidence summary. |

#### Created

| New boundary | Purpose |
| --- | --- |
| `src/telemetry_provider.py` or equivalent | Narrow provider contract: provider identity, signal identity, capability status, evidence quality. |
| HWiNFO provider helper | Isolate Windows/HWiNFO shared memory acquisition. |
| NVML provider helper | Isolate NVIDIA/NVML acquisition. |
| Provider policy/readiness helper | Map provider capabilities into ABORT/WARN/SILENT or successor policy decisions. |
| Provider evidence summary helper | Give report/export/compare a shared persisted provider summary without live probing. |

Status: inferred; ready except for persistence shape and Linux safety policy decisions.

### J. Scope-Fit / Exclusion Discipline

| Candidate concern | Scope fit | Reason |
| --- | --- | --- |
| Telemetry provider interfaces | Phase 3 | Direct center of gravity. |
| Provider-neutral evidence-quality model | Phase 3 | Required to avoid weakening trust under missing/degraded providers. |
| Linux/NVIDIA-first provider support | Phase 3 | Explicit target from Audit 5 and roadmap. |
| Doctor/provider readiness integration | Phase 3 | Required acceptance criterion under QM-018. |
| Resolved runtime reality provider slice | Phase 3 | Provider identity/capability is resolved evidence, not backend abstraction. |
| Backend adapter design | Later phase | QM-019 remains blocked behind settings and telemetry groundwork. |
| Report consolidation | Later phase | Not needed for provider-aware evidence; high blast radius. |
| Runner decomposition | Later phase with tiny Phase 3 seams | Broad decomposition deferred; Phase 3 must avoid enlarging runner and may create only necessary seams. |
| Optimization/recommendation semantics | Later phase | Depends on stable provider evidence, but not Phase 3 work. |
| Packaging / one-click install | Later phase | Separate operational/productization problem. |
| Universal hardware support | Out of scope for Phase 3 | Explicitly deferred by Audit 5. |

Status: verified from docs plus inferred implementation boundaries.

## 4. Additional Implementation-Readiness Findings

### Finding 1: `src.run_context` import is currently broken

Evidence: `src/run_context.py` imports `from characterization import ...` instead of `from src.characterization import ...`. A direct import probe produced `ModuleNotFoundError: No module named 'characterization'`.

Why it matters: `run_context` contains useful evidence-confidence logic that Phase 3 should reuse or align with. If it cannot import, provider evidence-quality improvements may bypass the existing context model or silently omit per-cycle environment evidence.

Disposition: required early preflight fix or first implementation gate before relying on run-context evidence in Phase 3.

Status: verified.

### Finding 2: `src.runner` appears to call `collect_campaign_start_snapshot()` with newer keyword arguments that the function signature does not accept

Evidence: `src/runner.py` calls `tele.collect_campaign_start_snapshot(...)` with keyword arguments including `baseline`, `quantmap_identity`, and `run_plan_snapshot`, while `src/telemetry.py collect_campaign_start_snapshot()` accepts only the older positional/keyword set through `cpu_affinity_policy`.

Why it matters: Phase 3 will likely extend campaign start snapshot provider fields. A call/signature mismatch on the existing snapshot seam must be reconciled before layering provider identity on top of it.

Disposition: verify in tests and fix as a narrow prerequisite during implementation. This is not a provider-design decision, but it is a blocker to safe provider snapshot work if confirmed at runtime.

Status: verified by static inspection; runtime confirmation recommended.

## 5. Resolution Matrix

| Issue | Current reality | Why it matters | Scope fit | Design options | Recommended direction | Why | Explicitly deferred | Boundary-enforcement note | Decision status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Provider contract | No provider-neutral contract; telemetry policy and acquisition are fused in `src/telemetry.py`. | Linux/NVIDIA cannot be added honestly without separating provider identity, capability, and policy. | Phase 3 | Add branches in `telemetry.py`; create narrow contract; create full plugin framework. | Create a narrow static provider contract module, no plugin framework. | Gives enough boundary without overbuilding. | Dynamic provider plugins, universal hardware registry. | Prevents `telemetry.py` from absorbing every provider. | ready |
| HWiNFO wall | HWiNFO shared memory is embedded in telemetry and doctor. | Blocks non-Windows support and hides provider-specific assumptions. | Phase 3 | Keep as-is; replace HWiNFO; make HWiNFO one provider. | Make HWiNFO a Windows provider path while preserving current behavior. | Provider abstraction, not provider replacement, matches Audit 5. | Removing HWiNFO support. | Extract HWiNFO code out of core policy path. | ready |
| NVML handling | NVML is used in telemetry, characterization, and runner. | Linux/NVIDIA first needs NVML, but direct use scattered in runner increases risk. | Phase 3 | Leave scattered; centralize in provider helper; backend abstraction. | Centralize NVML acquisition in a provider helper. | Reuses current capability while reducing scatter. | Full backend/GPU platform registry. | Replace direct `runner.py` NVML branch with helper output. | ready |
| ABORT-tier safety on Linux/NVIDIA | Current policy requires HWiNFO CPU temp plus NVML VRAM/throttle. | Linux may not have CPU package temp through HWiNFO; weakening this silently would violate trust. | Phase 3 | Block until all current signals exist; allow degraded Linux policy; support provider-specific ABORT sets. | Implement provider-neutral policy, but require human approval for Linux CPU-temp semantics before claiming Linux measurement support. | Separates boundary work from safety-policy change. | Optimization/recommendation use of degraded telemetry. | Keep policy outside runner and providers. | needs approval |
| Provider persistence | DB records HWiNFO/NVIDIA fields but no provider identity/evidence quality. | Reports/export/compare need historical provider truth, not live probing. | Phase 3 | New provider table; JSON fields on snapshot; only report labels. | Add minimal run-level provider identity/capability JSON to snapshot or equivalent authoritative run evidence. | Smallest trust-preserving persistence addition. | Per-sample provider schema redesign. | Persistence helper should be shared, not report-owned. | needs approval |
| Doctor readiness | Doctor checks HWiNFO directly. | Operators need active/missing/degraded/unsupported provider state. | Phase 3 | Add more checks directly; consume provider readiness summary. | Doctor consumes provider-neutral readiness results. | Keeps UX useful without making doctor provider engine. | Full hardware wizard. | Provider diagnostics helper, not doctor branches. | ready |
| Report/export provider surfaces | Reports show telemetry artifacts but not provider identity. | Provider-aware evidence must be visible historically. | Phase 3 | Redesign reports; add small shared summary; leave hidden. | Add small provider evidence summary consumed by reports/export/compare. | Honest, bounded, trust-preserving. | Report consolidation and case-file redesign. | Avoid adding provider aggregation to `report_campaign.py`. | ready |
| Run-context confidence | Useful model exists but import path is broken. | Provider evidence quality should not bypass existing confidence vocabulary. | Phase 3 prerequisite | Ignore; fix import; rewrite. | Fix import and align state vocabulary as first preflight. | Small, necessary, bounded. | Rewriting characterization architecture. | Avoid adding duplicate confidence model. | ready |
| Campaign start snapshot seam | Runner/snapshot signature appears inconsistent. | Provider snapshot fields would touch this seam. | Phase 3 prerequisite | Ignore; verify/fix narrow; redesign snapshots. | Verify and reconcile before provider persistence changes. | Prevents stacking new evidence on a broken writer seam. | New snapshot store. | Keep one snapshot authority. | ready |
| Backend abstraction | `src/server.py` is llama-server/CUDA/MKL-shaped. | Important for later portability but not required for provider boundary. | Later phase | Start backend adapter now; leave as-is; tiny observation seam. | Defer backend adapter; avoid importing server from provider discovery. | Keeps Phase 3 contained. | Backend launch/health/log adapter. | Do not grow `server.py` during provider work. | ready |
| Runner decomposition | Runner is high-risk and crowded. | Provider work will naturally touch runner. | Later phase with tiny seams | Broad decomposition; add branches; small policy seam. | Add only a telemetry readiness/policy seam now. | Prevents God-object growth without starting a refactor phase. | Full runner decomposition. | No provider branches in runner. | ready |

## 6. Future-Fit Check

### Does this make later telemetry/provider strategy easier?

Yes. A narrow provider contract and policy boundary lets QuantMap preserve Windows/HWiNFO behavior while adding Linux/NVIDIA support without burying provider conditionals in runtime, doctor, and report modules.

Status: inferred.

### Does this make backend abstraction easier or harder?

Easier, if Phase 3 keeps provider identity separate from backend launch identity. Backend abstraction should later build on resolved runtime reality, not on telemetry providers. Provider work must not import `src.server` as its discovery mechanism.

Status: inferred.

### Does this make report consolidation easier or harder?

Easier, if report/provider evidence is exposed through a shared summary helper. Harder, if provider-specific explanations are added directly to both report stacks.

Status: inferred.

### Does this make recommendation/optimization safer?

Easier, because recommendations need to know whether telemetry evidence is complete, degraded, missing, unsupported, or provider-shifted. Phase 3 should persist this evidence quality before later optimization relies on it.

Status: inferred.

### Does this paint QuantMap into a corner?

Not if Phase 3 remains static and narrow: no plugin framework, no universal provider registry, no backend adapter, no report redesign. The proposed seams prepare future work without forcing it.

Status: inferred.

## 7. Interrogation Conclusion

Phase 3 is ready to plan as a contained Platform Generalization phase centered on telemetry/provider boundaries and Linux/NVIDIA-first support. The strongest existing foundations are the Phase 2.1 settings/env bridge, `src.diagnostics`, the trust model, and the run-context/characterization capability vocabulary. The weakest current surfaces are `src.telemetry.py` as a fused provider/policy/acquisition/persistence module, `src.runner.py` direct provider coupling, and HWiNFO-only doctor readiness.

The most important unresolved design decision is Linux/NVIDIA safety policy: specifically, whether and how a run may proceed when HWiNFO CPU package temperature is unavailable but Linux/NVIDIA provider signals are otherwise available. The provider boundary can be implemented before that decision, but Linux/NVIDIA measurement support should not be claimed until the policy is approved.
