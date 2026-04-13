# Phase 2 Operational Robustness Interrogation

Status: pre-implementation design interrogation  
Date: 2026-04-12  
Scope: Phase 2 Operational Robustness only

## Purpose

Phase 1 and Phase 1.1 made the historical trust model stable. Phase 2 now needs to harden the operational shell around that trusted core without weakening snapshot-first guarantees.

This document asks and answers the design questions that should be resolved before implementation begins. It is not an implementation plan by itself and it is not a broad audit.

## Evidence Basis

Primary grounding documents:

- `docs/decisions/Phase-1.1-Real-Workflow-Validation-Memo.md`
- `docs/system/known_issues_tracker.md`
- `docs/system/TO-DO.md`
- `docs/AUDITS/4-11/Post-Audit-Synthesis-Memo.md`
- `docs/system/trust_surface.md`
- `docs/system/architecture.md`
- `docs/system/methodology_lifecycle.md`

Primary code inspected:

- `quantmap.py`
- `rescore.py`
- `src/governance.py`
- `src/config.py`
- `src/server.py`
- `src/runner.py`
- `src/score.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/compare.py`
- `src/export.py`
- `src/explain.py`
- `src/audit_methodology.py`
- `src/trust_identity.py`
- `src/doctor.py`
- `src/diagnostics.py`

## A. Phase 2 Scope Clarity

| Question | Answer | Evidence | Status |
|---|---|---|---|
| What exactly counts as Operational Robustness now? | Operational Robustness means making the current trusted system survive ordinary shell/config/environment damage in predictable ways: malformed current profile files, missing env vars, bad paths, missing runtime files, reader startup failures, unclear remediation messages, and avoidable import-time crashes. It does not mean adding new trust authority, providers, backends, recommendations, or report architecture. | Real-workflow validation calls out the brittle shell constraint. K.I.T. marks QM-022 as the first Phase 2 blocker and QM-005/QM-001/QM-009/QM-010 as related robustness items. | verified |
| What belongs in Phase 2 vs later architecture/generalization? | Phase 2 should handle lazy current-state loading, CLI startup isolation, reader behavior under broken current files, operator-facing error classification, small settings/path hardening, and diagnostic checks. Later phases should handle telemetry provider architecture, backend abstraction, full runner decomposition, report consolidation, packaging overhaul, and optimization semantics. | Post-audit synthesis separates Phase 2 boundary stabilization from Phase 3 telemetry/provider generalization and Phase 4 optimization. K.I.T. keeps QM-018, QM-019, QM-020, QM-021 as broader work. | verified |
| What robustness problems are explicitly surfaced? | QM-022: import-time default profile loading can crash readers. QM-005: lab-root/path assumptions reduce portability. QM-009: dry-run can be mistaken for readiness. QM-010: optional context/characterization failures need stronger evidence-quality signaling. QM-001: installed command/bootstrap is brittle. TODO-017: design centralized settings/path resolution. | `docs/system/known_issues_tracker.md`; `docs/system/TO-DO.md`; real-workflow validation memo. | verified |
| What would be dangerous Phase 2 scope creep? | Building a generic app initialization framework, telemetry provider interfaces, backend adapters, report stack consolidation, recommendation artifacts, multi-platform packaging redesign, or broad runner refactor would be scope creep. Phase 2 should create narrow error/loading boundaries that later work can use. | Phase 1.1 plan explicitly deferred provider/backend/report/optimization work. Post-audit synthesis warns against provider overreach and shallow splits. | verified |

Scope resolution: Phase 2 should be a contained shell-hardening pass centered on import-time and current-file failure boundaries, plus minimal diagnostics and messaging. It should not weaken historical snapshot behavior and should not start Phase 3 platform work.

## B. Import-Time / Startup-Time Brittleness

