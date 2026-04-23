# ACPM Recommendation Record Contract Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 recommendation outcome contract only

## Outcome

Recommended v1 contract:

- persist a small recommendation record after execution and scoring complete
- make it a post-scoring outcome record, not a second results table and not a shadow report
- let it own:
  - recommendation status
  - the leading config reference
  - the actually recommended config reference, if any
  - compact supporting evidence
  - compact caveat/reason codes
  - references to execution and methodology truth
  - a variable-only machine-handoff projection
- do not let it own:
  - execution truth
  - planner metadata
  - full methodology truth
  - full ranked lists or finalist tables
  - narrative explanation text

Recommended top-level shape:

```json
{
  "schema_version": "acpm-recommendation-record-v1",
  "recommendation_policy_id": "acpm_recommendation_v1",
  "recommendation_policy_version": "1.0",
  "recorded_at_utc": "2026-04-22T16:00:00Z",
  "recommendation_status": "strong_provisional_leader",
  "selection_basis": "score_winner",
  "leading_config_id": "NGL_sweep__quick_40",
  "recommended_config_id": "NGL_sweep__quick_40",
  "source_refs": {
    "effective_campaign_id": "NGL_sweep__quick",
    "methodology_snapshot_id": 123
  },
  "caveat_codes": [
    "quick_mode_low_density",
    "full_run_confirmation_recommended"
  ],
  "evidence_snapshot": {
    "composite_score": 0.812,
    "warm_tg_median": 14.21,
    "warm_tg_p10": 13.74,
    "warm_ttft_median_ms": 241,
    "warm_tg_cv": 0.028,
    "valid_warm_request_count": 4,
    "thermal_events": 0
  },
  "machine_handoff": {
    "format": "llama_cpp_variables_v1",
    "variables": {
      "n_gpu_layers": 40
    }
  }
}
```

This is the smallest durable shape that can support:

- a human-facing recommendation statement
- export/history persistence
- explain/audit use
- a thin machine-facing variable handoff

