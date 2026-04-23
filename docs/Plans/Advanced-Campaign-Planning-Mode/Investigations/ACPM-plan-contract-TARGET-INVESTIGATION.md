# ACPM Plan Contract Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 planner/execution contract shape and ownership boundary only

## Outcome

Recommended v1 contract model:

- ACPM planner state should live adjacent to `RunPlan`, not be stuffed into it
- ACPM should compile into:
  - a narrow `RunPlan` for execution truth
  - a separate ACPM planning metadata record for planner intent
- if ACPM needs one `RunPlan` change for truthful downstream behavior, it should be a generic execution-truth field such as scope/selection authority, not ACPM-specific planner payload

Bottom line:

- `RunPlan` should remain the engine-facing description of what will be executed
- ACPM profile/policy intent should survive beside it as planner metadata
- recommendation metadata should remain separate from both

This is the cleanest repo fit because `RunPlan` is already treated as the authoritative resolved execution object, while richer methodology and historical identity already live outside it in trust/export surfaces.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/run_plan.py`
- `src/runner.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/trust_identity.py`
- `src/score.py`

Supporting docs inspected:

- `docs/Design Memo's/Advanced-Campaign-Planning-Mode-ADR/Adaptive-Campaign-Planning-Mode-v1-Design.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-refactor-seams-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `.agent/README.md`
- `.agent/policies/architecture.md`

Validation used:

- targeted source inspection only
- no product-code changes
- no broad test theater; this pass is about contract fit and ownership

## What `RunPlan` Currently Represents

In repo terms, `RunPlan` is the resolved execution plan for one QuantMap run.

Concretely, it currently owns:

- run identity
  - `parent_campaign_id`
  - `effective_campaign_id`
  - `run_mode`
- execution scope
  - `variable`
  - `all_campaign_values`
  - `selected_values`
  - `selected_configs`
- execution schedule
  - `cycles_per_config`
  - `requests_per_cycle`
- infrastructure/output paths
  - `baseline_path`
  - `effective_lab_root`
  - `db_path`
  - `state_file`
  - `results_dir`
- execution-affecting overrides and audit trail
  - `filter_overrides`
  - `mode_flag`
  - `values_override`
  - `cycles_override`
  - `requests_per_cycle_override`

It also provides convenience properties used by downstream surfaces:

- `is_custom`, `is_full`, `is_standard`, `is_quick`
- `mode_label`, `mode_description`
- `untested_values`
- `coverage_fraction`
- `warm_samples_per_config`

Most importantly, the repo already treats `RunPlan` as:

- the single authoritative description of execution in `src/runner.py`
- a live input for report generation in `src/report.py`
- a mode/scope input for `src/report_campaign.py`
- a persisted run-start identity snapshot via `to_snapshot_dict()` into `campaign_start_snapshot.run_plan_json`
- a historical identity input through `src/trust_identity.py`

That means `RunPlan` is not merely a convenience object. It is already an execution-truth contract and a persisted historical record of run intent.

## Candidate Contract Models Considered

### 1. Extend `RunPlan` to carry ACPM planner state directly

Meaning:

- put ACPM profile, planner policy, repeat tier, selection rationale, maybe recommendation info directly onto `RunPlan`

Assessment:

- tempting because it keeps ACPM "in one object"
- wrong ownership boundary for this repo

Why it is risky:

- `RunPlan` is already persisted as run-start execution identity
- report surfaces already assume its fields describe scope/schedule facts, not planner semantics
- methodology/profile identity already has a different trust-bearing home in scoring/trust surfaces
- recommendation state would be especially unsafe here because it changes after execution/scoring and could become stale or duplicative

Recommendation:

- reject for v1

### 2. Subclass or replace `RunPlan` with an ACPM-specific super-plan

Meaning:

- create `AcpmRunPlan` or a more generic plan object and have runner/report surfaces consume that instead

Assessment:

- structurally heavier than v1 needs
- fights the existing repo rather than using it

Why it is risky:

- `report.py` imports the concrete `RunPlan`
- `runner.py` already constructs and snapshots `RunPlan`
- replacing the object would widen blast radius across execution, reporting, and trust history all at once

Recommendation:

- reject for v1

### 3. Compile ACPM down into `RunPlan` plus adjacent ACPM planning metadata

Meaning:

- ACPM planner produces a normal engine-facing `RunPlan`
- ACPM planner also emits a sidecar metadata record containing planner intent
- downstream surfaces can consume whichever layer they actually own

