# ACPM Filter Policy Persistence, History, and Export Investigation

## Outcome

Recommended v1 design: persist effective filter-policy truth in one new run-start snapshot JSON field, `campaign_start_snapshot.effective_filter_policy_json`, as a sibling to `run_plan_json`. Treat it as the durable history/export authority for final applied filter thresholds and their provenance. Export/history consumers should read it through `src/trust_identity.py`; `metadata.json` should project it, not become its source of truth.

Do not store effective filter-policy truth only in `RunPlan`, `methodology_snapshots`, ACPM planning metadata, or export-only metadata:

- `RunPlan` should keep execution intent and raw execution-origin override inputs.
- `methodology_snapshots.gates_json` should keep profile/default methodology gates.
- ACPM planning metadata should keep planner identity and exception references, not duplicate threshold values.
- Export/history should consume a shared projection with explicit/reconstructed/inferred/unknown labeling.

## Scope / What Was Inspected

Repo guidance:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/scripts/helpers/verify_dev_contract.py`

Primary repo surfaces:

- `src/db.py`
- `src/telemetry.py`
- `src/run_plan.py`
- `src/runner.py`
- `src/score.py`
- `src/trust_identity.py`
- `src/export.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/compare.py`
- `src/explain.py`
- `src/governance.py`
- `configs/profiles/default_throughput_v1.yaml`
- `configs/metrics.yaml`

Relevant prior ACPM investigations:

- `ACPM-effective-filter-provenance-and-surface-disclosure-TARGET-INVESTIGATION.md`
- `ACPM-planner-directed-scoring-filter-policy-TARGET-INVESTIGATION.md`
- `ACPM-history-surface-scope-and-coverage-projection-TARGET-INVESTIGATION.md`

## Current Persistence / Reader Model

Current durable run-start identity:

- `src/db.py` defines `campaign_start_snapshot` with one row per campaign and fields including `campaign_yaml_content`, `baseline_yaml_content`, `baseline_identity_json`, `quantmap_identity_json`, `run_plan_json`, `snapshot_schema_version`, telemetry identity, and execution-environment evidence.
- `src/runner.py` calls `tele.collect_campaign_start_snapshot(...)` with `run_plan_snapshot=run_plan.to_snapshot_dict()`, inserts it once, and preserves an existing row.
- `src/telemetry.py` serializes `run_plan_json` into that snapshot.
- `src/trust_identity.py` reads `campaign_start_snapshot`, parses `run_plan_json`, parses methodology snapshots, and labels source quality such as `snapshot`, `derived_legacy`, `legacy_incomplete`, and `unknown`.

Current methodology persistence:

- `src/db.py` defines `methodology_snapshots` with `weights_json`, `gates_json`, `anchors_json`, source paths/hashes, capture quality, and capture source.
- `src.score._capture_methodology_snapshot()` persists `profile.gate_overrides` as `gates_json`.
- `src.score.score_campaign()` then builds `effective_filters = {**profile.gate_overrides, **(filter_overrides or {})}`.
- `score_campaign()` returns `effective_filters` in memory, but no durable DB field currently stores the final effective filters plus provenance.

Current filter override sources:

- `src/runner.py` injects mode-level `RunPlan.filter_overrides`: `custom` gets `min_valid_warm_count=1`, `quick` gets `min_valid_warm_count=3`, and `standard`/`full` get no mode override.
- `src/runner.py` later merges campaign YAML `elimination_overrides` on top of `RunPlan.filter_overrides`; YAML wins.
- `src/run_plan.py::to_snapshot_dict()` persists only `filter_overrides`, not source/reason per key and not the final methodology-plus-override effective filter set.

Current export/history readers:

- `src/export.py` copies `campaign_start_snapshot` and `methodology_snapshots` into case-file exports.
- `src/export.py::generate_metadata_json()` writes `methodology.eligibility_filters` from `trust_identity.methodology.get("gates")`, which is profile/default gate truth, not necessarily final effective filter truth.
- `src/runner.py::list_campaigns()` uses `campaigns.run_mode`, status fields, scores, artifacts, and execution environment; it does not expose filter-policy provenance.
- `src/report.py`, `src/report_campaign.py`, `src.compare`, and `src.explain` already depend on `trust_identity` for persisted identity, making it the right shared reader seam.

## Ownership and Schema Location Analysis

The first-class effective-filter facts for v1 are:

- `schema_version`
- `policy_id`
- `policy_authority`
- `truth_status`
- `base_gates`
- `base_gates_source`
- `base_methodology_snapshot_id` when available
- `overrides`
- `override_sources`
- `effective_filters`
- `rankability_affecting_keys`
- `legacy_reconstruction_notes`

Recommended ownership:

| Fact | First-class persisted? | Owner |
| --- | --- | --- |
| Profile/default gates | Yes | `methodology_snapshots.gates_json` |
| Raw execution override inputs | Yes | `RunPlan.filter_overrides` in `run_plan_json` |
| Override source/reason per key | Yes | `campaign_start_snapshot.effective_filter_policy_json` |
| Final effective filters used for elimination | Yes | `campaign_start_snapshot.effective_filter_policy_json` |
| ACPM planner identity/selection reason | Yes, separately | ACPM planning metadata |
| ACPM scoring exception reference | Yes, if used | ACPM metadata may reference; effective policy JSON records applied threshold effect |
| Export/history display object | Derived | `metadata.json` / history projection from `trust_identity` |

Safest exact schema location:

- Add a new nullable JSON column to `campaign_start_snapshot`: `effective_filter_policy_json`.
- Keep it adjacent to `run_plan_json`, not embedded inside `run_plan_json`, because it combines methodology gates, execution overrides, campaign YAML overrides, and possible ACPM policy references.
- Do not put it in `methodology_snapshots`, because effective filters are per-run execution/campaign policy, not profile methodology defaults.
- Do not make `metadata.json` authoritative, because export generation can be regenerated and is currently a projection artifact.
- Do not put final filter values in ACPM planning metadata, because non-ACPM runs need the same truth model and ACPM should not become a shadow scoring authority.

One sequencing caveat:

- Current `campaign_start_snapshot` is inserted before scoring, while `methodology_snapshots` are captured during `score_campaign()`.
- V1 should still store the effective filter-policy JSON in the snapshot lineage, but the contract should require it to be computed before measurement/scoring from the same profile/gate inputs that scoring will use.
- If `base_methodology_snapshot_id` is not known at snapshot time, persist the profile/gate identity and later link to the methodology snapshot when available; do not delay all truth until export/report generation.

## Legacy / Back-Compat Reconstruction Policy

Legacy reader behavior should never silently promote inferred facts to explicit truth.

Recommended reconstruction tiers:

| Evidence available | Label | Reader behavior |
| --- | --- | --- |
| `effective_filter_policy_json` exists | `explicit` | Use it as authoritative history/export truth |
| Methodology gates plus `run_plan_json.filter_overrides` plus campaign YAML `elimination_overrides` are available | `reconstructed` | Rebuild effective filters; mark source details reconstructed |
| Methodology gates plus `run_plan_json.filter_overrides` only | `reconstructed_partial` | Rebuild known effective filters; mark campaign-YAML override source unknown/unverified |
| Methodology gates only | `methodology_only` | Show base gates, but do not claim no runtime overrides |
| `campaigns.run_mode` only | `inferred_limited` | Infer only legacy convention, such as Custom likely `min_valid_warm_count=1` and Quick likely `3`; keep base filters unknown unless snapshot gates exist |
| No methodology/run-plan evidence | `unknown` | Export/history should say unknown rather than using current files |

Safe legacy reconstruction:

- `custom` can be treated as evidence that legacy mode policy likely relaxed `min_valid_warm_count` to 1 only when paired with historical code/run-plan evidence.
- `quick` can be treated as evidence that legacy mode policy likely used `min_valid_warm_count` 3 only as limited inference.
- `standard`/`full` do not prove absence of campaign YAML overrides unless the run-start campaign YAML snapshot is available.
- Current profile gates should not be used to backfill old runs unless the reader labels that as current-code inference, not historical truth.

What must remain unknown:

- Per-key override source when only merged overrides survive.
- Whether a missing override field means no override or just pre-snapshot legacy absence.
- Base methodology gates for old runs without `methodology_snapshots`.
- ACPM planner policy provenance for pre-ACPM runs.

## History / Export Projection Policy

History/export consumers need a compact projection, not a second methodology system.

Minimum projection shape:

```json
{
  "truth_status": "explicit",
  "policy_id": "profile_default",
  "policy_authority": "execution",
  "base_gates_source": "methodology_snapshot",
  "base_methodology_snapshot_id": 123,
  "effective_filters": {
    "min_valid_warm_count": 3
  },
  "overrides": {},
  "override_sources": {},
  "rankability_affecting_keys": ["min_valid_warm_count"],
  "legacy_reconstruction_notes": []
}
```

Projection rules:

- `metadata.json` should include this object under a distinct key such as `filter_policy`, not overload `methodology.eligibility_filters`.
- `methodology.eligibility_filters` may continue to expose base profile gates for compatibility, but export should make clear that `filter_policy.effective_filters` is the run-effective threshold set.
- `provenance_sources` should gain a filter-policy source label so downstream consumers know whether the object is explicit, reconstructed, inferred, or unknown.
- `quantmap list` / history summaries should only need `policy_id` and `truth_status`, not full threshold maps.
- Case-file exports already copy `campaign_start_snapshot` and `methodology_snapshots`; adding one snapshot JSON field keeps exported DBs reconstructable without depending on regenerated `metadata.json`.

## Recommended v1 Persistence Model

Persist these as first-class truth:

- In `methodology_snapshots.gates_json`: base profile/default methodology gates only.
- In `run_plan_json`: raw execution-intent `filter_overrides` and resolved run scope/schedule.
- In new `campaign_start_snapshot.effective_filter_policy_json`: final filter-policy projection with effective filters, source per override, policy authority, and truth status.
- In ACPM planning metadata: planner identity, selection rationale, and any exception/policy reference; no duplicated threshold map.
- In `metadata.json`: export projection copied from `trust_identity`, not independently recomputed.

Recommended v1 `policy_id` values:

- `profile_default`
- `user_directed_sparse_custom`
- `depth_required_relaxation`
- `campaign_override`
- `acpm_exception`
- `legacy_reconstructed`
- `legacy_unknown`

Recommended v1 authorities:

- `methodology_profile`
- `execution_mode`
- `campaign_yaml`
- `user_directed_scope`
- `planner_policy`
- `legacy_reader`
- `unknown`

This model keeps the durable truth small, queryable through the existing snapshot-first trust seam, and reusable by export/history without forcing every consumer to parse mode semantics.

## Recommended v1 Labeling Model

Use two separate labels:

- `truth_status`: how well the repo can prove the effective filter policy.
- `policy_id`: what policy class the effective filters represent.

Recommended `truth_status` values:

- `explicit`: v1+ run with first-class persisted effective filter-policy JSON.
- `reconstructed`: all effective thresholds can be rebuilt from persisted gates and overrides, but the v1 JSON was absent.
- `reconstructed_partial`: some thresholds or sources can be rebuilt; source details are incomplete.
- `methodology_only`: only base methodology gates are known.
- `inferred_limited`: legacy convention supports a bounded inference, usually from `run_mode`.
- `unknown`: effective filters cannot be safely reconstructed.

Recommended history/export wording:

- Explicit: "Effective filter policy captured at run start."
- Reconstructed: "Effective filter policy reconstructed from persisted methodology and run-plan/campaign evidence."
- Reconstructed partial: "Effective filter policy partially reconstructed; some override provenance is unavailable."
- Methodology only: "Base methodology gates known; runtime override evidence unavailable."
- Inferred limited: "Filter policy inferred from legacy mode convention; not authoritative."
- Unknown: "Effective filter policy unavailable for this legacy run."

## Risks of Getting This Wrong

- If too little is persisted, export/history consumers will guess from `run_mode`, hiding differences such as `min_valid_warm_count=1` versus `3`.
- If too much is duplicated, methodology snapshots, run plans, ACPM metadata, and metadata exports can drift into competing filter truths.
- If stored in `methodology_snapshots`, per-run execution/campaign overrides become mislabeled as methodology defaults.
- If stored only in ACPM metadata, non-ACPM runs lack equivalent provenance and ACPM becomes a shadow scoring authority.
- If stored only in `metadata.json`, regenerated exports can become the source of truth after the fact.
- If legacy rows are over-labeled, old runs will look more auditable than their persisted evidence supports.

## Remaining Open Questions

- Should `effective_filter_policy_json` be nullable-only for new runs, or should migrations backfill `legacy_unknown` rows?
- Should the scorer also persist a post-scoring checksum of the applied `effective_filters` to detect mismatch with run-start policy?
- Should `campaign_override` be a standalone `policy_id` or a modifier layered on another policy class?
- Should ACPM-generated campaign YAML be allowed to contain `elimination_overrides` in v1?
- Should history tables ever index `truth_status` / `policy_id`, or is JSON-only sufficient for v1?

## Recommended Next Investigations

- Define the exact JSON schema for `campaign_start_snapshot.effective_filter_policy_json`.
- Investigate whether the methodology resolver can expose base gates before measurement without changing scoring semantics.
- Investigate export metadata versioning for adding `filter_policy` while preserving existing `methodology.eligibility_filters`.
- Investigate history/list display constraints for compact `policy_id` and `truth_status` labels.
- Investigate whether governance should reconcile the active `min_valid_warm_count=3` profile gate with Registry `min_sample_gate=10` and stale code comments.

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/scripts/helpers/verify_dev_contract.py`
