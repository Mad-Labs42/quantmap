# ACPM Effective Filter Provenance and Surface Disclosure Investigation

## Outcome

Recommended v1 policy: persist effective scoring/filter truth as a small run-start provenance/projection record adjacent to `run_plan_json`, derived from methodology snapshot gates plus explicit execution/caller overrides. Do not make report/export/compare artifacts re-derive their own filter truth, and do not put ACPM planner metadata in charge of scoring thresholds.

The safest ownership split is:

- Methodology truth: `methodology_snapshots.gates_json` remains the source for profile/default gates.
- Execution truth: `RunPlan`/`run_plan_json` owns resolved run mode, schedule, scope, and non-methodology filter overrides requested by execution policy.
- Planner provenance: ACPM metadata owns planner identity, reason, and any policy reference, but not duplicate filter values.
- Derived disclosure: a small `effective_filter_policy` / `effective_filters_projection` should expose the final applied thresholds, source per overridden key, and reconstruction quality for compare/report/export/history/explain.

This is the smallest durable v1 model that preserves trust without creating shadow methodology or shadow recommendation logic.

## Scope / What Was Inspected

Primary repo surfaces inspected:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/scripts/helpers/verify_dev_contract.py`
- `src/run_plan.py`
- `src/runner.py`
- `src/score.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/trust_identity.py`
- `src/db.py`
- `src/telemetry.py`
- `src/compare.py`
- `src/governance.py`
- `configs/profiles/default_throughput_v1.yaml`
- `configs/metrics.yaml`

Relevant ACPM investigation context inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planner-directed-scoring-filter-policy-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-legacy-custom-mode-compatibility-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-history-surface-scope-and-coverage-projection-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planning-metadata-schema-TARGET-INVESTIGATION.md`

## Current Effective-Filter Truth Model

Current scoring path:

- `src/runner.py` resolves `run_mode`, then injects mode-level `RunPlan.filter_overrides`.
- `custom` gets `{"min_valid_warm_count": 1}` for intentionally sparse targeted runs.
- `quick` gets `{"min_valid_warm_count": 3}` because its one-cycle schedule cannot satisfy the older documented default of 10.
- `standard` and `full` get no mode override.
- `src/runner.py` merges campaign YAML `elimination_overrides` on top of `RunPlan.filter_overrides`; YAML wins.
- `src/score.py::score_campaign()` merges `profile.gate_overrides` with caller `filter_overrides` to produce `effective_filters`.
- `src/score.py` returns `effective_filters` in the in-memory scoring result.

Current persistence:

- `src/run_plan.py::RunPlan.to_snapshot_dict()` persists `filter_overrides`, `run_mode`, selected values/configs, schedule, paths, and CLI overrides in `run_plan_json`.
- `src/telemetry.py` writes `run_plan_json` into `campaign_start_snapshot`.
- `src/db.py` has `campaign_start_snapshot.run_plan_json`.
- `src/db.py` has `methodology_snapshots.gates_json`, but those gates are only profile/default methodology gates.
- `src/score.py::_capture_methodology_snapshot()` persists `profile.gate_overrides` as `gates_json`.
- No current durable row or JSON field stores the final `effective_filters` plus source/provenance per override.

Current disclosure:

- `src/report_campaign.py` displays `scores_result.effective_filters` when the scoring result is live, falling back to `methodology.gates` when it is not.
- `src/report.py` shows `RunPlan.filter_overrides` in Run Scope, but not the final merged effective filters or sources.
- `src/export.py` writes `methodology.eligibility_filters` from methodology snapshot gates, not necessarily the effective filters actually used.
- `src/compare.py` compares elimination reasons/counts and methodology compatibility, but not effective filter policy/provenance.
- `src/trust_identity.py` already reads both current methodology snapshots and `run_plan_json`, making it the best existing reader seam for future reconstruction/projection.

Policy drift / accidental truth observed:

- `src/score.py` header still documents `min_valid_warm_count` as 10, while live `ELIMINATION_FILTERS` from the active profile resolve to 3.
- `src/report_campaign.py` fallback display still defaults missing `min_valid_warm_count` to 10.
- `configs/metrics.yaml` has `min_sample_gate: 10` for primary TG metrics, while `configs/profiles/default_throughput_v1.yaml` sets `min_valid_warm_count: 3`.
- `src/governance.py` comments say gate overrides may only tighten and sample gates cannot relax below Registry minimums, but current validation mainly checks recognized gate keys.