Assessment:

- best fit for current repo shape
- preserves separation between execution truth and planner meaning

Recommendation:

- recommend for v1

### 4. Use a small ACPM envelope locally, but keep durable contracts split

Meaning:

- inside `src/acpm/`, use an in-memory wrapper like:
  - `run_plan`
  - `acpm_plan_metadata`
- do not make that wrapper the new global engine/report contract

Assessment:

- acceptable as an internal convenience pattern
- only if the durable contract still remains split

Recommendation:

- acceptable locally, but not as the repo-wide replacement for `RunPlan`

## Recommended v1 Planner/Execution Contract

Recommended model:

- ACPM planner emits two artifacts:
  - `RunPlan`
  - ACPM planning metadata

Ownership split:

- `RunPlan` owns execution-truth facts required to run and honestly describe what was run
- ACPM planning metadata owns planner intent and planner policy context
- recommendation metadata remains a later, separate layer

### Minimum v1 contract ACPM needs to hand execution

The minimum engine-facing contract is still a `RunPlan`-shaped execution object containing:

- parent/effective campaign identity
- resolved execution scope
  - selected values
  - selected configs
- resolved schedule
  - cycles per config
  - requests per cycle
- required paths
- any execution-affecting filter overrides that truly belong to the run

In v1 ACPM, repeat-strength tiers should compile down to schedule fields here, not remain only as planner labels.

### One important contract correction

There is one pressure point where the current `RunPlan` shape is too lossy for ACPM:

- `run_mode="custom"` currently means user-directed partial scope
- ACPM may also produce partial scope, but planner-directed rather than user-directed

That means ACPM should not simply masquerade as current `custom` semantics.

The cleanest contract answer is:

- keep planner identity outside `RunPlan`
- add only a narrow execution-truth field if needed to distinguish who/what chose the narrowed scope

Good shape:

- `selection_authority`
- `scope_authority`
- or similarly generic wording

Bad shape:

- putting ACPM profile/policy names into `run_mode`
- reusing `custom` unchanged for planner-directed narrowing

## What Belongs in `RunPlan` vs Adjacent ACPM Metadata

### Belongs in `RunPlan`

These are execution-shape facts:

- effective campaign identity
- selected values/configs actually executed
- effective schedule
- effective paths and state locations
- execution-affecting overrides
- partial/full coverage facts
- if needed, a generic scope-selection authority field because it changes the truthful interpretation of partial coverage

Rule:

- if the engine must know it to execute correctly, or a report must know it to describe what was actually run, it belongs in `RunPlan`

### Does not belong in `RunPlan`

These are planner or methodology-adjacent semantics, not execution facts:

- ACPM profile identity as planner lens
- planner policy name/version
- repeat-strength tier label as a label
  - the resolved schedule belongs in `RunPlan`
  - the original tier label belongs beside it
- score-shape labeling
- profile-weight-lens labeling
- planner narrowing rationale
- omitted-family reasoning
- candidate-stage reasoning
- recommendation status
- recommended variable handoff content

Rule:

- if it explains why ACPM chose the plan rather than what the engine executed, it should live beside `RunPlan`

### Minimum ACPM metadata that must survive alongside execution

Without going into full recommendation-record design, the minimum sidecar planner metadata for later reporting/audit should include:

- ACPM enabled / planner identity
- ACPM profile used
- planner policy identifier/version
- user-selected repeat-strength tier
- linkage to the compiled execution run
  - parent/effective campaign ID or equivalent stable join key
- bounded-scope selection summary
  - enough to reconstruct that narrowing was planner-directed and not user-directed
- explicit separation from methodology/scoring authority
  - planner metadata should reference, not replace, governed scoring identity

## Risks of Getting This Wrong

### 1. Overstuffing `RunPlan`

If ACPM profile, planner policy, and recommendation meaning all go into `RunPlan`:

- execution truth and planner interpretation will blur
- `run_plan_json` will become a mixed-ownership historical record
- downstream surfaces may accidentally treat planner labels as execution facts

### 2. Making ACPM state too lossy

If ACPM compiles only to a bare `RunPlan` and discards planner metadata:

- later reporting/audit will not be able to reconstruct which profile/policy shaped the run
- planner-directed partial coverage may be mistaken for user-directed custom scope
- ACPM will appear more magical and less explainable than it really is

