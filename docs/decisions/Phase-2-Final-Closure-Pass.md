# Phase 2 Final Closure Pass

Status: final closure pass, not closed  
Date: 2026-04-12  
Scope: Phase 2 Operational Robustness only

## Purpose

This document performs the final Phase 2 closure check after the Operational Robustness implementation pass.

It answers whether Phase 2 can be honestly closed, whether a tiny Phase 2 follow-up remains, whether a Phase 2.1 bridge is justified, and whether Phase 3 Platform Generalization can safely activate.

## Inputs

Primary grounding:

- `docs/decisions/Phase-2-Closure-Readiness-Assessment.md`
- `docs/decisions/Current-Phase-Status-and-Roadmap-Alignment.md`
- `docs/decisions/Phase-2-Operational-Robustness-Interrogation.md`
- `docs/decisions/Phase-2-Operational-Robustness-Pre-Implementation-Plan.md`
- `docs/AUDITS/4-11/Post-Audit-Synthesis-Memo.md`
- `docs/system/known_issues_tracker.md`
- `docs/system/TO-DO.md`

Code inspected or probed:

- `quantmap.py`
- `src/governance.py`
- `src/config.py`
- `src/server.py`
- `src/doctor.py`
- `src/diagnostics.py`
- `src/score.py`
- `src/trust_identity.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/explain.py`
- `src/compare.py`
- `src/audit_methodology.py`
- `src/runner.py`
- `rescore.py`

## Validation Performed

The following probes were run in the project virtual environment unless noted otherwise.

| Probe | Result | Evidence status |
|---|---|---|
| `quantmap --help` with `QUANTMAP_LAB_ROOT`, `QUANTMAP_SERVER_BIN`, and `QUANTMAP_MODEL_PATH` set to empty strings | Help rendered successfully. | verified |
| `quantmap --plain status` with empty env vars | Status degraded: lab root blocked, DB unavailable, methodology loaded, readiness blocked with doctor hint. | verified |
| `quantmap --plain doctor` with empty env vars | Doctor reported missing lab root and server binary as failures; continued through registry/profile and other checks. | verified |
| `quantmap --plain about` with empty env vars | About rendered software/current-methodology identity and marked lab/DB unavailable. | verified |
| explicit-DB `explain TrustPilot_v1` with empty env vars | Historical briefing rendered from DB. | verified |
| explicit-DB `audit TrustPilot_v1 TrustPilot_v1` with empty env vars | Methodology audit completed. | verified |
| explicit-DB `compare TrustPilot_v1 TrustPilot_v1 --output ... --force` with empty env vars | Comparison completed and wrote output. | verified |
| explicit-DB `export TrustPilot_v1 --output ... --lite` with empty env vars | Export completed. | verified |
| explicit-DB `export TrustPilot_v1 --output ... --lite --strip-env` with empty env vars | Export completed, but revealed a settings boundary risk because `src.config` treats empty lab root as `Path('.')` for redaction. | verified |
| guarded imports blocking any open of `configs/metrics.yaml` or `configs/profiles/default_throughput_v1.yaml` | `src.governance`, `src.score`, `src.report`, `src.report_campaign`, `src.export`, `src.explain`, `src.compare`, `src.audit_methodology`, `src.trust_identity`, `src.doctor`, and `quantmap` imported without live methodology reads. | verified |
| guarded `generate_report()` on a copied DB and temp lab root | Historical report generation completed without live methodology file reads. | verified |
| guarded current-input rescore on a copied DB | Rescore failed before scoring writes completed, with `CurrentMethodologyLoadError`; the CLI showed failure and logger traceback. | verified |
| guarded `run --validate` for a current campaign | Validation completed successfully without current methodology reads. | verified |
| guarded `run --dry-run` for a current campaign | Dry-run raised `CurrentMethodologyLoadError` when trying to print lazy elimination filters. | verified |
| normal `run --dry-run --mode quick` | Dry-run output described campaign shape and filters but did not clearly state "structural validation only; run doctor/status for readiness." | verified |

## Part 1 - Re-evaluated Open Closure Gates

### A. Dry-Run / Readiness Messaging

Question: Is dry-run wording now clearly framed as structural validation only?

Answer: No.

Evidence:

- `src/runner.py` comments state that reaching dry-run output means the campaign is structurally valid.
- The actual `quantmap run --dry-run --mode quick` output lists the run plan, requests, filters, and configs, but does not clearly say that telemetry/runtime readiness has not been proven.
- The output does not point the user to `quantmap doctor` or `quantmap status` for readiness.
- Under forced current-methodology failure, dry-run raises `CurrentMethodologyLoadError` while trying to render `dict(ELIMINATION_FILTERS)`.

Status: verified.

Closure decision: this remains a true Phase 2 closure blocker, but it is tiny. The sufficient closure behavior is:

- dry-run output explicitly says it is structural validation only
- dry-run output points to `quantmap doctor` or `quantmap status` for runtime readiness
- if current methodology cannot be loaded for filter display, dry-run should fail with a concise current-methodology error, not an unhandled exception path

### B. Missing-Env Behavior

Question: Are missing environment-variable failures clear and properly scoped?

Answer: Partially.

Verified good behavior:

- `quantmap --help` works with empty lab/server/model env vars.
- `status` degrades instead of crashing.
- `doctor` reports missing lab root and server binary as explicit diagnostic failures.
- `about` renders software/current-methodology identity and labels lab/DB unavailable.
- explicit-DB `explain`, `audit`, `compare`, and non-redacted `export` work with empty env vars.

Remaining problem:

- `src.config` only checks whether `QUANTMAP_LAB_ROOT` is `None`. If the variable exists but is an empty string, `LAB_ROOT` becomes `Path('.')`.
- `src.server` uses the same `None`-only pattern for server/model env paths.
- `export --strip-env` with empty `QUANTMAP_LAB_ROOT` completed, but the redaction path uses `str(LAB_ROOT)`. With `LAB_ROOT == Path('.')`, redaction can target `"."`, which is not a trustworthy local-lab redaction root.

Status: verified.

Closure decision: the general missing-env shell is improved, but empty-env handling is a newly confirmed settings boundary risk. It should be included in the Phase 2.1 bridge or fixed as a very small Phase 2 final patch if the project wants Phase 2 to close without a bridge label.

### C. Historical Reader Resilience

Question: Under malformed current methodology/config, do snapshot-first historical readers still work where they should?

Answer: Yes for the main reader paths tested.

Verified:

- imports of historical reader modules do not read live methodology files
- explicit-DB `explain` works with live methodology file reads blocked
- explicit-DB `compare` works with live methodology file reads blocked
- explicit-DB `export --lite` works with live methodology file reads blocked
- explicit-DB `audit` works without importing lab root at module import time
- `generate_report()` on a copied DB and temp lab root works with live methodology file reads blocked

Remaining caveats:

- `export --strip-env` still depends on `src.config` for redaction root.
- direct script entry points such as `python rescore.py` still import `src.config` eagerly.
- `list` still imports `runner` and remains lab-root based, not an explicit-DB reader.

Status: verified with bounded caveats.

Closure decision: historical reader resilience is strong enough for the original QM-022 blocker, but the redaction/config caveat should be tracked under settings/environment boundary work.

### D. Current-Input / Current-Run Fail-Loud Behavior

Question: Do current-input paths fail loudly and trust-safely when current files are malformed?

Answer: Yes, trust-safely. The operator polish is only partial.

Evidence:

- guarded `load_methodology_for_historical_scoring(..., allow_current_input=True)` raises `CurrentMethodologyLoadError`.
- guarded `quantmap rescore --current-input` on a copied temp DB exits non-zero and refuses to complete.
- `score_campaign()` refuses `force_new_anchors` unless `current_input=True`.
- snapshot-locked scoring still refuses `legacy_partial_methodology`.

Concern:

- current-input rescore logs a traceback through `logger.exception`. This is fail-loud and trust-safe, but not as operator-clean as `doctor`/`status`.

Status: verified.

Closure decision: fail-loud trust behavior is acceptable for closure, but a concise current-input rescore error message is a strongly preferred cleanup, not a separate phase blocker.

### E. Settings / Environment Boundary Readiness

Question: Is there now enough settings/environment boundary clarity to activate Phase 3 safely?

Answer: No.

Evidence:

- `src.config` still owns import-time `LAB_ROOT` as a constant.
- `src.server` still owns import-time server/model path constants.
- empty env strings are treated inconsistently: `quantmap.py` helper treats them as missing, while `src.config` treats them as `Path('.')`.
- `export --strip-env` still uses `src.config.LAB_ROOT` as the redaction authority, which becomes unsafe if the env var is empty.
- the canonical synthesis memo says telemetry/provider abstraction should follow settings decoupling.

