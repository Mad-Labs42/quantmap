# QuantMap TO-DO

Last review: 2026-04-12

This file holds smaller, broader, or not-yet-promoted work that should not live in the Known Issues Tracker (K.I.T.) yet.

K.I.T. path: `docs/system/known_issues_tracker.md`

## Current Project State

As of the 2026-04-12 Phase 2.1 completion pass, the Phase 1 Trust Bundle and Phase 1.1 Trust Bundle Stabilization are stable, Phase 2 Operational Robustness is closed, and Phase 2.1 Settings/Environment Bridge is closed. Phase 3 Platform Generalization is now active, beginning with boundary-aware telemetry/provider design.

This TO-DO file keeps smaller follow-ups and design prompts. Current root issues and Phase 2 blockers belong in K.I.T.

## Rules

1. If the item is a serious root issue with clear evidence and remediation value, promote it to K.I.T. as `QM-NNN`.
2. If the item is a smaller follow-up, design micro-decision, audit seed, doc cleanup, or investigation prompt, keep it here.
3. Keep each entry short and copy/paste friendly for AI use.
4. Do not duplicate active K.I.T. issues. Link them under `Related K.I.T.` instead.
5. When promoting an item, mark it `promoted` and add the new `QM-NNN`.
6. When discarding an item, mark it `closed` and state why in one sentence.
7. Keep each item bounded to one follow-up, decision, cleanup, or investigation prompt. If it expands into a root problem or multi-symptom issue, promote it or split it deliberately.

## Status

| Status | Meaning |
|---|---|
| `open` | Captured, but not ready or prioritized for immediate work. |
| `ready` | Clear enough to hand to an AI assistant or work directly now. |
| `waiting` | Blocked by an audit, dependency, decision, or related K.I.T. issue. |
| `promoted` | Moved into K.I.T. as `QM-NNN`. |
| `closed` | No longer needed; brief reason should be recorded. |

## Priority

| Priority | Meaning |
|---|---|
| `P1` | Do soon because it unblocks important work or prevents confusion. |
| `P2` | Useful planned work, but not blocking the current critical path. |
| `P3` | Keep visible; revisit when touching the related area. |

## Entry Schema

```markdown
### TODO-NNN: Short title

Priority: `P2`
Status: `open`
Source: audit/doc/command/manual note
Related K.I.T.: QM-NNN or none
Type: docs / audit seed / design decision / cleanup / investigation
Next step: One immediate action.
Why not K.I.T.?: One short boundary note.
Prompt-ready brief: One compact paragraph with enough context for an AI assistant to act.
Done when: Short acceptance signal.
```

## Open Items

### TODO-001: Clarify thermal event semantics

- Priority: `P2`
- Status: `ready`
- Source: Audit follow-up seed; root-cause attribution amendment
- Related K.I.T.: QM-006, QM-014
- Type: investigation
- Next step: Search report/explain/analysis text for thermal wording and compare it to the RCA amendment.
- Why not K.I.T.?: Narrow wording/threshold review unless concrete misleading output is found.
- Prompt-ready brief: Review QuantMap thermal event wording and thresholds, especially `thermal_events`, `CPU_THERMAL_HIGH`, and report/explain language. Identify any places where observed high temperature is conflated with confirmed throttling. Preserve the amendment rule: 95-99 C is thermal concern only; >=100 C is TjMax/rank-invalidating.
- Done when: Ambiguous wording or threshold mismatches are either fixed, documented, or promoted to K.I.T. with evidence.

### TODO-002: Assess oversized mixed-responsibility files

- Priority: `P3`
- Status: `promoted`
- Source: Audit 1 architecture/generalization follow-up; repo audit LOC output
- Related K.I.T.: QM-004, QM-011, QM-017
- Type: audit seed
- Next step: Work the promoted K.I.T. issues and report consolidation links.
- Why not K.I.T.?: Promoted after Audit 5 found concrete responsibility concentration risk.
- Prompt-ready brief: Audit 5 confirmed that line count alone is not the issue; responsibility concentration is. `src/runner.py` is now tracked under QM-017, while report responsibility drag is folded into QM-004/QM-011 so report decomposition stays aligned with Audit 3.
- Done when: QM-017 and the report consolidation issues carry the active remediation work.

### TODO-003: Map Smart Mode / Quick Tune prerequisites

