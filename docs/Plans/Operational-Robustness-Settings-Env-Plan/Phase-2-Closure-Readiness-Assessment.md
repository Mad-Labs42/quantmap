# Phase 2 Closure Readiness Assessment

Status: closure-readiness assessment  
Date: 2026-04-12  
Scope: Phase 2 Operational Robustness only

## Purpose

This assessment determines whether Phase 2 Operational Robustness is ready to be called complete, what evidence exists, what remains open, and whether QuantMap can safely activate Phase 3 Platform Generalization.

This is not a new audit and not an implementation plan. It is a closure gate review against the approved Phase 2 plan, current code, validation probes, and living trackers.

## Evidence Basis

Primary documents reviewed:

- `docs/decisions/Phase-2-Operational-Robustness-Interrogation.md`
- `docs/decisions/Phase-2-Operational-Robustness-Pre-Implementation-Plan.md`
- `docs/decisions/Trust-Bundle/Phase-1.1-Real-Workflow-Validation-Memo.md`
- `docs/AUDITS/4-11/Post-Audit-Synthesis-Memo.md`
- `docs/system/known_issues_tracker.md`
- `docs/system/TO-DO.md`
- `README.md`
- `docs/README.md`
- `docs/decisions/README.md`
- `docs/system/architecture.md`
- `docs/system/trust_surface.md`
- `docs/system/database_schema.md`

Code inspected:

- `quantmap.py`
- `src/governance.py`
- `src/score.py`
- `src/trust_identity.py`
- `src/doctor.py`
- `src/diagnostics.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/explain.py`
- `src/compare.py`
- `src/audit_methodology.py`
- `src/config.py`
- `rescore.py`

Validation probes available during this review:

- `.venv\Scripts\python.exe -m compileall quantmap.py src\governance.py src\score.py src\trust_identity.py src\report.py src\doctor.py src\diagnostics.py src\audit_methodology.py`
- guarded import probe proving `src.governance`, `src.score`, `src.report`, and `quantmap` do not read `metrics.yaml` or `default_throughput_v1.yaml` at import time
- guarded degraded `quantmap status` probe under forced current-methodology read failure
- guarded `quantmap doctor` probe under forced current-methodology read failure
- guarded `explain`, `compare`, and `export` probes for `TrustPilot_v1` with live methodology reads blocked
- current-input fail-loud probe via `load_methodology_for_historical_scoring(..., allow_current_input=True)` under forced live methodology failure
- legacy-partial snapshot-locked rescore refusal probe for `C01_threads_batch__standard`
- normal smoke checks for `quantmap --help`, `quantmap --plain status`, `quantmap --plain doctor`, `quantmap --plain about`, and `quantmap --plain audit TrustPilot_v1 TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite`

## Closure Definition

For this review, Phase 2 complete means:

1. The brittle current-methodology import shell no longer blocks unrelated commands.
2. Snapshot-complete historical readers can use persisted evidence even when current methodology files are bad.
3. Current-run and explicit current-input paths still fail loudly when current methodology is invalid.
4. Operator diagnostics classify current config, environment, and historical-trust states clearly.
5. `--help`, `init`, status/doctor/about, and read-only historical paths have appropriate startup blast-radius boundaries.
6. Dry-run/readiness wording no longer implies runtime readiness.
7. Remaining settings/environment work is either actually closed or explicitly retained as a Phase 2 blocker before Phase 3 provider work.
8. Living docs do not imply Phase 3 is active before Phase 2 closure.

## Part 1 - Closure Questions