| Question | Answer | Evidence | Status |
|---|---|---|---|
| Which modules currently do meaningful work at import time? | `src.governance` loads and validates the registry and default profile at import time. `src.config` requires `QUANTMAP_LAB_ROOT` at import time. `src.server` loads `.env`, requires server/model env vars, and creates lab/log directories at import time. `src.runner` loads `.env`, imports config, imports score, and defines path constants from env-derived roots. `src.score` imports governance and materializes `ELIMINATION_FILTERS`/`SCORE_WEIGHTS` from live default profile at import time. `quantmap.py` imports config, runner, doctor, explain, export, version, and rescore before command dispatch. | `src/governance.py:545-550`; `src/config.py:38-45`; `src/server.py:47-87` and `src/server.py:115-116`; `src/runner.py:61-75`; `src/score.py:60-75`; `quantmap.py:54-64`. | verified |
| Which imports can fail because of malformed profile/config data? | A malformed default profile can fail `src.governance` import. Because `src.score` imports governance, `src.runner` imports score, and `quantmap.py` imports runner before argparse dispatch, a malformed current profile can crash the whole CLI before a historical reader can run. | `src/governance.py:503-550`; `src/score.py:60-75`; `src/runner.py:67`; `quantmap.py:54-64`; validation memo brittle shell finding. | verified |
| Does `src.governance` still load `DEFAULT_PROFILE` at module import time? | Yes. `BUILTIN_REGISTRY = load_registry()`, `DEFAULT_PROFILE = load_profile("default_throughput_v1")`, and validation all run at module import. | `src/governance.py:545-550`. | verified |
| If that import fails, which commands/readers fail catastrophically? | Through `quantmap.py`, effectively every command can fail before dispatch because the dispatcher imports `runner`, and `runner` imports `score`, and `score` imports `governance`. This includes reader commands such as `list`, `explain`, `compare`, `export`, `audit`, `status`, and `about`, even though several of those could otherwise read historical snapshots. Direct module usage varies: `src.explain` and `src.export` are lighter at top level, while `src.report` imports `score` directly and therefore inherits the governance import risk. | `quantmap.py:54-64`; `src/runner.py:67`; `src/score.py:60-75`; `src/report.py:38`; `src/explain.py:67-70`; `src/export.py:153-165`. | verified |
| Which failures should hard fail? | Current-run scoring, `run`, `run --validate` when validating active methodology, `self-test` registry/scoring checks, and explicit current-input rescore should hard fail on malformed active profile/registry. These paths are making current methodology claims or preparing new measurements. | `src.score.score_campaign()` uses current-input mode only when explicitly requested; `src.selftest.py` checks registry and scoring; `src.runner.validate_campaign()` validates runtime inputs. | inferred |
| Which failures should soft fail or degrade? | Historical readers (`explain`, `compare`, `audit`, `export`, report regeneration from complete snapshots, and list/status DB summaries) should continue when current profile files are malformed if the needed persisted snapshot evidence exists. They should attach a current-profile warning rather than crashing or silently using current files. | Phase 1 trust docs require snapshot-first readers. Real-workflow memo says snapshot-trust behavior is stable but reader shell is brittle. `src.trust_identity.py` can load run identity without top-level governance import. | verified |
| What is the best design for replacing brittle import-time loading? | Use narrow lazy getters with structured errors. Keep schema classes and parsing functions importable, but move loading of default registry/profile behind functions such as `get_builtin_registry()` and `get_default_profile()`. Cache successful loads, and expose a structured `CurrentMethodologyLoadError` or equivalent for CLI/doctor/reporting to classify. Avoid a broad application lifecycle framework. | Existing `load_registry()` and `load_profile()` already isolate the IO/parsing behavior. Current failure comes from module-level singleton creation, not from the parser shape. | inferred |
| How can we reduce brittleness without hiding configuration problems? | Do not make current-profile errors disappear. Reader paths may proceed from persisted snapshots with an explicit warning. Current-input scoring and active status/about should still show current profile failure as blocking for current methodology use. Doctor should report profile/registry failures with remediation hints. | Trust surface docs say historical methodology authority comes from snapshots; K.I.T. QM-022 says current-run scoring/profile editing should still fail loudly. | verified |

Import/startup resolution: Phase 2 should remove current registry/profile IO from module import, lazy-load current methodology only at command/use points, and make `quantmap.py` dispatch commands without importing runner/score/governance unless the chosen command needs them.

## C. Config / Profile / Registry Failure Behavior

