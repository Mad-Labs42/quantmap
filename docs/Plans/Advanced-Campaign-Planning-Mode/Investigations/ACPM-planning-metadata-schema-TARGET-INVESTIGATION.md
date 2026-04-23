# ACPM Planning Metadata Schema Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 adjacent planning metadata schema only

## Outcome

Recommended v1 schema direction:

- keep ACPM planning metadata small, immutable, and snapshot-style
- persist only planner-side identity and bounded planning provenance that `RunPlan` does not already capture
- do not duplicate execution truth from `RunPlan`
- do not duplicate trust-bearing methodology truth from `methodology_snapshots`
- do not store recommendation outcomes here

Recommended minimum durable v1 shape:

```json
{
  "schema_version": "acpm-planning-metadata-v1",
  "planner_id": "acpm",
  "planner_version": "v1",
  "profile_id": "balanced",
  "planner_policy_id": "balanced_v1",
  "planner_policy_version": "1.0",
  "repeat_strength_tier": "3x",
  "narrowing": {
    "applied": true,
    "reason_codes": ["bounded_campaign_subset"],
    "campaign_ids_considered": ["NGL_sweep", "UBatch_sweep"],
    "variable_families_considered": ["ngl", "ubatch"]
  }
}
```

This is intentionally not a second plan object. It is a compact planner-side provenance record that explains:

- which planner was used
- which planner policy/profile were in force
- which repeat tier was requested
- whether planner-directed narrowing happened
- the minimum factual context needed to reconstruct that narrowing later

Bottom line:

- store identifiers, versions, repeat-tier intent, and compact narrowing provenance
- do not store weights, gates, selected configs, resolved schedule, runtime state, or recommendation outcomes here

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/run_plan.py`
- `src/runner.py`
- `src/trust_identity.py`
- `src/export.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/explain.py`
- `src/compare.py`
- `src/report_compare.py`

Supporting docs inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-plan-contract-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-run-mode-and-scope-authority-semantics-TARGET-INVESTIGATION.md`
- `docs/Design Memo's/Advanced-Campaign-Planning-Mode-ADR/Adaptive-Campaign-Planning-Mode-v1-Design.md`

Repo-governance surfaces inspected:

- `.agent/README.md`
- `.agent/policies/architecture.md`

Validation used:

- targeted source inspection only
- no product-code changes
- no broad test theater; this pass is about schema shape, persistence boundaries, and repo fit

## Current Metadata / Snapshot Constraints

### 1. The repo already has a snapshot-first trust pattern

`src/runner.py` persists a `campaign_start_snapshot` at run start and explicitly preserves the original row if one already exists.

Implication:

- ACPM planning metadata should follow the same immutable snapshot spirit
- it should describe planning-time truth, not later interpretation or mutable state

### 2. `RunPlan` already owns execution truth

`RunPlan` and `run_plan_json` already carry:

- effective run identity
- selected scope
- selected configs
- resolved schedule
- paths
- execution-affecting overrides

Implication:

- planning metadata must not repeat selected values/configs, cycles, requests, paths, or filter overrides

### 3. Methodology snapshots already own trust-bearing profile/weights/gates truth

`src/trust_identity.py` and `methodology_snapshots` already persist:

- methodology version
- profile name/version
- weights
- gates
- anchors
- capture quality and source

`src/export.py` already exposes those as structured methodology metadata.

Implication:

- ACPM planning metadata should not become a second place that claims exact weights, gates, anchors, or methodology version truth

### 4. Export metadata is a consumer view, not the source of truth

`metadata.json` already composes:

- campaign identity
- methodology
- ranking
- environment summary
- provenance sources

Implication:

- ACPM planning metadata should be persisted as a durable source record that export/report/history can later consume
- it should not be designed as a display-optimized report fragment first

### 5. Compare and audit surfaces prefer stable, structured identities

`src/compare.py` grades methodology compatibility using persisted structured evidence and compares campaigns using stable typed fields.

Implication:

- ACPM planning metadata should use stable identifiers and versions, not free-form prose or transient heuristic dumps

### 6. Explain surfaces use compact evidence, not raw planner internals

`src/explain.py` currently consumes:

- methodology evidence labels
- execution environment evidence
- elimination summaries

Implication:

- ACPM planning metadata only needs enough signal for concise explanation, not a full planner trace

## Candidate Schema Models Considered

### 1. Fat shadow-plan schema

Meaning:

- store selected values/configs, resolved schedule, filter overrides, resolved runtime identity, and maybe weights/gates alongside planner metadata

Assessment:

- reject

Why:

- duplicates `RunPlan`
- duplicates methodology snapshots
- creates drift and confused ownership immediately

### 2. Identifier-only schema

Meaning:

- store only `planner_id`, `profile_id`, and maybe `repeat_tier`

Assessment:

- too lossy

Why:

- insufficient for audit/history to reconstruct planner policy version
- insufficient to explain planner-directed narrowing
- too weak for future compare/audit use

### 3. Compact planner identity + bounded narrowing provenance

Meaning:

- store stable planner identifiers and versions
- store repeat-tier intent
- store a compact factual summary of planner-directed narrowing above the `RunPlan` layer

Assessment:

- best v1 fit

Why:

- gives history/export/explain enough signal
- stays clearly separate from execution truth and recommendation truth
- matches the repo’s snapshot-first provenance style

### 4. Full planner trace / debug dump

Meaning:

- store raw heuristic scores, candidate rankings, rejected values/configs, probe outputs, and planner intermediates

Assessment:

- reject for v1

Why:

- turns the record into a junk drawer
- raises drift and maintenance risk
- is far more implementation-coupled than current repo provenance patterns

## Recommended v1 Planning Metadata Schema

### Recommended top-level shape

```json
{
  "schema_version": "acpm-planning-metadata-v1",
  "planner_id": "acpm",
  "planner_version": "v1",
  "profile_id": "balanced",
  "planner_policy_id": "balanced_v1",
  "planner_policy_version": "1.0",
  "repeat_strength_tier": "3x",
  "narrowing": {
    "applied": true,
    "reason_codes": ["bounded_campaign_subset"],
    "campaign_ids_considered": ["NGL_sweep", "UBatch_sweep"],
    "variable_families_considered": ["ngl", "ubatch"]
  }
}
```

### Field-by-field intent

`schema_version`

- required
- lets readers evolve safely without guessing shape

`planner_id`

- required
- stable planner family identifier
- v1 value can simply be `acpm`

`planner_version`

- required
- identifies which planner implementation/version produced the plan
- needed for audit and future compare meaning

`profile_id`

- required
- the planner-side selected profile lens
- should be stable ACPM profile identity such as `balanced`, `t_s`, or `ttft`

`planner_policy_id`

- required
- identifies the paired planner policy, which is not identical to the trust-bearing scoring profile

`planner_policy_version`

- required
- planner policy can evolve independently from schema shape

`repeat_strength_tier`

- required
- stores the user/planner-facing tier label (`1x`, `3x`, `5x`)
- the resolved schedule still belongs in `RunPlan`

`narrowing.applied`

- required
- stable boolean saying whether planner-directed narrowing occurred above plain execution scope facts

`narrowing.reason_codes`

- optional but recommended
- compact stable codes only
- enough for explanation/audit without storing a verbose reasoning essay

`narrowing.campaign_ids_considered`

- optional
- include only when the planner considered multiple campaign choices upstream of the chosen run

`narrowing.variable_families_considered`

- optional
- include only when useful to reconstruct planner-directed family narrowing that `RunPlan` cannot show

### Recommended reason-code style

Use stable short codes, not prose blobs.

Examples:

- `bounded_campaign_subset`
- `machine_capability_pruning`
- `model_capability_pruning`
- `planner_budget_limit`

This keeps the schema durable and compare-friendly.

## What Belongs Here vs in `RunPlan` vs in the Future Recommendation Record

### Belongs in ACPM planning metadata

- planner identity
- planner version
- planner profile selection
- planner policy identity/version
- repeat-tier label
- compact planner-directed narrowing provenance above execution scope facts

### Belongs in `RunPlan`

- effective run identity
- actual selected scope
- selected values/configs
- actual schedule
- execution-affecting overrides
- scope authority
- paths and state locations

### Belongs in methodology snapshots, not here

- exact weight vector
- gates / eligibility filters
- anchors
- methodology version
- methodology capture quality/source

### Belongs in execution/runtime state, not here

- telemetry/provider evidence
- execution environment
- resolved runtime values
- measurement outputs
- failures / retries / abort causes

### Belongs in the future recommendation record, not here

- recommended config
- recommendation strength / qualifier
- evidence class for the recommendation
- handoff variables
- final explanation of why this was recommended over alternatives

### Should definitely not be stored here

- full selected values/config lists copied from `RunPlan`
- cycles / requests copied from `RunPlan`
- explicit weights copied from methodology snapshots
- filter overrides copied from `RunPlan` or methodology
- raw planner scoring tables
- raw hardware/model probe dumps
- rejected candidate tables
- final winner / recommendation outcome

## Required Fields vs Optional/Later Fields

### Required for v1

