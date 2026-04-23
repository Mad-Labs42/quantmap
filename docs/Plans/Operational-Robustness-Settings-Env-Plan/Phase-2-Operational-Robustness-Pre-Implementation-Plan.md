# Phase 2 Operational Robustness Pre-Implementation Plan

Status: pre-implementation plan, pending review  
Date: 2026-04-12  
Scope: Phase 2 Operational Robustness only

## 1. Purpose

Phase 2 Operational Robustness hardens the shell around QuantMap's now-stable trust bundle.

It exists to make QuantMap safer under malformed current config files, missing environment variables, brittle startup paths, unclear operational errors, and reader flows that should not collapse before they can use persisted historical evidence.

Phase 2 is not:

- telemetry provider architecture
- backend abstraction
- optimization/recommendation work
- full report consolidation
- broad packaging redesign
- broad runner decomposition
- a new trust model

The governing rule is:

> Robustness must protect or expose trust, never blur it.

## 2. Why Phase 2 Exists

Phase 1/1.1 validation confirmed QuantMap is snapshot-first and stable for historical trust. The same real-workflow validation also found the next blocker: the operational shell can still crash before historical trust evidence is used.

The concrete failure is `src.governance` loading the default profile at module import time. If a current profile file is malformed, Pydantic/YAML validation can crash the process. Because `quantmap.py` imports `runner`, `runner` imports `score`, and `score` imports `governance` before command dispatch, this can take down historical readers that should be able to operate from persisted snapshots.

That is a Phase 2 problem: the trust core is stable, but the shell is too eager, too global, and too brittle.

## 3. Robustness Goals

Phase 2 should make these things true:

1. `quantmap --help` and `quantmap init` do not require a valid current profile, server path, model path, or lab root.
2. Historical readers can start when current profile/registry files are malformed, if their required DB/snapshot evidence is present.
3. Current-run scoring and explicit current-input rescoring still fail loudly on malformed current methodology.
4. Current methodology loading happens at use points, not at module import.
5. CLI command dispatch imports only what the selected command needs.
6. Doctor/status/about classify current config failures instead of causing global startup crashes.
7. Missing env vars produce clear setup/remediation messages.
8. Dry-run remains structural validation and does not imply runtime readiness.
9. No Phase 2 change silently upgrades incomplete historical evidence from current files.
10. The pass stays small enough to avoid starting telemetry/provider, backend, report consolidation, or optimization work.

## 4. Locked Design Decisions

These decisions are ready for implementation unless review changes them:

1. Use lazy current-methodology getters, not import-time default profile/registry singletons.
2. Keep `src.governance` as the schema/parser home. Do not build a new governance service layer.
3. Keep historical trust readers snapshot-first through `src.trust_identity`.
4. Move heavy CLI imports into command handlers after argument parsing.
5. Keep current-input and writer paths fail-loud for invalid current methodology.
6. Add small structured operational error labels; do not build a generic error framework.
7. Make doctor reachable under broken current methodology and have it report profile/registry status explicitly.
8. Treat telemetry provider abstraction, backend adapters, report consolidation, optimization, and broad runner refactor as deferred.

Review decisions:

1. Decide how far to go on `src.config` import-time `QUANTMAP_LAB_ROOT` failure in this pass.
2. Decide exact degraded behavior for `quantmap status` when current methodology is invalid but historical DB reads are still possible.

## 5. Scope

### In Scope

- `src.governance` import-time profile/registry loading
- `src.score` import-time governance constants
- `quantmap.py` startup/import behavior
- reader startup robustness for snapshot-complete historical data
- current-methodology error classification
- doctor/status/about current-config diagnostics
- small env/path startup hardening where needed to make readers and init/help reachable
- dry-run readiness wording
- focused regression tests/probes

### Out Of Scope

- telemetry provider interfaces
- Linux/NVIDIA provider implementation
- backend adapter contract
- full settings/path framework
- full installed packaging redesign
- full report stack consolidation
- recommendation/optimization semantics
- root-cause attribution implementation
- broad runner decomposition

## 6. Workstreams

### Workstream A - Import-Time Governance Brittleness

Goal: make `src.governance` importable even when current default profile/registry files are missing or malformed.

Implementation intent:

- Keep Pydantic models, enums, `load_registry()`, `load_profile()`, and `validate_profile_against_registry()` importable.
- Replace import-time `BUILTIN_REGISTRY = load_registry()` and `DEFAULT_PROFILE = load_profile(...)` with lazy accessors.
- Add a narrow structured error type, for example `CurrentMethodologyLoadError`, carrying:
  - component: `registry` or `profile`
  - path if known
  - original exception summary
  - remediation hint
