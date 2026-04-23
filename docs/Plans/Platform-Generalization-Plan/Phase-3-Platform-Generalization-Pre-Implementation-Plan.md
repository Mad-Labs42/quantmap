# Phase 3 Platform Generalization Pre-Implementation Plan

Status: pre-implementation plan for review  
Date: 2026-04-12  
Scope: Phase 3 Platform Generalization  
Primary input: Phase 3 interrogation, Phase 2.1 settings/environment bridge, current roadmap alignment, Audit 5 architecture/generalization findings

## 1. Purpose

Phase 3 generalizes QuantMap's platform shell enough to begin escaping the Windows/HWiNFO-only telemetry shape while preserving the stabilized Phase 1 trust model and the Phase 2/2.1 operational robustness foundations.

Phase 3 is not:

- backend adapter implementation
- optimization/recommendation work
- report consolidation
- universal hardware support
- packaging or one-click install work
- broad runner/report refactoring
- a generic plugin framework

Phase 3 is:

- a provider-neutral telemetry boundary
- explicit provider identity and evidence-quality vocabulary
- Windows/HWiNFO preservation through a provider path
- Linux/NVIDIA-first provider groundwork
- provider-aware doctor/status/report/export surfaces
- small, phase-coupled boundary extractions that prevent God-object growth

## 2. Why Phase 3 Exists

Phase 1 and Phase 1.1 stabilized snapshot-first trust. Phase 2 and Phase 2.1 stabilized the operational shell and minimum settings/environment contract. The remaining platform blocker is telemetry/provider lock-in.

Today, telemetry policy and acquisition are fused to Windows/HWiNFO and pynvml. `src/telemetry.py` owns provider acquisition, startup safety policy, sample normalization, collection lifecycle, and campaign start hardware fingerprints. `src/doctor.py` treats HWiNFO shared memory as the telemetry readiness surface. `src/runner.py` invokes telemetry startup directly and imports NVML directly for campaign-start VRAM evidence.

This makes Linux/NVIDIA support unsafe to add directly. Without a provider boundary, Phase 3 would either weaken telemetry trust or enlarge the most fragile modules.

## 3. Goals

Phase 3 must accomplish the following:

- Define a narrow provider-neutral telemetry contract.
- Separate provider acquisition from telemetry safety/readiness policy.
- Preserve current Windows/HWiNFO behavior as a provider-backed path.
- Add a Linux/NVIDIA-first provider path or staged implementation with explicit validation requirements.
- Persist provider identity and evidence-quality enough for historical report/export/compare truth.
- Surface active/missing/degraded/unsupported provider states in doctor/status.
- Prevent live provider probing from contaminating snapshot-first historical readers.
- Avoid adding scattered provider branches to `src/runner.py`, `src/telemetry.py`, `src/doctor.py`, `src/report_campaign.py`, or `src/server.py`.

## 4. Locked Design Decisions

### Decision 1: Provider boundary before provider variety

Phase 3 must first create a small provider contract and policy boundary before adding or enabling non-Windows provider behavior.

Why: Adding Linux/NVIDIA branches directly to current modules would preserve the same structural problem in a larger form.

### Decision 2: Static provider list, no plugin framework

Use a small static set of provider helpers for Phase 3. Do not build dynamic plugin loading, provider registration, marketplace-style discovery, or a generic hardware framework.

Why: The project needs one trustworthy boundary, not a platform framework.

### Decision 3: HWiNFO remains supported

Windows/HWiNFO should become a provider implementation, not be removed or treated as legacy failure.

Why: Audit 5 recommends provider abstraction, not provider replacement.

### Decision 4: Provider policy is not provider acquisition

Provider helpers should report identity, capability, readings, and failures. A separate policy/readiness boundary decides what blocks a run, what degrades evidence, and what is informational.

Why: This preserves trust and prevents provider implementations from silently changing safety semantics.

### Decision 5: Historical readers use persisted provider evidence