Status: verified.

Closure decision: this is not the same as the original Phase 2 brittle-shell blocker, but it is real. It should become a narrow Phase 2.1 bridge before Phase 3 provider abstraction activates.

## Part 2 - Additional Blockers, Needs, and Considerations

| Issue | Why it matters | Classification | New or tracked? | Evidence |
|---|---|---|---|---|
| Empty env vars can become `Path('.')` in `src.config` and `src.server` | This can point runtime or redaction behavior at the repo/current directory instead of a real lab root or runtime path. It is a settings safety issue and can make export redaction misleading. | Phase 2.1 bridge candidate | New concrete evidence under existing QM-005 | `src.config.py` checks `is None`; `src.server.py` checks `is None`; probe showed `LAB_ROOT` resolves to repo root when env is empty. |
| `export --strip-env` relies on `src.config.LAB_ROOT` even when an explicit DB/output path is supplied | Historical export can be otherwise explicit-DB, but redaction still depends on current lab-root settings. With empty lab root, redaction root can become `"."`. | Phase 2.1 bridge candidate | Previously partially tracked under QM-005/export assumptions; this is sharper evidence | `src/export.py:207`, `src/export.py:220`; empty-env strip export completed. |
| Dry-run loads current methodology only to print elimination filters | This makes a structural dry-run vulnerable to active profile/registry failure. That may be acceptable for current-run semantics, but it needs a clear error and wording. | Phase 2 blocker | Previously tracked under QM-009; new validation detail | guarded dry-run raised `CurrentMethodologyLoadError`; normal dry-run lacks readiness handoff. |
| Direct `python rescore.py` remains config-import coupled | The CLI wrapper is improved, but direct script usage still depends on current env at import. | Carry forward / Phase 2.1 consideration | Previously visible in closure assessment | `rescore.py:33`; not required if `quantmap rescore` is the supported path. |
| Current-input rescore failure logs a traceback | Trust-safe but operator-noisy. It may confuse non-developer operators. | Strongly preferred Phase 2 cleanup | New validation detail under existing QM-022/QM-009 UX themes | guarded current-input rescore on copied DB exited 1 with `CurrentMethodologyLoadError` and traceback. |
| `list` remains lab-root based and cannot use explicit `--db` | This is not part of the snapshot-first explicit-DB reader set, but it limits read-only history usability under bad lab-root config. | Phase 2.1 bridge candidate | Tracked under QM-005/QM-007 | `quantmap.py` routes `list` to `runner.list_campaigns()`, which is lab-root/config based. |
| Provider work would currently need settings policy that does not exist | Starting telemetry providers now would likely recreate local assumptions in provider code. | Phase 3 gating consideration | Tracked under QM-005/TODO-017/QM-018 | synthesis memo Phase 3 warning; current `src.config`/`src.server` constants. |
| Anti-God-object guardrails remain important for any bridge | The next small fixes should avoid adding more logic to crowded modules except at the touched boundary. | Phase 3 gating consideration | Tracked under QM-017 and roadmap note | `src/runner.py` remains the dry-run/status/reporting pressure point. |

## Part 3 - Final Closure Gate Table

