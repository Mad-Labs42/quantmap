# Phase 2.1 Settings/Environment Bridge Pre-Implementation Plan

Status: pre-implementation plan  
Date: 2026-04-12  
Scope: narrow settings/environment bridge before Phase 3

## 1. Purpose

Phase 2.1 exists to close the settings/environment boundary gap between the closed Phase 2 Operational Robustness work and future Phase 3 Platform Generalization.

The goal is simple:

> Required runtime paths must never silently become `Path('.')`, and explicit-DB historical readers must remain independent of current lab environment when their required paths are supplied.

This plan is implementation-ready once reviewed, but it is not implementation.

## 2. Why Phase 2.1 Exists

Phase 2 closed the brittle current-methodology shell. It proved that historical readers can survive malformed or missing current state when they have explicit persisted evidence.

The remaining risk is different:

- `src.config` still turns empty `QUANTMAP_LAB_ROOT` into `Path('.')`
- `src.server` still turns empty `QUANTMAP_SERVER_BIN` / `QUANTMAP_MODEL_PATH` into `Path('.')`
- report modules still have direct module-level lab-root fallback logic
- export redaction still imports `src.config.LAB_ROOT`
- Phase 3 provider work needs a common settings/environment contract before telemetry/provider abstraction begins

Phase 3 must not start by building telemetry providers on top of these unresolved settings semantics.

## 3. Goals

Phase 2.1 is complete when:

- missing and empty required env vars are treated consistently
- required paths never silently resolve to `Path('.')`
- current-run paths fail loudly and clearly when required env is unavailable
- explicit-DB historical readers keep working without lab-root env
- `export --strip-env` uses a trustworthy redaction root or reports/fails incomplete redaction honestly
- Phase 3 has a minimal documented settings/environment input contract
- implementation does not bloat `src.runner.py`, `src.report_campaign.py`, `src.telemetry.py`, or backend/report modules

## 4. Locked Design Decisions

| Decision | Ruling |
|---|---|
| Missing vs empty env | `None`, `""`, and whitespace-only env values all mean unavailable for required runtime paths. |
| `Path('.')` | Disallowed as an implicit required-path fallback. It may only appear if the user explicitly passes `.` as a CLI path where that command allows relative paths. |
| Shared boundary shape | Add a narrow stdlib-only helper module, tentatively `src/settings_env.py`. Do not build a general settings framework. |
| `src.config` role | Keep `src.config` as infrastructure constants authority, but make its env parsing use the shared normalization rule. |
| Explicit-DB readers | Explicit `--db` / `--output` arguments outrank lab-root defaults. Readers must not import lab-root settings when explicit paths are sufficient. |
| Export redaction | Redaction root must be explicit/validated enough to be trustworthy. Hidden `src.config.LAB_ROOT` redaction is disallowed. |
| Phase 3 provider inputs | Define input contract only; do not implement telemetry providers. |
| Boundary enforcement | Prefer surgical helper extraction and call-site adaptation. Avoid broad edits to `runner.py`, `report_campaign.py`, and `telemetry.py`. |

## 5. Scope

### In Scope

- normalize env-path parsing for:
  - `QUANTMAP_LAB_ROOT`
  - `QUANTMAP_SERVER_BIN`
  - `QUANTMAP_MODEL_PATH`
- prevent empty env values from becoming `Path('.')`
- update CLI/path helpers to consume the shared semantics
- update `src.config` and `src.server` import-time constants to fail loudly on missing/empty required values
- preserve explicit-DB historical reader independence
- tighten `export --strip-env` redaction root behavior
- document the minimum settings/environment contract for Phase 3 providers
- add focused smoke/regression tests or probe scripts as appropriate

### Out Of Scope

- telemetry provider implementation
- Linux/NVIDIA telemetry support
- backend adapter implementation
- broad settings framework
- packaging overhaul
- report consolidation
- runner decomposition
- optimization/recommendation work
- broad refactor of `src.runner.py`, `src.report_campaign.py`, or `src.telemetry.py`

## 6. Workstreams

### Workstream A: Shared Env Path Semantics

Create a small stdlib-only module, tentatively [settings_env.py](D:/Workspaces/QuantMap_agent/src/settings_env.py).

Recommended minimal types/functions:

- `EnvPathStatus`: `available`, `missing`, `empty`, `invalid`
- `EnvPath`: dataclass with `name`, `raw`, `path`, `status`, `message`, `recommendation`
- `read_env_path(name: str, required: bool = False) -> EnvPath`
- `require_env_path(name: str, purpose: str) -> Path`
- `derive_lab_paths(lab_root: Path) -> LabPaths`

Rules:

- strip whitespace before deciding empty/unavailable
- do not call `.resolve()` as a validation substitute
- do not require paths to exist unless the caller asks for existence checks
- use clear messages such as `QUANTMAP_LAB_ROOT is empty; set it to a lab directory or pass --db/--output where supported`

### Workstream B: Config and Server Boundary

Update:

- [config.py](D:/Workspaces/QuantMap_agent/src/config.py)
- [server.py](D:/Workspaces/QuantMap_agent/src/server.py)

Implementation intent:

- `src.config.LAB_ROOT` fails on missing or empty lab root
- `src.server.SERVER_BIN` and `src.server.MODEL_PATH` fail on missing or empty values
- server logs dir is not created under `logs` because empty lab root became `Path('.')`

Keep:

- `CONFIGS_DIR` / `REQUESTS_DIR` repo-root defaults
- `DEFAULT_HOST` / `PRODUCTION_PORT`
- existing backend behavior when required env is valid

Do not:

- implement backend adapters
- move server lifecycle out of `src.server`
- add provider discovery

### Workstream C: CLI Path Resolution

Update:

- [quantmap.py](D:/Workspaces/QuantMap_agent/quantmap.py)

Implementation intent:

- replace `_env_path()` / `_load_lab_root()` with shared helper usage
- keep `--db` and `--output` precedence
- ensure default DB/results path derivation uses lab root only after lab root is available
- keep help/status/doctor/about usable under missing/empty env
- preserve current path-resolution error hint style

Expected command behavior:

- `quantmap --help`: works without env
- `quantmap status`: works in degraded mode
- `quantmap doctor`: works and classifies missing/empty env
- `quantmap about`: works and marks lab/DB unavailable
- `quantmap explain --db`: works without lab root
- `quantmap audit --db`: works without lab root
- `quantmap compare --db --output`: works without lab root
- `quantmap export --db --output`: works without lab root unless `--strip-env` needs a missing redaction root decision

### Workstream D: Doctor and Diagnostics

Update:

- [doctor.py](D:/Workspaces/QuantMap_agent/src/doctor.py)

Implementation intent:

- classify missing vs empty separately where useful
- keep current methodology diagnostics separate from lab/server/model path diagnostics
- avoid importing `src.server` just to inspect env state
- preserve degraded status behavior introduced in Phase 2

Desired labels:

- `missing`: env var absent
- `empty`: env var set but blank/whitespace
- `not_found`: path supplied but does not exist
- `unavailable`: umbrella operator-facing state when detail is not needed

### Workstream E: Export Redaction Root Semantics

Update:

- [export.py](D:/Workspaces/QuantMap_agent/src/export.py)
- [quantmap.py](D:/Workspaces/QuantMap_agent/quantmap.py), only if CLI option pressure appears during implementation

Implementation intent:

- pass a redaction root into export internals when known
- stop importing `src.config.LAB_ROOT` inside `_write_manifest()` and `_redact_env()`
- redaction status should be schema-aware and honest

Recommended behavior:

- if `--strip-env` and valid redaction root exists: redact and record `schema_aware_applied:<count>`
- if `--strip-env` and no valid root exists: either fail clearly or export with `redaction_status=incomplete:no_valid_redaction_root`
- final console privacy label must not say simply `Stripped/Redacted` when redaction is incomplete

Decision requiring review:

- choose hard-fail vs labeled incomplete export when `--strip-env` is requested without a valid redaction root.

Default recommendation:

- fail clearly for ordinary CLI use, because privacy redaction is an operator promise
- allow labeled incomplete behavior only if an internal/test caller explicitly asks for permissive export

### Workstream F: Report Fallback Containment

Update only if necessary:

- [report.py](D:/Workspaces/QuantMap_agent/src/report.py)
- [report_campaign.py](D:/Workspaces/QuantMap_agent/src/report_campaign.py)

Implementation intent:

- prevent empty env from becoming report output root `Path('.')`
- prefer injected `lab_root` where already supported
- use shared helper for module-level fallback only if keeping fallback is necessary

Do not:

- consolidate report stacks
- rewrite report layout
- change report truth/identity model

### Workstream G: Phase 3 Settings Contract Documentation

Update or create a small current-state doc section in:

- [architecture.md](D:/Workspaces/QuantMap_agent/docs/system/architecture.md), or
- a new focused decision note only if needed

Minimum provider input contract:

- provider discovery must not import `src.server`
- provider diagnostics can ask for lab root availability, but must tolerate unavailable lab root where read-only diagnostics allow it
- backend path availability is separate from telemetry provider availability
- missing/degraded telemetry must be represented as evidence quality, not hidden setup state
- provider work must not add new hardcoded lab-root, Windows, CUDA, or HWiNFO assumptions

## 7. File-Level Responsibilities