| Question | Answer | Evidence | Status |
|---|---|---|---|
| What was Phase 2 supposed to accomplish? | Phase 2 was supposed to harden the operational shell around the stable Phase 1/1.1 trust model: lazy current-methodology loading, command-local CLI imports, historical reader resilience under malformed current files, clearer diagnostics, small env/path hardening, and focused validation. It explicitly deferred telemetry providers, backend adapters, report consolidation, optimization, broad packaging, and broad runner decomposition. | Phase 2 plan sections 1, 3, 4, 5, and 6. | verified |
| What exact Operational Robustness issue was the center of gravity? | The main issue was `src.governance` loading current registry/profile at import time, then spreading through `src.score`, `src.runner`, and top-level `quantmap.py` imports. This let a malformed current profile crash commands that should read historical snapshot evidence. | Phase 2 interrogation sections B-D; `src/governance.py`; previous top-level `quantmap.py` import path; K.I.T. QM-022. | verified |
| Which Phase 2 items now have implementation evidence? | Lazy governance getters and structured current-methodology errors exist in `src/governance.py`. `src.score` uses lazy governance mappings. `quantmap.py` uses command-local imports and degraded `status`. `doctor` has registry/profile checks. `report.py` no longer imports `score_campaign` at top level. `audit_methodology.py` defers `LAB_ROOT` import until no `--db` was supplied. `trust_identity` current-input path uses the lazy current methodology loader. | `src/governance.py:382`, `src/governance.py:561`, `src/governance.py:572`, `src/governance.py:594`, `src/governance.py:656`; `src/score.py:73`, `src/score.py:142`; `quantmap.py:62`, `quantmap.py:122`, `quantmap.py:143`; `src/doctor.py:72`, `src/doctor.py:93`; `src/report.py:461`; `src/audit_methodology.py:114`; `src/trust_identity.py:239`. | verified |
| Which items have validation evidence? | Import containment, degraded status, doctor failure classification, guarded historical `explain`/`compare`/`export`, current-input fail-loud, legacy-partial snapshot-locked refusal, compile, and basic smoke commands have validation evidence. | Validation probes listed in Evidence Basis. | verified |
| Which items still rely on planning assumptions rather than proof? | `quantmap init` under missing env was not directly exercised because it is interactive. Missing-env command behavior was only partially proven. `run --validate` under malformed current profile was not exercised. Dry-run/readiness wording remains unchanged in `src.runner`. `export --strip-env` still imports `src.config` for lab-root redaction. Direct `python rescore.py` still imports `src.config` at module import time, though `quantmap rescore` is now command-local. | `src/runner.py:1806-1880`; `src/export.py:207`, `src/export.py:220`; `rescore.py:33`; validation probes did not include direct `init` or malformed-profile `run --validate`. | verified |
| What surfaced during Phase 2 that must be resolved before closure? | Phase 2 fixed the main governance import blast radius, but it exposed three closure gaps: dry-run/readiness wording is still open, the settings/env boundary remains a Phase 3 precondition rather than a completed foundation, and a formal closure validation memo has not yet been written from the completed probes. | Phase 2 plan exit criteria; current `src.runner` dry-run output; `src.config` still fail-loud at import; living docs still mark Phase 2 as active. | verified |
| What can carry forward to Phase 3 rather than block Phase 2? | Full telemetry provider architecture, Linux/NVIDIA provider implementation, backend adapters, report consolidation, broad runner decomposition, packaging polish, and optimization/recommendation work can carry forward. However, Phase 3 provider work should not activate until the settings/environment boundary question is explicitly resolved enough for provider discovery policy. | Post-audit synthesis Phase 3 section; Phase 2 plan out-of-scope list; K.I.T. QM-018/QM-019/QM-020/QM-021. | verified |

## Part 2 - Closure Gate List