| Gate | Why it matters | Evidence | Status | Required for Phase 2 closure | Recommended disposition |
|---|---|---|---|---|---|
| Import-time current methodology loading removed from core reader imports | Prevents malformed current files from taking down historical readers. | guarded import probe passed for governance, score, report, report_campaign, export, explain, compare, audit_methodology, trust_identity, doctor, and quantmap. | met | required | Mark implementation evidence complete; keep QM-022 open until final closure fix lands. |
| Command-local CLI imports | Reduces blast radius across commands. | `quantmap --help` works with empty env; code shows command-local imports. | met | required | Keep. No extra CLI framework needed. |
| Degraded `status` | Operators can see software/DB/current-methodology separation. | empty-env and malformed-methodology probes show degraded status behavior. | met | strongly preferred | Keep. |
| Doctor current-methodology diagnostics | Operators need remediation path. | empty-env and malformed-methodology doctor probes show registry/profile checks and missing env messages. | met | required | Keep. |
| Explicit-DB historical readers under missing env | Historical snapshot readers should not require current lab env when explicit DB is supplied. | explain, audit, compare, and non-redacted export all passed with empty env. | met | required | Keep explicit-DB precedence. |
| Historical readers under malformed current methodology | Historical trust must come from snapshots. | explain, compare, report, export, audit/import probes passed with live methodology reads blocked. | met | required | Keep; document validation. |
| Current-input fail-loud semantics | Robustness must not hide invalid current files. | current-input loader and temp-DB rescore failed with `CurrentMethodologyLoadError`. | met | required | Keep; optionally polish traceback. |
| Snapshot-locked legacy partial refusal | Preserves Phase 1.1 trust invariant. | legacy-partial probe for `C01_threads_batch__standard` refused snapshot-locked scoring. | met | required | Keep. |
| Dry-run readiness messaging | Prevents dry-run from implying runtime readiness. | normal dry-run output lacks clear readiness handoff; guarded dry-run raises current methodology error. | not met | required | Tiny Phase 2 final patch required. |
| Missing/empty env semantics | Prevents wrong paths and misleading redaction/runtime assumptions. | `status`/`doctor` handle empty env, but `src.config` turns empty lab root into `Path('.')`; strip export completed with unsafe redaction root. | partially met | required for bridge, not original brittle-shell fix | Create Phase 2.1 bridge or include a narrow settings patch before Phase 3. |
| Settings/environment boundary for Phase 3 provider work | Providers need common config/discovery policy. | `src.config`/`src.server` import-time constants remain; TODO-017 open. | not met | required before Phase 3 activation | Phase 2.1 bridge recommended. |
| Boundary discipline | Prevents next work from enlarging god modules. | Phase 2 code stayed narrow; runner/report remain high-blast-radius. | partially met | strongly preferred | Carry as explicit guardrail in bridge and Phase 3 entry docs. |

## Part 4 - Recommendation

Recommendation: **Option B - Phase 2 is almost ready, but needs one tiny follow-up pass.**

Phase 2 should not be closed today.

The tiny Phase 2 final patch should be:

1. Update dry-run output/help to state that dry-run is structural validation only and that runtime readiness requires `quantmap doctor` / `quantmap status`.
2. Handle current-methodology load failure during dry-run filter rendering with a concise current-methodology error instead of an unhandled exception path.
3. Optionally remove traceback noise from current-input rescore failure while preserving fail-loud semantics.
4. Record a short Phase 2 closure validation memo after those probes pass.

This should be called a **Phase 2 final patch**, not Phase 2.1.

Why:

- It is tiny.
- It is directly tied to Phase 2 exit criteria.
- It does not require settings architecture or provider work.

## Part 5 - Is a Phase 2.1 Bridge Needed?

Yes, but for a different reason than the tiny closure patch.

A narrow **Phase 2.1 bridge** is justified before Phase 3 activation because settings/environment boundary readiness is not yet sufficient for telemetry/provider abstraction.

The bridge should be bounded to:

- normalize missing vs empty env behavior
- provide a small shared settings/path load boundary or result object
- make explicit-DB reader behavior independent of lab-root fallback where practical
- define redaction root behavior for export without relying blindly on current `LAB_ROOT`
- document the provider-discovery settings contract needed by Phase 3

The bridge should not include:

- telemetry provider implementation
- backend adapters
- broad runner refactor
- full packaging redesign
- report consolidation

## Part 6 - Phase 3 Activation Readiness

Phase 3 is **not ready to become active**.

Blocking condition:

> Settings/environment boundary hardening is only partially met.

Specific blockers:

- `src.config` still treats empty env as current directory.
- `src.server` still uses import-time path constants.
- export redaction can still depend on current lab-root state even for explicit-DB exports.
- provider work lacks a shared environment discovery policy.

Sequencing rule remains:

> Telemetry/provider abstraction follows settings/environment boundary hardening.

Phase 3 can become active only after either:

1. the Phase 2.1 bridge lands, or
2. a formal Phase 3 entry contract makes settings/environment boundary the first workstream and blocks provider implementation until it is done.

The safer recommendation is to land the bridge first.

## Final State

Current honest status:

- Phase 1 / 1.1: stable
- Phase 2: almost complete, but not closed
- Phase 2 final patch: required for dry-run/readiness closure
- Phase 2.1 bridge: recommended before Phase 3 activation
- Phase 3: pending, not active

