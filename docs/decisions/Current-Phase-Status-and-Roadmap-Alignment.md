# Current Phase Status and Roadmap Alignment

Status: living roadmap alignment note  
Date: 2026-04-13  
Scope: current phase state, closure gates, and Phase 3 activation boundary

## Current State

QuantMap's current project state is:

| Phase | Status | Current meaning |
|---|---|---|
| Phase 1 Trust Bundle | stable | Snapshot-first historical identity, baseline/methodology self-containment, QuantMap code identity, layered runtime/report state, and non-misleading report/export trust behavior are stable based on Phase 1.1 real-workflow validation. |
| Phase 1.1 Trust Bundle Stabilization | complete/stable | Methodology shadow truth and reader convergence were stabilized enough to treat the trust bundle as the foundation for future work. |
| Phase 2 Operational Robustness | closed | The brittle-shell implementation pass and tiny dry-run/readiness closure patch are validated. Operational robustness is stable enough to hand off to the settings/environment bridge. |
| Phase 2.1 Settings/Environment Bridge | complete | Missing/empty env semantics, `Path('.')` prevention, explicit-DB reader independence, and export redaction root behavior are validated enough to unblock Phase 3. |
| Phase 3 Platform Generalization | active / WSL degraded execution validated; appendix_b fix applied | Telemetry/provider abstraction and Linux/NVIDIA-first portability are the active major direction. WSL 2 is now an explicit degraded Linux-like execution tier with real WSL startup/persistence validation, explicit backend-boundary enforcement, and one successful end-to-end WSL measurement smoke run using a Linux-native backend; native `linux_native` support remains future bare-metal Linux work. The `report_v2` Appendix B `NameError` (`name 'stats' is not defined`) identified during the WSL smoke run is resolved. |

## Active Work Boundary

The active phase is now:

> **Phase 3: Platform Generalization**

Phase 2 Operational Robustness is closed. Phase 2.1 Settings/Environment Bridge is also complete. The bridge validation confirmed:

- missing, empty, whitespace-only, and current-directory required path env values are not silently treated as usable runtime paths
- required runtime paths no longer silently become `Path('.')`
- explicit-DB historical readers remain usable under missing/empty current env
- `export --strip-env` hard-fails without a trustworthy redaction root
- current-run/current-input paths fail loudly when required settings are unavailable

The remaining portability work now belongs to Phase 3 and later staged architecture work, not to Phase 2.1 closure.

## Phase 3 Activation Rule

Phase 3 is active because this rule has been satisfied for the initial provider workstream:

> Telemetry/provider abstraction follows settings/environment boundary hardening because providers need common config, path, runtime-env, and discovery policy.

This means Phase 3 must not begin by adding telemetry providers directly to `runner.py`, `telemetry.py`, `doctor.py`, or report modules.

Phase 3 began with provider boundary design and validation, then moved into implementation. It should continue as boundary-aware provider work, not as scattered provider conditionals in existing high-blast-radius modules.

## Boundary-Enforcement Policy

Every new phase and subphase must include anti-God-object guardrails.

Current policy:

- prefer surgical extraction where new work naturally touches crowded modules
- do not start a giant standalone refactor as a substitute for feature work
- do not let Phase 3 enlarge `src/runner.py`, `src/report_campaign.py`, or similar high-blast-radius modules without an explicit boundary plan
- do not add provider/backend abstractions through scattered conditionals
- keep trust authority in the existing snapshot-first model; robustness and portability must expose trust, not blur it

This is especially important for Phase 3 because provider work can easily recreate local assumptions in a new shape.

## Roadmap Sequence

The current roadmap sequence is:

1. Complete the Phase 2.1 settings/environment bridge.
2. Activate Phase 3 Platform Generalization.
3. Start Phase 3 with telemetry/provider boundary design, not broad provider implementation.
4. Implement the initial provider boundary and run a required Windows/Linux hardening slice before claiming Phase 3 complete.
5. Keep backend abstraction, optimization/recommendation, report consolidation, and runner decomposition staged behind their own explicit plans.

The first three steps are now complete or underway. Step 4 now has WSL 2 target evidence, explicit degraded semantics, WSL Python dependency validation, explicit rejection of Windows `.exe` backend execution through WSL interop, and a successful end-to-end WSL measurement smoke run using a Linux-native llama.cpp backend. Native `linux_native` validation and measurement-grade Linux support remain deferred.

## Phase 2 Closure Evidence

Phase 2 is closed by:

- `docs/decisions/Phase-2-Operational-Robustness-Closure-Validation-Memo.md`
- dry-run/readiness messaging validation
- missing-env shell validation
- malformed-current-methodology reader/current-input validation
- explicit-DB historical reader validation

## Phase 2.1 Closure Evidence

Phase 2.1 is closed by:

- `docs/decisions/Phase-2.1-Settings-Environment-Bridge-Implementation-Validation-Memo.md`
- missing/empty/current-directory env path validation
- explicit-DB historical reader validation under empty env
- export redaction root hard-fail validation
- current-run/current-input fail-loud validation

## Current Recommendation

Phase 3 is now active.

Treat the active move as:

> **Phase 3 WSL degraded support hardening and future native-Linux preparation.**

Continue from the provider boundary implementation into bounded WSL degraded support. WSL 2 may be used as an explicitly degraded Linux-like execution target with measurement-grade false. Do not claim native Linux support complete until a later bare-metal Linux validation phase proves normal Linux CPU thermal interfaces and provider policy.

The WSL follow-up validation proves WSL degraded startup/readiness, persisted execution/provider evidence, report/export visibility, and explicit-DB historical reader behavior. The backend policy follow-up rejects Windows `llama-server.exe` execution through WSL interop before measurement startup, with a clear diagnostic and persisted failure reason. The Linux-native backend smoke validation proves a real in-WSL measurement run can complete with persisted `wsl_degraded` truth when `QUANTMAP_SERVER_BIN` points to a valid Linux backend. This is not native Linux support and not a reason to weaken WSL degraded telemetry semantics.