| Gate | Why it matters | Evidence currently available | Status | Still needed | Required for Phase 2 closure? |
|---|---|---|---|---|---|
| Governance/profile import-time brittleness handled | A malformed current profile must not crash unrelated historical readers. | `src.governance` now has lazy getters and proxies; guarded import probe passed for `src.governance`, `src.score`, `src.report`, and `quantmap`. | met | Capture in closure validation memo. | required |
| CLI command dispatch blast radius reduced | `quantmap --help`, status, doctor, and readers should not import runner/score/server before command selection. | `quantmap.py` only imports version before dispatch; command-local imports are present; `quantmap --help` passes. | met | Direct missing-env `init` smoke remains desirable. | required |
| Historical readers survive bad current methodology when they have persisted evidence | Trust-first behavior depends on current-file damage not blocking snapshot evidence. | Guarded `explain`, `compare`, and `export` probes ran with live methodology reads blocked; `audit` with explicit DB passed; `trust_identity` load probe passed. | met | Run a final fixture/probe against a known snapshot-complete-not-current-input campaign if available. | required |
| Current-run/current-input paths fail loudly | Robustness must not hide current methodology damage for new interpretation. | Forced current-input loader probe raised `CurrentMethodologyLoadError`; `score_campaign` requires current-input for re-anchoring and uses `load_methodology_for_historical_scoring`. | partially met | Exercise CLI current-input rescore or `run --validate` under forced malformed current methodology. | required |
| Legacy partial methodology remains blocked for snapshot-locked rescore | Phase 1.1 invariant must survive Phase 2. | Probe against `C01_threads_batch__standard` refused snapshot-locked scoring with `legacy_partial_methodology`. | met | Include in closure validation memo. | required |
| Degraded status is clear and non-misleading | Operators need DB/software signal without believing current methodology is healthy. | Guarded `cmd_status` displayed software version, lab root, campaign count, current methodology blocked, historical trust note, and remediation hint. | met | Consider one copy polish pass after final validation. | strongly preferred |
| Doctor classifies current methodology failure | Operators need a recovery path for malformed profile/registry. | Guarded doctor probe reported Metric Registry and Default Profile failures; normal doctor smoke passed with warnings only. | met | None beyond closure memo. | required |
| Dry-run wording distinguishes structural validation from runtime readiness | Dry-run can otherwise overclaim readiness and was explicitly in the Phase 2 plan. | `src.runner` dry-run output still describes structural validity but does not clearly hand off to doctor/readiness in the displayed summary. | not met | Add/validate wording in a small follow-up implementation pass. | required |
| Missing env handling is classified, not catastrophic | Missing lab/server/model paths should guide operators instead of killing unrelated commands. | `doctor` now accepts optional paths; `status` reads env directly. `src.config` still fails at import, and `src.server` remains fail-loud. | partially met | Explicit missing-env subprocess probes and, if needed, a tiny fallback polish pass. | required |
| Explicit DB readers avoid lab-root fallback where possible | Historical reads should not need lab root when `--db` is supplied. | `quantmap audit/explain/compare/export` prefer `--db`; `audit_methodology.py` defers `LAB_ROOT` import. | partially met | `export --strip-env` and direct scripts still have config imports; decide whether that is acceptable or needs a narrow fix. | strongly preferred |
| Settings/environment boundary is ready for Phase 3 provider work | Telemetry providers need common config and environment discovery policy. | Phase 2 chose command-local routing rather than broad `src.config` redesign. `src.config` still requires `QUANTMAP_LAB_ROOT` at import. | not met | A bounded settings/environment boundary decision or implementation slice before Phase 3 activation. | required before Phase 3 activation |
| Boundary-enforcement policy is preserved | Phase 3 must not enlarge god modules while adding providers/backends. | Phase 2 code changes were narrow and avoided runner/report/backend/provider framework work. Living trackers still have QM-017, QM-018, QM-019. | partially met | Roadmap note should lock anti-God-object guardrails for Phase 3 from day one. | strongly preferred |
| Formal Phase 2 closure evidence exists | Future planning should not rely on memory of ad hoc probes. | This assessment records observed probes, but there is no dedicated Phase 2 validation memo yet. | partially met | Create a concise Phase 2 validation memo or append closure validation results to a living closure artifact after final probes. | required |

## Part 3 - Required Closure Questions

### A. Has the brittle import-time/default-profile problem been resolved enough to stop being a Phase 2 blocker?

Answer: Mostly yes for the core QM-022 failure mode, but not enough to close Phase 2 without final validation documentation.

Evidence:

- `src.governance.py` no longer constructs real `BUILTIN_REGISTRY` and `DEFAULT_PROFILE` by loading YAML at import; it defines lazy accessors and compatibility proxies.
- `src.score.py` no longer materializes live `ELIMINATION_FILTERS` and `SCORE_WEIGHTS` from the active profile at import.
- `quantmap.py` moved heavy imports into command handlers.
- Guarded import probes confirmed imports do not touch current methodology YAML files.
- Guarded reader probes confirmed `explain`, `compare`, and `export` can run with live methodology reads blocked.

Status: verified.

Remaining:

- Formalize the validation evidence.
- Exercise direct malformed-profile command scenarios that were not covered by guarded in-process probes, especially current-run/current-input command behavior.

### B. Are current config/profile/registry failures isolated enough that historical readers can still function when they should?

Answer: For the main snapshot-first reader paths, yes. For all possible entry points, partially.

Readers with positive evidence:

- `explain`: guarded probe completed using DB/trust evidence.
- `compare`: guarded probe completed and wrote a comparison report.
- `export`: guarded probe completed a lite export when `strip_env=False`.
- `audit`: explicit `--db` path works and `audit_methodology.py` no longer imports `LAB_ROOT` at top level.
- `status`: degrades and separates current methodology failure from DB history.

Remaining coupling:

- `export --strip-env` still imports `src.config` for lab-root redaction.
- direct `python rescore.py` still imports `src.config` at module import time.
- report modules retain module-level lab-root fallbacks, though they do not reload current methodology unless scoring is requested.
- `list` still imports `runner`, which imports `src.config`; it is not an explicit-DB historical reader.

Status: verified for primary readers, inferred/partial for all entry points.

### C. Is settings/environment boundary hardening sufficiently in place to support future Phase 3 provider abstraction?

Answer: No. It is improved for CLI blast-radius containment, but not yet sufficient as a provider foundation.

Evidence:

