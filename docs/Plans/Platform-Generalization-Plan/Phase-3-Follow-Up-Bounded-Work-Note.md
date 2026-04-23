# Phase 3 Follow-Up Bounded Work Note

Status: bounded follow-up updated after WSL degraded decision  
Date: 2026-04-13  
Scope: Phase 3 provider-boundary hardening only

Update: WSL 2 is now an explicit `wsl_degraded` support tier. The remaining target-validation work is full in-WSL campaign validation after Python dependency setup and a later bare-metal `linux_native` phase, not a prerequisite to using WSL as degraded.

## 1. Why This Note Exists

The Phase 3 provider boundary is implemented and partially hardened, but full Phase 3 closure is not yet justified. The remaining work is bounded and should not become backend abstraction, report consolidation, optimization, packaging, or a generic provider framework.

## 2. Required Follow-Up

### A. WSL Degraded Campaign Validation

Run a full QuantMap campaign inside WSL after the WSL Python dependency environment is installed.

Validate:

- WSL classified as `wsl_degraded`
- measurement-grade persisted as false
- CPU thermal evidence unavailable and clearly degraded
- NVIDIA visibility represented where available
- provider evidence persistence
- report/export/compare behavior from persisted provider evidence
- explicit-DB historical reader independence from live provider state

### B. Native Linux CPU Thermal Safety Policy Decision

Resolve the bare-metal Linux/NVIDIA CPU thermal safety question before claiming measurement-grade native Linux support.

See:

- `docs/decisions/Phase-3-Linux-NVIDIA-Safety-Decision-Note.md`

### C. Continue HWiNFO/NVML Extraction Carefully

The initial pass created HWiNFO and NVML helper modules and routed readiness/provider evidence through them. `src.telemetry.py` still contains significant provider-specific acquisition internals for sample collection.

Bounded next step:

- Continue moving acquisition helpers behind provider modules where naturally touched.
- Do not rewrite the telemetry collector or telemetry table in this follow-up.
- Do not add Linux branches directly to `src.telemetry.py`.

### D. Provider Evidence Report Helper

Provider evidence display now uses a shared helper in `src.telemetry_provider`. If report/provider display grows further, consider a tiny report-summary helper.

Bounded rule:

- Do not add provider aggregation logic directly to `src.report_campaign.py`.

## 3. Not In Scope

- backend adapter
- plugin framework
- universal hardware support
- report consolidation
- runner decomposition
- optimization/recommendation semantics
- packaging overhaul

## 4. Closure Condition

Phase 3 can move from implementation-in-progress to boundary-complete when:

- Windows provider readiness and historical-reader behavior remain stable.
- Linux/NVIDIA target validation is either completed or explicitly marked as validation-pending.
- CPU thermal policy is approved or remains a clear blocker to measurement-grade Linux/NVIDIA support.
- No new provider logic is being added through God-object growth.
