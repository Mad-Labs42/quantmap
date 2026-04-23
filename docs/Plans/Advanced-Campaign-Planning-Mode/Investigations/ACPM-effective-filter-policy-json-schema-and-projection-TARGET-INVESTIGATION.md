# ACPM Effective Filter Policy JSON Schema and Projection Target Investigation

Status: investigation-only

Scope: exact v1 contract for `campaign_start_snapshot.effective_filter_policy_json`

## Outcome

Recommended v1 contract: add one nullable snapshot JSON column, `campaign_start_snapshot.effective_filter_policy_json`, with a small explicit schema that records final effective filter thresholds, provenance layers, truth status, and a stable hash. Treat it as the durable history/export authority for run-effective filters. `metadata.json`, history/list output, report/explain, and compare should consume a `trust_identity` projection from this field, not recompute their own truth.

Do not reopen the physical-home decision. The live repo supports the prior recommendation: `campaign_start_snapshot.run_plan_json` is already the snapshot lane for run intent, `methodology_snapshots.gates_json` is methodology truth, and `src/trust_identity.py` is the shared reader seam.

Key v1 decisions:

- `campaign_override` should be a modifier/layer, not a standalone `policy_id`.
- Include a mandatory canonical hash for the intended `effective_filters`.
- Include an optional post-scoring confirmation object; it solves the specific risk that run-start policy and `score_campaign()` output drift.
- Keep `metadata.json.methodology.eligibility_filters` as base methodology gates for compatibility, and add `metadata.json.filter_policy` as the run-effective projection.
- Legacy rows should stay null in storage; readers should synthesize `inferred_limited` or `unknown` projections without backfilling fake certainty.
- ACPM-generated YAML should not be allowed to carry `elimination_overrides` in v1 except through a separately governed `acpm_exception`.
- The `min_valid_warm_count` 3-vs-10 drift is not a schema blocker, but it is governance debt that should block approving new ACPM relaxations until reconciled.

## Scope / What Was Inspected

Required repo-agent surfaces:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/policies/boundaries.md`
- `.agent/scripts/helpers/verify_dev_contract.py`

Required prior investigations:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planner-directed-scoring-filter-policy-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-effective-filter-provenance-and-surface-disclosure-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-filter-policy-persistence-history-and-export-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-history-surface-scope-and-coverage-projection-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-legacy-custom-mode-compatibility-TARGET-INVESTIGATION.md`

Repo surfaces:

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

## Current State / Relevant Live Behavior

Current persistence split:

- `src/db.py` has `campaign_start_snapshot.run_plan_json`, but no `effective_filter_policy_json`.
- `src/db.py` has `methodology_snapshots.gates_json`, which is base methodology gate truth, not final run-effective filters.
- `src/telemetry.py::collect_campaign_start_snapshot()` serializes `run_plan_json` into the start snapshot.
- `src/trust_identity.py` loads `campaign_start_snapshot`, parses `run_plan_json`, parses methodology gates, and labels legacy source quality; it is the right shared reader seam.

Current filter/scoring path:

- `src/run_plan.py::resolve_run_mode()` maps `--mode quick` to `quick`, `--mode standard` to `standard`, any `--values` subset to `custom`, and default to `full`.
- `src/run_plan.py::RunPlan.to_snapshot_dict()` persists `filter_overrides`, but not source/reason per key.
- `src/runner.py` injects mode overrides: `custom` gets `{"min_valid_warm_count": 1}`; `quick` gets `{"min_valid_warm_count": 3}`; `standard` and `full` use profile gates unchanged.
- `src/runner.py` validates campaign YAML `elimination_overrides` keys, then later merges YAML overrides on top of mode/run-plan overrides; YAML wins.
- `src/score.py::score_campaign()` merges `profile.gate_overrides` with caller `filter_overrides` to produce `effective_filters`, applies them, and returns them in memory.
- No durable row currently records final `effective_filters` plus source/reason per override.

Current disclosure gaps:

- `src/export.py::generate_metadata_json()` writes `methodology.eligibility_filters` from `trust_identity.methodology.gates`, which can differ from run-effective filters.
- `src/report.py` can show `RunPlan.filter_overrides`, but not final merged effective filters and provenance.
- `src/report_campaign.py` displays `scores_result.effective_filters` when live, otherwise falls back to methodology gates and a stale display default of `10` for `min_valid_warm_count`.
- `src/compare.py` compares methodology and elimination outcomes, but not effective filter policy.
- `src/explain.py` uses `trust_identity` for persisted context, but has no effective-filter projection yet.

Important policy drift:

- Live `ELIMINATION_FILTERS` resolves `min_valid_warm_count` to `3.0` from `configs/profiles/default_throughput_v1.yaml`.
- `src/score.py` header text and `src/report_campaign.py` fallback wording still imply `10`.
- `src/governance.py` comments say the min sample gate cannot relax below Registry minimums, but current validation does not enforce that comparison.

## Recommended v1 JSON Schema

Persist this JSON in `campaign_start_snapshot.effective_filter_policy_json`. It is the authoritative run-effective filter policy record for v1+ rows.

```json
{
  "schema": "quantmap.effective_filter_policy",
  "schema_version": 1,
  "truth_status": "explicit",
  "policy_id": "profile_default",
  "policy_modifiers": [],
  "final_policy_authority": "methodology_profile",
  "authority_chain": ["methodology_profile"],
  "created_by": "runner",
  "created_at_utc": "2026-04-22T00:00:00Z",
  "base_gates_source": {
    "source": "methodology_snapshot",
    "snapshot_id": 123,
    "profile_name": "default_throughput_v1",
    "profile_version": "v1",
    "methodology_version": "1.0",
    "capture_quality": "complete",
    "capture_source": "score_campaign:initial_scoring"
  },
  "base_gates": {
    "max_cv": 0.05,
    "max_thermal_events": 0.0,
    "max_outliers": 3.0,
    "max_warm_ttft_p90_ms": 500.0,
    "min_success_rate": 0.9,
    "min_warm_tg_p10": 7.0,
    "min_valid_warm_count": 3.0
  },
  "override_layers": [],
  "effective_filters": {
    "max_cv": 0.05,
    "max_thermal_events": 0.0,
    "max_outliers": 3.0,
    "max_warm_ttft_p90_ms": 500.0,
    "min_success_rate": 0.9,
    "min_warm_tg_p10": 7.0,
    "min_valid_warm_count": 3.0
  },
  "changed_filter_keys": [],
  "rankability_affecting_keys": [],
  "effective_filters_sha256": "canonical-json-sha256",
  "scoring_confirmation": {
    "status": "not_confirmed",
    "score_effective_filters_sha256": null,
    "confirmed_at_utc": null
  },
  "legacy_reader": {
    "label": null,
    "inferred_from": [],
    "notes": []
  }
}
```

Override layer shape:

```json
{
  "layer_id": "mode_custom_sparse_floor",
  "authority": "execution_mode",
  "source": "run_plan.filter_overrides",
  "source_id": "custom",
  "policy_effect": "user_directed_sparse_custom",
  "overrides": {
    "min_valid_warm_count": 1
  },
  "reason": "legacy custom user-directed sparse subset compatibility"
}
```

Allowed v1 enum values:

| Field | v1 values |
| --- | --- |
| `truth_status` | `explicit`, `reconstructed`, `inferred_limited`, `unknown` |
| `policy_id` | `profile_default`, `user_directed_sparse_custom`, `depth_required_relaxation`, `acpm_exception`, `legacy_reconstructed`, `legacy_unknown` |
| `policy_modifiers` | empty list or one or more of `campaign_override`, `acpm_exception_reference` |
| `final_policy_authority` | `methodology_profile`, `execution_mode`, `campaign_yaml`, `acpm_governed_exception`, `legacy_reader`, `unknown` |
| `authority_chain` | ordered subset of `methodology_profile`, `execution_mode`, `campaign_yaml`, `acpm_governed_exception`, `legacy_reader`, `unknown` |
| `override_layers[].policy_effect` | `user_directed_sparse_custom`, `depth_required_relaxation`, `campaign_override`, `acpm_exception` |
| `scoring_confirmation.status` | `not_confirmed`, `confirmed`, `mismatch`, `unavailable` |
| `legacy_reader.label` | null, `legacy_reconstructed`, `legacy_inferred_limited`, `legacy_unknown` |