| Question | Answer | Evidence | Status |
|---|---|---|---|
| How are malformed baseline/profile/registry files handled today? | Baseline/campaign YAML loads happen inside runner validation/run flows and usually surface as file/YAML exceptions there. Profile/registry loads happen at governance import and can crash outside the intended lifecycle. Trust readers use persisted snapshots for baseline/methodology when available, but some current-file fallbacks and imports still exist. | `src/runner.py:200-214`; `src/governance.py:464-550`; `src/trust_identity.py:222-284`; `src/report.py:454-462`; `src/report_campaign.py:2360-2378`. | verified |
| Where do parsing/validation errors currently surface? | `runner.validate_campaign()` catches baseline/campaign load errors and reports PASS/FAIL lines. `governance.load_registry()` and `load_profile()` raise `FileNotFoundError`, `ValueError`, or Pydantic errors; module-level default loading lets those errors surface as import-time crashes. Doctor can catch governance errors in `check_registry_load()`, but `quantmap.py` can crash before doctor runs. | `src/runner.py:778-793`; `src/governance.py:464-550`; `src/doctor.py:63-79`; `quantmap.py:54-64`. | verified |
| Are those errors user-clear or developer-clear? | Runner validation errors are operator-facing. Governance import errors are more developer-clear than user-clear when they occur during import. They do not reliably say which command can still proceed from historical snapshots. | `src/runner.py:718-793`; `src/governance.py:527-535`; `quantmap.py:54-64`. | inferred |
| Do they occur at the correct lifecycle point? | Baseline/campaign errors mostly occur at the correct lifecycle point. Current profile/registry errors do not: they occur before command dispatch rather than when a command actually needs current methodology. Server/model env errors also occur too early for some flows because `quantmap.py` imports broad modules and some commands import `src.server` before they can present structured diagnostics. | `src/config.py:38-45`; `src/server.py:60-84`; `quantmap.py:54-64`; `quantmap.py:110-111`; `quantmap.py:154-158`. | verified |
| Which readers should be allowed to function with incomplete or bad current config files if historical snapshots are complete? | `list`, `explain`, `compare`, `audit`, `export`, and historical report regeneration should function when their required DB/snapshot evidence is present. `status` can degrade by showing current-profile failure separately from DB history. `about` should either fail current-methodology identity clearly or show software identity plus current-methodology unavailable. | Phase 1.1 validation lists converged readers; `src.trust_identity.py` provides snapshot-first read helpers; K.I.T. QM-022 acceptance criteria require snapshot-complete historical readers to start. | inferred |
| Which commands truly require valid current config files? | `run`, `run --validate`, current-input `rescore`, self-test scoring/registry checks, and active methodology sections of `about/status` require valid current profile/registry. `doctor` should not require them to import; it should check and report them. Runtime measurement commands also require valid env paths for lab root, server binary, model path, configs, and request files. | `src/runner.py`; `src/score.py:683-815`; `rescore.py:73-115`; `src/selftest.py:18-46`; `quantmap.py:126-158`; `quantmap.py:255-265`. | verified |
| What should happen when current files are malformed but the user is only reading historical data? | Historical read should proceed from snapshots when complete, with a clear warning such as "Current profile invalid; historical snapshot evidence used." If historical evidence is incomplete, do not strengthen it from current files; show legacy/incomplete labels and block operations such as snapshot-locked rescore as Phase 1.1 already requires. | `docs/system/methodology_lifecycle.md`; `src.trust_identity.py` legacy labels; K.I.T. QM-022. | verified |

Config/profile resolution: move current methodology validity from a global prerequisite to a per-command/current-input prerequisite. Reader commands may survive current-file damage only by using persisted historical truth.

## D. Reader Robustness vs Writer Robustness