Reports, exports, compare, and explain must read provider identity/evidence quality from persisted run evidence when present. They must not perform live provider discovery to describe historical runs.

Why: This preserves the Phase 1 snapshot-first trust model.

### Decision 6: Backend abstraction remains deferred

Phase 3 may observe runtime provider facts, but must not turn into a backend adapter or server lifecycle redesign.

Why: Backend coupling is tracked separately and should follow settings and telemetry groundwork.

## 5. Scope

### In Scope

- Provider-neutral telemetry contract and vocabulary.
- HWiNFO provider isolation.
- NVML provider isolation for NVIDIA signals.
- Provider readiness/policy boundary.
- Provider identity/evidence persistence at the run level.
- Provider-aware doctor/status messaging.
- Minimal report/export/compare/explain surface alignment.
- Run-context/characterization alignment where it supports provider evidence quality.
- Tiny runner seam for telemetry readiness and collector lifecycle.

### Out of Scope

- Full backend abstraction.
- Universal hardware support.
- Apple Silicon, ROCm, CPU-only parity.
- Report stack consolidation.
- Broad runner decomposition.
- Optimization/recommendation semantics.
- Packaging/cloud deployment.
- Generic plugin/provider framework.

## 6. Workstreams

### Workstream A: Preflight Integrity Checks

Purpose: Make sure Phase 3 does not build provider evidence on already-broken seams.

Tasks:

- Verify and fix the `src.run_context` import path defect before relying on run-context evidence.
- Verify and reconcile the apparent `src.runner` to `src.telemetry.collect_campaign_start_snapshot()` signature mismatch before adding provider snapshot fields.
- Add focused regression coverage for both seams.

Files:

- `src/run_context.py`
- `src/runner.py`
- `src/telemetry.py`
- tests or validation scripts already used by the project

Boundary rule: Keep this as narrow prerequisite cleanup, not a run-context redesign.

### Workstream B: Provider Contract and Evidence Vocabulary

Purpose: Define the smallest shared language needed for providers, policy, diagnostics, and reports.

Create:

- `src/telemetry_provider.py` or equivalent narrow module.

Recommended contents:

- provider identity fields:
  - `provider_id`
  - `provider_label`
  - `provider_version`
  - `platform`
  - `source`
- signal identity fields:
  - `signal_name`
  - `signal_tier`
  - `unit`
- status/evidence vocabulary:
  - `available`
  - `missing`
  - `degraded`
  - `unsupported`
  - `failed`
  - `not_applicable`
- provider readiness structure:
  - active providers
  - missing required signals
  - degraded optional signals
  - unsupported signals
  - remediation messages

Boundary rule: This module should contain dataclasses/enums/helpers only. It must not perform live hardware probing.

### Workstream C: Provider Acquisition Isolation

Purpose: Move provider-specific acquisition behind helpers without changing current behavior more than necessary.

Create or isolate:

- HWiNFO provider helper for Windows shared-memory acquisition.
- NVML provider helper for NVIDIA GPU signals.

Modify:

- `src/telemetry.py` to call provider helpers rather than owning all provider internals.
- `src/characterization.py` only where useful to share NVML/probe vocabulary, without making characterization the telemetry provider engine.

Boundary rule: Do not add Linux branches directly to `src/telemetry.py`. If Linux/NVIDIA needs new probing, add it behind the provider helper.

### Workstream D: Telemetry Policy / Readiness Boundary

Purpose: Separate safety policy from provider acquisition.

Create:

- `src/telemetry_policy.py` or a similarly narrow helper if implementation pressure justifies a separate module.

Responsibilities:

- Map provider capability status to ABORT/WARN/SILENT or successor readiness states.
- Preserve current Windows/HWiNFO behavior initially.
- Represent missing/degraded provider signals honestly.
- Return one startup/readiness assessment that runner and doctor can consume.

Open policy item:

- Linux/NVIDIA CPU temperature semantics need explicit approval before QuantMap claims measurement-grade Linux/NVIDIA support.

