# Phase 2.1 Settings/Environment Bridge Interrogation

Status: pre-implementation interrogation  
Date: 2026-04-12  
Scope: Phase 2.1 settings/environment bridge only

## Purpose

This artifact interrogates the narrow bridge between closed Phase 2 Operational Robustness and future Phase 3 Platform Generalization.

Phase 2 closed the brittle current-methodology shell. Phase 2.1 must now make the current settings/environment boundary explicit enough that Phase 3 telemetry/provider work does not inherit hidden lab-root, empty-env, or local-path assumptions.

This is not telemetry provider architecture, backend abstraction, packaging overhaul, runner decomposition, report consolidation, or optimization work.

## Evidence Snapshot

| Evidence | Finding | Status |
|---|---|---|
| `src/config.py:38-45` | `QUANTMAP_LAB_ROOT` is checked only for `None`; empty string becomes `Path('')`, which resolves to `Path('.')`. | verified |
| direct probe with `QUANTMAP_LAB_ROOT=''` | `src.config.LAB_ROOT` printed as `'.'` and resolved to the repo working directory. | verified |
| `src/server.py:67-84` | `QUANTMAP_SERVER_BIN` and `QUANTMAP_MODEL_PATH` are checked only for `None`; empty strings become `Path('.')`. | verified |
| direct probe with empty lab/server/model env | `src.server.SERVER_BIN == '.'`, `src.server.MODEL_PATH == '.'`, and `LOGS_DIR == logs`. | verified |
| `quantmap.py:68-77` | CLI helper `_env_path()` treats empty env values as missing and returns `None`; this is safer but inconsistent with `src.config` / `src.server`. | verified |
| `src/export.py:207-221` | manifest and redaction logic import `src.config.LAB_ROOT`, so `export --strip-env` can redact against a hidden `Path('.')` root. | verified |
| `src/report.py:131`, `src/report_campaign.py:40` | report modules have module-level lab-root fallback defaults and empty env can become `Path('.')`; missing env defaults to `D:/Workspaces/QuantMap`. | verified |
| Phase 2 closure validation | explicit-DB historical readers work under empty env in several cases, but settings/environment policy remains carry-forward. | verified |

## A. Missing vs Empty Environment Semantics

### Question

What should missing and empty required environment values mean after Phase 2.1?

### Answer

Missing and empty required env vars must both mean `unavailable`, not `Path('.')`.

The minimum required vars for this bridge are:

- `QUANTMAP_LAB_ROOT`
- `QUANTMAP_SERVER_BIN`
- `QUANTMAP_MODEL_PATH`

For these, whitespace-only values should also be treated as empty/unavailable.

### Evidence

- `src.config.py:38-45` only checks `os.getenv("QUANTMAP_LAB_ROOT") is None`.
- `src.server.py:67-84` only checks server/model env values for `None`.
- `quantmap.py:68-77` already treats falsy env values as missing in CLI-local code.
- Direct probes confirmed empty env values resolve to `Path('.')` in config/server/report modules.

### Status

verified

### Decision

Use one shared env-path normalization rule: `None`, `""`, and whitespace-only strings are unavailable. Do not preserve empty-string-as-current-directory behavior.

## B. Preventing Required Paths From Becoming `Path('.')`

### Question

Where can required paths still become `Path('.')`, and what is the smallest safe correction?

### Answer

The current direct risk lives in:

- `src.config.LAB_ROOT`
- `src.server.SERVER_BIN`
- `src.server.MODEL_PATH`
- `src.report.LAB_ROOT`
- `src.report_campaign.LAB_ROOT`
- any consumer importing those module constants instead of using explicit paths or safer CLI helpers

The smallest correction is a narrow stdlib-only settings/env helper used by `src.config`, `src.server`, `quantmap.py`, `src.doctor`, and `src.export`. It should not become a general settings framework.

### Evidence

- `src.config.py:45`: `LAB_ROOT: Path = Path(_lab_root_raw)`.
- `src.server.py:74`, `src.server.py:84`: server/model paths are assigned directly from raw env.
- `src.report.py:131` and `src.report_campaign.py:40` use direct `Path(os.getenv(...))` fallback logic.
- Probe: empty `QUANTMAP_LAB_ROOT` produced `'.'`; empty server/model env produced `'.'`.

