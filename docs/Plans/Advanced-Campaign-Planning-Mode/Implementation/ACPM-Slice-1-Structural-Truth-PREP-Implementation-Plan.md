# ACPM Slice 1 Structural Truth PREP Implementation Plan

## Outcome

Create the first ACPM implementation slice as structural truth prep only. Slice 1 should establish where planner intent lives, how planner output compiles toward existing execution, how execution records the generic authority for selected scope, and where minimal ACPM planning provenance is persisted adjacent to execution truth.

This slice must not implement planner heuristics, scoring profiles, effective filter-policy truth, recommendation records, report prose, export behavior, or machine handoff.

## Scope / What This Slice Covers

- Define a dedicated ACPM planner/orchestrator module boundary outside runner core.
- Define a typed planner output contract that can later carry selected scope, profile, repeat tier, and planner provenance toward execution.
- Add or prepare the generic `scope_authority` execution-truth seam so planner-directed scope is not mislabeled as `custom`.
- Add the minimum adjacent ACPM planning-metadata persistence seam needed to preserve planner provenance without duplicating `RunPlan`.
- Keep runner integration to a tiny handoff seam only: existing execution remains the engine.

## Locked Inputs From Baseline

- `RunPlan` stays execution truth.
- ACPM planning metadata stays adjacent planner provenance, not execution truth.
- No ACPM-specific `run_mode` values.
- `scope_authority` is required and generic.
- Legacy `custom` remains user-directed subset semantics.
- Report/export/history/compare/explain are consumers of structured truth, not owners of planner logic.
- Planner logic must not be placed directly in runner core unless a tiny invocation/compilation seam is unavoidable.
- Effective filter-policy truth, recommendation claim truth, and profile-weight implementation belong to later slices.

## Proposed Module Boundary

Implement the ACPM planner boundary as a small dedicated module, tentatively `src/acpm_planning.py`.

Responsibilities owned by this module in Slice 1:

- Define planner-facing contracts such as `ACPMPlannerOutput`, `ACPMSelectedScope`, and `ACPMPlanningMetadata`.
- Define validation rules that keep planner metadata provenance-only.
- Define a compile boundary that returns execution inputs for `RunPlan` without mutating runner behavior.
- Define constants for v1 planner metadata schema ID/version and allowed repeat-tier/profile identifiers only where needed for contract validation.

Responsibilities not owned by this module:

- Running benchmarks or campaign cycles.
- Scoring, ranking, gates, filters, or winner selection.
- Report/export/history/compare wording.
- Recommendation status, caveats, or handoff serialization.
- Effective filter-policy persistence.

Runner core should only call or receive this module through a narrow seam once ACPM CLI entry exists. The planner module owns planner policy; `src/runner.py` remains execution orchestration.

## Proposed Planner Output Contract

Create a planner output object with four lanes:

- `selected_scope`: the planner-selected execution scope in the same semantic shape needed to compile a `RunPlan`; this is not persisted as planner authority once execution owns the compiled `RunPlan`.
- `execution_inputs`: minimal values needed to build or update `RunPlan`, including existing `run_mode` and generic `scope_authority`.
- `planning_metadata`: immutable planner provenance for persistence beside `run_plan_json`.
- `profile_context`: ACPM profile and repeat tier labels used by planner policy; scoring-profile implementation remains later-slice work.

Suggested v1 fields:

```text
ACPMPlannerOutput
- selected_scope
- run_mode
- scope_authority
- profile_name
- repeat_tier
- planning_metadata
```

Validation rules:

- `scope_authority` must be `planner` for ACPM planner-directed runs.
- `run_mode` must remain an existing execution-depth value; ACPM must not add `run_mode="acpm"` or similar.
- Planner output may reference selected scope for compilation, but persisted planning metadata must not duplicate the full `RunPlan`.
- Planner output must not contain effective filter thresholds, scoring results, recommendation status, or report wording.

## Proposed `scope_authority` Seam

Add `scope_authority` as a generic execution-truth field on `RunPlan`.

Recommended values:

- `campaign_yaml`: the committed campaign definition selected the execution scope.
- `user`: the user selected an explicit subset, including legacy `custom`.
- `planner`: a planner selected or narrowed scope before execution.

Implementation intent:

- Existing full/default campaign paths should write `campaign_yaml`.
- Existing user-subset/custom paths should write `user`.
- Future ACPM planner-directed paths should write `planner`.
- Legacy persisted `RunPlan` records without the field should remain readable and should project as `unknown` or be compatibility-derived only in display/helper code, not silently rewritten.

This seam is generic by design. It says who selected scope, not why ACPM exists, and not how deep the run repeats.

## Proposed adjacent ACPM planning-metadata seam

Persist minimal ACPM planning metadata adjacent to `run_plan_json`, tentatively as nullable `campaign_start_snapshot.acpm_planning_metadata_json` or the nearest existing campaign-start snapshot equivalent.

Minimum metadata contract:

```text
ACPMPlanningMetadata
- schema_id: "quantmap.acpm.planning_metadata"
- schema_version: 1
- planner_id
- planner_version
- planner_policy_id
- profile_name
- repeat_tier
- scope_authority
- source_campaign_ref
- selected_scope_digest
- narrowing_steps
- coverage_policy
```

Rules:

- Store provenance and digest/summary, not a second copy of `RunPlan`.
- Store planner policy identity and narrowing rationale, not scoring thresholds.
- Store profile/repeat-tier labels as planner provenance; governed profile definitions and weights remain methodology truth in later slices.
- Store NGL scaffold policy labels only as planner coverage provenance when relevant; recommendation-grade coverage claims remain later slices.
- Keep the field nullable for non-ACPM and legacy runs.

## Candidate touched files

Implement now:

- `src/acpm_planning.py`: new planner contract and planning metadata module.
- `src/run_plan.py`: add generic `scope_authority` field, serialization, and legacy-read handling.
- `src/runner.py`: add only the tiny seam needed to pass/write `scope_authority` and adjacent planning metadata when supplied; no planner policy logic.
- `src/db.py`: add the adjacent nullable planning metadata storage if campaign-start snapshot schema is DB-backed here.

Potential tests:

- `tests/test_acpm_planning.py`: planner output and metadata contract validation.
- `tests/test_run_plan.py` or nearest existing run-plan test file: `scope_authority` defaults, serialization, and legacy compatibility.
- `tests/test_runner.py` or nearest existing runner/snapshot test file: runner persists `scope_authority` and optional planning metadata without changing execution behavior.
- `tests/test_db.py` or nearest schema test: nullable planning metadata storage migration/creation if DB schema changes.

Implementation-start validation:

- Before code changes, inspect the current source/test filenames above and adjust to the nearest existing owner files. Do not broaden into report/export/history/compare unless source inspection proves the structural seam cannot be validated otherwise.

## Data-flow / lifecycle sketch

1. Future ACPM entry chooses campaign YAML, profile, repeat tier, and planner policy.
2. `src/acpm_planning.py` produces `ACPMPlannerOutput`.
3. Planner output compiles selected execution scope into existing `RunPlan` inputs.
4. `RunPlan` records execution truth, including `scope_authority="planner"` for planner-directed runs.
5. Runner executes the existing campaign path without embedding planner heuristics.
6. Campaign-start snapshot persists `run_plan_json` as execution truth and optional ACPM planning metadata as adjacent provenance.
7. Later slices project the persisted truth lanes into filter policy, profiles, recommendation records, report/export/history/compare/explain, and optional handoff.

## Blast radius / risk notes

- Persisted `RunPlan` shape changes are trust-bearing; legacy missing-field reads must stay explicit and non-destructive.
- `scope_authority` must not alter scoring, gates, filtering, ranking, or report wording in Slice 1.
- Runner changes must stay seam-only; putting planner policy in `src/runner.py` would violate the baseline.
- Adjacent metadata must not become a shadow execution record, threshold map, methodology snapshot, or recommendation record.
- DB/schema change risk is limited if the planning metadata field is nullable and ignored by non-ACPM paths.
- Product-code implementation should stop if source inspection shows current storage is not campaign-start-snapshot-based or if adding metadata requires a broader artifact redesign.

## Minimum tests / validation strategy

- Run dev preflight before implementation: `.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick`.
- Unit-test `scope_authority` serialization and legacy-read behavior on `RunPlan`.
- Unit-test that `custom` or explicit subset paths map to `scope_authority="user"`, not planner.
- Unit-test planner metadata validation rejects duplicated execution truth, effective filter thresholds, scoring results, and recommendation fields.
- Test optional persistence: non-ACPM runs allow null planning metadata; ACPM-prepared runs persist and reload metadata unchanged.
- Run Ruff on touched files after each edit batch.
- Run focused tests for touched modules, then `changed_path_verify.py --paths <touched paths>` if unrelated dirty files remain.

## Explicit defer list for later slices

- ACPM CLI command spelling and user-facing entry.
- Actual planner heuristics, applicability pruning, repeat-tier expansion, and fixed NGL scaffold behavior.
- Governed ACPM scoring profile definitions and profile weight vectors.
- Effective filter-policy persistence/projection.
- Stale `min_valid_warm_count` wording cleanup.
- Recommendation record, status policy, caveat policy, and machine handoff gating.
- Report/export/history/compare/explain projections beyond any tiny structural-read helper needed to prove persistence.
- Formal machine handoff artifact family.
- Any broad runner, report, export, compare, or history redesign.

## Open issues only if truly blocking implementation of this slice

NA. The baseline leaves exact metadata home/name deferred, but this slice can choose a narrow adjacent nullable field during implementation as long as it does not duplicate `RunPlan` or own methodology/recommendation truth.

## `.agent` files used this turn

- `.agent/README.md`
- `.agent/policies/boundaries.md`
- `.agent/policies/architecture.md`