- Priority: `P2`
- Status: `waiting`
- Source: Audit 1 and Audit 2 follow-up planning
- Related K.I.T.: QM-001, QM-005, QM-006, QM-010, QM-016, QM-017, QM-018, QM-019, QM-020, QM-021, QM-022
- Type: design planning
- Next step: After the Phase 3 telemetry/provider boundary plan is settled, draft a dependency map with hard blockers vs nice-to-haves.
- Why not K.I.T.?: Planning artifact, not a single defect or confirmed root issue.
- Prompt-ready brief: Create a concise dependency map for future Smart Mode, Quick Tune, and Optimize Mode. Treat Phase 1 trust/provenance foundations as stable, then identify which attribution, portability, operational robustness, resolved-runtime, telemetry-provider, runner-boundary, backend-coupling, recommendation-semantics, and search/control issues must be resolved before automated recommendations are safe.
- Done when: There is a short prerequisite map that separates hard blockers from nice-to-have improvements.

### TODO-004: Decide baseline-override namespaced lab-root UX

- Priority: `P2`
- Status: `open`
- Source: Audit 2 response
- Related K.I.T.: QM-005, QM-007
- Type: design decision
- Next step: Trace how `--baseline` changes lab root, DB path, logs path, and `list` visibility.
- Why not K.I.T.?: Currently a scoped design wrinkle under broader portability/discovery issues.
- Prompt-ready brief: Audit 2 notes that `--baseline` can create namespaced lab roots such as `profiles/basename/`, which may hide databases/logs from default `quantmap list` views unless the same baseline is active. Decide whether this is acceptable advanced behavior, needs clearer operator labeling, or should be normalized.
- Done when: The intended behavior is documented or a concrete operator failure is promoted to K.I.T.

### TODO-005: Review duplicate registration logic

- Priority: `P3`
- Status: `open`
- Source: Audit 2 response
- Related K.I.T.: QM-008
- Type: cleanup
- Next step: Inspect resume/config registration flow when already touching runner idempotency code.
- Why not K.I.T.?: Low-priority smell without current evidence of user-visible failure.
- Prompt-ready brief: Audit 2 flags repeated `INSERT OR IGNORE` config registration on resume as a low-priority smell that may blur planning vs execution phases. Review only when touching runner resume/idempotency code; do not promote unless it causes misleading state or brittle behavior.
- Done when: Either confirmed harmless and documented in code comments/tests, or promoted to K.I.T. with concrete evidence.

### TODO-006: Decide final report artifact micro-policy

- Priority: `P2`
- Status: `waiting`
- Source: Audit 3 response
- Related K.I.T.: QM-004, QM-011
- Type: design decision
- Next step: Wait for canonical report model decision, then choose final filenames/sidecars.
- Why not K.I.T.?: Micro-policy deferred by Audit 3 until report consolidation direction is settled.
- Prompt-ready brief: Audit 3 defers exact choices for unified report filename, optional JSON summary sidecar, `scores.csv` long-term status, and appendix structure. Revisit after the canonical report model is chosen so these details do not become permanent transitional ambiguity.
- Done when: Final artifact naming and sidecar policy are captured in a decision record or implemented as part of report consolidation.

### TODO-007: Preserve command mutation classification in docs

- Priority: `P3`
- Status: `ready`
- Source: Audit 1 response
- Related K.I.T.: QM-012
- Type: docs
- Next step: Add side-effect classes to `docs/system/command_reference.md` for major commands.
- Why not K.I.T.?: Concrete doc follow-up under existing K.I.T. issue QM-012.
- Prompt-ready brief: Audit 1 accepts command mutation classification as important project knowledge. Update command docs or help surfaces so operators can distinguish read-only commands from file-writing, DB-writing, and mixed mutating commands.
- Done when: `docs/system/command_reference.md` or CLI help includes side-effect classes for major commands.

### TODO-008: Tighten "monitored and enforced" trust wording

- Priority: `P3`
- Status: `ready`
- Source: Audit 1 response
- Related K.I.T.: QM-012, QM-010
- Type: docs
- Next step: Search docs and report text for broad claims about monitoring/enforcement guarantees.
- Why not K.I.T.?: Wording cleanup unless specific misleading operator-facing claims are found.
- Prompt-ready brief: Audit 1 accepts that QuantMap monitors broadly and enforces specific hard constraints, but does not guarantee a clean environment in all respects. Review docs/help/report language for overbroad claims that imply full environmental enforcement.
- Done when: Trust-surface wording consistently distinguishes observed, monitored, enforced, degraded, and unknown states.

