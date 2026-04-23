# ACPM History Surface Scope and Coverage Projection Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 history/export/provenance preservation of scaffolded vs full-ladder `NGL_sweep` scope truth only

## Outcome

Recommended v1 policy:

- keep canonical execution-scope truth in `RunPlan`
- keep planner identity and scaffold policy provenance in adjacent ACPM planning metadata
- persist one small immutable history-grade scope/coverage projection beside those records so compare, audit, and export do not have to reverse-engineer intent later
- keep methodology snapshots completely separate from this lane
- keep human-readable history/export wording derived from the structured fields rather than storing prose as truth

Best v1 design:

- `RunPlan` remains the source for:
  - full campaign values
  - selected values
  - run mode
  - future generic `scope_authority`
- ACPM planning metadata remains the source for:
  - planner identity
  - planner policy identity/version
  - repeat tier
  - scaffold label/policy ID when applicable
  - narrowing provenance
- a compact history-grade `scope_coverage_projection` should be persisted as a frozen derived block so later consumers can directly read:
  - `coverage_class`
  - `selected_ngl_values`
  - `coverage_authority`
  - optional `scaffold_policy_id`

Strongest repo-grounded reason:

- the repo already uses a snapshot-first trust pattern. `run_plan_json` captures execution intent, methodology snapshots capture scoring truth, and `metadata.json` projects structured provenance. The missing seam is not another plan system, but one small projection layer that preserves scope/coverage meaning without forcing later compare/history consumers to guess from raw values.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/run_plan.py`
- `src/runner.py`
- `src/telemetry.py`
- `src/trust_identity.py`
- `src/export.py`
- `src/compare.py`
- `src/report_compare.py`
- `src/db.py`

Supporting ACPM investigations inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planning-metadata-schema-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-run-mode-and-scope-authority-semantics-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-compare-surface-coverage-class-labeling-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-NGL-report-and-audit-wording-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-NGL-scaffold-subset-policy-TARGET-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`

Validation used:

- targeted source/doc inspection
- one light proportional verification step confirming where `run_plan_json`, snapshot-first provenance, metadata export projection, and compare reconstruction currently live
- no product-code edits

## Current History / Provenance Constraints

### 1. The repo already has a snapshot-first history lane

`src/runner.py` writes `campaign_start_snapshot` once at run start and preserves the original row if one already exists. `src/telemetry.py` captures `run_plan_json` into that snapshot. `src/trust_identity.py` reads it back as snapshot-first historical truth.

Implication:

- ACPM scope/coverage truth should live in this same immutable history lane, not in transient report text

### 2. `RunPlan` already preserves most execution-scope facts

`src/run_plan.py` and `run_plan_json` already preserve:

- `all_campaign_values`
- `selected_values`
- `run_mode`
- effective identity and schedule fields

Implication:

- the repo already has enough raw scope truth to know whether a run was full or partial
- what it does not preserve cleanly yet is why a partial scope existed

### 3. Current history truth is insufficient to distinguish scaffolded vs custom subset coverage

Today, later consumers can inspect `selected_values`, but cannot cleanly distinguish:

- planner-directed fixed scaffold coverage
- user-directed custom subset coverage
- full ladder coverage

without reverse-engineering from values, mode semantics, and future ACPM policy knowledge.

Implication:

- raw `RunPlan` values alone are not enough for durable compare/history consumption

### 4. Methodology snapshots are the wrong place for this truth

`methodology_snapshots` and `src/trust_identity.py` already own:

- profile name/version
- weights
- gates
- anchors
- methodology capture quality

Implication:

- ACPM scope/coverage truth should not be stored in methodology snapshots
- doing so would blur execution-scope history with scoring-governance history

### 5. `metadata.json` is a projection surface, not the source of truth

`src/export.py` builds `metadata.json` from persisted campaign, snapshot, methodology, ranking, and run-context data. It already works as the machine-readable export projection.

Implication:

- export should project ACPM scope/coverage truth
- but it should not be the primary place where that truth lives

### 6. Compare currently has no dedicated history-grade scope/coverage input

`src/compare.py` and `src/report_compare.py` currently compare:

- methodology
- environment
- winner deltas
- shared-config deltas

They do not yet consume a compact scope/coverage record.

Implication:

- if v1 does not preserve a small structured projection, compare will either guess later or stay misleadingly silent

### 7. `campaigns.notes_json` is the wrong durability pattern for new ACPM scope truth