- `src.config.py` still requires `QUANTMAP_LAB_ROOT` at import time.
- `src.server.py` still requires `QUANTMAP_SERVER_BIN` and `QUANTMAP_MODEL_PATH` at import time.
- Phase 2 deliberately chose command-local imports and explicit `--db` precedence instead of a broad settings layer.
- The canonical synthesis memo says telemetry abstraction should follow settings decoupling because providers need common config and environment discovery policy.

Status: verified.

Closure implication: this does not erase the value of the Phase 2 brittle-shell pass, but it means Phase 3 should remain inactive until a bounded settings/environment boundary follow-up is completed or explicitly approved as Phase 3 entry work.

### D. Are Phase 2 error semantics and operator guidance good enough?

Answer: Improved, but not fully closed.

Improved:

- `doctor` now reports registry/profile failures as diagnostic checks.
- `status` can show current methodology as blocked while still reporting DB/software state.
- missing runtime paths can be represented by doctor checks instead of forcing `src.server` import.
- current-input methodology failure is structured as `CurrentMethodologyLoadError`.

Still weak:

- dry-run output still does not clearly say "structural validation only; run doctor for readiness."
- command-level missing-env behavior has not been fully exercised in subprocess conditions.
- there is no final Phase 2 validation memo preserving the operator UX evidence.

Status: verified/partial.

### E. Are there remaining hidden robustness issues that would make activating Phase 3 premature?

Answer: Yes. Phase 3 provider abstraction would be premature because the settings/environment boundary is still not a common policy surface.

Specific issues:

- `src.config` import-time lab-root requirement remains.
- `src.server` still owns backend env requirements eagerly.
- telemetry provider work would need a provider discovery/config model that does not yet exist.
- QM-005 and TODO-017 remain open/ready and directly govern path/settings policy.
- QM-017 warns that Phase 3 must avoid enlarging `runner.py` while adding provider/backend logic.

Status: verified.

## Part 4 - Closure Recommendation

Recommendation: **Phase 2 is almost ready to close, but needs one small follow-up pass.**

Why:

- The central QM-022 brittle-shell issue has implementation and guarded validation evidence.
- Reader convergence under broken current methodology is materially better.
- Fail-loud current-input and legacy-partial refusal semantics remain intact.
- However, Phase 2 closure criteria were broader than just QM-022. Dry-run/readiness wording is not met, missing-env behavior needs final subprocess validation, and settings/environment policy is not strong enough to activate Phase 3 provider abstraction.

Required follow-up before closure:

1. Add or verify dry-run wording that clearly says dry-run is structural validation, not runtime readiness, and points to doctor/status for readiness.
2. Run and record a final Phase 2 validation memo covering:
   - malformed current methodology with `help`, `status`, `doctor`, `explain`, `compare`, `export`, current-input rescore, and snapshot-locked legacy rescore
   - missing env behavior for `help`, `doctor`, `status`, and explicit-DB historical readers
   - current-run/current-input fail-loud behavior
3. Decide the minimum settings/environment boundary required before Phase 3:
   - either implement a narrow settings/path boundary now
   - or keep Phase 3 inactive and create a Phase 2.1 settings/environment boundary plan.

Phase 3 status: **not active yet**.

## Carry-Forward Classification

| Item | Classification | Reason |
|---|---|---|
| QM-022 governance import brittleness | Phase 2 closure validation item | Core implementation appears done, but tracker should not be marked resolved until closure validation is recorded. |
| QM-009 dry-run readiness ambiguity | Phase 2 closure blocker | Explicit Phase 2 exit criterion and current output still lacks strong readiness handoff. |
| QM-005 lab-root/path assumptions | Phase 2/Phase 3 bridge blocker | Not required to prove malformed-profile reader resilience, but required before provider abstraction starts cleanly. |
| TODO-017 centralized settings/path design | Phase 2 follow-up | The project still needs a bounded settings/env boundary before Phase 3 provider work. |
| QM-018 telemetry provider lock-in | Phase 3 candidate, pending | Should not activate until settings/env boundary is ready. |
| QM-017 runner responsibility fusion | Cross-phase guardrail | Do not start a giant refactor, but Phase 3 must avoid enlarging runner/report modules. |
| QM-019 backend coupling | Later phase | Relevant to platform work, but not a Phase 2 closure blocker. |

## Final Assessment

Phase 2 has completed a real implementation pass and most of the central brittle-shell risk is resolved in code. It should not yet be called complete.

The honest current state is:

- Phase 1 / 1.1: stable
- Phase 2: implementation pass complete, closure validation and small follow-up still active
- Phase 3: next major direction, but pending Phase 2 closure and settings/environment boundary readiness