### TODO-012: Scope the first resolved-runtime-values slice

- Priority: `P2`
- Status: `open`
- Source: Audit 4 response
- Related K.I.T.: QM-016
- Type: investigation
- Next step: Identify the first 2-3 runtime values where requested and resolved state can diverge and can be observed reliably.
- Why not K.I.T.?: QM-016 tracks the root issue; this is a bounded implementation scoping pass.
- Prompt-ready brief: Audit 4 accepts that requested intent and achieved runtime state must both be persisted where material. Start by finding runtime parameters with known clipping/coercion risk, such as GPU layer placement, context size, batch/ubatch, or backend-reported model/runtime settings. Recommend the first small slice for a resolved-values mechanism, including source of truth and unknown-state labeling.
- Done when: There is a short first-slice proposal for resolved runtime persistence under QM-016.

### TODO-013: Preserve developer-rig release messaging

- Priority: `P2`
- Status: `ready`
- Source: Audit 1 response
- Related K.I.T.: QM-001, QM-005
- Type: docs
- Next step: Review README, command docs, and support-facing docs for claims that imply broad portability before packaging/lab-root work is complete.
- Why not K.I.T.?: Messaging follow-up under existing packaging and portability issues, not a separate root defect.
- Prompt-ready brief: Audit 1 accepts the standing project truth that QuantMap is currently a high-fidelity benchmarking framework with a brittle portability and installation layer. Preserve that "developer's rig" diagnosis in release/support/docs language until packaging, bootstrap, and lab-root assumptions are corrected. Avoid wording that implies friction-light broad portability before QM-001 and QM-005 are resolved.
- Done when: Public/internal docs and support guidance accurately set portability expectations without underselling the forensic core.

### TODO-014: Scope architecture/generalization audit inputs

- Priority: `P2`
- Status: `promoted`
- Source: Audit 1 response
- Related K.I.T.: QM-001, QM-004, QM-005, QM-017, QM-018, QM-019
- Type: audit seed
- Next step: Work the Audit 5 remediation issues and scoped design TODOs.
- Why not K.I.T.?: The architecture/generalization audit is complete; concrete findings are now tracked in K.I.T.
- Prompt-ready brief: Audit 5 completed the architecture/generalization truth-finding slice that Audit 1 requested. It promoted or reinforced distinct work for path/settings decoupling, telemetry provider abstraction, runner responsibility fusion, report module drag, and backend coupling.
- Done when: Active remediation is carried by QM-004, QM-005, QM-017, QM-018, QM-019, and the Audit 5 design TODOs.

### TODO-015: Decide report regeneration command policy

- Priority: `P3`
- Status: `waiting`
- Source: Audit 3 response
- Related K.I.T.: QM-004, QM-008, QM-011
- Type: design decision
- Next step: Revisit after the canonical report model is settled. The layered state model is no longer the blocker.
- Why not K.I.T.?: Audit 3 explicitly leaves exact CLI additions undecided; this is a micro-policy under report/state remediation.
- Prompt-ready brief: Audit 3 does not decide whether a later `quantmap report <ID>` retry/regeneration command should exist. Decide whether operators need an explicit presentation-layer retry command for cases where measurement data is valid but report/artifact generation failed, and define how it should avoid implying measurement rerun.
- Done when: The project either documents no separate report-regeneration command, or defines its command semantics and relationship to measurement, interpretation, and presentation state.

### TODO-016: Plan Optimize feasibility audit timing

- Priority: `P3`
- Status: `promoted`
- Source: Audit 1 response
- Related K.I.T.: QM-002, QM-003, QM-006, QM-008, QM-010, QM-015, QM-016, QM-017, QM-018, QM-019, QM-020, QM-021
- Type: audit seed
- Next step: Work the Audit 6 remediation issues and product-design TODOs.
- Why not K.I.T.?: The feasibility audit is complete; concrete recommendation/search findings are now tracked in K.I.T.
- Prompt-ready brief: Audit 6 completed the Optimize / Smart / Quick Tune feasibility audit. It confirmed QuantMap is nearer to a trustworthy optimization assistant than a fully autonomous optimizer, and split active work into recommendation semantics/output persistence and search/control orchestration.
- Done when: Active remediation is carried by QM-020, QM-021, TODO-003, and the Audit 6 design TODOs.

### TODO-018: Define telemetry provider interface boundaries