- Cache successful lazy loads to preserve current performance and deterministic behavior.
- Provide compatibility shims only where necessary, but avoid preserving import-time loading through a property-like trap that still crashes imports.

Do not:

- create a governance service object
- add plugin loading
- change methodology semantics
- weaken profile validation for current-run scoring

### Workstream B - Scoring Defaults and Current-Input Semantics

Goal: keep scoring fail-loud when current methodology is required, while avoiding current methodology loads during unrelated imports.

Implementation intent:

- Stop deriving `ELIMINATION_FILTERS` and `SCORE_WEIGHTS` from current profile at `src.score` import time.
- Replace them with lazy helpers or constants resolved only when current scoring/dry-run logic requires current methodology.
- Keep historical scoring through `load_methodology_for_historical_scoring()`.
- Preserve current behavior:
  - snapshot-complete historical scoring uses persisted methodology.
  - `legacy_partial` snapshot-locked rescore refuses.
  - explicit current-input mode loads and validates current profile/registry.

Do not:

- rewrite the scoring engine
- invent a new methodology store
- silently fall back to current files for historical scoring

### Workstream C - CLI Startup and Command-Local Imports

Goal: prevent one broken current dependency from killing every CLI command before dispatch.

Implementation intent:

- Keep `quantmap.py` startup limited to terminal bootstrap, dotenv loading, repo path setup, version import if safe, and argparse construction.
- Move imports for `runner`, `doctor`, `explain`, `export`, `compare`, `report_compare`, `rescore`, `server`, and config constants into the specific command functions that need them.
- Make import errors and operational load errors produce a short command-specific message and exit code.
- Ensure `quantmap --help` and `quantmap init` work without loading `src.runner`, `src.score`, `src.server`, or `src.governance`.

Do not:

- split the CLI into a package in this pass
- redesign all command handlers
- change command semantics beyond startup resilience and error clarity

### Workstream D - Historical Reader Robustness

Goal: allow snapshot-complete historical readers to run even if current files are broken.

Priority readers:

- `list`
- `explain`
- `compare`
- `audit`
- `export`
- historical report generation paths

Implementation intent:

- Ensure these readers do not import current scoring/governance modules unless they explicitly need current-input behavior.
- For commands that accept `--db`, prefer the explicit DB path before importing lab-root settings.
- Keep trust labels from `src.trust_identity` visible.
- If current profile/registry is invalid but historical snapshot evidence is complete, continue and display a warning.
- If historical evidence is incomplete, keep `legacy_partial`, `unknown`, or `incomplete` labels and do not use current files implicitly.

Do not:

- create a second trust reader
- merge report stacks
- weaken snapshot-locked behavior

### Workstream E - Diagnostics and Operator Messaging

Goal: make operational failures explain what failed, why it matters, and what the operator should do next.

Implementation intent:

- Extend doctor with separate current registry/profile checks using lazy governance loaders.
- Report malformed current profile as a current-input/config failure, not a historical trust failure.
- Add remediation hints:
  - fix current profile/registry file
  - run `quantmap doctor`
  - run `quantmap init`
  - pass `--db` for historical readers where supported
  - use explicit `--current-input` only when intentionally rescoring with current files
- Adjust `status` and `about` to show current methodology unavailable/blocked instead of crashing.
- Keep `DiagnosticReport`/`CheckResult` as the display structure; do not build a new diagnostics framework.

### Workstream F - Minimal Env/Path Startup Hardening

Goal: reduce unnecessary env-var blast radius without doing full path/settings architecture.

Implementation intent:

- Keep measurement commands strict about required env:
  - `QUANTMAP_LAB_ROOT`
  - `QUANTMAP_SERVER_BIN`
  - `QUANTMAP_MODEL_PATH`
- Do not require server/model env for `--help`, `init`, and historical readers that can use explicit DB paths.
- Where feasible, resolve reader `--db` before importing `LAB_ROOT`.
- Avoid changing `src.config` broadly unless review approves the import-time LAB_ROOT change.

Decision point:

- Option A: keep `src.config` fail-loud and route readers around it.
- Option B: make `src.config` expose lazy getters or a load result so missing lab root is command-classified.

Draft recommendation: start with Option A plus command-local imports. Escalate to Option B only if reader robustness remains awkward or duplicated.

