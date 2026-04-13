# QuantMap Known Issues and Audit Tracker

Last registry review: 2026-04-12

This is the living coordination tracker for QuantMap audit findings, live-run bugs, architectural debt, portability gaps, trust-surface risks, and feature blockers. It is intentionally markdown-first so it can be reviewed, diffed, and updated during active audits without depending on an external ticket system.

Use this file for actionable issues. Keep broad research notes, audit transcripts, and design essays in their source documents, then promote only concrete findings into this tracker.

## Current Project State

As of the 2026-04-12 Phase 2.1 completion pass, the Phase 1 Trust Bundle and Phase 1.1 Trust Bundle Stabilization are stable, Phase 2 Operational Robustness is closed, and Phase 2.1 Settings/Environment Bridge is closed. Phase 3 Platform Generalization is now active, beginning with boundary-aware telemetry/provider design.

Historical audit reports, audit response memos, and validation memos remain unchanged as records of what was known at the time. This tracker carries the current actionable state forward.

## How To Use This Tracker

1. Add one issue per root problem, not one issue per symptom.
2. Give every issue a stable `QM-NNN` ID. Do not reuse IDs after deletion or supersession.
3. Keep the summary table short enough to scan. Put evidence and nuance in the detail section.
4. Link related issues instead of duplicating the same concern in multiple entries.
5. Convert audit findings into tracker issues only when there is an action, decision, or explicit follow-up.
6. When an issue is resolved, record what changed and what evidence verifies it.
7. When an issue is deferred or challenged, record the reason. Silence is not a decision.
8. If a newer issue supersedes an older one, mark the older issue `resolved` or `wont_fix` and link the replacement.

## ID Convention

Use `QM-NNN` for all tracker issues.

Optional tags can appear in the title or related fields, but the ID stays neutral. This avoids renumbering when an issue moves from audit finding to bug, debt, or roadmap blocker.

Examples:

- `QM-001`: first tracked issue
- `QM-014`: later issue, even if it is a feature gap rather than a bug

## Status Model

| Status | Meaning |
|---|---|
| `new` | Captured but not yet validated or triaged. |
| `confirmed` | Reproduced, accepted as real, or backed by enough evidence to act. |
| `in_audit` | Currently under audit; evidence is still being gathered. |
| `accepted` | Accepted as a real issue, but not yet scheduled. |
| `challenged` | Plausible but disputed, incomplete, or contradicted by newer evidence. |
| `planned` | Intended for a defined upcoming cleanup or feature phase. |
| `in_progress` | Actively being worked. |
| `deferred` | Real issue, intentionally postponed with a reason. |
| `blocked` | Cannot proceed until another issue, audit, or dependency is resolved. |
| `resolved` | Fixed or otherwise completed; resolution notes must include verification. |
| `wont_fix` | Explicitly accepted as not worth changing; rationale required. |

## Category Model

Allowed categories:

- `bug`
- `audit_finding`
- `architectural_debt`
- `portability_gap`
- `trust_integrity_risk`
- `ux_issue`
- `feature_gap`
- `deferred_design_item`
- `investigation_needed`
- `blocked_by_audit`
- `blocked_by_dependency`

Use the category that best describes the primary root problem. Use impact fields to capture secondary effects.

## Severity Model

| Severity | Guidance |
|---|---|
| `critical` | Can corrupt benchmark meaning, break forensic reconstruction, or block core use in ordinary conditions. |
| `high` | Can mislead operators, damage trust, block major workflows, or make future optimization features unsafe to build on. |
| `medium` | Meaningful engineering or UX problem with a workaround or limited blast radius. |
| `low` | Cleanup, clarity, or future-proofing item with low immediate risk. |

## Priority Model

Priority is not the same as severity. Severity describes risk if the issue remains. Priority describes when it should be worked relative to other issues.

| Priority | Guidance |
|---|---|
| `P1` | Next-wave work. Fix or resolve before building more capability on top of this area. |
| `P2` | Important planned work. Should be scheduled, but may follow higher-leverage blockers. |
| `P3` | Track and revisit. Real issue, but acceptable to defer while stronger blockers are active. |

## Impact Dimensions

Use `none`, `low`, `medium`, or `high` for each dimension.

| Dimension | What It Means In QuantMap |
|---|---|
| Trust impact | Risk that QuantMap makes claims that cannot be verified, reconstructed, or trusted. |
| Portability impact | Risk that the tool depends on one machine, shell, path layout, OS behavior, or local lab setup. |
| Operator UX impact | Risk that an operator misreads state, gets stuck, or cannot tell what to do next. |
| Architecture impact | Risk to maintainability, module boundaries, testability, or safe evolution. |
| Optimize/Quick Tune impact | Risk to Smart Mode, Quick Tune, Optimize Mode, attribution, or automated recommendation features. |

## Summary Table