- Priority: `P1`
- Status: `completed`
- Source: Audit 5 response
- Related K.I.T.: QM-018, QM-010
- Type: design decision
- Next step: Closed by the initial Phase 3 implementation pass; continue remaining provider migration and hardening under QM-018 / TODO-023.
- Why not K.I.T.?: QM-018 tracks the root provider lock-in; this item is the interface design choice.
- Prompt-ready brief: Audit 5 says QuantMap should build provider-aware telemetry architecture rather than simply swapping HWiNFO out. Phase 2.1 completed the minimum settings/environment boundary, so define the boundary between telemetry providers and telemetry policy, including provider identity, supported sensors, missing/degraded signals, ABORT-tier signal semantics, Linux/NVIDIA-first support, and doctor/readiness reporting. Carry the anti-God-object rule from day one: do not add scattered provider conditionals to `src/runner.py`, `src/telemetry.py`, `src/doctor.py`, or report modules.
- Done when: A minimal telemetry provider interface and degraded-signal policy are documented for implementation.
- Completion note: 2026-04-13 Phase 3 implementation pass added `src/telemetry_provider.py`, `src/telemetry_hwinfo.py`, `src/telemetry_nvml.py`, and `src/telemetry_policy.py`; runner, doctor/status, reports, compare, and export now have initial provider-boundary wiring. This closes the interface-definition TODO, not the whole Phase 3 provider issue.

### TODO-019: Plan staged runner decomposition

- Priority: `P2`
- Status: `ready`
- Source: Audit 5 response
- Related K.I.T.: QM-017
- Type: design decision
- Next step: Draft a staged extraction plan for `src/runner.py`.
- Why not K.I.T.?: QM-017 tracks the root architecture risk; this item is the decomposition strategy.
- Prompt-ready brief: Audit 5 accepts `src/runner.py` as a critical mixed-responsibility risk, but says decomposition should happen after configuration and provider groundwork is clearer. Propose staged boundaries for campaign policy, measurement execution, persistence coordination, UI/output, resume/progress behavior, and error/failure semantics while preserving current runtime truth.
- Done when: A low-risk runner decomposition plan exists with ordering, non-goals, and verification checkpoints.

### TODO-020: Plan report_campaign decomposition after canonical report decision

- Priority: `P2`
- Status: `waiting`
- Source: Audit 5 response
- Related K.I.T.: QM-004, QM-011
- Type: design decision
- Next step: Wait for the canonical report model decision, then draft report module boundaries.
- Why not K.I.T.?: Report responsibility drag is already tracked under QM-004/QM-011; this is the sequencing and decomposition micro-policy.
- Prompt-ready brief: Audit 5 accepts that `src/report_campaign.py` mixes aggregation, interpretation, formatting/rendering, and report-specific decisions. It also warns not to use Audit 5 as a shortcut around Audit 3. After the canonical report model is chosen, propose boundaries that reduce architectural drag without deleting evidence-rich sections or creating new truth surfaces.
- Done when: Report decomposition is either captured in the canonical report plan or split into implementation tasks under QM-004/QM-011.

### TODO-021: Define minimum backend adapter contract

- Priority: `P2`
- Status: `open`
- Source: Audit 5 response
- Related K.I.T.: QM-019, QM-016
- Type: design decision
- Next step: Use the WSL backend-boundary and successful Linux-native backend smoke run as inputs to the future backend contract: real in-WSL measurement requires a Linux-native backend path, while Windows `.exe` backend execution through WSL interop is explicitly rejected unless a future approved interop mode is designed.
- Why not K.I.T.?: QM-019 tracks backend coupling; this item is the bounded contract design.
- Prompt-ready brief: Audit 5 justifies backend modularization but explicitly rejects immediate full multi-backend expansion. Define the minimum backend adapter contract around launch args, process/server lifecycle, health/readiness checks, runtime identity, resolved runtime values, logs, and failure semantics. Keep current `llama-server` behavior as the first implementation shape.
- Done when: A minimum backend adapter contract exists without committing to broad backend parity.
- Progress note: 2026-04-13 WSL backend policy pass added a narrow execution-boundary check rather than a backend abstraction. It rejects Windows `.exe` backend targets under `wsl_degraded` before backend startup and persists a clear reason. A later same-day smoke run proved a Linux-native llama.cpp backend can complete a real in-WSL QuantMap campaign cycle, but this is still not a backend abstraction or a native Linux support claim.

### TODO-022: Record platform support non-goals for generalization