Boundary rule: Runner should call one policy/readiness function and should not contain provider-specific conditionals.

### Workstream E: Provider Identity and Evidence Persistence

Purpose: Make provider identity historical evidence, not a live report-time inference.

Recommended persistence shape:

- Add minimal run-level provider evidence fields to `campaign_start_snapshot` or an equivalent single authoritative run evidence surface.
- Prefer JSON fields for Phase 3:
  - `telemetry_provider_identity_json`
  - `telemetry_capabilities_json`
  - `telemetry_capture_quality`

Rationale:

- This avoids a second snapshot authority.
- Existing per-sample telemetry schema can remain compatible.
- Reports/export/compare can consume one historical provider summary.

Boundary rule: Do not redesign the telemetry table unless implementation proves run-level evidence is insufficient.

### Workstream F: Doctor / Status Provider Readiness

Purpose: Make operator readiness provider-aware without turning doctor into a hardware engine.

Modify:

- `src/doctor.py`
- `quantmap.py`
- possibly `src/diagnostics.py` only if the existing generic statuses need a small label extension

Expected behavior:

- Show active provider(s).
- Show missing, degraded, unsupported, or failed provider state.
- Distinguish current-run blockers from historical-reader non-blockers.
- Preserve clear remediation messages.

Boundary rule: Doctor consumes provider readiness summaries. It does not own provider probing internals.

### Workstream G: Run-Context and Characterization Alignment

Purpose: Reuse existing evidence-confidence concepts instead of creating a second vocabulary.

Modify:

- `src/run_context.py`
- `src/characterization.py`

Tasks:

- Fix import path.
- Align capability state labels where needed.
- Ensure provider evidence quality can be summarized alongside environment confidence.
- Avoid making characterization responsible for telemetry policy.

Boundary rule: Characterization can observe and summarize; it should not decide whether a campaign is allowed to run.

### Workstream H: Report / Export / Compare Surface Alignment

Purpose: Surface provider evidence without redesigning readers.

Modify:

- `src/report_campaign.py`
- `src/report.py`
- `src/compare.py`
- `src/report_compare.py`
- `src/export.py`
- `src/explain.py` only if it makes provider/instrumentation claims

Tasks:

- Add provider identity/evidence-quality summary from persisted run evidence.
- Label legacy runs without provider evidence as legacy/incomplete, not inferred from live provider state.
- Export provider evidence/completeness metadata.
- Compare provider identity/capability differences if persisted.

Boundary rule: Add a small shared formatter/summary helper if needed. Do not build provider aggregation inside report modules.

## 7. File-Level Responsibilities

| File/module | Phase 3 responsibility |
| --- | --- |
| `src/settings_env.py` | Remains the settings/env availability foundation. Provider work should build on it, not change it broadly. |
| `src/config.py` | Infrastructure path authority. Avoid broad settings changes. |
| `src/server.py` | Remains llama-server lifecycle/backend-specific. Provider discovery should not depend on importing it. |
| `src/telemetry_provider.py` | New narrow contract/vocabulary module. No probing. |
| HWiNFO provider helper | Owns HWiNFO shared-memory acquisition. |
| NVML provider helper | Owns NVIDIA/NVML acquisition. |
| `src/telemetry_policy.py` | Maps provider capability to readiness/safety semantics if separated. |
| `src/telemetry.py` | Collector/persistence compatibility layer; delegates provider and policy concerns. |
| `src/runner.py` | Consumes one readiness/policy seam; no direct provider branches. |
| `src/doctor.py` | Displays provider readiness through shared diagnostics. |
| `src/diagnostics.py` | Generic result/readiness types; small extensions only if necessary. |
| `src/run_context.py` | Evidence confidence integration after import fix. |
| `src/characterization.py` | Capability observation and summary, not policy authority. |
| `src/db.py` | Minimal provider identity/evidence schema support. |
| `src/report_campaign.py` | Display persisted provider summary through shared helper. |
| `src/report.py` | Minimal provider summary display where it reports hardware/telemetry identity. |
| `src/compare.py` / `src/report_compare.py` | Compare/display provider identity deltas if persisted. |
| `src/export.py` | Export provider evidence and completeness labels. |
| `src/explain.py` | Use persisted provider evidence only if explaining instrumentation degradation. |
| `quantmap.py` | CLI status/doctor wiring through command-local imports. |