| ID | Title | Category | Status | Severity | Priority | Affected area | Discovered from | Trust | Portability | UX | Architecture | Optimize / Quick Tune | Owner | Last updated |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [QM-001](#qm-001-packaging-and-installed-command-bootstrap-are-brittle) | Packaging and installed command bootstrap are brittle | `portability_gap` | `accepted` | `high` | `P2` | packaging, CLI bootstrap, install path | Audit 1 response, pyproject inspection | medium | high | high | medium | medium | unassigned | 2026-04-11 |
| [QM-002](#qm-002-baseline-state-is-not-fully-self-contained-with-runs) | Baseline state is not fully self-contained with runs | `trust_integrity_risk` | `resolved` | `critical` | `P1` | campaign start snapshot, DB, export, report | Audit 1 response, Audit 3 response, Audit 4 response | high | low | medium | medium | high | unassigned | 2026-04-12 |
| [QM-003](#qm-003-methodology-and-governance-state-are-not-snapshotted-completely) | Methodology and governance state are not snapshotted completely | `trust_integrity_risk` | `resolved` | `critical` | `P1` | methodology lifecycle, scoring, compare, rescore | Audit 1 response, Audit 4 response | high | low | medium | medium | high | unassigned | 2026-04-12 |
| [QM-004](#qm-004-report-stack-risks-duplication-and-confusing-truth-surfaces) | Report stack risks duplication and confusing truth surfaces | `audit_finding` | `planned` | `high` | `P2` | report.md, report_v2.md, report_campaign.py, artifact hierarchy, report generation, identity sourcing | Audit 1 response, Audit 3 response, Audit 4 response, Audit 5 response | medium | low | high | high | medium | unassigned | 2026-04-12 |
| [QM-005](#qm-005-lab-root-and-local-path-assumptions-reduce-portability) | Lab-root and local path assumptions reduce portability | `portability_gap` | `planned` | `high` | `P2` | LAB_ROOT, results paths, server/log paths, environment defaults, settings resolution | Audit 1 response, Audit 5 response, repo audit assumptions scan | medium | high | medium | medium | high | unassigned | 2026-04-12 |
| [QM-006](#qm-006-root-cause-attribution-implementation-is-no-longer-blocked-on-evidence-audit) | Root-cause attribution implementation is no longer blocked on evidence audit | `feature_gap` | `planned` | `high` | `P1` | attribution MVP, telemetry evidence, background snapshots, migration dependencies | RCA Evidence Audit | high | low | medium | medium | high | unassigned | 2026-04-11 |
| [QM-007](#qm-007-historical-campaign-history-and-runnable-campaign-definitions-are-not-clearly-distinguished) | Historical campaign history and runnable campaign definitions are not clearly distinguished | `ux_issue` | `confirmed` | `medium` | `P2` | campaign discovery, `quantmap list`, `quantmap run`, DB history, campaign YAML files | Audit 2 response | medium | medium | high | medium | medium | unassigned | 2026-04-11 |
| [QM-008](#qm-008-campaign-completion-state-conflates-measurement-success-with-post-run-analysis-and-artifact-success) | Campaign completion state conflates measurement success with post-run analysis and artifact success | `trust_integrity_risk` | `resolved` | `high` | `P1` | campaign status, measurement persistence, analysis, report generation, artifacts | Audit 2 response | high | low | high | medium | high | unassigned | 2026-04-12 |
| [QM-009](#qm-009-dry-run-is-not-a-readiness-check-and-can-mislead-operators) | `--dry-run` is not a readiness check and can mislead operators | `ux_issue` | `resolved` | `medium` | `P1` | `quantmap run --dry-run`, YAML validation, telemetry startup, environment preflight | Audit 2 response | medium | medium | high | low | medium | unassigned | 2026-04-12 |
| [QM-010](#qm-010-optional-run-context-and-characterization-failure-degrades-evidence-quality-without-strong-enough-operator-signaling) | Optional run-context and characterization failure degrades evidence quality without strong enough operator signaling | `trust_integrity_risk` | `confirmed` | `high` | `P1` | run context capture, characterization, environmental evidence, reports, attribution readiness | Audit 2 response | high | medium | medium | medium | high | unassigned | 2026-04-11 |
| [QM-011](#qm-011-report-rendering-brittleness-can-produce-partial-or-misleading-artifacts) | Report rendering brittleness can produce partial or misleading artifacts | `trust_integrity_risk` | `planned` | `high` | `P2` | report rendering, report sections, artifact index, scoring-method display | Audit 3 response | medium | low | high | medium | medium | unassigned | 2026-04-12 |
| [QM-012](#qm-012-cli-mutation-and-side-effect-boundaries-are-not-surfaced-clearly-enough) | CLI mutation and side-effect boundaries are not surfaced clearly enough | `ux_issue` | `accepted` | `medium` | `P3` | command reference, help text, trust-surface docs, support triage | Audit 1 response | medium | low | high | low | low | unassigned | 2026-04-11 |
| [QM-013](#qm-013-identity-and-provenance-audit-completed-and-split-into-remediation-issues) | Identity and provenance audit completed and split into remediation issues | `blocked_by_audit` | `resolved` | `high` | `P1` | model identity, quantization identity, baseline identity, backend/build identity, methodology identity, reports | Audit 1 response, Audit 3 response, Audit 4 response | high | medium | medium | medium | high | unassigned | 2026-04-12 |
| [QM-014](#qm-014-explain-confidence-semantics-need-a-later-trust-review) | Explain confidence semantics need a later trust review | `deferred_design_item` | `deferred` | `medium` | `P3` | `explain.py`, confidence wording, briefing output, attribution confidence mapping | Audit 1 response | medium | low | medium | low | medium | unassigned | 2026-04-11 |
| [QM-015](#qm-015-quantmap-code-identity-is-not-persisted-with-runs) | QuantMap code identity is not persisted with runs | `trust_integrity_risk` | `resolved` | `high` | `P1` | run-start metadata, source/version fingerprinting, reports, exports | Audit 4 response | high | medium | medium | medium | high | unassigned | 2026-04-12 |
| [QM-016](#qm-016-requested-runtime-intent-is-not-separated-from-resolved-runtime-reality) | Requested runtime intent is not separated from resolved runtime reality | `trust_integrity_risk` | `planned` | `high` | `P2` | runner launch metadata, backend runtime inspection, DB provenance, reports | Audit 4 response | high | medium | medium | medium | high | unassigned | 2026-04-12 |
| [QM-017](#qm-017-runner-responsibility-fusion-creates-critical-change-risk) | Runner responsibility fusion creates critical change risk | `architectural_debt` | `accepted` | `critical` | `P1` | `src/runner.py`, campaign policy, measurement, persistence, UI, resume semantics | Audit 5 response | medium | medium | medium | high | high | unassigned | 2026-04-11 |
| [QM-018](#qm-018-telemetry-policy-is-too-fused-to-windows-centric-providers) | Telemetry policy is too fused to Windows-centric providers | `portability_gap` | `in_progress` | `high` | `P1` | telemetry providers, HWiNFO, sensor policy, Linux/NVIDIA portability, doctor/wizard readiness | Audit 5 response | high | high | medium | high | high | unassigned | 2026-04-13 |
| [QM-019](#qm-019-backend-coupling-to-llama-server-blocks-staged-generalization) | Backend coupling to llama-server blocks staged generalization | `architectural_debt` | `accepted` | `high` | `P2` | backend launch/control, runtime inspection, server contracts, future adapters | Audit 5 response | medium | high | medium | high | high | unassigned | 2026-04-11 |
| [QM-020](#qm-020-recommendation-semantics-and-output-persistence-are-missing) | Recommendation semantics and output persistence are missing | `trust_integrity_risk` | `accepted` | `high` | `P1` | optimization recommendations, reports, DB/export artifacts, CLI/UI wording | Audit 6 response | high | low | high | medium | high | unassigned | 2026-04-11 |
| [QM-021](#qm-021-optimization-search-and-control-orchestration-is-missing) | Optimization search and control orchestration is missing | `feature_gap` | `accepted` | `high` | `P2` | adaptive search, pruning, stopping rules, sweep orchestration, recommendation workflow | Audit 6 response | medium | low | medium | high | high | unassigned | 2026-04-11 |
| [QM-022](#qm-022-governance-default-profile-import-is-brittle-for-readers) | Governance default-profile import is brittle for readers | `architectural_debt` | `resolved` | `high` | `P1` | `src/governance.py`, CLI readers, profile loading, operational shell | Phase 1.1 real-workflow validation | low | medium | high | high | medium | unassigned | 2026-04-12 |

## Issue Template

Copy this block for new issues.

```markdown
### QM-NNN: Short imperative or descriptive title

| Field | Value |
|---|---|
| Category | `bug` |
| Status | `new` |
| Severity | `medium` |
| Priority | `P2` |
| Scope / affected area | module, command, report section, data table, workflow |
| Discovered from | audit number, live run ID, manual inspection, design review, repo audit |
| Evidence | File paths, commands, logs, audit excerpt, DB rows, report sections |
| Why it matters | Concrete risk or failure mode |
| Trust impact | `none` / `low` / `medium` / `high` |
| Portability impact | `none` / `low` / `medium` / `high` |
| Operator UX impact | `none` / `low` / `medium` / `high` |
| Architecture impact | `none` / `low` / `medium` / `high` |
| Optimize/Quick Tune impact | `none` / `low` / `medium` / `high` |
| Owner / current handler | unassigned |
| Recommended next action | Smallest useful next action |
| Blocked by | none, issue IDs, audit name, dependency |
| Related issues | issue IDs or source docs |
| Decision / resolution notes | Empty until accepted, deferred, resolved, or wont_fix |
| Verification evidence | Empty until resolved; include command, audit rerun, DB query, report inspection, or test evidence |
| Last updated | YYYY-MM-DD |

#### Evidence Notes

- Add concise evidence here. Prefer links to source files, audit docs, commands, and observed outputs.

#### Acceptance / Resolution Criteria

- Clear condition that would let this issue move to `resolved`.
```

## Detailed Issues

### QM-001: Packaging and installed command bootstrap are brittle

| Field | Value |
|---|---|
| Category | `portability_gap` |
| Status | `accepted` |
| Severity | `high` |
| Priority | `P2` |
| Scope / affected area | `pyproject.toml`, installed `quantmap` command, import/bootstrap path, fresh environment setup |
| Discovered from | Audit 1 response; manual pyproject inspection |
| Evidence | Audit 1 notes that the installed command path is not robust and ordinary shell use is not yet dependable. `pyproject.toml` exposes `quantmap = "quantmap:main"` while the project packages `src`, `configs`, and `requests` as top-level packages. |
| Why it matters | QuantMap cannot be treated as a dependable benchmarking tool if a fresh operator install depends on a tuned developer shell or fragile path assumptions. |
| Trust impact | `medium` |
| Portability impact | `high` |
| Operator UX impact | `high` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `medium` |
| Owner / current handler | unassigned |
| Recommended next action | Define and test the intended install/bootstrap story: fresh venv, editable install, installed console command, and direct repo-root command. |
| Blocked by | QM-005 should be understood first so packaging does not preserve lab-root assumptions. |
| Related issues | QM-005, Audit 1 response |
| Decision / resolution notes | Accepted as a stabilization target, but not the first forensic fix. |
| Verification evidence | Not resolved yet. |
| Last updated | 2026-04-11 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-1-RE`
- Source: `pyproject.toml`
- The risk is not just "install polish"; it is whether QuantMap can be run reliably outside the original development environment.

#### Acceptance / Resolution Criteria

- A documented fresh-environment install path works on Windows.
- `quantmap --help` and the core diagnostic/status commands work from an ordinary shell.
- Import paths do not rely on incidental current working directory behavior.
- Packaging tests or smoke commands are added to the release checklist.

### QM-002: Baseline state is not fully self-contained with runs

| Field | Value |
|---|---|
| Category | `trust_integrity_risk` |
| Status | `resolved` |
| Severity | `critical` |
| Priority | `P2` |
| Scope / affected area | campaign start snapshot, baseline YAML handling, DB persistence, export bundles, reports |
| Discovered from | Audit 1 response; Audit 3 response; Audit 4 response |
| Evidence | Audit 1 states that storing only the hash of `baseline.yaml` is not sufficient for historical reconstruction if the file changes later. Audit 3 strongly supports adding verbatim `baseline_content` and `campaign_content` into campaign snapshot state as part of reporting integrity work. Audit 4 accepts baseline ghosting as a critical provenance failure because hash-only traceability cannot reconstruct the effective historical configuration that governed a run. |
| Why it matters | A historical benchmark run must remain interpretable after local config files change. Hash-only traceability can prove difference but cannot reconstruct meaning, and reports need durable source content for the run definition they describe. |
| Trust impact | `high` |
| Portability impact | `low` |
| Operator UX impact | `medium` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Closed for Phase 1. Monitor only for legacy edge cases or future export/case-file expansion. |
| Blocked by | none |
| Related issues | QM-003, QM-004, QM-013, QM-015, Audit 1 response, Audit 4 response |
| Decision / resolution notes | Resolved by Phase 1 Trust Bundle and Phase 1.1 stabilization. Baseline content is persisted in `campaign_start_snapshot`, reports use snapshot-first identity, and legacy missing content is labeled as weaker evidence instead of silently inferred. |
| Verification evidence | `docs/decisions/Phase-1.1-Real-Workflow-Validation-Memo.md` verifies drift resistance after mutating `baseline.yaml`; Phase 1.1 direct probes verified snapshot baseline wins and no implicit fallback in snapshot-locked mode. |
| Last updated | 2026-04-12 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-1-RE`
- Source: `docs/AUDITS/4-11/Audit-3-RE`
- Source: `docs/AUDITS/4-11/Audit-4-RE`
- Relevant code area: `src/telemetry.py` campaign start snapshot collection.
- Relevant downstream users: reports, compare, export, rescore, future automated tuning.
- Audit 4 clarifies that hashes are useful for drift detection, but not sufficient when historical meaning must be reconstructed or explained.
- 2026-04-12 update: Phase 1/1.1 implementation and real-workflow validation verify snapshot-first baseline behavior for new snapshot-complete runs. Older hash-only rows remain weaker legacy evidence by design.

#### Acceptance / Resolution Criteria

- Every campaign persists the effective baseline content, not just the path and hash.
- Campaign definition content needed by reports/exports is preserved in DB-backed snapshot state or an explicitly equivalent self-contained artifact strategy.
- Reports and exports can identify and include the baseline state used by the run.
- A run remains interpretable after `configs/baselines/*.yaml` changes.
- A migration or fallback path is documented for older runs that only have hashes.

### QM-003: Methodology and governance state are not snapshotted completely

| Field | Value |
|---|---|
| Category | `trust_integrity_risk` |
| Status | `resolved` |
| Severity | `critical` |
| Priority | `P2` |
| Scope / affected area | scoring methodology, metric registry, governance profiles, compare, rescore, methodology lifecycle |
| Discovered from | Audit 1 response; Audit 4 response |
| Evidence | Audit 1 states that methodology snapshotting remains incomplete and that current on-disk methodology files plus scattered hashes are not enough for historically trustworthy interpretation. Audit 4 adds that historical interpretation must be tied to immutable methodology state, not live profile reloads or incomplete snapshots. |
| Why it matters | Score meaning can drift if metrics, gates, weights, or governance profiles change after a campaign. Automated optimization must not train or recommend against ambiguous historical semantics. |
| Trust impact | `high` |
| Portability impact | `low` |
| Operator UX impact | `medium` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Closed for Phase 1. The later operational shell brittleness was resolved under QM-022, not this trust snapshot issue. |
| Blocked by | none |
| Related issues | QM-002, QM-004, QM-013, QM-015, Audit 1 response, Audit 4 response, `docs/system/methodology_lifecycle.md` |
| Decision / resolution notes | Resolved by Phase 1.1 stabilization. `methodology_snapshots` is the historical methodology authority; snapshot-locked rescore refuses `legacy_partial` methodology; explicit current-input rescore is labeled separately. |
| Verification evidence | `docs/decisions/Phase-1.1-Real-Workflow-Validation-Memo.md` verifies profile/registry drift resistance, snapshot-locked rescore behavior, explicit current-input behavior, and legacy refusal. |
| Last updated | 2026-04-12 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-1-RE`
- Source: `docs/AUDITS/4-11/Audit-4-RE`
- Source: `docs/system/methodology_lifecycle.md`
- Relevant code areas: `src/governance.py`, `src/score.py`, `src/version.py`, reporting and rescore flows.
- 2026-04-12 update: Phase 1.1 real-workflow validation confirms snapshot-first methodology behavior. The separate malformed-profile import brittleness found during validation was tracked and resolved as QM-022 during Phase 2 Operational Robustness.

#### Acceptance / Resolution Criteria

- Each campaign records the effective methodology/governance state needed to interpret its scores.
- Reports distinguish the methodology used at run time from the methodology currently installed.
- Rescoring is explicitly treated as a migration/new interpretation, not a silent refresh.
- Export bundles carry enough methodology state for offline review.

### QM-004: Report stack risks duplication and confusing truth surfaces

| Field | Value |
|---|---|
| Category | `audit_finding` |
| Status | `resolved` |
| Severity | `high` |
| Priority | `P2` |
| Scope / affected area | `report.md`, `report_v2.md`, `src/report_campaign.py`, artifact hierarchy, report generation functions, identity sourcing, operator interpretation |
| Discovered from | Audit 1 response; Audit 3 response; Audit 4 response; Audit 5 response; manual inspection |
| Evidence | Audit 3 accepts that the dual-report model is too ambiguous, report naming does not identify the canonical human-facing report, and the current report stack duplicates conceptual territory across summaries, rankings, eliminations, campaign identity, artifact references, and interpretation logic. Audit 4 confirms that report identity can leak from live disk state and must move to snapshot-first sourcing. Audit 5 adds that `src/report_campaign.py` is oversized and mixes aggregation, interpretation, formatting, rendering, and report-specific decisions in a way that creates architectural drag. |
| Why it matters | If multiple report surfaces disagree, duplicate stale logic, imply stronger claims than the DB supports, derive identity labels from current disk state, or centralize too many report responsibilities in one module, operators can make bad benchmarking decisions and historical reports can drift away from historical truth. |
| Trust impact | `medium` |
| Portability impact | `low` |
| Operator UX impact | `high` |
| Architecture impact | `high` |
| Optimize/Quick Tune impact | `medium` |
| Owner / current handler | unassigned |
| Recommended next action | In Phase 2, decide the canonical report model and reduce duplicated report paths. Snapshot-first identity work is complete; report consolidation remains. |
| Blocked by | none |
| Related issues | QM-002, QM-003, QM-008, QM-011, QM-013, QM-015, QM-016, QM-017, Audit 1 response, Audit 3 response, Audit 4 response, Audit 5 response |
| Decision / resolution notes | Partially resolved by Phase 1/1.1: historical identity now uses snapshot-first trust surfaces and legacy/current-input labels are explicit. Remaining work is Phase 2 report consolidation and module-boundary cleanup, not a Phase 1 trust blocker. |
| Verification evidence | `docs/decisions/Phase-1.1-Real-Workflow-Validation-Memo.md` verifies `report v1/v2` convergence on snapshot identity. Remaining canonical report-model work has not been implemented. |
| Last updated | 2026-04-12 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-1-RE`
- Source: `docs/AUDITS/4-11/Audit-3-RE`
- Source: `docs/AUDITS/4-11/Audit-4-RE`
- Source: `docs/AUDITS/4-11/Audit-5-RE`
- Relevant code area: `src/report_campaign.py`
- Audit 3 accepts that `report.md` and `report_v2.md` create real confusion because their names do not communicate which is canonical, deeper, transitional, or long-term.
- Audit 3 accepts that duplicated conceptual territory now imposes maintenance cost, truth-surface ambiguity, and rendering risk.
- Audit 3 explicitly rejects solving this by stripping evidence depth; the evidence-first philosophy should be preserved.
- Audit 4 frames live-state identity leakage as the ordinary operational danger behind stronger spoofing risks: report identity must come from immutable historical state, not current disk state.
- Audit 5 accepts that `src/report_campaign.py` is architecturally oversized, but cautions that reporting refactor work must respect the Audit 3 canonical report direction.
- 2026-04-12 update: Phase 1.1 closed the snapshot-first report identity portion. Do not close this issue until the duplicated report surface and canonical report model are resolved.

#### Acceptance / Resolution Criteria

- Canonical report surface is named and documented.
- Every major report claim has a clear data source.
- Report identity is sourced from immutable run snapshot state before live disk state.
- Legacy fallback identity, when unavoidable, is visibly labeled as weaker than immutable historical identity.
- Duplicate report-generation paths are removed, isolated, or explicitly justified with a transition plan.
- Useful compact-report elements are ported or intentionally preserved before any old report path is retired.
- Artifact registration reflects the current canonical report outputs.
- The canonical artifact strategy is captured as a decision record once chosen.
- Report decomposition reduces responsibility fusion without dropping evidence-rich sections or bypassing the canonical report-model decision.

### QM-005: Lab-root and local path assumptions reduce portability

| Field | Value |
|---|---|
| Category | `portability_gap` |
| Status | `in_progress` |
| Severity | `high` |
| Priority | `P2` |
| Scope / affected area | `LAB_ROOT`, results paths, logs, server startup, environment defaults, settings resolution, local path handling |
| Discovered from | Audit 1 response; Audit 5 response; `python tools/repo_audit.py assumptions` |
| Evidence | Audit 1 says hardcoded or sticky lab-root assumptions must be removed or normalized. The repo audit assumptions scan reports Windows drive paths, local user paths, CUDA paths, HWiNFO assumptions, model-store paths, and backend assumptions. Audit 5 accepts hardcoded lab-root and drive assumptions as real deployment blockers and makes configuration/environment decoupling the first architecture/generalization priority. |
| Why it matters | QuantMap must run on arbitrary operator machines without silently inheriting one lab's directory layout, model storage, CUDA installation path, or HWiNFO setup. |
| Trust impact | `medium` |
| Portability impact | `high` |
| Operator UX impact | `medium` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Carry remaining local-path portability issues into Phase 3/later platform work without reopening the completed Phase 2.1 bridge. Use the assumptions audit CSV to separate legitimate examples from runtime assumptions. |
| Blocked by | none |
| Related issues | QM-001, QM-018, QM-019, Audit 1 response, Audit 5 response, `tools/repo_audit.py` |
| Decision / resolution notes | Phase 2.1 completed the narrow settings/environment bridge: missing/empty/current-directory required path env values no longer silently become `Path('.')`; explicit-DB historical readers remain independent; and `export --strip-env` hard-fails without a trustworthy redaction root. Broader local-path portability remains open for Phase 3/later work because this issue also includes CUDA, HWiNFO, model-store, packaging, and backend assumptions. |
| Verification evidence | `docs/decisions/Phase-2.1-Settings-Environment-Bridge-Implementation-Validation-Memo.md` verifies the completed Phase 2.1 bridge. Broader portability is not fully resolved. |
| Last updated | 2026-04-12 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-1-RE`
- Source: `docs/AUDITS/4-11/Audit-5-RE`
- Tooling: `python tools/repo_audit.py assumptions --csv audit_assumptions.csv`
- Important distinction: documentation examples can remain if clearly marked; runtime defaults and hidden fallbacks need stricter treatment.
- Audit 5 clarifies that path hardcoding, telemetry provider lock-in, backend coupling, and oversized modules are related but distinct remediation families.
- 2026-04-12 update: This became the Phase 2.1 settings/environment bridge after Phase 2 Operational Robustness closure.
- 2026-04-12 closure-readiness update: Phase 2 brittle-shell work routed around several import-time assumptions, but did not close the broader settings/path boundary needed before telemetry provider abstraction.
- 2026-04-12 final closure pass: explicit-DB readers work under empty env in several cases, but `export --strip-env` still depends on current `LAB_ROOT` redaction semantics; this was assigned to the Phase 2.1 bridge before Phase 3.
- 2026-04-12 Phase 2.1 completion: bridge validation confirms missing/empty/current-directory required paths are unavailable instead of `Path('.')`, explicit-DB readers remain independent, and export redaction now requires a trustworthy root.

#### Acceptance / Resolution Criteria

- Runtime paths come from explicit config, CLI args, or documented environment variables.
- Default lab root behavior is predictable and portable.
- CUDA, HWiNFO, model-store, and backend assumptions are detected and reported rather than silently assumed.
- Settings/config resolution is centralized enough that later provider and backend work does not preserve the original lab layout.
- Fresh-machine smoke tests do not require the original developer path layout.

### QM-006: Root-cause attribution implementation is no longer blocked on evidence audit

| Field | Value |
|---|---|
| Category | `feature_gap` |
| Status | `in_progress` |
| Severity | `high` |
| Priority | `P1` |
| Scope / affected area | Attribution MVP, telemetry evidence model, `background_snapshots`, `campaign_start_snapshot`, attribution rule implementation |
| Discovered from | RCA Evidence Audit, 2026-04-11 |
| Evidence | The RCA Evidence Audit confirms that the database and telemetry formats are ready for the Stage 2 implementation. |
| Why it matters | Attribution increases QuantMap's explanatory power and trust surface. |
| Trust impact | `high` |
| Portability impact | `low` |
| Operator UX impact | `medium` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Proceed to Stage 2 implementation planning: core module and first rules. |
| Blocked by | none |
| Related issues | QM-003, QM-004, `docs/AUDITS/4-11/RCA-Evidence-Audit.md`, `docs/decisions/Root-Cause-Attribution/DECISION-Root-Cause-Attribution.md` |
| Decision / resolution notes | Audit complete. Database schema and connectivity for attribution confirmed. |
| Verification evidence | [RCA Evidence Audit](file:///d:/Workspaces/QuantMap_agent/docs/AUDITS/4-11/RCA-Evidence-Audit.md) |
| Last updated | 2026-04-11 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/RCA-Evidence-Audit.md`
- Findings confirm:
  - `gpu_throttle_reasons` format consistency.
  - `gpu_vram_total_mb` presence in snapshot.
  - Population of activity flags in `background_snapshots`.
  - Valid `cycle_id` linkage in telemetry rows.

#### Acceptance / Resolution Criteria

- A short evidence audit report exists and is linked from this issue.
- The report records findings for each required evidence source.
- The report explicitly states whether `GPU_HW_OTHER_THROTTLE` remains deferred or needs review for reinstatement.
- Stage 2 attribution implementation is authorized.

### QM-007: Historical campaign history and runnable campaign definitions are not clearly distinguished

| Field | Value |
|---|---|
| Category | `ux_issue` |
| Status | `in_progress` |
| Severity | `medium` |
| Priority | `P1` |
| Scope / affected area | Campaign discovery, `quantmap list`, `quantmap run`, DB history, campaign YAML files, rescore workflow |
| Discovered from | Audit 2 response |
| Evidence | Audit 2 identifies the "Ghost Campaign" problem: `quantmap list` pulls exclusively from `lab.sqlite`, while `quantmap run` requires a valid YAML file on disk. A campaign can remain visible in history after its YAML is deleted, and disk-only campaign definitions may not appear in DB-backed history views. |
| Why it matters | Operators need to know whether a campaign is historical evidence, a runnable definition, or both. Blurring DB history with runnable YAML definitions can make the project feel inconsistent even when each subsystem is technically doing what it was designed to do. |
| Trust impact | `medium` |
| Portability impact | `medium` |
| Operator UX impact | `high` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `medium` |
| Owner / current handler | unassigned |
| Recommended next action | Define the campaign truth model in operator-facing terms: historical campaigns from DB, runnable campaign definitions from YAML, and the explicit states where they overlap or diverge. Then update list/run/status messaging to expose that distinction. |
| Blocked by | none |
| Related issues | QM-001, QM-005 |
| Decision / resolution notes | Confirmed by Audit 2 as a root discovery/history ambiguity, not merely a missing-file bug. |
| Verification evidence | Not resolved yet. |
| Last updated | 2026-04-11 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-2-RE`
- Audit 2 states that `quantmap list` shows every campaign record in `lab.sqlite`.
- Audit 2 states that `quantmap run` requires a valid YAML on disk plus a valid runtime environment.
- Audit 2 explicitly concludes that a campaign can be historical, meaning DB-only, but not runnable, meaning YAML-missing.

#### Acceptance / Resolution Criteria

- Operator-facing campaign discovery distinguishes historical DB records from runnable YAML definitions.
- A campaign that is historical but not runnable is labeled as such instead of appearing simply "available."
- Disk-only runnable definitions have an intentional discovery path or an explicit explanation for why they are not shown in DB history.
- Rescore/history flows continue to work for DB-backed historical campaigns without implying those campaigns can be rerun.

### QM-008: Campaign completion state conflates measurement success with post-run analysis and artifact success

| Field | Value |
|---|---|
| Category | `trust_integrity_risk` |
| Status | `resolved` |
| Severity | `high` |
| Priority | `P1` |
| Scope / affected area | Campaign status, cycle/config completion, request persistence, `analyze_campaign`, report generation, artifact creation |
| Discovered from | Audit 2 response |
| Evidence | Audit 2 identifies "Completion Boundary Ambiguity": `raw.jsonl` and DB requests are persisted immediately, but a crash during post-measurement `analyze_campaign` can mark the campaign failed even when all measurement data is safely on disk. Audit 2 also flags post-run failure masking when report generation fails and the operator cannot easily tell that measurement succeeded. |
| Why it matters | A failed report or analysis step is materially different from failed measurement. If campaign status does not preserve that boundary, operators may discard valid data, misread run health, or lose confidence in the DB as the execution state machine. |
| Trust impact | `high` |
| Portability impact | `low` |
| Operator UX impact | `high` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Closed for Phase 1. Future UX polish should use the layered fields rather than reopening the core state-model issue. |
| Blocked by | none |
| Related issues | QM-004, QM-002, QM-003 |
| Decision / resolution notes | Resolved by Phase 1/1.1 layered runtime state. Campaign measurement status, analysis status, report status, and per-artifact truth are now separated; `report_status='partial'` is the approved mixed-artifact outcome. |
| Verification evidence | Phase 1.1 stabilization implemented and validated report/artifact status separation; real-workflow validation treats the trust bundle as stable. |
| Last updated | 2026-04-12 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-2-RE`
- Audit 2 runtime mutation table marks campaign end as writing `report.md`, `report_v2.md`, and `scores.csv`, while noting that artifact generation is post-completion logic.
- Audit 2 states that if `analyze_campaign` crashes after measurement, the campaign can be marked `failed` despite 100% of measurement data being persisted.
- Audit 2 prioritizes post-run failure masking as high severity.
- 2026-04-12 update: Layered state is no longer a Phase 1 blocker. Related report consolidation or UX display refinements should be tracked under QM-004/QM-011 or future Phase 2 items if concrete.

#### Acceptance / Resolution Criteria

- A completed measurement phase remains distinguishable from failed analysis/report/artifact generation.
- Operator output and history/status views make clear whether measurement data is available.
- Post-run artifact failures do not imply measurement data loss.
- Recovery or rerun guidance tells the operator whether to rerun measurement or regenerate/analyze artifacts.

### QM-009: `--dry-run` is not a readiness check and can mislead operators

| Field | Value |
|---|---|
| Category | `ux_issue` |
| Status | `in_progress` |
| Severity | `medium` |
| Priority | `P1` |
| Scope / affected area | `quantmap run --dry-run`, YAML validation, run-plan construction, telemetry startup checks, environment readiness messaging |
| Discovered from | Audit 2 response |
| Evidence | Audit 2 identifies "Dry-Run Purity Illusion": `run --dry-run` performs structural validation of YAML and schedule, but skips `tele.startup_check()`. A campaign can pass dry-run and immediately fail at runtime due to missing sensors or invalid environment state. |
| Why it matters | Dry-run is useful, but operators may reasonably interpret it as readiness validation. If it only validates structure, its output must say so clearly or provide a separate readiness path. |
| Trust impact | `medium` |
| Portability impact | `medium` |
| Operator UX impact | `high` |
| Architecture impact | `low` |
| Optimize/Quick Tune impact | `medium` |
| Owner / current handler | unassigned |
| Recommended next action | Closed. Keep broader settings/environment readiness work under QM-005 and TODO-031. |
| Blocked by | none |
| Related issues | QM-001, QM-005, QM-010 |
| Decision / resolution notes | Confirmed by Audit 2 as a UX/trust-surface problem, not as evidence that dry-run should necessarily perform live telemetry checks by default. Resolved by clarifying dry-run as structural validation only, adding a doctor/status readiness handoff, and cleanly blocking dry-run when active current methodology cannot be loaded. |
| Verification evidence | `docs/decisions/Phase-2-Operational-Robustness-Closure-Validation-Memo.md` verifies normal dry-run wording and malformed-current-methodology dry-run blocking behavior. |
| Last updated | 2026-04-12 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-2-RE`
- Audit 2 states that dry-run skips `tele.startup_check()`.
- Audit 2 states that a campaign can pass dry-run and fail immediately at runtime due to missing sensor or invalid environment state.
- 2026-04-12 closure validation: dry-run output now states structural validation only and points operators to `quantmap doctor` / `quantmap status`.

#### Acceptance / Resolution Criteria

- `--dry-run` help/output states whether it is structural validation, readiness validation, or both.
- A passing dry-run no longer implies telemetry/environment readiness unless those checks actually ran.
- Operators have a clear next command or mode for environment readiness when they need it.
- Tests or smoke checks cover the distinction between structural dry-run and runtime preflight.

### QM-010: Optional run-context and characterization failure degrades evidence quality without strong enough operator signaling

| Field | Value |
|---|---|
| Category | `trust_integrity_risk` |
| Status | `confirmed` |
| Severity | `high` |
| Priority | `P1` |
| Scope / affected area | `run_context.py`, characterization capture, cycle context files, environment report sections, contamination confidence, future attribution evidence |
| Discovered from | Audit 2 response |
| Evidence | Audit 2 identifies "Environmental Context vs. Measurement Validity": if `create_run_context` fails, such as from an `nvsmi` error, the runner logs a warning and proceeds. Core TTFT/TG measurements may remain valid, but environmental context and contamination confidence are degraded. |
| Why it matters | QuantMap is a benchmarking and forensic tool. A run can have valid performance measurements but weakened environmental evidence. That distinction must be surfaced strongly enough that reports and future attribution do not appear more certain than the captured context supports. |
| Trust impact | `high` |
| Portability impact | `medium` |
| Operator UX impact | `medium` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Define evidence-quality states for non-fatal run-context/characterization failures and surface them in run output, DB/report context, and any future attribution confidence logic. |
| Blocked by | none |
| Related issues | QM-003, QM-006, QM-009 |
| Decision / resolution notes | Confirmed by Audit 2 as evidence-quality degradation, not a generic optional dependency complaint. |
| Verification evidence | Not resolved yet. |
| Last updated | 2026-04-11 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-2-RE`
- Audit 2 runtime mutation table notes that `run_context` failure at cycle start is non-fatal.
- Audit 2 states that when `create_run_context` fails, the runner logs a warning and proceeds.
- Audit 2 states that core measurement data can remain valid while the environment section of the report becomes unreliable.

#### Acceptance / Resolution Criteria

- Non-fatal run-context or characterization failures produce an explicit evidence-quality state, not only a warning line.
- Reports distinguish measurement validity from environmental context completeness.
- Future attribution confidence can consume the evidence-quality state instead of inferring from missing fields ad hoc.
- Operators can tell whether degraded context requires rerun, caution, or no action.

### QM-011: Report rendering brittleness can produce partial or misleading artifacts

| Field | Value |
|---|---|
| Category | `trust_integrity_risk` |
| Status | `planned` |
| Severity | `high` |
| Priority | `P2` |
| Scope / affected area | Report rendering, report sections, artifact index, scoring-method display, presentation failure handling |
| Discovered from | Audit 3: Reporting, Artifacts, and Evidence Audit |
| Evidence | Audit 3 accepts direct evidence that report rendering can fail partially while the underlying benchmark run remains valid, including localized section failures such as Appendix B with `name 'stats' is not defined` (fixed 2026-04-13), artifact self-reference inconsistencies, output mismatch between claimed and indexed artifacts, and `LCB Computation Method: unknown` appearing where the system should know the method. |
| Why it matters | The report layer is the operator's main interpretation surface. If it renders partial failures, unknown fallbacks, or artifact claims that do not line up with the artifact index, operators may doubt valid measurement data or trust a report claim that is not actually supported. |
| Trust impact | `medium` |
| Portability impact | `low` |
| Operator UX impact | `high` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `medium` |
| Owner / current handler | unassigned |
| Recommended next action | In Phase 2, continue report rendering hardening and canonical report cleanup. Phase 1.1 already made artifact status/failure visibility non-misleading enough for trust stability. |
| Blocked by | none |
| Related issues | QM-004, QM-008, QM-002, QM-003 |
| Decision / resolution notes | Partially resolved by Phase 1.1: artifact status/hash/error/verification are surfaced and report failures can produce `partial` status. Remaining work is broader report hardening/consolidation. |
| Verification evidence | Phase 1.1 validation verified artifact-reader convergence and report partial behavior. No full canonical report consolidation has been completed. |
| Last updated | 2026-04-13 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-3-RE`
- Audit 3 cites localized report section failure with `name 'stats' is not defined`. Fixed 2026-04-13: `_appendix_eliminations` in `src/report_campaign.py` now reads from `scores_result.get("stats", {})` instead of the undefined bare name `stats`. Validated via unit test and rescore end-to-end pass.
- Audit 3 cites artifact self-reference inconsistencies and mismatch between claimed output and artifact index.
- Audit 3 says `LCB Computation Method: unknown` and similar fallback weakness are unacceptable in canonical reporting.
- Audit 3 supports hardening report rendering with safer lookups and avoiding routine fallback stubs in ordinary campaign runs.
- 2026-04-12 update: Phase 1.1 closed the trust-surface portion of artifact/report truth. Keep this issue open for Phase 2 report rendering robustness and canonical output cleanup.

#### Acceptance / Resolution Criteria

- Known brittle report sections render without routine fallback failures.
- `lcb_method` is populated and displayed consistently when the scoring method is known.
- Artifact index entries match the actual canonical outputs.
- If a report section fails, the output clearly marks presentation degradation without implying benchmark measurement failure.

### QM-012: CLI mutation and side-effect boundaries are not surfaced clearly enough

| Field | Value |
|---|---|
| Category | `ux_issue` |
| Status | `accepted` |
| Severity | `medium` |
| Priority | `P3` |
| Scope / affected area | Command reference, CLI help, trust-surface docs, support triage, read-only vs mutating command expectations |
| Discovered from | Audit 1: Project Reality / Capability Audit |
| Evidence | Audit 1 response accepts the command mutation classification as valuable and says it should not remain audit-only knowledge. It should inform command reference docs, help output where appropriate, support triage guidance, and trust-surface language. |
| Why it matters | QuantMap writes DB rows, files, reports, and runtime artifacts. Operators need to know which commands inspect state safely and which commands mutate evidence or filesystem state. Hidden side effects weaken trust, even when the mutations are correct. |
| Trust impact | `medium` |
| Portability impact | `low` |
| Operator UX impact | `high` |
| Architecture impact | `low` |
| Optimize/Quick Tune impact | `low` |
| Owner / current handler | unassigned |
| Recommended next action | Promote the audit command-side-effect matrix into durable docs and, where useful, CLI help text: read-only, file-writing, DB-writing, and mixed mutating paths. |
| Blocked by | none |
| Related issues | QM-007, QM-008, QM-009 |
| Decision / resolution notes | Accepted from Audit 1, but lower priority than forensic self-containment and runtime truth-model fixes. |
| Verification evidence | Not resolved yet. |
| Last updated | 2026-04-11 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-1-RE`
- Audit 1 response explicitly states that command mutation classification should not stay buried in the audit.
- Relevant docs: `docs/system/command_reference.md`, future CLI help text, support playbooks.

#### Acceptance / Resolution Criteria

- Command reference documents side-effect classes for major commands.
- Commands that mutate DB/files are distinguishable from inspection commands in docs or help.
- Support guidance can tell an operator which commands are safe to run during diagnosis.

### QM-013: Identity and provenance audit completed and split into remediation issues

| Field | Value |
|---|---|
| Category | `blocked_by_audit` |
| Status | `resolved` |
| Severity | `high` |
| Priority | `P1` |
| Scope / affected area | Model identity, quantization identity, baseline identity, backend/build identity, methodology identity, report metadata, export metadata |
| Discovered from | Audit 1 response; Audit 3 response; Audit 4 response |
| Evidence | Audit 1 response says the identity/provenance audit must verify that model, quantization, baseline, backend/build, and methodology identity are surfaced correctly and without stale leakage. Audit 3 response says later identity/provenance work must inspect report metadata sourcing. Audit 4 completed that focused review and accepted baseline ghosting, system amnesia, identity leakage, requested-vs-resolved drift, and governance fragility as distinct provenance weaknesses. |
| Why it matters | QuantMap's forensic value depends on being able to say exactly what was measured, how it was run, which QuantMap logic measured it, and how it was interpreted. Stale or leaky identity metadata can make reports and future optimization features look more certain than the underlying evidence allows. |
| Trust impact | `high` |
| Portability impact | `medium` |
| Operator UX impact | `medium` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | No direct action on this placeholder. Use the split remediation issues for current work; Phase 1 trust remediations are stable, while requested-vs-resolved runtime provenance remains under QM-016. |
| Blocked by | none |
| Related issues | QM-002, QM-003, QM-004, QM-005, QM-011, QM-015, QM-016 |
| Decision / resolution notes | Resolved as an audit blocker because Audit 4 completed the focused identity/provenance review. Active remediation is now tracked under the related issues rather than this audit placeholder. |
| Verification evidence | `docs/AUDITS/4-11/Audit-4-RE` accepted the focused identity/provenance findings and remediation priorities. `docs/decisions/Phase-1.1-Real-Workflow-Validation-Memo.md` verifies the Phase 1 trust remediations are stable. |
| Last updated | 2026-04-12 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-1-RE`
- Source: `docs/AUDITS/4-11/Audit-3-RE`
- Source: `docs/AUDITS/4-11/Audit-4-RE`
- Audit 1 lists model identity, quantization identity, baseline identity, backend/build identity, and methodology identity as required provenance audit targets.
- Audit 3 adds that report metadata sourcing must be inspected as part of later identity/provenance work.
- Audit 4 splits the confirmed problem into baseline ghosting, system amnesia, identity leakage, provenance drift, and governance fragility.
- 2026-04-12 update: This remains closed as an audit placeholder. Baseline, methodology, snapshot-first report identity, and QuantMap code identity remediations are now stable; unresolved provenance work continues under QM-016 and Phase 2 operational robustness issues.

#### Acceptance / Resolution Criteria

- Identity/provenance audit document exists and is linked from this issue.
- Audit verifies where each identity field originates and where it is surfaced.
- Confirmed stale/leaky identity defects are promoted to specific remediation issues or folded into existing ones.
- Reports and exports have an explicit path to trustworthy identity/provenance display.

### QM-014: Explain confidence semantics need a later trust review

| Field | Value |
|---|---|
| Category | `deferred_design_item` |
| Status | `deferred` |
| Severity | `medium` |
| Priority | `P3` |
| Scope / affected area | `explain.py`, confidence wording, briefing output, attribution confidence mapping |
| Discovered from | Audit 1 response |
| Evidence | Audit 1 response accepts confidence metric logic in `explain.py` as a valid issue, but explicitly places it below structural traceability and portability problems and says it should be revisited after reporting and provenance audits. |
| Why it matters | Confidence language is part of QuantMap's trust surface. If it becomes too strong, too vague, or inconsistent with attribution confidence later, operators may over-trust explanations. |
| Trust impact | `medium` |
| Portability impact | `low` |
| Operator UX impact | `medium` |
| Architecture impact | `low` |
| Optimize/Quick Tune impact | `medium` |
| Owner / current handler | unassigned |
| Recommended next action | Revisit confidence semantics after report consolidation and identity/provenance audit, especially where `explain.py` will interact with attribution confidence. |
| Blocked by | QM-004 and the active provenance remediation issues should progress first; QM-006 may also affect attribution confidence vocabulary. |
| Related issues | QM-003, QM-006, QM-011, QM-015, QM-016 |
| Decision / resolution notes | Deferred by Audit 1 priority decision; valid but intentionally not first-wave remediation. |
| Verification evidence | Not resolved yet. |
| Last updated | 2026-04-11 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-1-RE`
- Audit 1 response says confidence metric logic matters but does not currently threaten forensic trust at the same level as missing baseline/methodology state.
- Root-cause attribution docs propose confidence semantics that may need alignment with `explain.py`.

#### Acceptance / Resolution Criteria

- Confidence terms in `explain.py`, reports, and attribution are reviewed together.
- Confidence output distinguishes observed facts, inferred explanations, degraded evidence, and unknown states.
- Any renamed or remapped confidence values are documented and covered by tests or fixtures.

### QM-015: QuantMap code identity is not persisted with runs

| Field | Value |
|---|---|
| Category | `trust_integrity_risk` |
| Status | `resolved` |
| Severity | `high` |
| Priority | `P1` |
| Scope / affected area | run-start metadata, source/version fingerprinting, DB provenance, reports, exports, forensic review |
| Discovered from | Audit 4 response |
| Evidence | Audit 4 accepts "system amnesia" as real: QuantMap captures identity for the inference binary more robustly than it captures identity for itself. Without a QuantMap git commit, version string, or equivalent source fingerprint, historical review cannot prove which QuantMap logic measured and interpreted a run. |
| Why it matters | A benchmark's meaning depends on the code that measured it and interpreted it. Bug-era and post-fix-era runs must be distinguishable, and reports/exports should not imply that runtime input identity is enough to reconstruct the result. |
| Trust impact | `high` |
| Portability impact | `medium` |
| Operator UX impact | `medium` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Closed for Phase 1. Future packaging work may refine identity labels, but run-time QuantMap identity is now persisted. |
| Blocked by | none |
| Related issues | QM-002, QM-003, QM-004, QM-013, QM-016 |
| Decision / resolution notes | Resolved by Phase 1 Trust Bundle. `src/code_identity.py` captures QuantMap version/git/source-tree identity and stores it in run-start snapshot metadata; reports and exports carry run identity separately from exporter identity. |
| Verification evidence | Phase 1 post-implementation validation verified QuantMap identity capture; Phase 1.1 export validation verified run/exporter identity separation remains converged. |
| Last updated | 2026-04-12 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-4-RE`
- Audit 4 says forensic review must separate "same run inputs" from "same QuantMap logic."
- Relevant code areas likely include `src/version.py`, run-start snapshot collection, report generation, and export paths.
- 2026-04-12 update: The fallback policy has been implemented narrowly enough for Phase 1 trust stability. Packaging/installed-command identity polish remains under QM-001 if needed.

#### Acceptance / Resolution Criteria

- New runs persist QuantMap's code identity in immutable run-start metadata.
- Reports and exports display or carry the code identity used for the run.
- Non-git installs have a documented fallback identity strategy.
- Older runs without code identity are labeled as historically weaker rather than silently filled from current source state.

### QM-016: Requested runtime intent is not separated from resolved runtime reality

| Field | Value |
|---|---|
| Category | `trust_integrity_risk` |
| Status | `planned` |
| Severity | `high` |
| Priority | `P2` |
| Scope / affected area | runner launch metadata, backend runtime inspection, DB provenance, report identity, compare/export truth surface |
| Discovered from | Audit 4 response |
| Evidence | Audit 4 accepts that storing requested launch intent is not enough when the server may clip, coerce, ignore, or resolve runtime parameters differently from what QuantMap asked for, such as a requested `-ngl 90` resolving to an effective 62-layer configuration. |
| Why it matters | Requested intent and achieved runtime state are both important, but not interchangeable. If QuantMap preserves only intent, reports and future optimization can mistake planned runtime configuration for actual runtime reality. |
| Trust impact | `high` |
| Portability impact | `medium` |
| Operator UX impact | `medium` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Carry into Phase 2 as a bounded resolved-runtime slice. Requested intent is now persisted; resolved runtime reality remains the open part. |
| Blocked by | none |
| Related issues | QM-004, QM-006, QM-010, QM-013, QM-015 |
| Decision / resolution notes | Planned for Phase 2. Phase 1 persisted effective run intent through `RunPlan` snapshots, but did not fully solve backend-observed resolved values. Do not mark resolved until material resolved runtime values are captured where observable. |
| Verification evidence | Phase 1 implementation plan and validation cover persisted run intent. Resolved runtime reality remains unverified/open. |
| Last updated | 2026-04-12 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-4-RE`
- Audit 4 explicitly says requested command remains important and should not be discarded.
- The target is a dual record: what QuantMap asked for, and what the runtime actually instantiated where materially knowable.
- 2026-04-12 update: The requested-intent half is improved by Phase 1. The achieved-runtime half remains Phase 2+ work and should be coordinated with backend/runtime robustness.

#### Acceptance / Resolution Criteria

- Requested runtime intent remains persisted.
- Material resolved runtime values are persisted where the backend exposes them reliably.
- Reports and exports distinguish requested values from resolved values.
- Unknown or unobservable resolved values are labeled as unknown rather than inferred from intent.
- Tests or fixtures cover at least one parameter where requested and resolved values can diverge.

### QM-017: Runner responsibility fusion creates critical change risk

| Field | Value |
|---|---|
| Category | `architectural_debt` |
| Status | `accepted` |
| Severity | `critical` |
| Priority | `P1` |
| Scope / affected area | `src/runner.py`, CLI handling, UI orchestration, campaign policy, measurement mechanism, DB persistence, resume/progress behavior, error/failure semantics |
| Discovered from | Audit 5 response |
| Evidence | Audit 5 accepts `src/runner.py` as the single most concentrated maintenance and evolution risk in the repository because CLI handling, UI orchestration, campaign policy, measurement, persistence, resume/progress behavior, and failure semantics are fused into one operational center of gravity. |
| Why it matters | Changes to runtime semantics, telemetry/provider behavior, backend support, resume/recompute logic, and operator feedback all pass through a high-blast-radius module. That raises regression risk and makes future portability or automation work harder to evolve safely. |
| Trust impact | `medium` |
| Portability impact | `medium` |
| Operator UX impact | `medium` |
| Architecture impact | `high` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Define a staged boundary plan for `runner.py` that separates campaign policy, measurement mechanism, persistence coordination, UI/output concerns, and failure-state semantics without changing runtime truth. |
| Blocked by | QM-005 and QM-018 should be understood first so runner decomposition does not preserve current path/provider coupling. |
| Related issues | QM-005, QM-008, QM-009, QM-010, QM-016, QM-018, QM-019 |
| Decision / resolution notes | Accepted as Audit 5 Priority 3 remediation. Refactoring should be staged after configuration and provider groundwork is clearer. |
| Verification evidence | Not resolved yet. |
| Last updated | 2026-04-11 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-5-RE`
- Audit 5 explicitly cautions that this is not a shallow line-count issue; the root risk is responsibility concentration and change amplification.
- Keep the current measurement/runtime truth intact while reducing responsibility fusion.

#### Acceptance / Resolution Criteria

- `src/runner.py` has clearer boundaries for campaign policy, measurement execution, persistence coordination, UI/output, and failure semantics.
- Runtime behavior remains covered by tests or smoke fixtures before and after decomposition.
- Future telemetry/provider and backend work can plug into runner boundaries without editing unrelated UI, persistence, or policy code.
- Resume/progress behavior remains explicit and does not become more ambiguous during decomposition.

### QM-018: Telemetry policy is too fused to Windows-centric providers

| Field | Value |
|---|---|
| Category | `portability_gap` |
| Status | `planned` |
| Severity | `high` |
| Priority | `P1` |
| Scope / affected area | telemetry provider architecture, HWiNFO assumptions, sensor policy, abort-tier signals, Linux/NVIDIA portability, doctor/wizard readiness |
| Discovered from | Audit 5 response |
| Evidence | Audit 5 accepts the "HWiNFO wall" as the primary portability blocker: high-value or ABORT-tier CPU/environment signals are too dependent on Windows-specific telemetry sourcing, and provider details are too fused into runtime policy. |
| Why it matters | Linux/cloud/NVIDIA portability cannot become trustworthy if runtime policy assumes one Windows-centric sensor path. QuantMap needs provider-aware telemetry architecture so missing, degraded, or alternate sensors can be represented honestly instead of blocking generalization or weakening trust silently. |
| Trust impact | `high` |
| Portability impact | `high` |
| Operator UX impact | `medium` |
| Architecture impact | `high` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Continue Phase 3 provider hardening with WSL treated as explicit degraded support. WSL Python dependency setup, Windows-backend-through-WSL policy rejection, and one successful real in-WSL Linux-native-backend smoke run are complete. Keep `linux_native` deferred to a later bare-metal Linux phase and preserve Windows fail-loud safety. |
| Blocked by | none; Phase 2.1 settings/environment bridge is complete. |
| Related issues | QM-005, QM-006, QM-010, QM-017 |
| Decision / resolution notes | Phase 3 provider-boundary implementation pass started after Phase 2.1 settings/environment boundary work. Phase 1/1.1 stabilized trust surfaces, Phase 2 closed brittle-shell robustness, and Phase 2.1 created the minimum settings/environment contract. Telemetry provider work is using a boundary-aware path and must not add scattered provider conditionals to `runner.py`, `telemetry.py`, `doctor.py`, or report modules. |
| Verification evidence | Initial implementation evidence: `src/telemetry_provider.py`, `src/telemetry_hwinfo.py`, `src/telemetry_nvml.py`, and `src/telemetry_policy.py` exist; runner consumes the policy seam; doctor/status consume provider readiness; run-start snapshots now have provider evidence fields. 2026-04-13 WSL evidence: Ubuntu under WSL 2 is detected explicitly as `wsl_degraded`; Docker and GPU passthrough work; direct WSL `nvidia-smi` sees the RTX 3090; normal Linux CPU thermal interfaces are absent; provider readiness returns degraded, not ready or blocked; Windows provider readiness remains measurement-grade when HWiNFO/NVML are available. Follow-up validation created a WSL Python venv, installed QuantMap dependencies, and verified persisted `wsl_degraded` evidence in the run DB/export/report. Backend policy validation rejects Windows `.exe` backend execution through WSL interop before config/cycle/server launch and persists `wsl_windows_backend_interop_disallowed`. Linux-native backend smoke validation used llama.cpp b8779 for Linux x64 from WSL, completed one real campaign cycle with three successful requests, and preserved degraded WSL truth in DB/report/export/explain/history surfaces. |
| Last updated | 2026-04-13 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-5-RE`
- Audit 5 says Linux/NVIDIA-first is the correct next generalization target.
- Audit 5 distinguishes telemetry provider lock-in from hardcoded path assumptions and backend coupling.
- 2026-04-12 update: This remains open by design after Phase 2. It is now the active Phase 3 generalization entry point after the Phase 2.1 settings/environment bridge.
- 2026-04-13 update: Initial Phase 3 implementation pass added a narrow provider contract, HWiNFO/NVML helper modules, a readiness policy seam, run-level provider evidence fields, and reader/export/report surfaces for persisted provider evidence. This is not yet Phase 3 closure; Linux/NVIDIA target validation and the Windows/Linux hardening slice remain open.
- 2026-04-13 WSL update: Target evidence supports WSL 2 as an explicit degraded Linux-like execution tier, not native Linux. The implementation persists execution environment evidence, marks WSL as `wsl_degraded`, sets measurement-grade false, and records missing Linux CPU thermal interfaces as a degradation reason. `linux_native` remains future bare-metal Linux work.
- 2026-04-13 WSL follow-up: WSL Python environment setup completed with user-local pip/virtualenv and editable QuantMap install. A bounded real WSL campaign startup passed telemetry/readiness as `wsl_degraded`, persisted degraded provider/execution evidence, and generated reports. The measurement cycle itself produced no valid requests because the current backend path launches a Windows `llama-server.exe` through WSL interop and exited before HTTP readiness; this is a bounded backend-execution follow-up, not native Linux validation.
- 2026-04-13 backend policy follow-up: `src/backend_execution_policy.py` now classifies Windows `.exe` backend targets and rejects them under `wsl_degraded`. WSL `doctor` reports a dedicated `Backend Execution Policy` failure, and WSL runs abort before config/cycle/server launch with persisted `wsl_windows_backend_interop_disallowed` evidence. Windows-native `.exe` backend use remains policy-allowed under `windows_native`.
- 2026-04-13 Linux-native WSL backend smoke: A WSL-native llama.cpp b8779 backend completed a real QuantMap smoke campaign from WSL with 3/3 successful streamed requests. The run persisted `support_tier=wsl_degraded`, `measurement_grade=false`, missing Linux CPU thermal interfaces, NVML availability, and a Linux-native resolved backend command. Reports, export, explain, and history surfaces now preserve that degraded truth from persisted evidence. This still does not claim measurement-grade bare-metal `linux_native`.

#### Acceptance / Resolution Criteria

- Telemetry policy consumes provider-neutral evidence/state rather than directly assuming a single provider shape.
- Current Windows/HWiNFO behavior remains supported where available.
- Linux/NVIDIA-capable telemetry has an explicit provider path or documented staged plan.
- Missing or degraded provider signals are surfaced as evidence-quality states rather than silently treated as clean or equivalent.
- Doctor/readiness surfaces can explain which provider is active, missing, degraded, or unsupported.

### QM-019: Backend coupling to llama-server blocks staged generalization

| Field | Value |
|---|---|
| Category | `architectural_debt` |
| Status | `accepted` |
| Severity | `high` |
| Priority | `P2` |
| Scope / affected area | backend launch/control, `llama-server` assumptions, runtime inspection, server contracts, future backend adapters |
| Discovered from | Audit 5 response |
| Evidence | Audit 5 accepts that QuantMap is currently coupled too tightly to a `llama-server`-shaped backend model. That coupling is acceptable for current lab use, but becomes a structural blocker for backend diversity, Linux/cloud/NVIDIA portability, and product growth beyond one backend family. |
| Why it matters | Future backend support and resolved-runtime provenance will be brittle if QuantMap's runner, telemetry, reports, and launch logic assume one backend contract everywhere. A staged adapter boundary is needed before broader backend expansion is safe. |
| Trust impact | `medium` |
| Portability impact | `high` |
| Operator UX impact | `medium` |
| Architecture impact | `high` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Identify the minimum backend abstraction boundary around launch arguments, health/readiness checks, runtime identity, resolved values, logs, and failure semantics before implementing additional backend families. |
| Blocked by | QM-005 and QM-018 should progress first; settings and telemetry groundwork should shape the backend boundary. |
| Related issues | QM-001, QM-005, QM-016, QM-017, QM-018 |
| Decision / resolution notes | Accepted as Audit 5 Priority 4 remediation. This justifies staged backend modularization, not immediate full multi-backend expansion. |
| Verification evidence | Not resolved yet. |
| Last updated | 2026-04-11 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-5-RE`
- Audit 5 explicitly says not to prematurely build a giant backend framework.
- Backend adapter work should preserve current `llama-server` behavior while defining the boundary needed for later backends.

#### Acceptance / Resolution Criteria

- The minimum backend contract is documented before broad backend expansion.
- Current `llama-server` behavior is represented as one backend implementation or adapter shape.
- Backend-specific launch, health, identity, resolved-values, logs, and failure semantics are not scattered across unrelated runner/report/telemetry code.
- Future backend work can add support without rewriting core campaign policy or report interpretation.

### QM-020: Recommendation semantics and output persistence are missing

| Field | Value |
|---|---|
| Category | `trust_integrity_risk` |
| Status | `accepted` |
| Severity | `high` |
| Priority | `P1` |
| Scope / affected area | optimization recommendations, recommendation vocabulary, DB persistence, reports, exports, CLI/UI wording, future configs/artifacts |
| Discovered from | Audit 6 response |
| Evidence | Audit 6 accepts that QuantMap lacks a formal recommendation layer: it cannot safely output a raw winner and call that optimization, and it has no canonical way to store, explain, export, or qualify recommendation outcomes. |
| Why it matters | Recommendation language is a trust mechanism. Without explicit semantics and persistence, QuantMap could overstate evidence, confuse provisional leaders with validated winners, or produce transient recommendation claims that cannot be reconstructed later. |
| Trust impact | `high` |
| Portability impact | `low` |
| Operator UX impact | `high` |
| Architecture impact | `medium` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | Define recommendation semantics and a persisted output/artifact model before any optimization flow makes strong claims about best configurations. |
| Blocked by | QM-002, QM-003, QM-004, QM-008, QM-015, and QM-016 must shape recommendation trust boundaries. |
| Related issues | QM-002, QM-003, QM-004, QM-006, QM-008, QM-010, QM-015, QM-016, QM-017, QM-021 |
| Decision / resolution notes | Accepted as Audit 6 Priority 1 and Priority 3 remediation: trust prerequisites come before recommendation authority, and recommendation artifacts are first-class design work. |
| Verification evidence | Not resolved yet. |
| Last updated | 2026-04-11 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-6-RE`
- Audit 6 accepts recommendation labels such as "Strong Provisional Leader," "Best Validated Config," "Insufficient Evidence to Recommend," and "Needs Deeper Validation" as directionally correct.
- Audit 6 says recommendation strength must be coupled to evidence quality and sampling depth.
- Audit 6 says future recommendations must define where they live, how they are represented, how they are exported, and how they relate to reports, DB state, and future configs/artifacts.

#### Acceptance / Resolution Criteria

- Recommendation strength vocabulary is documented and tied to explicit evidence conditions.
- Recommendations are persisted or exported through a canonical artifact/model rather than only printed transiently.
- Reports/CLI distinguish provisional leaders from validated winners and insufficient-evidence states.
- Recommendation records reference the evidence, methodology, runtime state, and provenance context they depend on.
- Strong "best config" language is unavailable unless the required evidence conditions are satisfied.

### QM-021: Optimization search and control orchestration is missing

| Field | Value |
|---|---|
| Category | `feature_gap` |
| Status | `accepted` |
| Severity | `high` |
| Priority | `P2` |
| Scope / affected area | adaptive search, dynamic pruning, stopping rules, exploration/exploitation behavior, sweep orchestration, recommendation workflow |
| Discovered from | Audit 6 response |
| Evidence | Audit 6 accepts the "brain vs. legs" gap: QuantMap has scoring, governance, confidence-aware ranking, comparison logic, and multi-objective reasoning foundations, but lacks adaptive search, dynamic pruning, stopping logic, exploration/exploitation behavior, and recommendation persistence/output structure. |
| Why it matters | QuantMap can evaluate configured sweeps, but it cannot yet control an optimization process safely or efficiently. Without orchestration, future Quick Tune or Optimize flows would be manual sweep wrappers rather than trustworthy optimization assistants. |
| Trust impact | `medium` |
| Portability impact | `low` |
| Operator UX impact | `medium` |
| Architecture impact | `high` |
| Optimize/Quick Tune impact | `high` |
| Owner / current handler | unassigned |
| Recommended next action | After trust and recommendation semantics are clearer, design the first constrained single-variable search/control loop with explicit stopping and validation rules. |
| Blocked by | QM-020 should define recommendation semantics first; QM-017 should reduce runner/orchestration concentration before sophisticated control expands. |
| Related issues | QM-006, QM-008, QM-016, QM-017, QM-018, QM-019, QM-020 |
| Decision / resolution notes | Accepted as Audit 6 Priority 4 remediation. Search/control is real work, but downstream of trust, state, provenance, and recommendation boundaries. |
| Verification evidence | Not resolved yet. |
| Last updated | 2026-04-11 |

#### Evidence Notes

- Source: `docs/AUDITS/4-11/Audit-6-RE`
- Audit 6 says optimization is not reducible to "maximize LCB and done."
- Audit 6 says single-variable optimization is materially nearer than multi-variable optimization.
- Audit 6 says multi-variable optimization remains a later-phase objective.

#### Acceptance / Resolution Criteria

- The first optimization control loop has documented search, pruning, stopping, and validation behavior.
- The initial scope is constrained to single-variable provisional optimization unless a later decision expands it.
- Search/control outputs feed the canonical recommendation artifact/model from QM-020.
- Multi-variable optimization remains explicitly deferred until single-variable trust and orchestration are mature.
- Control logic is separated enough from runner internals that future search strategies do not worsen responsibility fusion.

### QM-022: Governance default-profile import is brittle for readers

| Field | Value |
|---|---|
| Category | `architectural_debt` |
| Status | `resolved` |
| Severity | `high` |
| Priority | `P1` |
| Scope / affected area | `src/governance.py`, reader commands, CLI shell, profile loading, operational robustness |
| Discovered from | Phase 1.1 real-workflow validation |
| Evidence | `docs/decisions/Phase-1.1-Real-Workflow-Validation-Memo.md` reports that malformed profile files can still crash readers because `src.governance` loads `DEFAULT_PROFILE` at module import time. |
| Why it matters | Snapshot-trust behavior is stable, but the operational shell is brittle. A damaged current profile file should not prevent snapshot-complete historical readers from starting, auditing, explaining, or exporting existing runs. |
| Trust impact | `low` |
| Portability impact | `medium` |
| Operator UX impact | `high` |
| Architecture impact | `high` |
| Optimize/Quick Tune impact | `medium` |
| Owner / current handler | unassigned |
| Recommended next action | Closed. Carry the remaining common settings/environment boundary through QM-005 and TODO-031, not this brittle-reader issue. |
| Blocked by | none |
| Related issues | QM-001, QM-003, QM-004, QM-005, QM-018 |
| Decision / resolution notes | This is not a reopened Phase 1 trust failure. It was the first concrete Phase 2 Operational Robustness blocker surfaced by real-workflow validation. Resolved by lazy current-methodology loading, command-local CLI imports, degraded status behavior, clearer doctor diagnostics, trust-safe current-input blocking, and explicit-DB historical reader resilience. |
| Verification evidence | `docs/decisions/Phase-2-Operational-Robustness-Closure-Validation-Memo.md` verifies guarded malformed-current-methodology behavior, missing-env shell behavior, explicit-DB historical readers, snapshot-complete report regeneration, and snapshot-incomplete refusal. |
| Last updated | 2026-04-12 |

#### Evidence Notes

- Source: `docs/decisions/Phase-1.1-Real-Workflow-Validation-Memo.md`
- The validation memo calls this the "Brittle Shell Constraint."
- The desired behavior is not to ignore malformed profiles for current-run scoring; it is to prevent reader commands from crashing before they can use persisted historical snapshot truth.
- Source: `docs/decisions/Phase-2-Operational-Robustness-Closure-Validation-Memo.md`
- Phase 2 closure validation resolves the brittle-reader blocker. Remaining settings/environment normalization is tracked separately under QM-005 / TODO-031.

#### Acceptance / Resolution Criteria

- A malformed current profile file does not prevent snapshot-complete historical readers from starting.
- Current-run scoring and profile editing still fail loudly when the active profile is invalid.
- Reader commands clearly distinguish current-profile failure from historical snapshot trust state.
- Validation includes at least one malformed-profile fixture or direct probe.

## Backlog Seeds To Triage Later

Smaller, broader, or not-yet-promoted work belongs in `docs/system/TO-DO.md`.

Rule: if a TO-DO item becomes a serious root issue with clear evidence and remediation value, promote it into this tracker as the next `QM-NNN`. If it stays fuzzy or is merely a design micro-decision, keep it out of K.I.T. so this tracker remains a registry of actionable root issues.

## Review Cadence

- During active audits: update this file whenever a finding becomes actionable.
- Before starting a major fix: check related issues and blocked-by fields.
- After merging a fix: update status, resolution notes, last updated date, and verification evidence.
- Weekly during cleanup phases: prune vague backlog seeds, promote real issues, and close resolved items.
