# ACPM Refactor Seams Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 structural prep, seams, and repo-fit only

## Outcome

Recommended structural direction:

- implement ACPM as a new planner/orchestrator package, not as new logic inside `src/runner.py`
- reuse the existing execution engine by compiling ACPM decisions into a bounded execution plan
- treat `src/run_plan.py` as the strongest existing seam and extend around it rather than bypassing it
- create a recommendation/planner record seam before ACPM starts making recommendation-grade claims
- do only the minimum runner/report prep needed to avoid bolting ACPM into already overloaded modules

Bottom line:

- ACPM can start on the current repo only after a small but real prep slice
- the biggest blocker is not missing math; it is missing structure around orchestration and recommendation state

## Scope / What Was Inspected

Primary code surfaces inspected:

- `quantmap.py`
- `src/runner.py`
- `src/run_plan.py`
- `src/score.py`
- `src/governance.py`
- `src/trust_identity.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/explain.py`
- `src/export.py`
- `src/artifact_paths.py`

Supporting docs inspected:

- `docs/Design Memo's/Advanced-Campaign-Planning-Mode-ADR/Adaptive-Campaign-Planning-Mode-v1-Design.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-weight-and-gate-spec-TARGET-INVESTIGATION.md`
- `docs/K.I.T.-&-ToDo/known_issues_tracker.md`

Validation used:

- targeted source inspection only
- no product-code changes
- no broad test theater; this pass is structural mapping

## Current ACPM-Relevant Seams

### 1. Thin CLI seam exists

`quantmap.py` is still a workable command-entry seam. It already delegates real work to module functions and is not the main structural problem.

Repo-fit reading:

- future ACPM command wiring can live here
- ACPM logic should not live here

### 2. `RunPlan` is the strongest existing execution seam

`src/run_plan.py` is the cleanest ACPM-relevant module in the repo.

Why it matters:

- it is a compact, explicit execution-shape contract
- it already represents selected values, selected configs, coverage, mode, sampling depth, and snapshot serialization
- it is much closer to the kind of artifact ACPM needs to emit than any part of `runner.py`

Recommendation:

- ACPM should compile its planner decisions into a `RunPlan`-shaped contract or a narrow extension of it
- do not invent a parallel opaque plan object if the current `RunPlan` can carry the required execution shape cleanly

### 3. Governed scoring seam already exists

`src/governance.py` and `src/score.py` already provide a real scoring identity seam.

What is reusable:

- explicit profile identity
- governed weight sets
- shared gate/constraint semantics
- persisted methodology snapshot handling

Constraint:

- `score.py` is usable, but not cleanly separated; scoring, elimination, methodology persistence, and some campaign-shape awareness are mixed together

### 4. Trust/provenance seam already exists

`src/trust_identity.py` is a good ACPM-adjacent seam.

Why it matters:

- it already reconstructs persisted methodology, run plan, execution environment, and provider evidence
- it is the right general direction for ACPM audit-grade reconstruction

### 5. Export and explain surfaces are relatively adaptable

`src/export.py` and `src/explain.py` are not tiny, but they already consume persisted identity rather than recomputing truth from scratch.

This makes them better ACPM attachment points later than `runner.py` or `report_campaign.py`.

### 6. Artifact path policy already has a seam

`src/artifact_paths.py` is healthy and should remain the place where any ACPM-specific artifact placement policy gets wired.

This surface looks like light prep only.

## Missing Seams / Structural Gaps

### 1. No planner-to-execution contract exists yet

There is no explicit contract for:

- planner identity
- planner policy
- ACPM profile selection
- repeat-strength selection
- candidate narrowing decisions
- why certain values/configs were selected or omitted

`RunPlan` captures execution shape, but it does not yet represent planner intent or planner provenance.

### 2. No recommendation record/model exists

This is the largest structural gap after runner concentration.

The repo has:

- winners
- scores
- reports
- exports

The repo does not yet have a canonical recommendation record that can say:

- what was recommended
- under which profile/policy
- with which evidence strength
- from which tested set
- under which shared validity floor

This gap directly overlaps `QM-020`.

### 3. No explicit boundary separates campaign policy from measurement orchestration

`src/runner.py` still blends:

- campaign loading and validation
- execution planning details
- start-snapshot collection
- policy enforcement
- measurement control
- DB status updates
- post-run reporting/export generation

ACPM needs to plug into this area, but there is not yet a clean boundary for doing so safely.

### 4. No dedicated planner home exists

There is no existing package or module that obviously owns:

- context inspection
- candidate generation
- narrowing policy
- planner state
- recommendation selection workflow

If ACPM started now without prep, it would almost certainly end up inside `runner.py`, `score.py`, or both.

### 5. No stable report-facing recommendation adapter exists

Current report surfaces know how to talk about run mode, methodology, filters, rankings, and confidence language, but they do not consume a first-class recommendation object.

That means ACPM would otherwise have to push new semantics into already-large report builders.

## Overloaded or Risky Surfaces

### 1. `src/runner.py` is the primary risky seam

This is the biggest ACPM risk in the repo.

Why:

- it is already the operational center of gravity
- it mixes execution truth, orchestration, state persistence, and operator output
- ACPM is itself an orchestration feature, so bolting it here would amplify the repo's highest-blast-radius module

K.I.T. confirmation:

- this is already recognized as `QM-017`

### 2. `src/report_campaign.py` is an overloaded interpretation surface

It already owns:

- methodology rendering
- result framing
- confidence qualifiers
- environment sections
- warnings
- supporting artifact linkage

ACPM should not begin by embedding new planner semantics directly into this file. The report stack can consume ACPM metadata later, but it should not become ACPM's primary home.

### 3. `src/report.py` is also structurally heavy

It is lighter than `report_campaign.py` in purpose, but it still mixes summary generation, recommendation wording, run-mode caveats, and methodology disclosure in one large surface.

### 4. `src/score.py` is usable but responsibility-mixed

It already contains valuable scoring logic and persistence behavior, but it is not a clean "pure scoring" module.

Risk:

- ACPM could be tempted to push planner semantics into scoring-time code
- that would blur methodology/scoring authority with planner policy

### 5. `build_config_list()` is a useful seam, but the file hosting it is wrong

`build_config_list()` in `src/runner.py` is logically reusable, but its current home inside `runner.py` makes reuse more coupled than it should be.

This is a good extraction candidate.

## Minimum Required Refactors Before ACPM

These are the minimum prep items I would treat as must-do before ACPM implementation starts.

### 1. Define the planner/execution contract

Create a narrow ACPM-facing contract that separates:

- planner identity
- planner policy
- selected values/configs
- repeat-strength choice
- execution overrides actually handed to the engine

Best repo-fit:

- keep execution shape grounded in `RunPlan`
- add a planner-side wrapper or adjacent metadata object rather than making `runner.py` infer ACPM meaning ad hoc

### 2. Create a first-class recommendation record seam

Before ACPM can recommend anything, the repo needs a canonical representation for recommendation outcomes.

This seam should be able to persist or serialize at least:

- recommended config/config set
- ACPM profile used
- planner policy used
- weight lens in force
- shared validity/gate baseline referenced
- evidence/recommendation strength
- tested-set scope

This is required, not optional, because otherwise ACPM will have no trustworthy place to store its output semantics.

### 3. Extract config/candidate materialization out of `runner.py`

The minimum useful extraction is not a full runner rewrite. It is a narrow seam for:

- campaign-to-config materialization
- selected-values/config filtering
- deterministic config list generation for bounded plans

`build_config_list()` and closely related shaping logic are the right initial extraction target.

### 4. Introduce a dedicated ACPM package/module boundary

Recommended home:

- `src/acpm/`

Recommended ownership:

- planner/orchestrator logic
- profile-to-planner-policy mapping
- plan assembly
- recommendation outcome assembly

Not recommended:

- putting ACPM orchestration into `runner.py`
- putting ACPM policy into `quantmap.py`
- putting ACPM recommendation semantics into report builders first

### 5. Add a thin report/export/explain adapter boundary for recommendation data

Do not refactor the entire report stack first.

Do create a narrow, shared ingestion point so those surfaces can consume recommendation metadata consistently when ACPM arrives.

Minimum needed:

- one stable metadata payload shape
- one consistent way for report/export/explain to load it

## Nice-to-Have Later Refactors

These are worthwhile, but ACPM should not wait for all of them.

### 1. Broader `runner.py` decomposition

Needed eventually, but ACPM does not require a full runner breakup before work starts.

Do the seam extraction that ACPM directly depends on first.

### 2. Full report stack decomposition

`src/report.py` and `src/report_campaign.py` should be reduced later, but a full rewrite before ACPM would be over-cleaning.

### 3. Deeper scoring-layer cleanup

Longer-term it would be healthier to separate:

- pure score computation
- elimination logic
- methodology persistence
- ranking/result assembly

But ACPM v1 can start without that full split if planner policy stays outside scoring.

### 4. Backend abstraction expansion

Relevant in the medium term because of `QM-019`, but not the minimum structural prep for ACPM v1 itself.

### 5. Cross-surface wording unification pass

Useful after the recommendation seam exists.
Not a precondition for beginning ACPM structural work.

## K.I.T. / Fragility Overlaps in Touched Surfaces

### Direct overlaps

- `QM-017` runner responsibility fusion
- `QM-020` recommendation semantics and output persistence missing
- `QM-021` optimization search and control orchestration missing

These three issues are ACPM-adjacent enough that they should shape prep directly, not be deferred as unrelated cleanup.

### Strong secondary overlaps

- `QM-016` requested intent vs resolved runtime reality
- `QM-004` report truth-surface duplication/confusion risk
- `QM-011` report rendering brittleness / partial artifact risk

Why they matter:

- ACPM will produce stronger recommendation-oriented outputs
- recommendation trust gets weaker if requested planner intent and achieved runtime reality are not distinguishable
- fragile or duplicated report truth surfaces become more dangerous once ACPM adds another interpretive layer

### Adjacent but not minimum blockers

- `QM-018` telemetry provider seam
- `QM-019` backend coupling

These matter because ACPM depends on trustworthy execution evidence, but they are not the first structural cuts I would make specifically for ACPM.

## Recommended Structural Prep Order

### 1. Lock the plan/recommendation contracts first

Define:

- ACPM planner input/output contract
- recommendation outcome contract
- how those contracts relate to `RunPlan`, trust identity, and export/report loading

This gives all later work a stable shape.

### 2. Extract the minimum runner seam ACPM needs

Move config/candidate materialization and bounded execution-shape assembly out of `src/runner.py` enough that ACPM can hand the engine a prepared plan without embedding its logic in the runner core.

### 3. Create the dedicated ACPM package

Put planner orchestration behind a focused module boundary before implementation logic accumulates.

### 4. Add thin metadata ingestion for report/export/explain

Make those surfaces consumers of ACPM metadata, not owners of ACPM logic.

### 5. Begin ACPM implementation on top of those seams

Only after the above should the repo start adding actual planner behavior.

## Risks of Starting ACPM Too Early

### 1. ACPM logic will get bolted into `runner.py`

That would immediately widen the highest-risk coordination layer in the repo.

### 2. Recommendation semantics will become transient and inconsistent

Without a recommendation record seam, ACPM would likely rely on:

- temporary CLI wording
- ad hoc report fields
- export-only fragments

That would weaken auditability and increase cross-surface drift.

### 3. Planner policy could blur with scoring truth

If ACPM policy lands inside `score.py` or report builders first, the repo will start mixing:

- trust-bearing scoring semantics
- planner preference logic
- human-facing interpretation wording

That is the wrong boundary for this feature.

### 4. Report complexity will grow faster than structure

The current report stack can display ACPM results later, but it is not a safe first home for ACPM-specific meaning.