## 8. Sequence of Work

### Step 1: Preflight validation and seam repair

- Verify `src.run_context` import behavior.
- Verify campaign start snapshot writer behavior.
- Repair only the narrow defects required before provider evidence can be persisted.

Why first: Provider evidence should not be layered on broken runtime context or snapshot seams.

### Step 2: Define provider contract and vocabulary

- Add the narrow provider contract.
- Decide exact status labels.
- Map current HWiNFO/NVML signals into the contract.

Why second: All later work depends on a shared language.

### Step 3: Isolate provider acquisition

- Move or wrap HWiNFO shared-memory acquisition.
- Move or wrap NVML acquisition.
- Keep current Windows behavior stable.

Why third: Provider variety should happen only after acquisition is behind a boundary.

### Step 4: Add provider policy/readiness seam

- Preserve current Windows/HWiNFO ABORT/WARN/SILENT behavior.
- Return one readiness object for runner and doctor.
- Flag Linux/NVIDIA policy decision before enabling measurement-grade support.

Why fourth: Policy should consume provider capabilities, not be embedded inside provider readers.

### Step 5: Persist run-level provider evidence

- Add minimal provider identity/capability/evidence-quality persistence.
- Populate it for new runs.
- Label legacy runs with no provider evidence.

Why fifth: Historical readers need persisted provider truth before reports are changed.

### Step 6: Update doctor/status

- Display provider readiness and remediation.
- Preserve current-run fail-loud behavior.
- Avoid probing historical readers.

Why sixth: Operators need clear provider state once the readiness model exists.

### Step 7: Update reports/export/compare/explain

- Display persisted provider identity/evidence quality.
- Add export manifest completeness labels.
- Compare provider differences where persisted.

Why seventh: Readers should consume the new persisted evidence, not force live discovery.

### Step 8: Linux/NVIDIA-first target validation

- Validate import safety on non-Windows or simulated non-Windows.
- Validate NVML provider behavior where NVIDIA is available.
- Validate unsupported/missing/degraded labels where provider support is absent.
- Do not close Linux/NVIDIA support without real target evidence or an explicit staged limitation.

Why eighth: The provider boundary can be implemented on Windows, but the Linux/NVIDIA target needs target validation before closure claims.

## 9. Verification Plan

### Required Tests / Scenarios

- Current Windows/HWiNFO path still starts and records telemetry as before when HWiNFO and NVML are available.
- HWiNFO missing on Windows produces the same or clearer blocking behavior for current measurement.
- Provider readiness output identifies active/missing/degraded/unsupported providers.
- `quantmap doctor` and `quantmap status` show provider state without importing backend/server paths unnecessarily.
- `src.telemetry` can be imported on non-Windows or simulated non-Windows without failing due to `ctypes.windll`.
- Runner has no direct provider-specific NVML branch for new provider evidence.
- Explicit-DB historical readers do not perform live provider discovery.
- New runs persist provider identity/evidence quality.
- Reports display persisted provider identity/evidence quality.
- Legacy runs without provider evidence are labeled legacy/incomplete.
- Export includes provider evidence/completeness and does not infer it from current hardware.
- Compare can show provider differences when provider evidence is persisted.
- `src.run_context` imports and produces confidence output.
- Campaign start snapshot writer accepts and persists the intended snapshot/provider fields.

### Linux/NVIDIA Validation

Before claiming Linux/NVIDIA support complete:

- run provider readiness on a Linux/NVIDIA host or documented equivalent environment
- verify NVML provider detection
- verify missing HWiNFO is treated as unsupported/not applicable rather than a Windows-style HWiNFO failure
- verify safety policy behavior under the approved CPU-temperature decision
- verify provider identity appears in persisted run evidence and reports