without becoming a second report or a second scoring database.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/score.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/explain.py`
- `src/compare.py`
- `src/report_compare.py`
- `src/run_plan.py`
- `src/trust_identity.py`

Supporting docs inspected:

- `docs/Design Memo's/Advanced-Campaign-Planning-Mode-ADR/Adaptive-Campaign-Planning-Mode-v1-Design.md`
- `docs/AUDITS/4-11/Results-4-11/Audit-6.md`
- `docs/MVP/quantmap_mvp_decisions_and_reporting_contract.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-blast-radius-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-plan-contract-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planning-metadata-schema-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `.agent/README.md`
- `.agent/policies/architecture.md`

Validation used:

- targeted source inspection only
- no product-code changes
- no broad validation theater; this pass is contract shape and ownership mapping

## Current Recommendation / Winner / Export Constraints

### 1. The repo already has winner truth, but not recommendation-record truth

`src/score.py` already persists:

- `is_score_winner`
- `is_highest_tg`
- Pareto status
- composite score
- rank
- key stats

It also returns a `scores_result` with:

- `winner`
- `highest_tg`
- `pareto_frontier`
- `effective_filters`
- methodology references

Implication:

- ACPM does not need to persist another ranked table
- the recommendation record should point at the selected outcome and carry only the compact evidence needed to justify the recommendation statement

### 2. Report surfaces already turn winners into recommendation-like statements

`src/report.py` currently does several recommendation-adjacent things:

- changes language by run mode
  - `best tested config`
  - `top config`
  - `validated optimal`
- adds caution language for quick, standard, and custom scope
- emits a production command for the winning config
- includes specialized recommendation logic for `n_gpu_layers` campaigns

Implication:

- recommendation meaning is currently scattered between score winner selection and report interpretation
- ACPM needs a persistent recommendation outcome layer so these statements are reconstructable later

### 3. Explain surfaces operate on winner + caveat style, not on a recommendation record

`src/explain.py` currently:

- loads the winner from `scores`
- derives confidence heuristically
- summarizes eliminations and trust evidence

Implication:

- explain surfaces would benefit from a compact recommendation status and reason-code layer
- they do not need a verbose narrative stored in the record

### 4. Export already has structured provenance and ranking, but no recommendation object

`metadata.json` currently includes:

- methodology
- ranking
- environment summary
- provenance sources

It does not include:

- recommendation strength/status
- compact recommendation caveats
- a machine-facing handoff projection

Implication:

- a recommendation record can be exported cleanly as a structured sibling to methodology and ranking
- it should not replace those sections

### 5. Compare surfaces compare winners, not recommendation-grade statements

`src/compare.py` and `src/report_compare.py` currently compare:

- winner shifts
- shared config deltas
- methodology compatibility
- environment deltas

Implication:

- a recommendation record should give compare/audit surfaces a stable outcome object to compare
- they do not need full finalist or rejected-candidate lists in v1

### 6. Current machine-usable output is only adjacent, not authoritative

The repo’s current nearest machine-facing surfaces are:

- `configs.config_values_json`
- `configs.resolved_command`
- the report production-command section

These are not ACPM recommendation records.

Implication:

- the future llama.cpp variables file should not be the recommendation record itself
- it should be a thin projection derived from a recommendation-owned machine-handoff block

## Candidate Contract Models Considered

### 1. Bare winner pointer

Meaning:

- persist only `winner_config_id`

Assessment:

- too small

Why:

- cannot express provisional vs validated vs insufficient evidence
- cannot support machine handoff cleanly
- cannot support explain/history/audit use without recomputing meaning from many other surfaces

### 2. Full shadow report / shadow results database

Meaning:

- persist winner, finalists, rejected finalists, long narrative reasons, many metrics, full commands, maybe full ranked rows

Assessment:

- reject

Why:

- duplicates `scores`, reports, and export
- high drift risk
- wrong ownership boundary

### 3. Recommendation status + subject config + compact evidence + machine projection

Meaning:

- persist the recommendation-grade statement ACPM is allowed to make
- keep only compact evidence and caveat codes
- include a machine-handoff projection block

Assessment:

- best v1 fit

Why:

- enough for human, machine, export, explain, and audit consumers
- small enough to stay stable
- avoids duplicating execution, methodology, and full ranking truth

### 4. Machine handoff only

Meaning:

- make the llama.cpp variable file the recommendation record

Assessment:

- reject

Why:

- too lossy for human/explain/export/audit use
- no place for recommendation status, caveats, or provenance refs
- encourages the machine artifact to become the primary truth

## Recommended v1 Recommendation-Record Contract

### Recommended fields

`schema_version`

- required
- stable reader/writer compatibility

`recommendation_policy_id`

- required
- identifies the recommendation semantics policy, which is distinct from planner policy and methodology profile

`recommendation_policy_version`

- required
- preserves meaning if recommendation status rules evolve

`recorded_at_utc`

- required
- makes the outcome a real historical record

`recommendation_status`

- required
- recommended stable enum values:
  - `strong_provisional_leader`
  - `best_validated_config`
  - `insufficient_evidence_to_recommend`
  - `needs_deeper_validation`

This is the primary “what statement are we allowed to make?” field.

`selection_basis`

- required
- v1 value should be explicit, such as `score_winner`
- avoids hiding how the lead candidate was chosen

`leading_config_id`

- required, nullable
- the config that led under the current methodology/scoring result
- needed even when a recommendation is withheld

`recommended_config_id`

- required, nullable
- the config ACPM is actually willing to recommend
- may equal `leading_config_id`
- should be `null` when status is `insufficient_evidence_to_recommend` or similar non-recommending outcomes

`source_refs`

- required
- minimum v1 fields:
  - `effective_campaign_id`
  - `methodology_snapshot_id`

These anchor the record back to execution truth and methodology truth.

`caveat_codes`

- required
- terse stable codes, not prose
- examples:
  - `tested_subset_only`
  - `quick_mode_low_density`
  - `standard_mode_development_grade`
  - `full_run_confirmation_recommended`
  - `winner_not_highest_tg`
  - `methodology_evidence_incomplete`
  - `telemetry_degraded`
  - `high_variance`
  - `noise_band_competition`
  - `thermal_risk`

These preserve tentative-suggestion semantics without storing a whole explanation essay.

`evidence_snapshot`

- required when `leading_config_id` is present
- minimum recommended fields:
  - `composite_score`
  - `warm_tg_median`
  - `warm_tg_p10`
  - `warm_ttft_median_ms`
  - `warm_tg_cv`
  - `valid_warm_request_count`
  - `thermal_events`

This is the smallest useful evidence block because it matches the repo’s current winner and caution language more closely than a bare config ID does.

`machine_handoff`

- required, nullable
- recommended shape:

```json
"machine_handoff": {
  "format": "llama_cpp_variables_v1",
  "variables": {
    "n_gpu_layers": 40
  }
}
```

- `null` when there is no deployable recommendation to hand off

### Why this is the smallest durable shape

It preserves:

- recommendation strength/status
- separation between a leading config and a truly recommended config
- enough evidence to explain the recommendation briefly
- enough structure to derive a machine artifact

without storing:

- full rankings
- finalist sets
- narrative report text
- full command lines
- planner internals

## What Belongs Here vs in `RunPlan` vs ACPM Planning Metadata vs Methodology Snapshots

### Belongs in the recommendation record

- recommendation status
- leading config ID
- recommended config ID
- selection basis
- compact caveat codes
- compact evidence snapshot
- source references to run/methodology truth
- variable-only machine-handoff projection

### Belongs in `RunPlan`

- actual selected scope
- schedule
- execution paths
- scope authority
- execution-affecting overrides
- coverage truth

### Belongs in ACPM planning metadata

- planner identity/version
- planner profile/policy identity
- repeat-tier label
- planning-time narrowing provenance

### Belongs in methodology snapshots

- trust-bearing profile identity
- weights
- gates
- anchors
- methodology version
- methodology capture quality/source

### Belongs in raw campaign results / existing artifacts

- full ranked config list
- eliminated config list
- raw stats tables
- background context/evidence
- long narrative explanations
- production command details

## Machine-Handoff Relationship

Recommended v1 policy:

- the machine-facing llama.cpp variables file should be a projection derived from the recommendation record
- it should not be the recommendation record itself

Why:

- the machine file is intentionally thin
- the recommendation record needs status, caveats, and provenance refs that the machine file should not carry
- reports and exports need more than the machine file

Recommended ownership:

- recommendation record owns the authoritative variable-only handoff projection
- the actual handoff file is a serializer output of that projection block

This avoids:

- scraping report markdown
- over-trusting raw `config_values_json`
- forcing the machine artifact to become the primary recommendation truth

## Risks of Getting This Wrong

### 1. Building a shadow report

If the record stores long explanations, finalist discussions, or command blocks, it will drift from reports and become a second narrative surface.

### 2. Building a shadow results database

If the record stores full rankings, rejected finalists, or many per-config metrics, it duplicates `scores` and `metadata.json`.

### 3. Collapsing winner truth into recommendation truth

If the record stores only one `winner_config_id`, the repo cannot distinguish:

- the leading config
- the actually recommended config
- cases where no recommendation should be made

### 4. Letting machine-handoff shape dominate the record

If the handoff file becomes the recommendation record, human/audit/export semantics get lost.

### 5. Duplicating methodology or planning truth

If the record copies weights, gates, profile/policy details, or run-plan scope fields, ownership becomes confused and drift risk rises.

## Downstream Implementation Consequences

### 1. Recommendation semantics become first-class and reconstructable

The repo would finally have a durable place for:

- provisional vs validated vs withheld recommendation states

instead of forcing reports to invent that meaning transiently.

### 2. Reports and explain surfaces can consume a compact status object

They would no longer need to reconstruct all recommendation semantics ad hoc from winners plus run mode alone.

### 3. Export/history gains a clean structured object

`metadata.json` and future bundle/export surfaces can include recommendation outcome separately from methodology and ranking.

### 4. Compare/audit gets a stable comparison target

Future compare logic can compare:

- recommendation status
- leading vs recommended config changes
- caveat-code shifts

without storing whole report text.

## Questions Answered in This Pass

### 1. What recommendation-grade facts need to survive after execution/scoring for v1?

Need to survive:

- allowed recommendation statement
- leading config
- actual recommended config if any
- compact evidence and caveats
- refs to execution/methodology truth
- variable-only machine-handoff projection

### 2. Which of those facts are needed for machine handoff, human artifacts, explain, export/history, and audit/compare?

Machine handoff:

- recommended config presence
- variable-only handoff projection

Human artifacts:

- status
- leading/recommended config distinction
- caveat codes
- compact evidence snapshot

Explain:

- status
- caveat codes
- compact evidence snapshot

Export/history:

- full recommendation record
- source refs

Audit/compare:

- status
- leading/recommended config IDs
- caveat-code deltas
- methodology ref

### 3. What should definitely not live in the recommendation record?

Not here:

- `RunPlan` execution truth
- ACPM planning metadata
- weights / gates / anchors
- full rankings
- full command lines
- raw campaign tables
- long narrative explanations

### 4. What is the minimum durable v1 recommendation record?

Minimum:

- schema/policy versioning
- recommendation status
- leading config ID
- recommended config ID
- selection basis
- source refs
- caveat codes
- compact evidence snapshot
- machine-handoff projection

### 5. Does it need recommended config only, or winning config plus evidence, or more?

Recommended:

- leading config plus recommended config plus key supporting evidence

Not:

- recommended config only
- full finalist table

### 6. Should the machine-facing variables file be the recommendation record itself, a projection, or a separate thinner object?

Recommendation:

- a separate thinner object derived from the recommendation record

### 7. How should the record preserve “tentative suggestion, not guaranteed optimum” semantics?

By storing:

- recommendation status
- caveat codes
- leading vs recommended distinction

not by storing a full prose report.

### 8. What fields would create duplication, drift, or confused ownership if added too early?

Risky fields:

- full rankings
- rejected finalists
- weight vectors
- planner policy details
- run-plan scope/schedule copies
- full commands / runtime env
- long prose reasons

### 9. What is the best recommended v1 contract, and why?

Best contract:

- compact recommendation status object with config refs, evidence snapshot, caveat codes, and machine-handoff projection

Why:

- enough to support all intended consumers
- small enough to stay durable
- cleanly separated from execution truth, planning metadata, and methodology truth

## Remaining Open Questions

### 1. Should `needs_deeper_validation` still populate `machine_handoff` as a non-default suggestion, or should handoff be withheld unless `recommended_config_id` is non-null?

This is the one remaining policy question that directly affects machine-output behavior.

### 2. Should `evidence_snapshot` include one or two more fields for divergence context, such as `winner_not_highest_tg` as a boolean instead of only a caveat code?

This is a refinement question, not a blocker to the main contract.

## Recommended Next Investigations

- `ACPM-recommendation-status-policy-TARGET-INVESTIGATION.md`
- `ACPM-machine-handoff-projection-policy-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