### Workstream G - Migration/Error-Path Robustness

Goal: keep DB migrations trust-safe while improving operator clarity where errors surface.

Implementation intent:

- Keep duplicate snapshot detection fail-loud.
- Add or verify clear command-level handling for `SchemaVersionError` and duplicate snapshot migration errors.
- Add a focused validation probe for duplicate snapshot failure message and legacy DB migration path if practical.

Do not:

- redesign the migration framework
- add schema surfaces for Phase 2
- silently quarantine ambiguous trust duplicates

### Workstream H - Focused Validation Coverage

Goal: prove Phase 2 did not weaken trust while hardening the shell.

Validation scenarios:

1. Malform default profile; `quantmap explain <snapshot-complete-id>` still starts and uses historical snapshot evidence.
2. Malform default profile; `quantmap export <snapshot-complete-id>` still exports historical evidence or fails only on DB/export errors.
3. Malform default profile; `quantmap compare` for snapshot-complete campaigns still reaches methodology compatibility logic.
4. Malform default profile; `quantmap run` and explicit current-input rescore fail clearly.
5. Missing `QUANTMAP_SERVER_BIN`/`QUANTMAP_MODEL_PATH`; `quantmap --help` and `quantmap init` still work.
6. Missing or malformed current methodology; `doctor` reports current profile/registry status with remediation.
7. Dry-run output clearly says structural validation, not runtime readiness.
8. Snapshot-locked historical rescore still refuses `legacy_partial`.

## 7. File-Level Responsibilities

| File | Responsibility |
|---|---|
| `src/governance.py` | Remove import-time default registry/profile loading; add lazy current-methodology getters and structured load error. Keep schemas/parsers. |
| `src/score.py` | Remove import-time dependence on current `DEFAULT_PROFILE`/`BUILTIN_REGISTRY`; lazy-load current defaults only in current-scoring paths. Preserve snapshot scoring. |
| `quantmap.py` | Move heavy imports into command handlers; make help/init and historical readers reachable under broken current methodology. |
| `src/doctor.py` | Add explicit current registry/profile checks and clearer remediation messages. |
| `src/diagnostics.py` | Reuse existing status/check model; possibly add small fields only if needed for error classification. |
| `src/report.py` | Move `score_campaign` import into the branch that actually computes missing scores; keep report generation snapshot-first. |
| `src/report_campaign.py` | Keep lazy score import; verify no top-level governance import returns. |
| `src/explain.py` | Preserve historical trust-reader behavior; surface current-methodology warning only if relevant. |
| `src/compare.py` | Preserve trust-reader behavior; avoid current governance imports. |
| `src/report_compare.py` | No major change expected unless compare reporting needs operational warning display. |
| `src/export.py` | Avoid current config imports except when redaction needs lab-root fallback; keep run/export identity separation. |
| `src/audit_methodology.py` | Avoid top-level `LAB_ROOT` import where explicit `--db` can be used. |
| `rescore.py` | Keep snapshot-locked and current-input semantics; improve startup/import behavior if invoked through CLI or directly. |
| `src/config.py` | Review only for minimal env-loading boundary; avoid full settings framework unless approved. |
| `src/server.py` | Do not change backend behavior; ensure server/model env is loaded only by commands needing runtime measurement. |
| `src/runner.py` | Avoid broad refactor; adjust only if import-time score/config dependency changes require narrow updates. |

## 8. Sequence of Work

1. Add lazy governance loading boundary.
   - Make `src.governance` safe to import.
   - Add structured current-methodology load errors.
   - Update tests/probes for valid and invalid current profile.

2. Remove import-time scoring dependence on current governance.
   - Update `src.score` defaults.
   - Preserve snapshot historical scoring.
   - Verify current-input scoring still validates current files.

3. Localize CLI imports.
   - Refactor `quantmap.py` command imports.
   - Verify `--help` and `init` do not load runner/score/server/governance.

4. Harden historical readers.
   - Patch `report.py`, `audit_methodology.py`, and any reader still importing current config too early.
   - Prefer explicit DB paths before lab-root fallback.

5. Improve diagnostics and messages.
   - Add doctor checks for registry/profile.
   - Add status/about degraded behavior once review decision is settled.
   - Update dry-run wording.

6. Add focused validation probes.
   - Malformed profile reader tests.
   - Missing env startup tests.
   - Current-input fail-loud tests.
   - Legacy snapshot refusal regression.

