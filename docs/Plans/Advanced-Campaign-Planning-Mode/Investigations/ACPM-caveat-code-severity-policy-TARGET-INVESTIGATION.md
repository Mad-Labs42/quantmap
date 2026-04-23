# ACPM Caveat Code Severity Policy Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 caveat-code behavior and severity policy only

## Outcome

Recommended v1 policy:

- keep `recommendation_status` as the primary claim-control surface
- keep `caveat_codes` as compact secondary qualifiers that explain, limit, or block that claim
- do not use generic numeric severity or a large taxonomy
- use a small behavior-oriented caveat catalog, governed by recommendation policy, with four classes:
  - `explanatory`
  - `provisional_only`
  - `needs_validation`
  - `insufficient_evidence`
- persist only the `caveat_codes` in the recommendation record
- define severity/behavior in the recommendation policy catalog, not as a second persisted field on every record

Recommended governing rule:

- caveats may lower or block the allowed status
- caveats must never silently become the real status system
- if a caveat is serious enough to block machine handoff, it should also force a non-recommending status

Recommended v1 machine-handoff rule:

- `machine_handoff` remains allowed only when the final status is one of the two recommending statuses
- v1 should not introduce "recommendation allowed, but handoff blocked anyway" caveats
- if handoff must be blocked, status should already be `needs_deeper_validation` or `insufficient_evidence_to_recommend`