- `schema_version`
- `planner_id`
- `planner_version`
- `profile_id`
- `planner_policy_id`
- `planner_policy_version`
- `repeat_strength_tier`
- `narrowing.applied`

### Optional but recommended for v1

- `narrowing.reason_codes`

### Optional only when applicable

- `narrowing.campaign_ids_considered`
- `narrowing.variable_families_considered`

### Later / nice to have

- richer but still bounded planner provenance summaries
- structured omission summaries beyond terse reason codes
- compare-oriented normalization fields for planner-policy families if ACPM grows significantly

## Risks of Getting This Wrong

### 1. Building a shadow `RunPlan`

If planning metadata repeats selected values/configs, schedule, or filter overrides, the repo will have two competing execution-truth systems.

### 2. Building a shadow methodology system

If planning metadata stores explicit weights or gates, it will compete with the trust-bearing methodology snapshot.

### 3. Building a junk drawer of planner internals

If raw heuristic data and full decision traces are stored here, the schema will become unstable and implementation-coupled.

### 4. Making history too lossy

If only planner/profile labels are stored, later audit/history surfaces will not be able to reconstruct what planner policy or narrowing behavior shaped the run.

## Downstream Implementation Consequences

### 1. The metadata should be captured as immutable planning-time provenance

It should behave more like `run_plan_json` and methodology snapshots than like a mutable report summary.

### 2. Report/export/history consumers should read this as planner-side context only

They should not treat it as authority for execution facts or methodology facts.

### 3. Compare/audit consumers gain a clean future seam

With planner ID/version, policy ID/version, profile ID, and repeat tier, future comparisons can ask:

- same planner family?
- same planner policy?
- same repeat tier?
- comparable narrowing pattern?

without requiring raw planner internals.

### 4. Explicit weight vectors should stay out

Export and report surfaces already have a trust-bearing methodology location for weights, so putting them here would invite drift.

## Questions Answered in This Pass

### 1. What planner-side facts actually need to survive beyond initial planning for v1?

Need to survive:

- planner identity/version
- selected profile
- planner policy identity/version
- repeat-tier label
- compact planner-directed narrowing provenance

### 2. Which facts are needed for reporting, export, history, explain, and audit/compare?

Needed broadly:

- planner ID/version
- profile ID
- policy ID/version
- repeat tier
- narrowing applied flag

Needed mainly for audit/history/explain:

- compact reason codes
- upstream campaign/family consideration summary when applicable

### 3. What should definitely not be stored here?

Not here:

- `RunPlan` execution truth
- methodology weights/gates/anchors
- runtime state
- recommendation outcomes
- transient planner internals

### 4. What is the minimum durable v1 metadata shape?

Minimum:

- schema version
- planner ID/version
- profile ID
- policy ID/version
- repeat tier
- `narrowing.applied`

### 5. Which fields are required versus nice to have?

Required:

- identity/version/profile/policy/tier/narrowing flag

Nice to have:

- reason codes
- considered campaigns/families when applicable

### 6. Should the schema include the explicit weight vector?

Recommendation:

- no

Reason:

- exact weights belong to the methodology snapshot, which is the trust-bearing source

### 7. How much narrowing/provenance rationale should survive in v1?

Only a compact factual summary:

- `applied`
- terse reason codes
- considered campaign/family IDs when needed

No full ranked candidate traces.

### 8. Does v1 need planner versioning / schema versioning / snapshot identity?

Recommendation:

- schema version: yes
- planner version: yes
- policy version: yes
- separate planning snapshot ID: no, not required in v1 if this record is stored adjacent to the run and joined by effective campaign identity

### 9. What fields would create duplication, drift, or confused ownership?

Risky fields:

- selected values/configs
- cycles/requests
- filter overrides
- weights/gates
- runtime evidence
- final recommendation outcome

### 10. What is the best recommended v1 planning metadata schema, and why?

Best schema:

- compact planner identity + compact narrowing provenance

Why:

- enough for report/export/history/explain/audit use
- small enough to stay durable
- cleanly separated from execution truth and methodology truth

## Remaining Open Questions

### 1. Should considered campaign/family identifiers always be recorded, or only when narrowing actually happened above the chosen parent campaign?

This is a smaller policy question, not a blocker to the main schema recommendation.

### 2. Should planner-policy versioning align to QuantMap release/versioning or to a planner-policy-specific version stream?

This matters for future governance but does not block the v1 schema shape.

## Recommended Next Investigations

- `ACPM-planner-policy-versioning-TARGET-INVESTIGATION.md`
- `ACPM-planning-metadata-persistence-surface-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