## Questions Answered in This Pass

### 1. What existing modules/functions/classes are the most likely ACPM integration points?

Most likely:

- `quantmap.py` for CLI entry only
- `src/run_plan.py` for execution-plan shape
- `src/governance.py` and `src/score.py` for shared scoring identity
- `src/trust_identity.py` for provenance/audit reconstruction
- `src/export.py`, `src/explain.py`, and report builders as downstream consumers

### 2. Where is there already a usable seam, and where is there no real seam yet?

Usable seams:

- `RunPlan`
- trust identity loading
- governed profile loading
- artifact path policy

Missing seams:

- planner-to-execution contract
- recommendation record/model
- dedicated ACPM package boundary
- report/export/explain adapter for recommendation metadata

### 3. Which current files/modules are acting like god objects or overburdened coordination layers?

Primary:

- `src/runner.py`

Secondary:

- `src/report_campaign.py`
- `src/report.py`
- `src/score.py`

### 4. Where should the ACPM planner/orchestrator most likely live?

Recommended answer:

- a new `src/acpm/` package

### 5. What contracts/interfaces appear to be missing for ACPM to fit cleanly?

Missing:

- ACPM planner output contract
- recommendation outcome contract
- thin adapter between recommendation state and human/audit surfaces

### 6. Which pieces of current logic look extractable into reusable support?

Best candidates:

- `RunPlan` execution-shape logic
- config/candidate materialization around `build_config_list()`
- methodology/trust reconstruction via `trust_identity`
- artifact path handling

### 7. Which current responsibilities are too mixed together?

Most mixed:

- runner orchestration with persistence/output/policy
- report rendering with interpretation/warnings/methodology disclosure
- scoring with methodology persistence and some campaign-shape logic

### 8. Which surfaces likely require only light prep versus substantive refactor?

Light prep:

- `quantmap.py`
- `src/run_plan.py`
- `src/trust_identity.py`
- `src/artifact_paths.py`
- `src/explain.py`
- much of `src/export.py`

Substantive prep:

- `src/runner.py`
- recommendation persistence/model layer
- any ACPM-facing additions to report surfaces unless done through a thin adapter

### 9. Are there K.I.T. items or fragility zones in the same surfaces ACPM will depend on?

Yes:

- `QM-017`
- `QM-020`
- `QM-021`
- with important secondary overlap from `QM-016`, `QM-004`, and `QM-011`

### 10. What is the minimum pre-implementation refactor set needed?

Minimum set:

- define ACPM plan contract
- define recommendation record seam
- extract config/candidate materialization out of `runner.py`
- create `src/acpm/` as the orchestrator home
- add one shared metadata ingestion path for report/export/explain consumers

### 11. What refactors should explicitly wait until later?

Wait:

- full runner decomposition
- full report stack rewrite
- full scoring-module cleanup
- broad backend abstraction work

### 12. What is the best implementation order for structural prep?

Best order:

1. contracts
2. minimal runner seam extraction
3. ACPM package boundary
4. metadata adapters for reader surfaces
5. ACPM feature implementation

## Remaining Open Questions

### 1. Should planner intent extend `RunPlan` directly or live beside it?

This is the biggest still-open structural decision.

The repo already has a good execution-plan object, but ACPM will also need planner provenance that should not be confused with engine execution fields.

### 2. What is the narrowest durable recommendation record that satisfies `QM-020` without over-designing v1?

This pass can say the seam is required, but the exact record shape still deserves a targeted investigation before implementation starts.

### 3. How much of current report wording should be centralized before ACPM metadata is introduced?

The report stack is already large enough that this should stay bounded.

## Recommended Next Investigations

- `ACPM-plan-contract-TARGET-INVESTIGATION.md`
- `ACPM-recommendation-record-contract-TARGET-INVESTIGATION.md`
- `ACPM-runner-seam-extraction-order-TARGET-INVESTIGATION.md`

These are smaller and cleaner than trying to settle all remaining structural details inside ACPM implementation.

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