- Priority: `P3`
- Status: `ready`
- Source: Audit 5 response
- Related K.I.T.: QM-018, QM-019
- Type: docs
- Next step: Add a short generalization target note to architecture or portability docs.
- Why not K.I.T.?: This is expectation-setting, not a defect.
- Prompt-ready brief: Audit 5 accepts Linux/NVIDIA-first as the next generalization target and explicitly leaves Apple Silicon, ROCm, CPU-only parity, and universal backend parity for later unless separately elevated. Document these staged support expectations so provider/backend work is not misread as an immediate universal-platform commitment.
- Done when: Architecture or portability docs clearly state Linux/NVIDIA-first and list later-phase non-goals.

### TODO-023: Plan HWiNFO migration strategy to provider stack

- Priority: `P2`
- Status: `in_progress`
- Source: Audit 5 response
- Related K.I.T.: QM-018
- Type: design decision
- Next step: Continue staged provider hardening. WSL degraded setup, explicit rejection of Windows-backend-through-WSL interop, and a first successful real WSL measurement smoke run with a Linux-native backend are complete. Remaining native Linux support is deferred to a later bare-metal Linux phase.
- Why not K.I.T.?: QM-018 tracks the root provider lock-in; this item is the migration sequencing Audit 5 leaves undecided.
- Prompt-ready brief: Audit 5 says the answer is provider abstraction, not simply replacing HWiNFO. After the telemetry provider interface is drafted, plan how existing Windows/HWiNFO capture maps into the provider stack, how Linux/NVIDIA providers are introduced, and how legacy/current reports label provider identity and degraded evidence.
- Done when: HWiNFO remains supported as a provider or legacy path while the new provider stack has a staged migration plan.
- Progress note: 2026-04-13 initial Phase 3 implementation pass preserves HWiNFO as a provider-readiness path and records persisted provider evidence. The WSL degraded pass adds explicit `wsl_degraded` detection, execution environment persistence, Docker/GPU target validation evidence, and downstream degraded-truth propagation. WSL follow-up validation created a real WSL Python environment, installed QuantMap dependencies, and verified persisted degraded evidence in DB/report/export surfaces. The backend policy pass rejects Windows `llama-server.exe` execution through WSL interop before measurement startup. The Linux-native WSL backend smoke run completed a real measurement cycle with 3/3 successful streamed requests while preserving `wsl_degraded` and measurement-grade false. WSL is not `linux_native`; full native Linux support remains deferred to a later bare-metal Linux phase.

### TODO-024: Define recommendation strength vocabulary

- Priority: `P1`
- Status: `ready`
- Source: Audit 6 response
- Related K.I.T.: QM-020
- Type: design decision
- Next step: Turn the Audit 6 recommendation labels into explicit evidence-conditioned semantics.
- Why not K.I.T.?: QM-020 tracks the root missing recommendation layer; this is the bounded vocabulary/policy design.
- Prompt-ready brief: Audit 6 says QuantMap must not just output a raw winner. Define the recommendation-strength vocabulary, including terms such as Strong Provisional Leader, Best Validated Config, Insufficient Evidence to Recommend, and Needs Deeper Validation. Tie each term to evidence quality, sampling depth, methodology/provenance completeness, and validation state.
- Done when: Recommendation labels have explicit allowed meanings and evidence gates.

### TODO-025: Design recommendation artifact schema

- Priority: `P1`
- Status: `ready`
- Source: Audit 6 response
- Related K.I.T.: QM-020
- Type: design decision
- Next step: Propose where recommendations live and how they relate to DB, reports, exports, and future config artifacts.
- Why not K.I.T.?: QM-020 tracks the root persistence/output gap; this item is the schema/artifact design.
- Prompt-ready brief: Audit 6 says recommendation persistence/output needs a formal model. Define a minimal recommendation artifact/schema that records recommendation label, candidate config, evidence basis, methodology identity, provenance state, validation depth, caveats, export behavior, and links to reports/DB records.
- Done when: There is an implementable recommendation artifact/schema proposal.

### TODO-026: Plan first single-variable provisional optimization surface