| Question | Answer | Evidence | Status |
|---|---|---|---|
| Which read-only or historical readers should still work when current live files are broken? | `list`, `explain`, `compare`, `audit`, `export`, and snapshot-first reports should still work for snapshot-complete campaigns. These commands should not need current default profile files to state historical truth. | Real-workflow validation verified these reader types against the trust model. `src.explain`, `src.compare`, `src.audit_methodology`, and `src.export` read DB/trust identity surfaces. | verified |
| Which write or scoring paths should properly fail? | `run`, `run --validate`, current-input `rescore`, current scoring, and active profile editing/testing should fail on malformed current profile/registry. Export writes a bundle but reads historical evidence; it should fail only if DB/bundle operations fail, not because current profile is malformed. | `src.score.score_campaign()` current-input path; `rescore.py` current-input flag; `src.export.py` uses `load_run_identity()` for manifest. | inferred |
| Are readers currently too coupled to current config or startup paths? | Yes at the CLI level. `quantmap.py` imports `runner`, which imports `score`, which imports `governance`, before knowing the requested command. `src.report.py` imports `score_campaign` at module top. `audit_methodology.py` imports `LAB_ROOT` at top, which requires env even when a `--db` path could be enough. `export` imports config during redaction. | `quantmap.py:54-64`; `src/runner.py:67`; `src/score.py:60-75`; `src/report.py:38`; `src/audit_methodology.py:18`; `src/export.py:207-221`. | verified |
| Which commands should become more resilient in Phase 2? | Priority readers: `quantmap list`, `explain`, `compare`, `audit`, `export`, and historical report generation. Operational diagnostics: `doctor`, `status`, `about`, and `self-test` should classify current config failure instead of crashing. Writers should remain fail-loud where current config is invalid. | K.I.T. QM-022; diagnostics model in `src.diagnostics`; current dispatcher imports in `quantmap.py`. | inferred |
| Are any readers still accidentally depending on current live governance/config despite Phase 1 trust stabilization? | At historical trust-read level, Phase 1.1 moved readers toward `trust_identity`. The remaining problem is mostly startup/import coupling rather than intentional live truth use. `report.py` still imports `score` at top and may score if no result is passed, so its module import path remains governance-coupled. `report_campaign.py` imports score lazily only if scores are missing. | `src/report.py:38`; `src/report.py:459-462`; `src/report_campaign.py:2376-2378`; `src/trust_identity.py`. | verified |

Reader/writer resolution: Phase 2 should separate command startup and historical readers from current methodology imports, while preserving fail-loud current-input and writer semantics.

## E. Error Classification and Operator UX

| Question | Answer | Evidence | Status |
|---|---|---|---|
| How are operational errors currently surfaced? | Errors are surfaced through mixed mechanisms: exceptions at import time, logger errors, rich console messages, boolean returns, `sys.exit(1)`, and `DiagnosticReport` check results. The diagnostics model is useful but not used for early CLI/bootstrap failures. | `quantmap.py:54-64`; `rescore.py:73-115`; `src/doctor.py`; `src/diagnostics.py`; `src/runner.py:718-793`; `src/export.py:31-96`. | verified |
| Are trust failure, current-input failure, legacy-incomplete evidence, environment/setup failure, and export/report partial failure clearly distinct? | The Phase 1 trust labels distinguish historical evidence states. Operational shell failures are less consistently classified. Diagnostics has PASS/WARN/FAIL/SKIP/INFO but does not express categories such as current config invalid vs historical snapshot usable. | `src/trust_identity.py:181-197`; `src/diagnostics.py:9-35`; K.I.T. QM-010/QM-022. | verified |
| Does doctor/diagnostics help enough with robustness failures? | Doctor has useful checks for lab structure, registry load, server binary, Defender, Windows Search, HWiNFO, and terminal encoding. However, `check_registry_load()` only imports `BUILTIN_REGISTRY`; there is no separate default-profile check, no "historical readers can continue" message, and doctor may not be reachable if dispatcher imports fail first. | `src/doctor.py:30-79`; `src/doctor.py:241-271`; `quantmap.py:54-64`. | verified |
| What failures need clearer messages or remediation hints? | Current profile parse/validation errors need command-specific hints. Missing env vars need "run init or set .env" guidance without killing `--help`/`init`. Historical readers need warnings that current config is invalid but snapshot evidence is being used. Current-run commands need direct "fix active profile/registry first" messages. Redaction/export errors need clear fidelity/completeness labels. | `src/config.py:38-45`; `src/governance.py:527-535`; `src/export.py:31-96`; docs K.I.T. QM-022/QM-005/QM-010. | inferred |
| What should failures suggest? | Current config failure: "fix your profile/registry." Snapshot-complete historical read: "historical snapshot used; current profile invalid." Legacy-incomplete data: "evidence incomplete; no silent strengthening." Current-input rescore: "explicit current-input mode required." Setup/env failure: "run init, set .env, or pass --db where supported." | Methodology lifecycle docs and K.I.T. acceptance criteria. | inferred |

UX resolution: introduce a small shared operational error vocabulary and route startup/current-methodology checks through diagnostics where possible. Do not make a giant error framework.

## F. Runtime Dependency / Environment Brittleness