This is the smallest durable policy that fits current QuantMap warning language, Audit 6 status vocabulary, and the recommendation-record contract without letting caveats quietly replace status as the real authority surface.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/score.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/explain.py`
- `src/export.py`

Supporting docs inspected:

- `docs/AUDITS/4-11/Results-4-11/Audit-6.md`
- `docs/MVP/quantmap_mvp_decisions_and_reporting_contract.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-recommendation-record-contract-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-recommendation-status-policy-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/policies/boundaries.md`

Validation used:

- targeted source inspection only
- no product-code changes
- no broad validation theater; this pass is about trust semantics, withholding rules, and repo fit

## Current Warning / Qualifier / Caveat-Like Constraints

### 1. The repo already distinguishes validity from interpretation strength

`docs/MVP/quantmap_mvp_decisions_and_reporting_contract.md` is explicit that:

- confidence shapes interpretation and recommendation strength
- caveats and warnings must stay visible
- summaries must not outrun underlying warnings
- low-confidence or sparse evidence must not be flattened into strong conclusions

Implication:

- ACPM caveats should be about interpretation strength and recommendation allowance
- they should not redefine validity or replace methodology gates

### 2. Report surfaces already use caveat-like language with different behavioral weight

`src/report.py` already separates:

- `Custom`:
  - best among tested
  - not a full recommendation
- `Quick`:
  - broad but shallow
  - confirm before deploying
- `Standard`:
  - development-grade
  - confirm before deploying
- `Full`:
  - strongest winner language

Implication:

- the repo already contains the seeds of a severity model
- some caveats merely explain scope, while others cap the allowed recommendation strength

### 3. `src/report_campaign.py` already groups concerns by impact

It already distinguishes:

- low-impact explanatory conditions
- moderate reliability concerns
- truth-invalidated conditions

Examples:

- noisy environment adds uncertainty but does not invalidate results
- quick and standard mode are explicitly described as lower-confidence
- sensor collapse and truth-invalidated configurations are treated as materially more serious

Implication:

- ACPM should reuse this behavioral pattern
- not every caveat belongs in the same bucket

### 4. `src/explain.py` already uses caution semantics tied to evidence shape

`src/explain.py` downgrades confidence when:

- winner margin is inside the noise band
- there is no runner-up
- watchlist risks appear near stability or latency thresholds
- methodology evidence is incomplete

Implication:

- v1 caveat codes should align to evidence-driven caution signals already present in the repo
- margin ambiguity, limited competition, and config-specific watchlist risks are real candidate caveat families

### 5. `src/score.py` already exposes recommendation-limiting evidence defects

It already emits or persists:

- `high_nan_warnings`
- `collapsed_dimensions`
- `nan_invalid_ids`
- `winner`
- `highest_tg`
- Pareto state

Implication:

- caveat codes can be grounded in concrete existing signals
- some signals are explanatory, some are directional-only, and some are serious enough to block recommendation

### 6. Export already has a place for structured warnings, but not recommendation-behavior policy

`src/export.py` writes `metadata.json` with:

- `warnings`
- ranking outputs
- environment summary
- provenance completeness

Implication:

- ACPM recommendation caveats should be compact and structured enough to export cleanly
- but they need a governed behavior policy, not just a loose list of warning strings

## Candidate Caveat Severity Models Considered

### 1. No caveat classes at all; status only

Assessment:

- too small

Why:

- loses explanatory precision
- forces status names to carry too much meaning
- would push report/explain surfaces back toward ad hoc prose

### 2. Flat caveat codes with no severity behavior

Assessment:

- reject

Why:

- consumers cannot tell whether a code is merely explanatory or recommendation-blocking
- would encourage each surface to invent its own interpretation
- high risk of repo drift and audit inconsistency

### 3. Generic numeric or color severity per caveat

Assessment:

- reject for v1

Why:

- looks tidy, but is semantically weak
- "severity 2" or "yellow" does not tell readers whether recommendation or handoff is allowed
- pushes meaning into an arbitrary scale instead of the status model

### 4. Behavior-oriented caveat classes tied to status ceilings

Assessment:

- best v1 fit

Why:

- directly answers what each caveat is allowed to do
- keeps status primary
- preserves export/audit traceability without overbuilding

## Recommended v1 Caveat-Code Severity Policy

### Core policy shape

Use caveat codes as stable symbolic labels, but define their meaning through a small governed behavior catalog:

| Behavior class | What it means | Status effect | Handoff effect |
|---|---|---|---|
| `explanatory` | Adds interpretation context only | no status ceiling | none |
| `provisional_only` | Recommendation may still be emitted, but not as fully validated | ceiling of `strong_provisional_leader` | allowed if final status still recommends |
| `needs_validation` | A leader may exist, but recommendation must be withheld pending more validation | force `needs_deeper_validation` | blocked |
| `insufficient_evidence` | Evidence is too weak or structurally compromised to support recommendation | force `insufficient_evidence_to_recommend` | blocked |

Recommended persistence model:

- recommendation record stores `caveat_codes` only
- recommendation policy version defines each code's behavior class
- reports/explain/export surfaces can resolve the code through the catalog

This avoids duplicating:

- status meaning
- caveat behavior
- prose explanations

across multiple artifacts.

### Why this is better than a separate persisted `severity` field

Persisting both:

- `caveat_codes`
- and a second `severity` payload

would create duplicate truth about the same policy decision.

That would raise drift risks:

- policy table says one thing
- record says another
- report surface invents a third interpretation

For v1, the cleaner model is:

- persist the code
- version the governing recommendation policy
- let policy resolve the code into behavior

## Blocking vs Non-Blocking Caveats

### 1. `explanatory` caveats

These should remain visible, but should not weaken or block recommendation on their own.

Recommended v1 examples:

- `winner_not_highest_tg`
- `pareto_tradeoff_present`

Reasoning:

- the repo already accepts that score winner, Pareto frontier, and highest raw TG can differ
- those differences are important to explain, but they do not automatically mean the recommendation is unsafe

### 2. `provisional_only` caveats

These weaken confidence or cap recommendation strength, but can still allow a recommendation.

Recommended v1 examples:

- `quick_mode_low_density`
- `standard_mode_development_grade`
- `tested_subset_only`
- `single_passing_config_limited_competition`
- `environment_noise_observed`
- `telemetry_coverage_reduced`

Reasoning:

- these align closely to existing report and explain language
- they mean "use caution" or "do not overclaim"
- they do not automatically mean the evidence is unusable

Recommended policy:

- these caveats may coexist with `strong_provisional_leader`
- they should not coexist with `best_validated_config` unless the code is purely explanatory

In practice:

- `quick_mode_low_density`, `standard_mode_development_grade`, `tested_subset_only`, and `single_passing_config_limited_competition` should all cap status below `best_validated_config`
- `winner_not_highest_tg` and `pareto_tradeoff_present` may coexist with either recommending status

### 3. `needs_validation` caveats

These mean a leading config exists, but ACPM should withhold recommendation until a specific risk is resolved.

Recommended v1 examples:

- `high_variance`
- `stability_near_gate`
- `latency_tail_risk`
- `thermal_risk`
- `active_score_metric_high_nan`

Repo grounding:

- `src/explain.py` already watchlists stability-near-gate and latency-tail behavior
- `src/report.py` already warns about speed-medium degradation before production use
- `src/report_campaign.py` already treats high-NaN dimensions as directional-only evidence

Policy meaning:

- these are not "nothing useful here" caveats
- they are "there is a plausible leader, but a material unresolved risk remains" caveats

### 4. `insufficient_evidence` caveats

These mean ACPM should not recommend anything because the evidence does not support a responsible recommendation claim.

Recommended v1 examples:

- `noise_band_competition`
- `no_rankable_configs`
- `methodology_evidence_incomplete`
- `active_score_metric_collapsed`
- `leading_config_truth_invalidated`

Repo grounding:

- `src/explain.py` already treats sub-noise-band leads as cautionary
- `src/report_campaign.py` already treats sensor collapse and truth-invalidated configs as materially serious
- incomplete methodology evidence weakens the trust-bearing basis for recommendation reconstruction

Policy meaning:

- this is the "do not emit recommendation" class
- later report/explain surfaces can still say a leader appeared to exist, but ACPM is not allowed to promote it as a recommendation

## Status Interaction Rules

### Status remains primary

Recommended rule:

- status answers the main question: what claim is ACPM allowed to make?
- caveats answer the secondary question: what important limits or risks qualify that claim?

This keeps the model honest:

- users read one primary status
- auditors can still inspect the compact caveat basis

### Allowed interaction policy

Recommended v1 rules:

1. `explanatory` caveats do not change status.
2. `provisional_only` caveats cap status at `strong_provisional_leader`.
3. Any `needs_validation` caveat forces `needs_deeper_validation`.
4. Any `insufficient_evidence` caveat forces `insufficient_evidence_to_recommend`.
5. If multiple caveats are present, the most restrictive behavior class wins.

### Explicit v1 escalation combinations

v1 should allow only a small explicit escalation table, not a generic additive score.

Recommended combinations:

- `quick_mode_low_density` + `single_passing_config_limited_competition`
  - escalate to at least `needs_deeper_validation`
  - reason: sparse depth plus no real competitive field is too weak for a confident recommendation claim

- `tested_subset_only` + `single_passing_config_limited_competition`
  - escalate to at least `needs_deeper_validation`
  - reason: planner-bounded or custom-bounded subset plus limited competition risks overstating the lead

- `noise_band_competition` plus any other evidence-weakness caveat
  - remain `insufficient_evidence_to_recommend`
  - reason: once the leader is already inside the noise band, extra weakness never improves the claim

Recommended anti-pattern to avoid:

- do not create a weighted caveat score that silently decides status behind the scenes
- that would turn caveats into an unbounded shadow policy system

## Machine-Handoff Blocking Policy

Recommended v1 rule:

- machine handoff is blocked by status, not by a separate hidden caveat-only rule

That means:

- if a caveat is only `explanatory`, it never blocks handoff
- if a caveat is `provisional_only`, handoff may still be allowed because the status can still be `strong_provisional_leader`
- if a caveat is `needs_validation`, handoff is blocked because status becomes `needs_deeper_validation`
- if a caveat is `insufficient_evidence`, handoff is blocked because status becomes `insufficient_evidence_to_recommend`

Recommended v1 simplification:

- do not introduce "human recommendation allowed, but machine handoff blocked anyway" caveats

Why:

- it would create a confusing split between human and machine truth
- it would invite surfaces to disagree about whether ACPM really recommended the config
- it would make `machine_handoff` look like a second recommendation authority

## Risks of Getting This Wrong

### 1. Caveats too thin

If caveats are too thin:

- recommendation records become hard to interpret later
- explain/report/export surfaces will invent their own prose
- audit comparison becomes noisy and inconsistent

### 2. Caveats too strong

If caveats become the real claim-control surface:

- status becomes decorative
- the repo gains a second hidden trust policy
- later maintainers will struggle to reconstruct why recommendation or handoff was allowed

### 3. Caveats too vague

If the codes are broad or fuzzy:

- consumers cannot distinguish scope caveats from evidence blockers
- handoff allowance becomes ambiguous
- reports will drift toward magical or misleading language

### 4. Caveats too noisy

If every warning-like detail becomes a recommendation caveat:

- the recommendation record turns into a junk drawer
- export surfaces become harder to read
- important caveats stop standing out

### 5. Caveat classes inconsistent with current repo truth

If caveats ignore existing report/explain semantics:

- `metadata.json`, reports, explain, and ACPM outputs will contradict each other
- users will see a "recommended" machine output beside language that still says "directional only" or "confirm before deploying"

## Downstream Implementation Consequences

### 1. Recommendation policy needs a governed caveat catalog

The implementation will need a small stable table that maps each caveat code to:

- behavior class
- default human explanation label
- whether it is compatible with `best_validated_config`

### 2. Recommendation derivation needs a few compact evidence inputs

To support these caveats cleanly, the recommendation derivation step will likely need compact access to:

- passing-config count
- runner-up margin or a resolved noise-band judgment
- environment confidence rollup
- active score-dimension warning/collapse state

This is a small downstream consequence, but it is real.

### 3. Report and export surfaces should resolve caveats from one policy source

Human-facing reports, explain surfaces, and exported recommendation records should not each maintain their own ad hoc caveat meanings.

### 4. Planner metadata should stay separate

Profile, policy, repeat tier, and narrowing provenance still belong in ACPM planning metadata, not in caveat codes.

The recommendation caveat should only describe the recommendation implication of those facts:

- `tested_subset_only`

not the full planner history that caused them.

## Questions Answered in This Pass

### 1. What kinds of caveats does ACPM likely need in v1?

Four families:

- explanatory tradeoff caveats
- provisional-only confidence caveats
- leader-specific validation blockers
- overall evidence blockers

### 2. Which caveats should be purely explanatory and non-blocking?

At minimum:

- `winner_not_highest_tg`
- `pareto_tradeoff_present`

### 3. Which caveats should weaken confidence but still allow a recommendation?

At minimum:

- `quick_mode_low_density`
- `standard_mode_development_grade`
- `tested_subset_only`
- `single_passing_config_limited_competition`
- `environment_noise_observed`
- `telemetry_coverage_reduced`

### 4. Which caveats should force `needs_deeper_validation`?

At minimum:

- `high_variance`
- `stability_near_gate`
- `latency_tail_risk`
- `thermal_risk`
- `active_score_metric_high_nan`

### 5. Which caveats should force `insufficient_evidence_to_recommend`?

At minimum:

- `noise_band_competition`
- `no_rankable_configs`
- `methodology_evidence_incomplete`
- `active_score_metric_collapsed`
- `leading_config_truth_invalidated`

### 6. Should caveats have explicit severity classes in v1?

Yes, but behavior-oriented classes, not generic numeric or color severity.

### 7. What is the minimum durable v1 caveat model?

- stable `caveat_codes`
- a versioned recommendation policy catalog mapping each code to one of four behavior classes
- no extra persisted per-record severity field

### 8. How should caveats interact with status, `recommended_config_id`, `machine_handoff`, and `evidence_snapshot`?

- status stays primary
- caveats constrain status
- `recommended_config_id` exists only when status recommends
- `machine_handoff` exists only when status recommends
- evidence snapshot should provide compact factual support for any caveats emitted

### 9. Should combinations of caveats escalate?

Yes, but only through a small explicit combination table in v1, not a generic weighted severity engine.

### 10. What kinds of caveats belong in the recommendation record vs other surfaces?

Recommendation record:

- compact recommendation-limiting or interpretation-shaping caveats

Methodology truth / validation gates:

- score shape, weights, gates, anchors, pass/fail rules

Planner metadata:

- planner identity, policy identity, repeat tier, narrowing provenance

Report-only explanation:

- verbose diagnostics, long per-cycle details, low-level telemetry inventory

### 11. What is the best recommended v1 caveat-code severity policy, and why?

Use a four-class behavior catalog that caps or blocks statuses without replacing them.

Why:

- it is the smallest model that preserves trust, supports audit/export use, and matches current repo semantics.

## Remaining Open Questions

### 1. Exact threshold ownership for selected caveats

This pass supports the policy shape, but exact thresholds still need a narrower follow-up for:

- when `high_variance` becomes blocking
- how noise-band competition should be judged
- when environment weakness remains cautionary versus becomes blocking

### 2. Exact evidence snapshot additions needed to justify caveat assignment

The current recommendation-record sketch may need a few compact supporting fields so later audit/export consumers can reconstruct why a caveat was emitted.

### 3. Whether `standard_mode_development_grade` should always imply provisional-only in ACPM

Current repo language strongly suggests yes, but ACPM repeat-tier and planner policy coupling may warrant one last bounded check before implementation.

## Recommended Next Investigations

- `ACPM-caveat-code-catalog-TARGET-INVESTIGATION.md`
- `ACPM-recommendation-evidence-thresholds-TARGET-INVESTIGATION.md`
- `ACPM-recommendation-evidence-snapshot-support-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/policies/boundaries.md`