- Priority: `P2`
- Status: `ready`
- Source: Audit 6 response
- Related K.I.T.: QM-020, QM-021
- Type: design planning
- Next step: Pick the first constrained single-variable optimization target and define non-authoritative output behavior.
- Why not K.I.T.?: The root recommendation/search gaps are tracked in K.I.T.; this is a scoped product planning slice.
- Prompt-ready brief: Audit 6 says single-variable optimization is substantially nearer than multi-variable optimization, especially constrained sweeps such as NGL. Propose the first single-variable provisional optimization surface, including input assumptions, allowed recommendation labels, validation depth, stopping behavior dependencies, and how to avoid authoritative "best config" claims.
- Done when: A first-surface plan exists for single-variable provisional optimization.

### TODO-027: Define single-variable search, pruning, and stopping rules

- Priority: `P2`
- Status: `waiting`
- Source: Audit 6 response
- Related K.I.T.: QM-021, QM-017
- Type: design decision
- Next step: Wait for recommendation semantics and runner-boundary plans, then design the first search/control loop.
- Why not K.I.T.?: QM-021 tracks the root missing search/control orchestration; this item is the algorithm/control policy.
- Prompt-ready brief: Audit 6 says adaptive search, dynamic pruning, stopping logic, and exploration-vs-exploitation behavior are missing but should come after trust boundaries. Define the first single-variable search/control policy, including when to prune candidates, when to deepen validation, when to stop, and when to refuse a recommendation.
- Done when: A first-pass single-variable search/control policy is ready for implementation.

### TODO-028: Decide optimization product tier names and claim boundaries

- Priority: `P3`
- Status: `open`
- Source: Audit 6 response
- Related K.I.T.: QM-020, QM-021
- Type: design decision
- Next step: Decide whether Quick Tune, Smart Mode, and Optimize Mode are final product names or only planning labels.
- Why not K.I.T.?: Product taxonomy and copy boundaries are important but not a root implementation defect.
- Prompt-ready brief: Audit 6 treats Quick Tune, Smart Mode, and Optimize Mode as evaluated product-shape candidates, not finalized feature contracts. Decide the tier names, what each tier is allowed to claim, and which trust prerequisites are required before any tier can use stronger recommendation language.
- Done when: Product-tier naming and claim boundaries are documented or intentionally deferred.

### TODO-029: Preserve multi-variable optimization as later-phase scope

- Priority: `P3`
- Status: `ready`
- Source: Audit 6 response
- Related K.I.T.: QM-020, QM-021
- Type: docs
- Next step: Add planning wording that separates near-term single-variable optimization from later multi-variable optimization.
- Why not K.I.T.?: Scope discipline and expectation-setting, not a separate defect.
- Prompt-ready brief: Audit 6 draws a hard boundary between near-feasible single-variable provisional optimization and later multi-variable optimization. Update planning docs so multi-variable optimization, Bayesian or advanced search approaches, and fully authoritative hands-off Optimize Mode remain explicitly deferred until single-variable trust and orchestration are mature.
- Done when: Planning docs preserve single-variable-first and multi-variable-later scope language.

## Promoted

Use this section only for short history lines, for example: `TODO-000 -> QM-000, YYYY-MM-DD, reason`.

TODO-002 -> QM-017, 2026-04-11, Audit 5 confirmed concrete mixed-responsibility risk in `src/runner.py` and report drag under QM-004/QM-011.
TODO-014 -> QM-017/QM-018/QM-019, 2026-04-11, Audit 5 completed the architecture/generalization audit and split concrete findings into K.I.T.
TODO-016 -> QM-020/QM-021, 2026-04-11, Audit 6 completed the optimization feasibility audit and split concrete recommendation/search gaps into K.I.T.

## Closed

Use this section only for short closure lines, for example: `TODO-000, YYYY-MM-DD, no longer needed because ...`.

TODO-009, 2026-04-12, Phase 1/1.1 implemented and validated explicit legacy/current-input identity fallback labels.
TODO-010, 2026-04-12, Phase 1 selected and implemented the baseline/methodology snapshot storage shape.
TODO-011, 2026-04-12, Phase 1 implemented narrow QuantMap code identity capture and fallback labeling.
TODO-030, 2026-04-12, Phase 2 closure validation and dry-run/readiness messaging patch completed; evidence recorded in `docs/decisions/Phase-2-Operational-Robustness-Closure-Validation-Memo.md`.
TODO-017, 2026-04-12, Phase 2.1 planning and implementation created the minimum settings/path boundary needed before Phase 3.
TODO-031, 2026-04-12, Phase 2.1 settings/environment bridge implemented and validated; evidence recorded in `docs/decisions/Phase-2.1-Settings-Environment-Bridge-Implementation-Validation-Memo.md`.