| Question | Answer | Evidence | Status |
|---|---|---|---|
| Which environment assumptions still cause unnecessary brittleness? | `QUANTMAP_LAB_ROOT` is required by `src.config` at import. `QUANTMAP_SERVER_BIN` and `QUANTMAP_MODEL_PATH` are required by `src.server` at import. `quantmap.py` loads `.env` from script dir and cwd, then imports broad internals before command dispatch. `report.py` and `report_campaign.py` still have hardcoded default lab-root fallback strings. | `src/config.py:38-45`; `src/server.py:60-84`; `quantmap.py:43-64`; `src/report.py:129-132`; `src/report_campaign.py:40`; `.env.example`. | verified |
| Which current issues are Phase 2 robustness issues rather than Phase 3 portability issues? | Import-time env/config failure boundaries, clearer missing-env diagnostics, safe `init`/`help` behavior, DB-reader ability to use explicit `--db`, and path-setting design for current lab root are Phase 2. Provider-neutral telemetry and full Linux/NVIDIA support are later phases. | K.I.T. QM-001/QM-005/QM-018; Post-audit synthesis Phase 2 vs Phase 3. | verified |
| Are there file-path, env-var, or startup-resolution problems that should be hardened now? | Yes. The CLI should parse and route commands before importing heavy modules. `init` and `--help` should not require a configured lab. Historical readers with explicit `--db` should avoid importing lab-root/server settings when possible. Path fallback strings in report modules should be demoted or replaced with explicit caller-provided lab roots when touched. | `quantmap.py:54-64`; `src/audit_methodology.py:18`; `src/report.py:129-132`; `src/report_campaign.py:40`. | verified |
| Which are trust-critical vs convenience-only? | Trust-critical: current-file failures must not alter historical snapshot truth; explicit DB/snapshot readers must avoid live config. Operational but not trust-critical: installed command polish, broad packaging, full path portability, Linux provider setup. | Trust surface docs; K.I.T. QM-005/QM-022. | inferred |
| What should Phase 2 do without drifting into broad platform work? | Add narrow config access helpers or command-local imports, not a full settings framework. Make required env validation a command responsibility. Improve doctor/status messages. Leave provider architecture, backend adapters, and full packaging redesign for later. | Post-audit synthesis and TO-DO TODO-017/TODO-018/TODO-021 boundaries. | inferred |

Runtime/env resolution: Phase 2 should make startup and historical readers robust under missing current runtime env where possible, but not solve universal portability.

## G. Database / Migration Robustness

| Question | Answer | Evidence | Status |
|---|---|---|---|
| Are schema/migration behaviors still fragile operationally? | The migration system has a schema version table, downgrade detection, duplicate snapshot fail-loud behavior, and legacy methodology backfill. The main risk is operator clarity when migrations fail, not an obvious new Phase 2 schema redesign need. | `src/db.py:622-743`; `_assert_no_duplicate_campaign_start_snapshots` in `src/db.py:393-411`; legacy backfill in `src/db.py:416-472`. | verified |
| Are duplicate detection / fail-loud paths sufficient and clear? | Directionally yes: duplicate campaign start snapshots fail loudly with manual remediation text. The message is trust-appropriate. Phase 2 can improve wrapping/display if migration exceptions currently bubble through raw tracebacks. | `src/db.py:393-411`; Phase 1 migration decisions. | inferred |
| Are migration failures user-clear? | Not consistently. `init_db()` raises exceptions; callers vary in whether they catch and present them. Rescore calls `init_db()` before reads, but a migration failure may surface as a logger/exception rather than a structured diagnostic. | `src/db.py:622-743`; `rescore.py:86-91`; `src/runner.py` uses DB init during run. | inferred |
| Are there living schema or migration edge cases to address in Phase 2? | Only error-path wrapping and validation scenarios. Do not add a new schema model for Phase 2 unless a concrete operational failure appears. | Current schema docs and K.I.T. do not identify a new schema root issue beyond resolved Phase 1 trust surfaces and open QM-016. | inferred |
| Which belong in robustness vs later maintenance/refactor? | Robustness: clear migration failure messages, smoke tests for duplicate snapshot failure and legacy DB migration. Later maintenance: full migration framework redesign or schema docs overhaul. | `src/db.py` current migration design; K.I.T. Phase 2 scope. | inferred |