`src/db.py`, `src/score.py`, and `src/trust_identity.py` show that `notes_json` is a transitional bridge for older governance methodology data.

Implication:

- ACPM scope/coverage truth should not be introduced as another `notes_json` convention
- v1 should follow the newer snapshot-first structured pattern instead

## Candidate Projection Models Considered

### 1. Derive everything later from `RunPlan` only

Meaning:

- persist no extra scope/coverage projection
- let compare/export infer class from selected values and mode

Assessment:

- reject

Why:

- too lossy for planner-directed scaffold vs custom subset distinction
- forces future consumers to re-encode ACPM policy logic

### 2. Persist everything only in ACPM planning metadata

Meaning:

- put coverage class, authority, values, and scaffold identity all into adjacent planning metadata
- treat that record as the only source

Assessment:

- reject

Why:

- execution-scope truth already belongs partly in `RunPlan`
- this would overstuff planning metadata and make it feel like a shadow plan

### 3. Keep only canonical split truth and derive projection on every read

Meaning:

- preserve scope facts in `RunPlan`
- preserve planner provenance in ACPM metadata
- never store a compact projection

Assessment:

- workable but weaker than needed

Why:

- keeps ownership clean
- but makes compare/history/export redo the same logic repeatedly
- increases risk of drift across consumers

### 4. Canonical split truth plus one persisted derived projection

Meaning:

- keep source facts in `RunPlan` and ACPM planning metadata
- also persist a tiny immutable `scope_coverage_projection` block for history-grade consumers

Assessment:

- best v1 fit

Why:

- preserves ownership boundaries
- gives compare/export/history a clean compact input
- avoids a second plan system because the projection stays very small and explicitly derived

## Recommended v1 History-Surface Scope / Coverage Projection Policy

### Core policy

Use three layers with clear ownership:

1. `RunPlan`
   - execution-truth scope facts
2. ACPM planning metadata
   - planner identity and narrowing provenance
3. history-grade `scope_coverage_projection`
   - small derived consumer-facing structured truth

### What the projection should contain

Recommended minimum durable v1 shape:

```json
{
  "family": "NGL_sweep",
  "coverage_class": "fixed_1x_scaffold_coverage",
  "coverage_authority": "planner_directed",
  "selected_values": [10, 30, 50, 70, 90, 999],
  "scaffold_policy_id": "ngl_fixed_1x_v1"
}
```

For a full-ladder run:

```json
{
  "family": "NGL_sweep",
  "coverage_class": "full_ladder_coverage",
  "coverage_authority": "system_defined",
  "selected_values": [10, 20, 30, 40, 50, 60, 70, 80, 90, 999]
}
```

For a user subset:

```json
{
  "family": "NGL_sweep",
  "coverage_class": "custom_subset_coverage",
  "coverage_authority": "user_directed",
  "selected_values": [30, 50, 999]
}
```

### Why this projection is safe

- `coverage_class` is the minimum interpretive bucket compare needs
- `selected_values` preserves exact reconstruction without forcing consumers to reopen full run-plan semantics every time
- `coverage_authority` preserves planner-vs-user distinction
- `scaffold_policy_id` belongs only where scaffold policy provenance actually matters

## What Should Live Where

### In `RunPlan`

`RunPlan` should continue to own:

- `all_campaign_values`
- `selected_values`
- `run_mode`
- execution identity and schedule
- future generic `scope_authority` once that seam is added

It should not own:

- scaffold policy IDs
- planner profile IDs
- planner policy versions
- coverage-class labels that depend on planner interpretation

### In ACPM planning metadata

Adjacent ACPM planning metadata should own:

- `planner_id`
- `planner_version`
- `profile_id`
- `planner_policy_id`
- `planner_policy_version`
- `repeat_strength_tier`
- narrowing provenance
- scaffold label/policy ID when scaffold policy was actually applied

It should not become the only place selected values live.

### In the history-grade projection

The compact projection should own only the small consumer-facing reconstruction fields:

- `coverage_class`
- `selected_values`
- `coverage_authority`
- optional `scaffold_policy_id`

It should remain explicitly derived from `RunPlan` plus ACPM planning metadata.

### In export/report/compare surfaces

These should project from the structured truth above.

They should not become source systems themselves.

## Where the Projection Should Live

### Recommended primary persistence lane

Best v1 fit:

- persist the ACPM planning metadata and its tiny `scope_coverage_projection` in the same snapshot-first history lane as `run_plan_json`

Repo-fit interpretation:

- if ACPM adds one new durable history seam, it should sit adjacent to `run_plan_json` in the campaign-start snapshot lineage rather than in `methodology_snapshots`, `notes_json`, or markdown artifacts

### Why this lane fits

- it is immutable
- it is already treated as historical provenance
- `trust_identity` already reads from this lane
- compare/history consumers already conceptually belong here

### What should stay derived only

Human-readable strings like:

- `NGL coverage: fixed 1x scaffold coverage`
- `Selected NGL values: 10, 30, 50, 70, 90, 999`

should stay derived from the structured fields and should not become the stored source of truth.

## Structured-Only vs Human-Readable Projection Guidance

### Structured-only source fields

These should remain structured-only source truth:

- `coverage_class`
- `coverage_authority`
- `selected_values`
- `scaffold_policy_id`

### Human-readable projection

Human-readable history/export/report surfaces may render:

- one short coverage-class label
- one optional selected-values line
- one brief limitation note when the class is scaffolded or custom

But these surfaces should not carry unique truth that is missing from the structured fields.

## Planner-Directed vs User-Directed Coverage Distinction

### Required v1 rule

Planner-directed scaffold coverage must remain distinguishable from user-directed custom subset coverage even when the raw selected values happen to match.

That means v1 needs:

- `coverage_authority`
- not just `selected_values`

### Why this matters

Without authority, later consumers cannot tell whether a subset came from:

- ACPM governed planner-budget policy
- deliberate user scope choice

That is a trust/history failure even if the raw values are present.

## NGL-Specific vs General Seam Policy

### Recommended v1 posture

Use a small general projection seam with narrow v1 scope.

Meaning:

- the placement and shape should be generic enough to be reused later
- but v1 should only govern the `NGL_sweep` case explicitly

This avoids both extremes:

- not NGL-hardcoded prose scattered across surfaces
- not a giant universal scope taxonomy before the repo needs it

### Practical interpretation

The container may be generic, but the only governed coverage-class family in v1 should be:

- `NGL_sweep`

## Risks of Getting This Wrong

- compare and export will be forced to guess scaffold intent from raw selected values later
- planning metadata will become a shadow `RunPlan` if it absorbs too much scope truth
- methodology history will be polluted with non-methodology scope semantics if this is stored in the wrong lane
- human-readable projections may drift away from structured truth if they become the effective source
- overgeneralizing now will create a large taxonomy with no current repo consumer

## Downstream Implementation Consequences

- ACPM needs one additional durable history seam adjacent to the current snapshot-first provenance path
- `trust_identity`-style loading will eventually need to expose the small scope/coverage projection
- compare can then consume a direct coverage-class field rather than reverse-engineering raw values
- `metadata.json` can project the same structured truth cleanly
- no giant history framework is needed

## Questions Answered in This Pass

### Which existing history/provenance surfaces already preserve enough truth and which do not

- `run_plan_json` preserves raw scope facts well
- methodology snapshots preserve methodology truth well
- current history/export surfaces do not preserve planner-vs-user coverage meaning cleanly enough

### Should coverage-class truth be derived from `RunPlan` + planner metadata, persisted directly, or both

- both in a controlled way: canonical source facts remain split, but a tiny derived projection should be persisted for later consumers

### What minimum durable fields should exist for reconstruction

- `coverage_class`
- `selected_values`
- `coverage_authority`
- optional `scaffold_policy_id`

### Where scaffold label/policy ID belongs

- in ACPM planning metadata as planner-policy provenance, with optional mirrored presence in the compact projection when scaffold coverage was actually used

### What should remain structured-only versus what should have a human-readable projection

- the fields above stay structured-first
- reports/export/history can render short derived lines only

### How to preserve planner-directed scaffold coverage distinctly from user-directed custom subset coverage

- by storing `coverage_authority`, not by relying on selected values alone

### Whether v1 should keep this NGL-specific or introduce a more general seam now

- introduce a small general seam in placement, but keep the governed semantics narrow to the NGL case in v1

## Remaining Open Questions

- whether the compact projection should live inside the ACPM planning metadata record or as its own adjacent snapshot block within the same persistence lane
- whether `selected_values` should be mirrored in the compact projection for all NGL runs or only when the coverage class is not full ladder
- whether future non-NGL planner-budget exceptions should reuse the same projection object unchanged or require a slightly broader family-keyed shape

## Recommended Next Investigations

- `ACPM-snapshot-lane-placement-for-planner-history-TARGET-INVESTIGATION.md`
- `ACPM-metadata-json-scope-coverage-projection-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`