| File | Responsibility in Phase 2.1 |
|---|---|
| `src/settings_env.py` | New narrow env/path normalization helper; stdlib-only; no orchestration. |
| `src/config.py` | Infrastructure constants use shared missing/empty semantics; no `Path('.')` required-path fallback. |
| `src/server.py` | Backend-required paths use shared missing/empty semantics; no provider abstraction. |
| `quantmap.py` | CLI default path resolution and degraded behavior consume shared helper; preserve explicit path precedence. |
| `src/doctor.py` | Operator diagnostics classify missing/empty/not-found without importing backend startup state. |
| `src/export.py` | Redaction root passed explicitly/validated; no hidden `LAB_ROOT` import for stripping. |
| `src/report.py` | Only normalize fallback lab-root behavior if required; prefer existing injected `lab_root`. |
| `src/report_campaign.py` | Same as report; no report consolidation. |
| `rescore.py` | Review because it imports `src.config` at top level; change only if empty lab-root behavior makes it misleading. |
| `docs/system/architecture.md` | Record Phase 3 settings/provider input contract if needed. |
| `docs/system/known_issues_tracker.md` / `docs/system/TO-DO.md` | Update only after implementation/validation. |

## 8. Sequence Of Work

1. Add `src/settings_env.py` with the narrow dataclasses/functions and unit-level tests/probes.
2. Update `src.config` to use the helper for `QUANTMAP_LAB_ROOT`.
3. Update `src.server` to use the helper for `QUANTMAP_SERVER_BIN` and `QUANTMAP_MODEL_PATH`.
4. Update `quantmap.py` to use the helper while preserving explicit `--db` / `--output` precedence.
5. Update `src.doctor` diagnostics to show missing vs empty cleanly.
6. Update `src.export` redaction root handling and privacy/status output.
7. Contain report fallback behavior if probes still show `Path('.')` or stale default output roots.
8. Add/record validation evidence.
9. Update living trackers only after validation supports closure.

## 9. Verification Plan

### Required Smoke Probes

- Empty `QUANTMAP_LAB_ROOT` does not import `src.config.LAB_ROOT` as `Path('.')`; it fails with a clear settings error.
- Empty `QUANTMAP_SERVER_BIN` / `QUANTMAP_MODEL_PATH` do not import as `Path('.')`.
- `quantmap --plain --help` works with missing/empty env.
- `quantmap --plain status` works with missing/empty env and marks lab/server/model as blocked/unavailable.
- `quantmap --plain doctor` works with missing/empty env and distinguishes missing vs empty where applicable.
- `quantmap --plain about` works with missing/empty env.
- `quantmap --plain explain <ID> --db <path>` works with missing/empty lab env.
- `quantmap --plain audit <A> <B> --db <path>` works with missing/empty lab env.
- `quantmap --plain compare <A> <B> --db <path> --output <path>` works with missing/empty lab env.
- `quantmap --plain export <ID> --db <path> --output <path> --lite` works with missing/empty lab env.
- `quantmap --plain export <ID> --db <path> --output <path> --lite --strip-env` either fails clearly without valid redaction root or records incomplete redaction honestly.
- Current-run commands still fail loudly when required lab/server/model paths are unavailable.

### Regression Checks

- No command starts writing to repo-root `db`, `logs`, `results`, or `state` because env was empty.
- No redaction uses repo root/current working directory as hidden lab root.
- No new dependency from provider-adjacent docs/code to `src.server` for environment discovery.
- `runner.py` and `report_campaign.py` do not gain broad settings/provider policy code.

## 10. Risks And Controls

| Risk | Control |
|---|---|
| Helper grows into settings framework | Keep helper stdlib-only, path-only, no provider/backend policy. |
| Explicit-DB readers regress | Test explicit `--db` / `--output` commands under missing/empty env. |
| Export overclaims privacy | Require trustworthy redaction root or honest failure/incomplete status. |
| Current-run paths become too permissive | Keep fail-loud behavior for run/rescore/current-input paths requiring current state. |
| Phase 3 sneaks in early | No provider implementation, no backend adapter, no telemetry policy redesign. |
| God-object growth | No broad additions to `runner.py`, `report_campaign.py`, or `telemetry.py`; use helper and narrow call-site changes. |

## 11. Exit Criteria

Phase 2.1 can close when:

- required path env semantics are centralized and consistent
- empty required env vars no longer become `Path('.')`
- explicit-DB historical readers remain independent
- export redaction root semantics are honest and validated
- current-run/current-input paths still fail loudly when required settings are unavailable
- Phase 3 provider settings input contract is documented
- K.I.T. QM-005 has validation evidence for this bridge or a precise remaining carry-forward
- TODO-031 is closed or split into any truly remaining follow-up

## 12. Open Decisions Requiring Review

### Export redaction without valid root

Decision needed:

- Should `export --strip-env` hard-fail when no trustworthy redaction root exists?
- Or may it complete with `redaction_status=incomplete:no_valid_redaction_root` and a non-privacy-claiming console label?

Recommendation:

- Hard-fail for CLI `--strip-env` by default.
- Reserve labeled incomplete behavior for explicit internal/permissive callers only if needed.

No other approval appears required before implementation.

## 13. Final Recommendation

Proceed with Phase 2.1 as a contained bridge.

The first implementation move should be the narrow `src/settings_env.py` helper, followed by surgical call-site adoption in `src.config`, `src.server`, `quantmap.py`, `src.doctor`, and `src.export`.

Phase 3 should remain pending until the bridge passes validation.