### 3. Duplicating trust-bearing semantics

If `RunPlan` starts carrying profile/weight/methodology truth alongside scoring/trust snapshots:

- the repo will have multiple places that appear to define profile meaning
- drift between planner-time labels and scoring-time truth becomes likely

### 4. Using recommendation state as plan state

Recommendation outcomes happen after execution/scoring.
If they live in `RunPlan`, the object stops being a stable run-start contract.

## Downstream Implementation Consequences

### 1. Runner should keep consuming `RunPlan`, not ACPM policy objects

This preserves the current engine boundary.

### 2. Report/export/explain surfaces should eventually consume ACPM metadata as a sidecar

They should not need ACPM-specific logic embedded inside `RunPlan` to stay truthful.

### 3. Current `custom` mode wording will need a bounded truth fix before ACPM partial coverage is honest

This is the biggest immediate coupling implication.

Current repo wording assumes:

- partial coverage + `custom` = user-directed scope

ACPM introduces:

- partial coverage + planner-directed scope

That distinction needs a narrow contract-aware correction before ACPM partial plans can be surfaced honestly.

### 4. Recommendation record work should remain downstream of this contract

This pass supports that later work by keeping planner metadata and execution truth separate from the start.

## Questions Answered in This Pass

### 1. What does `RunPlan` currently represent, concretely, in repo terms?

It is the authoritative resolved execution plan and persisted run-start execution identity for one QuantMap run.

### 2. Which parts of ACPM intent naturally belong inside an execution-shape object like `RunPlan`, and which parts do not?

Belongs inside:

- what will actually run
- with what scope
- with what schedule
- with what execution-affecting overrides
- with what truthful scope-authority indicator if partial coverage semantics depend on it

Does not belong inside:

- profile lens
- planner policy
- tier label as planner intent
- rationale
- recommendation outcome

### 3. Should ACPM planner intent extend `RunPlan`, live adjacent to it, or use some other shape?

Recommendation:

- live adjacent to `RunPlan`
- compile down to `RunPlan` plus a separate ACPM planning metadata record

### 4. What contract shape best preserves separation between execution facts, planner intent, recommendation metadata, and downstream consumers?

Best shape:

- `RunPlan` for execution facts
- adjacent ACPM planning metadata for planner intent
- separate recommendation record later

### 5. What current repo code paths assume things about `RunPlan` that make extension risky?

The risky assumptions are:

- `runner.py` treats it as the single authoritative execution description
- `to_snapshot_dict()` persists it as effective run intent
- `report.py` and `report_campaign.py` directly use it for mode/scope/schedule wording
- `trust_identity.py` reconstructs it as historical run identity

### 6. What is the minimum v1 contract ACPM needs to hand execution?

Minimum:

- a normal `RunPlan` with resolved IDs, scope, schedule, paths, and real execution overrides

### 7. What is the minimum ACPM metadata that must survive alongside execution for later reporting/audit use?

Minimum:

- ACPM planner identity
- ACPM profile
- planner policy ID/version
- repeat tier label
- stable linkage to the compiled run
- evidence that narrowing was planner-directed

### 8. What contract shapes would create drift, duplication, or confused ownership?

Bad shapes:

- stuffing planner and recommendation semantics into `RunPlan`
- replacing `RunPlan` with an ACPM super-object repo-wide
- duplicating methodology truth between `RunPlan` and scoring/trust surfaces
- collapsing planner-directed partial coverage into current `custom` semantics without distinction

### 9. What is the best recommended v1 contract model, and why?

Best model:

- `RunPlan` plus adjacent ACPM planning metadata

Why:

- it matches existing ownership boundaries
- it keeps execution truth narrow and durable
- it preserves planner explainability without polluting run-start execution identity

## Remaining Open Questions

### 1. Should the generic scope-authority distinction be a new `RunPlan` field or a narrower reinterpretation of current mode semantics?

This is the most important unresolved contract detail.

I do not recommend leaving it unresolved during implementation, because ACPM partial coverage will otherwise inherit misleading `custom` semantics.

### 2. What is the smallest durable ACPM planning metadata schema that satisfies audit/report consumers without drifting into full recommendation-record design?

This should be settled in a bounded follow-up rather than improvised during implementation.

## Recommended Next Investigations

- `ACPM-run-mode-and-scope-authority-semantics-TARGET-INVESTIGATION.md`
- `ACPM-planning-metadata-schema-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