If real Linux/NVIDIA validation is unavailable, Phase 3 may close only the provider-boundary implementation, not full Linux/NVIDIA target support.

## 10. Risks and Controls

| Risk | Control |
| --- | --- |
| Provider work grows `src/telemetry.py` into a larger God object | Extract provider contract and provider helpers before adding new provider behavior. |
| Runner absorbs provider selection and Linux branches | Runner consumes one readiness/policy seam only. |
| Doctor becomes provider discovery engine | Doctor consumes provider diagnostics summaries. |
| Reports infer historical provider state from live hardware | Reports consume persisted provider evidence only. |
| Linux/NVIDIA support weakens ABORT-tier safety | Require explicit safety policy decision before claiming measurement-grade support. |
| Backend abstraction sneaks into provider work | Provider discovery must not depend on `src.server`; backend adapter remains deferred. |
| New provider persistence creates second trust store | Prefer minimal fields in existing run-start authority surface. |
| Existing run-context/snapshot defects undermine Phase 3 | Preflight and repair those seams first. |

## 11. Exit Criteria

Phase 3 can be called complete only when:

- A provider-neutral telemetry contract exists and is used by telemetry readiness.
- HWiNFO is represented as a provider path, not the core telemetry authority.
- NVIDIA/NVML provider behavior is isolated behind a provider helper.
- Runner no longer owns direct provider-specific logic for provider evidence.
- Doctor/status explain active/missing/degraded/unsupported provider states.
- New runs persist provider identity and evidence quality.
- Reports/export/compare use persisted provider evidence.
- Historical readers remain snapshot-first and do not live-probe providers for historical truth.
- Legacy runs without provider evidence are labeled honestly.
- Boundary enforcement is visible in the implementation: no scattered provider conditionals in high-blast-radius modules.
- Linux/NVIDIA-first support is either validated on target hardware or explicitly marked as boundary-ready but target-validation pending.

## 12. Open Decisions Requiring Review

### Decision A: Linux/NVIDIA ABORT-tier safety semantics

Question: If Linux/NVIDIA provider signals are available through NVML but CPU package temperature is unavailable, should current measurement:

- block,
- allow only explicitly labeled degraded runs,
- or proceed under a Linux-specific provider policy?

Recommendation: Do not claim measurement-grade Linux/NVIDIA support until this is explicitly approved. Preserve fail-loud safety for current Windows/HWiNFO behavior.

### Decision B: Provider evidence persistence shape

Question: Should provider identity/evidence quality be added as JSON fields on `campaign_start_snapshot`, or as a new linked provider evidence table?

Recommendation: Prefer minimal JSON fields on the existing run-start authority surface for Phase 3. Revisit a normalized table only if per-cycle or multi-provider evidence becomes too complex.

### Decision C: Module layout

Question: Should provider implementations live as flat modules or under a package?

Recommendation: Use the smallest layout that prevents `src/telemetry.py` growth. A narrow `src/telemetry_provider.py` contract plus flat provider helper modules is sufficient unless implementation pressure clearly favors a small package. Do not build a plugin framework.

### Decision D: Phase 3 closure standard for Linux/NVIDIA

Question: Does Phase 3 closure require actual Linux/NVIDIA validation, or can it close with provider-boundary implementation and target validation pending?

Recommendation: Require actual target validation before claiming Linux/NVIDIA support. If no target environment is available, call the boundary complete but keep Linux/NVIDIA support as validation-pending.

## 13. Draft Implementation Directive

Proceed with Phase 3 only after review approval. Begin by repairing narrow preflight seams, then create the provider contract and provider policy boundary. Preserve current Windows/HWiNFO behavior while moving HWiNFO and NVML acquisition behind provider helpers. Add provider identity/evidence persistence before changing report/export/compare surfaces. Keep backend abstraction, broad runner decomposition, report consolidation, optimization, and universal hardware support out of scope.