## Field-by-field ownership table

| Field | Ownership class | Owner / source | Notes |
| --- | --- | --- | --- |
| `schema`, `schema_version` | Reader contract | `campaign_start_snapshot.effective_filter_policy_json` | Enables strict v1 parsing without guessing. |
| `truth_status` | Legacy-reader label | Writer for v1; `trust_identity` for null legacy rows | Never promote inferred legacy facts to explicit. |
| `policy_id` | Policy/provenance | Runner or legacy reader projection | Classifies why the effective filter policy exists. |
| `policy_modifiers` | Policy/provenance | Runner from YAML/planner inputs | `campaign_override` belongs here, not as primary policy. |
| `final_policy_authority` | Authority truth | Runner or legacy reader | Identifies the final layer that changed or confirmed thresholds. |
| `authority_chain` | Authority truth | Runner or legacy reader | Ordered source chain from base methodology to final policy. |
| `created_by`, `created_at_utc` | Provenance | Runner | Audit metadata only. |
| `base_gates_source` | Methodology truth pointer | Methodology snapshot reader | Points to `methodology_snapshots`, does not replace it. |
| `base_gates` | Methodology truth copy | Methodology snapshot gates at run start | Copied for audit/export stability; source remains methodology snapshot. |
| `override_layers` | Execution/provenance | Runner from run mode, YAML, governed ACPM exception | Records source, reason, and merge order. |
| `effective_filters` | Derived methodology-plus-execution truth | Runner from base gates plus override layers | The final thresholds used or intended for elimination. |
| `changed_filter_keys` | Derived disclosure | Runner | Keys whose effective values differ from base gates. |
| `rankability_affecting_keys` | Derived disclosure | Runner | In v1, include changed elimination keys that can change pass/eliminate/rankable populations. |
| `effective_filters_sha256` | Integrity/disclosure | Runner | Canonical JSON hash of `effective_filters`; useful for compare/export and confirmation. |
| `scoring_confirmation` | Optional post-score confirmation | Runner/scoring caller | Cross-check only; not a separate authority. |
| `legacy_reader` | Legacy-reader labels | `trust_identity` projection for null or reconstructed rows | Keeps old runs interpretable without fake certainty. |

## Required vs optional fields

Mandatory for new v1 explicit rows:

- `schema`
- `schema_version`
- `truth_status`
- `policy_id`
- `policy_modifiers`
- `final_policy_authority`
- `authority_chain`
- `created_by`
- `created_at_utc`
- `base_gates_source`
- `base_gates`
- `override_layers`
- `effective_filters`
- `changed_filter_keys`
- `rankability_affecting_keys`
- `effective_filters_sha256`
- `legacy_reader`

Conditionally required:

- `scoring_confirmation` should be present in the schema, but may be `{"status": "not_confirmed", ...}` until the post-scoring caller confirms it.
- `base_gates_source.snapshot_id` is required when the source is `methodology_snapshot`; it may be null for `legacy_reader` or `unknown`.
- `override_layers` is an empty list when no non-methodology layer exists.
- `policy_modifiers` is an empty list when no modifier applies.

Optional/nullable:

- `base_gates_source.profile_version`
- `base_gates_source.methodology_version`
- `base_gates_source.capture_source`
- `scoring_confirmation.score_effective_filters_sha256`
- `scoring_confirmation.confirmed_at_utc`
- `legacy_reader.label`
- `legacy_reader.inferred_from`
- `legacy_reader.notes`

Mandatory for synthesized legacy projections returned by readers, but not physically backfilled into old rows:

- `truth_status`
- `policy_id`
- `policy_modifiers`
- `final_policy_authority`
- `authority_chain`
- `effective_filters` as object or null
- `effective_filters_sha256` as string or null
- `legacy_reader`

## Policy ID / truth-status / provenance model

`policy_id` should classify the primary reason the effective filter policy exists:

- `profile_default`: base methodology gates are used unchanged.
- `user_directed_sparse_custom`: legacy/manual Custom compatibility changed thresholds for user-directed sparse subsets.
- `depth_required_relaxation`: schedule/depth makes the profile floor structurally impossible or intentionally lower-confidence.
- `acpm_exception`: separately governed ACPM exception changed thresholds.
- `legacy_reconstructed`: old row reconstructed from persisted evidence but without v1 explicit JSON.
- `legacy_unknown`: old row lacks enough evidence to reconstruct.

`campaign_override` should not be a standalone `policy_id`. It is a modifier and an `override_layers[]` entry because campaign YAML can layer on top of any primary policy. A full run with YAML override should be `policy_id=profile_default`, `policy_modifiers=["campaign_override"]`, and `final_policy_authority=campaign_yaml`. A custom run with YAML override should be `policy_id=user_directed_sparse_custom`, `policy_modifiers=["campaign_override"]`, and include both layers in merge order.

`truth_status` should describe evidence quality:

- `explicit`: v1+ row has first-class policy JSON captured by the runner.
- `reconstructed`: enough persisted historical evidence exists to rebuild effective filters without live defaults.
- `inferred_limited`: only bounded convention evidence exists, such as legacy `run_mode=custom` implying likely `min_valid_warm_count=1`.
- `unknown`: effective policy cannot be safely reconstructed.

Planner identity remains separate. ACPM planning metadata may reference an approved exception ID, planner identity, or selection rationale, but final filter values live in `effective_filter_policy_json`.

Recommendation truth remains separate. This schema says which filters made candidates pass/eliminate/rankable; it does not certify a recommendation as valid, complete, or deployment-ready.

## Legacy/back-compat behavior

Use nullable-only rollout for existing rows. Do not run a migration that writes `legacy_unknown` into every old `campaign_start_snapshot` row. A null `effective_filter_policy_json` should mean "not captured in this schema"; `trust_identity` should synthesize the reader projection when needed.

Safe legacy reconstruction tiers:

| Evidence available | Reader projection |
| --- | --- |
| v1 JSON present | `truth_status=explicit`; use JSON as authority. |
| Methodology snapshot gates plus `run_plan_json.filter_overrides` present | `truth_status=reconstructed`; compute effective filters from persisted gates plus persisted overrides; label missing YAML provenance if campaign YAML snapshot cannot prove absence/presence. |
| `run_plan_json` absent, but `campaigns.run_mode` present | `truth_status=inferred_limited`; infer only legacy convention labels such as likely Custom or Quick sample-floor behavior; do not claim full threshold map unless base gates are persisted. |
| No methodology/run-plan evidence | `truth_status=unknown`; expose null effective filters and explicit unknown wording. |

Do not use current live profile gates to backfill old runs as historical truth. At most, current-code inference may be shown as `inferred_limited` with a note that it is not authoritative.

## Metadata/export projection recommendation

`metadata.json` should project the shared truth, not own it.

Keep existing `methodology.eligibility_filters` for compatibility, but define it as base methodology/profile gates. Add a distinct top-level `filter_policy` object for run-effective filters:

```json
{
  "methodology": {
    "eligibility_filters": {
      "min_valid_warm_count": 3.0
    }
  },
  "filter_policy": {
    "truth_status": "explicit",
    "policy_id": "profile_default",
    "policy_modifiers": [],
    "final_policy_authority": "methodology_profile",
    "effective_filters": {
      "min_valid_warm_count": 3.0
    },
    "changed_filter_keys": [],
    "rankability_affecting_keys": [],
    "effective_filters_sha256": "canonical-json-sha256",
    "scoring_confirmation_status": "confirmed",
    "source": "campaign_start_snapshot.effective_filter_policy_json"
  },
  "provenance_sources": {
    "filter_policy": "snapshot"
  }
}
```

Projection rules:

- If `filter_policy.effective_filters` differs from `methodology.eligibility_filters`, export should expose both rather than overwriting either.
- If no v1 JSON exists, `filter_policy.source` should be `legacy_reconstructed`, `legacy_inferred_limited`, or `unknown`.
- `metadata.json` must not derive filters directly from `run_mode`; it should use the same `trust_identity` helper as report/history/compare/explain.
- Case-file exports already copy `campaign_start_snapshot` and `methodology_snapshots`; the exported DB remains authoritative even if `metadata.json` is regenerated.