### Status

verified

### Decision

Add a narrow shared path normalization boundary and update the high-risk import-time constants to use it. If a required import-time constant remains, it must fail loudly on missing/empty values rather than silently becoming `Path('.')`.

## C. Explicit-DB Historical Reader Independence

### Question

Which historical readers must remain independent of lab-root settings when explicit `--db` is supplied?

### Answer

The minimum Phase 2.1 historical reader independence set is:

- `quantmap explain <ID> --db <path>`
- `quantmap audit <A> <B> --db <path>`
- `quantmap compare <A> <B> --db <path> --output <path>`
- `quantmap export <ID> --db <path> --output <path>`

These should not require `QUANTMAP_LAB_ROOT` when their needed input/output paths are explicit.

### Evidence

- Phase 2 closure validation verified explicit-DB `explain`, `audit`, `compare`, and `export` under empty env.
- `quantmap.py:256`, `quantmap.py:284`, `quantmap.py:296`, `quantmap.py:308-309`, and `quantmap.py:357-386` already prefer explicit `--db` / `--output` before default lab-root derivation.
- `src.audit_methodology.py:114-116` imports `LAB_ROOT` only when `--db` is absent.

### Status

verified

### Decision

Preserve explicit-DB reader independence as a non-regression invariant. Any Phase 2.1 helper must support reader-local explicit path override before consulting current lab settings.

## D. Export Redaction Root Semantics

### Question

What should `export --strip-env` use as its redaction authority?

### Answer

`export --strip-env` needs an explicit trustworthy redaction root. It must not import `src.config.LAB_ROOT` and silently redact against `Path('.')`.

Recommended Phase 2.1 behavior:

1. Accept an optional explicit redaction root in the export internals, and consider a CLI `--redaction-root` only if needed after implementation pressure.
2. If `--strip-env` is requested and no valid lab root/redaction root exists, complete export only if the manifest clearly records redaction as incomplete, or fail clearly if incomplete redaction would be misleading.
3. Redaction status must distinguish `not_requested`, `applied:<count>`, `incomplete:no_valid_redaction_root`, and `failed:<reason>`.

### Evidence

- `src.export.py:79-82` calls `_redact_env(dest_conn)` when `strip_env` is true.
- `src.export.py:207-221` imports `src.config.LAB_ROOT` both in manifest value replacement and `_redact_env`.
- Phase 2 closure validation allowed export under empty env for Phase 2, but explicitly carried redaction root policy to Phase 2.1.

### Status

verified, with one decision detail requiring implementation judgment

### Decision

Do not add broad export redesign. Add only enough redaction-root semantics to avoid false privacy claims and hidden `Path('.')` redaction.

## E. Minimum Shared Settings/Environment Contract

### Question

What is the minimum shared contract Phase 3 provider work needs?

### Answer

Phase 3 providers need a small contract that answers:

- whether lab root is available
- whether server binary path is available
- whether model path is available
- source of each value
- status of each value: `available`, `missing`, `empty`, `invalid`
- diagnostic/remediation text
- derived DB/results/logs/state paths only when lab root is available

They do not need:

- provider discovery
- telemetry provider objects
- backend adapters
- OS-specific telemetry policies
- a full settings framework

### Evidence

- `docs/decisions/Phase-2.1-Bridge-Recommendation.md` requires a settings/environment input contract before Phase 3.
- `docs/system/known_issues_tracker.md` QM-005 makes settings/path decoupling the active Phase 2.1 bridge.
- `src.server.py` currently couples provider-adjacent startup paths to import-time constants.

### Status

verified / inferred

### Decision

Create a narrow stdlib-only module, tentatively `src/settings_env.py`, with small dataclasses/functions. It should not import other QuantMap modules. `src.config.py` and `src.server.py` may consume it, preserving `src.config` as infrastructure authority without turning it into a framework.

## F. Boundary Enforcement

### Question

How do we implement Phase 2.1 without bloating `runner.py`, `report_campaign.py`, or similar crowded modules?

### Answer

The bridge should centralize path/env normalization in a tiny helper and change call sites surgically. Avoid adding new policy branches inside `src.runner.py` or report modules.

Allowed small call-site changes:

- replace direct env parsing with helper calls
- pass explicit lab/output/redaction paths already known at CLI boundaries
- improve user-facing error text

Disallowed:

- moving provider discovery into `runner.py`
- adding backend abstraction to `server.py`
- adding report consolidation work to `report_campaign.py`
- introducing broad app initialization or dependency injection

### Evidence

- `docs/system/architecture.md` now records boundary discipline.
- `src.runner.py` and `src.report_campaign.py` are already tracked as crowded/high-blast-radius modules under QM-017/QM-004.
- Phase 2.1 needs a bridge, not a full architecture split.

### Status

verified

### Decision

Implement through a small shared settings/env helper plus narrow call-site edits. If touching `runner.py`, only change imports/path usage needed to consume normalized constants.

## Resolution Matrix

| Issue | Current reality | Why it matters | Scope fit | Design options | Recommended resolution | Explicitly deferred | Decision status |
|---|---|---|---|---|---|---|---|
| Empty required env becomes `Path('.')` | `src.config` and `src.server` check only `None`; reports also use direct env fallback | Can redirect DB/logs/redaction to repo/current directory silently | Phase 2.1 | Patch each site; add helper; full settings framework | Add narrow stdlib-only helper and update high-risk sites | full settings framework | ready |
| CLI and config semantics disagree | `quantmap._env_path()` treats empty as missing; config/server treat empty as current dir | Different commands see different worlds | Phase 2.1 | Leave divergence; move all commands to CLI helpers; shared helper | Shared helper consumed by CLI/config/server/doctor/export | broad app initialization | ready |
| Export redaction root hidden behind `src.config.LAB_ROOT` | `export --strip-env` imports LAB_ROOT internally | Can overclaim privacy/completeness | Phase 2.1 | Fail if no lab root; incomplete label; add CLI redaction root | Internal explicit redaction root, incomplete/fail behavior; CLI flag only if needed | full case-file redesign | ready |
| Explicit-DB readers can regress | Phase 2 proved they can work, but new settings code could accidentally require lab root | Would undo Phase 2 reader independence | Phase 2.1 | Test only; helper supports explicit overrides | Preserve explicit path precedence and add smoke tests | report consolidation | ready |
| `src.server` import-time runtime constants | Empty server/model path becomes `Path('.')`; import creates logs dir | Provider work could inherit backend/global startup assumptions | Phase 2.1 / Phase 3 gate | Full backend adapter; lazy getter; normalized constants | Normalize missing/empty now; defer backend adapter/lazy provider design | backend abstraction | ready |
| Report module lab-root fallbacks | Missing env defaults to `D:/Workspaces/QuantMap`; empty env becomes `Path('.')` | Can write regenerated reports to unexpected locations when lab_root not injected | Phase 2.1 | Rewrite reports; require lab_root; normalize fallback | Normalize fallback via helper and prefer injected lab_root; do not consolidate reports | report stack consolidation | ready |
| Phase 3 provider settings inputs undefined | Provider work lacks a common settings contract | Telemetry abstraction could recreate local assumptions | Phase 2.1 | Document only; implement helper; full provider design | Implement helper and document allowed provider inputs | telemetry providers | ready |

## Future-Fit Check

This bridge makes Phase 3 easier if it stays narrow:

- telemetry providers can depend on explicit settings availability instead of importing `src.server`
- doctor/status can distinguish setup failure from evidence quality
- export can avoid false privacy claims
- reader commands keep explicit-DB independence
- backend and telemetry abstractions can later start from clear input contracts

It makes Phase 3 harder if it expands into:

- a generic settings framework before the needed fields are known
- scattered path conditionals across `runner.py`, `report_campaign.py`, and `telemetry.py`
- provider discovery hidden inside current server/bootstrap modules
- report-writing behavior changes unrelated to path safety

## Final Interrogation Conclusion

Phase 2.1 is a contained bridge, not a hidden subsystem effort.

The implementation should lock one rule:

> Required runtime paths are either explicit, available, and valid enough for the operation, or they are unavailable with a structured reason. They must never silently become `Path('.')`.

No human approval appears required before writing the implementation plan, unless the user wants `export --strip-env` to hard-fail without a valid redaction root instead of allowing an explicitly labeled incomplete-redaction export.