7. Documentation/tracker follow-up.
   - Update K.I.T. only after implementation and validation.
   - Do not edit historical validation memos retroactively.

## 9. Verification Plan

Required validation:

| Scenario | Expected Result |
|---|---|
| Default profile malformed, run `quantmap --help` | Help renders; no governance import crash. |
| Default profile malformed, run `quantmap init` | Init starts; no governance/server import crash before user action. |
| Default profile malformed, run historical `explain` on snapshot-complete campaign | Reader starts, uses persisted methodology, warns current profile invalid if detected. |
| Default profile malformed, run historical `export` on snapshot-complete campaign | Export uses persisted run identity; no current profile crash. |
| Default profile malformed, run `run --validate` | Fails clearly as current methodology/config invalid. |
| Default profile malformed, run explicit current-input rescore | Fails clearly unless current methodology is fixed. |
| Legacy partial methodology rescore without `--current-input` | Still refuses snapshot-locked rescore. |
| Missing server/model env, run `--help` and `init` | Works. |
| Missing server/model env, run `doctor` | Reports missing runtime paths with remediation. |
| Missing lab root, run explicit-DB historical reader if supported | Uses explicit DB or reports a clear missing-lab fallback error. |
| DB migration duplicate snapshot condition | Fails loudly with manual remediation message. |
| Dry-run output | States structural validation and points to doctor for readiness. |

Suggested checks:

- compile/import smoke checks for `src.governance`, `src.trust_identity`, `src.explain`, `src.export`, and `quantmap`.
- direct malformed-profile fixture/probe.
- direct missing-env subprocess probe.
- command smoke tests in plain mode.

## 10. Risks and Controls

| Risk | Control |
|---|---|
| Lazy loading hides current profile damage | Current-run/current-input paths must call strict current-methodology getters and fail loudly. Doctor must report profile errors. |
| Historical readers accidentally use current files | Keep `src.trust_identity` as the read path and preserve legacy labels. Add malformed-profile drift tests. |
| CLI refactor changes command behavior | Use command smoke tests before/after and keep command-local imports minimal. |
| Settings hardening becomes a framework | Start with command-local imports and explicit `--db` precedence. Defer full settings design. |
| Report changes become report consolidation | Only move imports/error labels. Do not merge report stacks. |
| Telemetry/backend work sneaks in | Treat provider/backend changes as out of scope unless needed only for error message wording. |
| Migration errors become softer than trust requires | Keep duplicate snapshot fail-loud behavior. Improve display, not semantics. |

## 11. Exit Criteria

Phase 2 Operational Robustness can be called complete when:

1. `src.governance` imports without loading current default profile/registry files.
2. Current methodology loads through explicit lazy getters with structured errors.
3. `quantmap.py` no longer imports runner/score/governance/server before command selection.
4. Historical readers can run from snapshot-complete DB evidence when current profile is malformed.
5. Current-run/current-input paths fail clearly when current profile/registry is malformed.
6. `doctor` reports current registry/profile health with remediation.
7. `--help` and `init` work without complete runtime env.
8. Dry-run messaging no longer implies readiness.
9. Snapshot-locked legacy refusal behavior remains intact.
10. No telemetry provider, backend adapter, report consolidation, optimization, or broad runner framework work was introduced.

## 12. Open Decisions Requiring Review

### Decision 1 - `src.config` import-time lab root

Question: Should Phase 2 change `src.config` so `QUANTMAP_LAB_ROOT` is no longer required at import time?

Recommendation: start conservatively. Keep `src.config` behavior for now and route reader commands around it with command-local imports and explicit `--db` precedence. If implementation shows repeated awkward special-casing, then approve a narrow lazy `get_lab_root()` style boundary.

Decision status: needs approval if implementation wants to change `src.config`.

### Decision 2 - `quantmap status` degraded behavior

Question: Should `status` run in degraded mode when current methodology is invalid?

Recommendation: yes, if startup can show:

- software version
- lab root if known
- DB campaign count if DB is reachable
- current methodology status as `blocked`
- doctor/remediation hint

It must not imply current methodology is valid.

Decision status: needs approval.

## Final Recommendation

Proceed to implementation only after reviewing the two open decisions. The first implementation pass should focus on:

1. lazy governance loading
2. command-local CLI imports
3. historical reader startup resilience
4. doctor/status/about current-config diagnostics
5. focused malformed-profile and missing-env validation

This is a contained robustness pass, not a hidden subsystem effort, as long as the deferred boundaries stay enforced.