DB resolution: keep migration behavior mostly unchanged; add focused error-message/validation coverage only if Phase 2 touches command startup and diagnostics.

## H. Future-Proofing Without Phase Creep

| Question | Answer | Evidence | Status |
|---|---|---|---|
| Which robustness fixes make later phases easier? | Lazy current-methodology loading makes telemetry/provider and backend work easier by keeping historical readers independent of current operational state. Command-local imports reduce blast radius for future runner/report/backend changes. Small settings access boundaries prepare path decoupling without a framework. | Post-audit synthesis themes on boundary problems; current import graph. | inferred |
| Which tempting fixes should be deferred? | Telemetry provider strategy, backend adapter contract, full runner decomposition, report consolidation, recommendation semantics/artifacts, installed packaging overhaul, and full Linux/cloud portability. | K.I.T. QM-018/QM-019/QM-020/QM-021; TO-DO TODO-018/TODO-021/TODO-024/TODO-025. | verified |
| How do we improve robustness now without generic frameworks? | Use narrow functions: lazy profile/registry getters, structured current-methodology load result, command-local imports, a few diagnostic checks, and explicit reader/writer policies. Avoid dependency injection containers, app contexts, plugin layers, or broad service abstractions. | Existing code already has parser functions (`load_registry`, `load_profile`) and diagnostics structures; the needed change is when and how they are called. | inferred |

Future-fit resolution: Phase 2 should reduce global work at import time and make command needs explicit. That is useful future architecture groundwork, but it is not the architecture phase itself.

## Resolution Matrix