## Ownership Analysis

Effective-filter facts should be classified this way:

| Fact | Classification | Recommended owner |
| --- | --- | --- |
| Profile gate defaults | Methodology truth | `methodology_snapshots.gates_json` |
| Mode/schedule/user-scope filter overrides | Execution truth | `RunPlan` / `run_plan_json` |
| Campaign YAML `elimination_overrides` | Execution/campaign policy truth | Run-start effective filter projection, sourced as campaign YAML |
| ACPM planner identity and selection rationale | Planner provenance | ACPM planning metadata |
| ACPM-approved scoring/filter exception ID | Planner/policy provenance | ACPM metadata may reference it; effective projection owns applied thresholds |
| Final thresholds passed to elimination filters | Derived methodology-plus-execution truth | Small effective filter projection |
| Report/export wording | Presentation/disclosure | Derived from shared projection, not independently inferred |

Do not store final effective filters only in `methodology_snapshots`: mode, schedule, `--values`, and campaign YAML overrides are not methodology profile definitions.

Do not store final effective filters only in ACPM planning metadata: ACPM should not become an alternate scoring authority, and non-ACPM runs need the same truth model.

Do not let each surface derive filters independently from `run_mode`: that repeats the existing `custom`/`quick` coupling and will mislabel planner-directed partial coverage.

## Legacy / Back-Compat Reconstruction Analysis

Legacy reconstruction can be tiered, but it must carry reconstruction quality:

| Available evidence | Safe reconstruction | Required caveat |
| --- | --- | --- |
| `methodology_snapshots.gates_json` plus `run_plan_json.filter_overrides` | Merge gates plus overrides | Override source may be only `legacy_merged_run_plan_override` unless newer source metadata exists |
| Methodology gates plus `run_plan_json.filter_overrides` plus campaign YAML snapshot with `elimination_overrides` | Merge gates, mode/run-plan overrides, then YAML overrides | If `run_plan.filter_overrides` already represented only mode overrides, YAML source can be identified; otherwise mark ambiguity |
| Live `scores_result.effective_filters` during report generation | Display as current scoring output | Not sufficient by itself as durable historical/audit truth |
| Only methodology gates | Display methodology gates | Do not claim there were no runtime overrides unless `run_plan_json` or equivalent proves it |
| Only `campaigns.run_mode` | Limited inference from current code: `custom` likely meant `min_valid_warm_count=1`, `quick` likely meant 3 | Mark as inferred legacy, not authoritative; base gates may differ by historical code/profile |
| No methodology snapshot and no run plan | Unknown | Keep unknown rather than backfilling from current files |

Old runs should remain interpretable, but not over-certified. For legacy cases, the reader should distinguish:

- `complete`: explicit methodology gates and explicit effective override provenance exist.
- `reconstructed`: gates plus overrides are available, but source detail is limited.
- `inferred_limited`: only `run_mode` or current-code convention supports inference.
- `unknown`: not enough persisted evidence to state effective filters.

## Surface Disclosure Analysis

Surfaces needing full effective-filter truth:

- `src.score`: needs actual thresholds, but should not own planner/source semantics beyond returning the effective thresholds it applied.
- `src.runner`: needs the execution/caller policy that decides overrides before scoring.
- `src.trust_identity`: should become the shared reconstruction/projection seam because it already loads methodology and `run_plan_json`.
- `src.export`: should include machine-readable effective filter policy/provenance, not just methodology gates.
- `src.compare`: should detect effective-filter differences that affect comparability.

Surfaces needing bounded disclosure projection:

- `src.report` should show run-level overrides and policy source without duplicating methodology tables.
- `src.report_campaign` should show effective thresholds and source/caveat, especially for `min_valid_warm_count`.
- History/list metadata should show a compact policy label and reconstruction quality, not full scoring internals.
- Explain/recommendation-adjacent surfaces should disclose if a winner/recommendation was rankable only under a relaxed or non-default filter policy.

Current misleading risks by surface:

- `report_campaign` can say filters were pre-committed based on the Experiment Profile even when mode/YAML overrides changed them.
- `export` currently exposes `methodology.eligibility_filters` as if that is enough, but it may omit the actual effective filters.
- `compare` can compare runs that used different thresholds without surfacing that as a methodology/trust difference.
- History consumers using `run_mode` alone will conflate manual `custom`, shallow `quick`, and future planner-directed partial scope.