## History/list projection recommendation

History/list does not need the full threshold map by default. It needs a compact, stable projection so users do not have to guess whether `run_mode` is the whole story.

Minimum v1 projection:

| Field | Purpose |
| --- | --- |
| `filter_policy_id` | Compact policy class, such as `profile_default` or `user_directed_sparse_custom`. |
| `filter_policy_truth_status` | `explicit`, `reconstructed`, `inferred_limited`, or `unknown`. |
| `filter_policy_modifiers` | Compact list, especially `campaign_override`. |
| `filter_policy_authority` | Final authority, such as `methodology_profile`, `execution_mode`, or `campaign_yaml`. |
| `effective_filters_sha256` | Optional compact identity for compare/export drill-down. |
| `filter_policy_warning` | Only when `truth_status` is not `explicit`, when confirmation is `mismatch`, or when non-default filters materially affect rankability. |

Display guidance:

- Default list output can show only policy ID and truth status when space is tight.
- Detailed history/export views should include changed keys, especially `min_valid_warm_count`.
- Do not display `custom` as a synonym for relaxed filters once ACPM exists; `custom` remains execution/presentation mode for manual user-directed subsets.

## Governance implications

ACPM-generated YAML `elimination_overrides` should be forbidden in v1 unless a separately governed `acpm_exception` explicitly authorizes the threshold change. Current runner behavior lets YAML win over mode overrides, which is acceptable for legacy/manual campaigns but too implicit for planner-authored scoring policy. ACPM must not smuggle methodology changes through campaign YAML.

Any `acpm_exception` should have:

- An exception ID or policy reference in ACPM planning metadata.
- A concrete `override_layers[]` entry in `effective_filter_policy_json`.
- Disclosure in report/export/history/explain that the run used non-default or exception filters.
- Compare behavior that flags materially different effective filter hashes or changed rankability keys.

`min_valid_warm_count` drift:

- This schema can safely capture the actual live value (`3`) and any override source, so the drift does not block adding the contract.
- The drift is governance debt because code comments, report fallback wording, profile gates, and Registry `min_sample_gate` semantics do not fully agree.
- Treat it as blocking for approving new ACPM relaxations or claiming a stricter sample-floor methodology, not as a blocker for persistence/projection.

## Risks of getting this wrong

- If `metadata.json` becomes authority, regenerated exports can rewrite history after the run.
- If ACPM metadata owns filter values, ACPM becomes a shadow scoring/methodology system.
- If `run_mode` remains the only source, ACPM partial scope can inherit or appear to inherit legacy `custom` relaxations.
- If `campaign_override` is a standalone `policy_id`, consumers lose the underlying base policy and cannot distinguish full+YAML from custom+YAML or ACPM-exception+YAML.
- If no post-score confirmation exists, a bug could persist one intended threshold map while `score_campaign()` applied another.
- If legacy rows are backfilled as explicit, old runs will look more auditable than the persisted evidence supports.
- If the 3-vs-10 `min_valid_warm_count` drift is ignored, reports can disclose one validity floor while scoring used another.

## Remaining open questions

- Should `effective_filters_sha256` hash only `effective_filters`, or include `schema_version` and normalized numeric formatting in the hash envelope?
- Which compare severity should apply when `effective_filters_sha256` differs but only non-winning candidates were affected?
- Should `rankability_affecting_keys` be all changed elimination keys in v1, or a smaller classified subset once gates are typed more formally?
- Should legacy reader projections be exposed through a new `TrustIdentity.filter_policy` property or a standalone helper imported by `trust_identity` consumers?

## Recommended next step

Draft a bounded implementation plan and test matrix for adding `campaign_start_snapshot.effective_filter_policy_json`, the `trust_identity` projection helper, metadata/history projections, legacy-reader cases, and the optional post-scoring confirmation check.

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/policies/boundaries.md`
- `.agent/scripts/helpers/verify_dev_contract.py`