| Issue | Current Reality | Why It Matters | Scope Fit | Design Options | Recommended Resolution | Why | Explicitly Deferred | Decision Status |
|---|---|---|---|---|---|---|---|---|
| Governance default profile loads at import | `DEFAULT_PROFILE` and registry validation run during `src.governance` import. | Malformed current profile can crash historical readers before snapshot evidence is available. | Phase 2 | A. Keep fail-fast import. B. Lazy getters with cache and structured errors. C. App-wide init framework. | B. Keep schemas/parsers importable; move default profile/registry loading behind narrow lazy getters. | Fixes the core brittle shell without weakening current-input failure semantics. | Generic app lifecycle framework. | ready |
| CLI imports heavy modules before dispatch | `quantmap.py` imports runner/doctor/explain/export/rescore before parsing subcommands. | One broken current file or env var can break every command. | Phase 2 | A. Keep global imports. B. Command-local imports. C. Split CLI into package. | B. Move command module imports into command handlers and keep only lightweight imports at startup. | Contains blast radius and allows `help`/`init`/readers to run when unrelated dependencies are broken. | Packaging overhaul. | ready |
| `src.score` materializes live governance constants at import | `ELIMINATION_FILTERS` and `SCORE_WEIGHTS` are derived from current default profile at import. | Any import of score can fail due to current profile and report imports score at module top. | Phase 2 | A. Leave constants. B. Lazy scoring defaults. C. Remove defaults entirely. | B. Replace import-time current profile constants with lazy current-default helpers or constants loaded only in current-scoring paths. | Preserves current-run semantics while avoiding reader import crashes. | Scoring engine redesign. | ready |
| Historical reports import score too early | `src.report.py` imports `score_campaign` at module top. | Report module import inherits governance brittleness even if caller has precomputed results. | Phase 2 | A. Leave. B. Lazy import score only when scoring is needed. C. Merge report stacks. | B. Move scoring import inside the branch that actually computes missing scores. | Small containment fix. | Report consolidation. | ready |
| Doctor cannot always diagnose startup brittleness | Doctor has registry check, but dispatcher may crash before doctor can run; default profile is not a separate check. | Operators need a remediation path when current profile is malformed. | Phase 2 | A. Leave. B. Add current-methodology diagnostics and make doctor reachable. C. Build full readiness engine. | B. Add profile/registry checks with structured current-methodology errors and ensure `doctor` can start without runner/score import. | Improves recovery without changing trust model. | Full readiness redesign/provider diagnostics. | ready |
| Missing env vars are import-time blockers | `src.config` and `src.server` require env vars at import. | `init`, `--help`, and historical readers should not always need server/model env. | Phase 2 | A. Keep import-time env. B. Command-local env requirements. C. Full settings subsystem. | B. Make lab/server/model env validation command-local where possible; keep current `config.py` constants for writer paths until later settings work. | Minimal shell hardening. | Full settings/path framework. | needs approval |
| Historical readers with explicit DB can still depend on lab root | `audit_methodology.py` imports `LAB_ROOT`; quantmap handlers use global `LAB_ROOT`; report modules have fallback lab roots. | Explicit historical DB reads should not require unrelated current lab env where avoidable. | Phase 2 | A. Leave. B. Prefer explicit `--db` and lazy lab-root fallback. C. Full path resolver. | B. For reader commands, resolve `--db` first and import lab-root settings only as fallback. | Makes historical reads more robust and keeps path work bounded. | Complete path/settings rewrite. | ready |
| Operational error messages are not classified enough | Errors mix exceptions, logger, booleans, console prints, and diagnostics. | Operators cannot always tell whether to fix files, use current-input, or trust historical snapshots. | Phase 2 | A. Leave. B. Small shared error vocabulary. C. Full exception hierarchy. | B. Add a small set of labels/messages for current-config invalid, historical snapshot used, legacy incomplete, environment missing, migration blocked. | Improves UX without framework building. | Large error framework. | ready |
| Dry-run/readiness ambiguity remains | Dry-run validates structure, not full runtime readiness. | Operators may mistake structural success for readiness. | Phase 2 | A. Leave. B. Improve labels/docs/doctor handoff. C. Turn dry-run into doctor. | B. Make dry-run output explicitly say structural validation and point to doctor for readiness. | Small operational clarity fix. | Broad run lifecycle redesign. | ready |
| Run-context/characterization degradation signaling remains open | Optional context failures can degrade evidence quality without enough operator signaling. | It affects operator trust and future attribution, but is broader than the immediate import shell. | Phase 2 | A. Include fully. B. Include only diagnostic vocabulary alignment. C. Defer entirely. | B. Align message vocabulary if touched; keep full remediation as separate QM-010 work after shell hardening. | Keeps Phase 2 first pass contained. | Full attribution/context evidence work. | ready |
| Telemetry provider lock-in | HWiNFO-centric telemetry remains. | Important for portability, but broader than shell robustness. | Later phase | A. Start provider interfaces now. B. Defer. | B. Defer provider architecture; only avoid making it harder. | Prevents Phase 2 from becoming platform generalization. | Telemetry provider strategy. | ready |
| Backend coupling | `llama-server` assumptions remain. | Important for future resolved runtime/platform work. | Later phase | A. Start adapter. B. Defer. | B. Defer backend abstraction; keep env/error messages backend-aware but not adapterized. | Avoids hidden subsystem effort. | Backend adapter contract. | ready |
| Report consolidation | Duplicate report stacks remain. | Important but not needed to fix import shell. | Later phase | A. Merge reports now. B. Touch only import/failure boundaries. | B. Do not consolidate; apply only lazy imports/error labels needed for robustness. | Avoids Phase 2 scope creep. | Canonical report model. | ready |

## Locked Conclusions

1. Phase 2 should begin with startup/import containment, not telemetry/provider architecture.
2. `src.governance` should keep schemas and parser functions importable, but default registry/profile loading should become lazy and structured.
3. `quantmap.py` should import heavy command modules only after command selection.
4. Historical readers must be allowed to run from complete persisted snapshots when current profile/registry files are malformed.
5. Current-run scoring, current-input rescore, and active methodology validation must still fail loudly on malformed current methodology.
6. Doctor/status/about should classify current-methodology failure instead of causing a global crash.
7. Missing server/model env should block measurement commands, not necessarily `help`, `init`, or explicit-DB historical readers.
8. Phase 2 should add minimal diagnostic/error vocabulary, not a generic framework.

## Decisions Needing Review

1. Whether to relax `src.config` import-time `QUANTMAP_LAB_ROOT` failure now, or only route historical readers around it with command-local imports and explicit `--db` precedence.
2. Whether `quantmap status` should be allowed to run in a degraded "software/DB only" mode when the current profile is malformed, or whether it should mark current methodology as blocked while still showing DB counts.

## Bottom Line

Phase 2 looks like a contained operational shell-hardening pass if it stays focused on lazy current-state loading, command-local imports, and clearer diagnostics. The hidden subsystem risk appears only if the work expands into full settings architecture, telemetry providers, backend adapters, or report consolidation.