## Recommended v1 Persistence / Projection Model

Persist the minimum effective-filter record at run start, adjacent to `run_plan_json` in the snapshot-first lineage. The record should be derived once from methodology gates plus execution/campaign/planner policy inputs and reused by consumers.

Recommended shape:

```json
{
  "schema_version": 1,
  "policy_id": "profile_default",
  "policy_source": "runner",
  "base_methodology_snapshot_id": 123,
  "base_gates_source": "methodology_snapshots.gates_json",
  "base_gates": {
    "min_valid_warm_count": 3
  },
  "overrides": {
    "min_valid_warm_count": 1
  },
  "override_sources": {
    "min_valid_warm_count": "mode:custom"
  },
  "effective_filters": {
    "min_valid_warm_count": 1
  },
  "reconstruction_status": "complete"
}
```

Allowed v1 `policy_id` values should remain generic:

- `profile_default`: no non-methodology relaxation.
- `user_directed_sparse_custom`: manual user subset requiring legacy Custom compatibility.
- `depth_required_relaxation`: schedule/depth makes the profile floor structurally impossible.
- `campaign_override`: explicit campaign YAML override affects thresholds.
- `acpm_exception`: separately approved planner/scoring exception, if v1 chooses to allow one.
- `legacy_reconstructed`: historical run reconstructed without full source detail.
- `legacy_unknown`: historical run lacks sufficient evidence.

Recommended ownership details:

- Persist `effective_filter_policy` or `effective_filters_projection` in the campaign-start snapshot lane, not only in reports.
- Keep `RunPlan.filter_overrides` for execution override intent, but add source/reason metadata rather than forcing consumers to infer from `run_mode`.
- Keep `methodology_snapshots.gates_json` unchanged as base gates; do not overwrite it with effective filters.
- ACPM metadata may reference a policy/exception ID, but should not duplicate final threshold values.
- Reports/export/compare/history/explain should read a shared projection helper rather than rebuilding truth from raw fields.

Recommended disclosure rules:

- Report/export should label both base methodology gates and effective filters when they differ.
- Compare should warn or downgrade comparability when effective filters differ, especially for rankability filters such as `min_valid_warm_count`.
- Explain should disclose when a recommendation depended on relaxed thresholds.
- Legacy displays should say `reconstructed`, `inferred`, or `unknown` rather than silently normalizing old runs to current defaults.

## Risks of Getting This Wrong

- Too thin: export/history/compare can misstate which configs were rankable, especially when `min_valid_warm_count` differs.
- Too duplicated: methodology snapshots, run plans, ACPM metadata, and reports can drift into competing scoring truths.
- Wrong owner: ACPM planning metadata could become a hidden scoring system, or report/export could become the de facto authority after the run.
- Run-mode inference drift: future ACPM partial runs could inherit `custom` relaxations or wording accidentally.
- Legacy over-certification: old runs without snapshots could be presented as more auditable than they are.
- Trust mismatch: recommendations may look comparable even when one run used materially looser elimination thresholds.

## Remaining Open Questions

- Should the durable projection live as a new `campaign_start_snapshot` JSON column, inside `run_plan_json`, or in a small adjacent table keyed by campaign ID?
- Should campaign YAML `elimination_overrides` remain allowed for ACPM-generated campaigns in v1, or be blocked unless backed by an explicit exception policy?
- Should effective-filter differences be a hard compare incompatibility, a warning, or severity-graded by key?
- Should `src.score` persist the exact effective filters it applied after scoring as a cross-check, or should run-start provenance be the only durable source?
- How should legacy rows without methodology snapshots be labeled in exported metadata schema versions?

## Recommended Next Investigations

- Define the exact schema location for `effective_filter_policy` / `effective_filters_projection`.
- Investigate compare severity rules for effective-filter differences, including `min_valid_warm_count` versus diagnostic-only thresholds.
- Investigate export metadata schema migration and backward-compatible reader behavior for legacy runs.
- Investigate whether governance validation should enforce the Registry/profile sample-gate relationship or update the current comments/contract.
- Investigate report/explain wording for recommendations produced under relaxed or reconstructed filter policy.

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/scripts/helpers/verify_dev_contract.py`
