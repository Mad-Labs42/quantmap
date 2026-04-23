# ACPM Profile Weight and Gate Spec Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 profile-specific weights, gates, and trust-boundary policy only

## Outcome

Recommended v1 policy:

- keep viability, trust, and safety floors global and identical across `Balanced`, `T/S`, and `TTFT`
- allow profile-specific score weighting and emphasis
- do not use profile-specific elimination gates in v1
- keep confidence aggregation and recommendation qualifier rules global; profile selection may change what is being optimized, but not how certainty is claimed

Weights are sufficient for v1 if ACPM profiles are treated as recommendation lenses over one shared scientific validity floor. Profile-specific gates are too risky under the current repo semantics because elimination reasons are treated as data-validity or usability failures, not as user-preference filters. Tightening or relaxing those gates per profile would blur the line between “not valid/recommendable” and “not preferred under this lens.”

In short:

- `Balanced`, `T/S`, and `TTFT` may change ranking emphasis
- they should not change what counts as scientifically valid evidence in v1

## Scope / What Was Inspected

Policies/docs inspected:

- `.agent/policies/project.md`
- `.agent/policies/boundaries.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-to-governance-mapping-TARGET-INVESTIGATION.md`

Config/methodology inspected:

- `configs/metrics.yaml`
- `configs/profiles/default_throughput_v1.yaml`

Code inspected:

- `src/governance.py`
- `src/score.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/explain.py`
- `src/trust_identity.py`

Validation run:

- `.\.venv\Scripts\python.exe test_governance.py` -> passed

## Current Relevant Repo Constraints

### 1. Profiles already carry trust-bearing methodology meaning

`default_throughput_v1.yaml`, `governance.py`, `score.py`, `trust_identity.py`, `report.py`, `report_campaign.py`, and `export.py` all treat profile identity as methodology evidence, not just UX flavor.

Implication:

- if ACPM profiles materially change winner judgment, that meaning must remain visible as methodology

### 2. Elimination filters currently mean validity/usability failure, not preference

`score._check_filters()` uses gates to produce elimination reasons such as:

- `insufficient_data`
- `thermal_events`
- `cv_too_high`
- `warm_ttft_p90_too_high`
- `low_success_rate`
- `tg_p10_below_floor`

Those reasons flow into:

- `scores.elimination_reason`
- `report.py`
- `report_campaign.py`
- `explain.py` normalized buckets

Implication:

- changing gates changes what the repo declares “failed,” not merely what it prefers

### 3. Repo policy explicitly protects scoring, ranking, confidence, and warning semantics

`.agent/policies/boundaries.md` forbids casual change to:

- scoring semantics
- ranking logic
- winner selection
- confidence aggregation
- methodology loading
- warning generation/suppression
- eliminated vs unrankable distinctions

Implication:

- ACPM profile behavior must stay inside a narrow, explicit policy envelope

### 4. Current profile schema allows more than current runtime actually uses

`ExperimentProfile` includes:

- `weights`
- `gate_overrides`
- `ranking_mode`
- `composite_basis`
- `confidence_policy`
- `report_emphasis`
- `diagnostic_metrics`

Current scoring/runtime use is mostly concentrated in:

- `weights`
- `gate_overrides`
- `confidence_policy`
- metric-family compatibility checks

Implication:

- v1 should use the least risky subset of profile variability that has clear trust semantics

### 5. Current gate-override enforcement is policy-stated but not fully hardened

`default_throughput_v1.yaml` says profiles may tighten but never relax below registry minimums.
`governance.validate_profile_against_registry()` recognizes gate keys, but does not yet robustly enforce all “tighten only” semantics against fully encoded registry minima.

Implication:

- profile-specific gate experimentation is especially risky right now because the trust policy is clearer than the enforcement mechanism

### 6. Current report language already separates optimization target from certainty language

`report.py` and `report_campaign.py` vary recommendation wording by run mode:

- Custom -> best among tested
- Quick -> lowest-confidence full-coverage result
- Standard -> development-grade
- Full -> validated optimal

`report_campaign.py` also states that language conservatism scales with confidence and run mode.

Implication:

- profile selection does not need its own confidence inflation/deflation model in v1
- optimizer preference and certainty claim are already separable concepts in this repo

### 7. Current confidence treatment is global and methodological

`score._compute_config_lcb()` uses `profile.confidence_policy`, but only in a narrow way today: `lcb_k1` vs `lcb_k2`.
`explain.py` and `report_campaign.py` also compute/display confidence from margins, variance, run mode, and environment quality.

Implication:

- changing confidence policy per profile would change conclusion conservatism, not just user preference

### 8. Mode-based filter relaxation already exists, but it is clearly execution-scoped

`runner.run_campaign()` injects `RunPlan.filter_overrides` for:

- Custom mode -> `min_valid_warm_count: 1`
- Quick mode -> `min_valid_warm_count: 3`

This is then merged into `score_campaign(filter_overrides=...)`.

Implication:

- the repo already tolerates non-global gates for execution-shape reasons
- but those relaxations are tied to explicit scope/coverage caveats, not user preference lenses
- ACPM profile gates would be a different and riskier category

## What Should Remain Global

Recommended global, fixed across all ACPM profiles in v1:

- metric definitions and objective directions
- raw measurement pipeline
- rankability vs elimination semantics
- thermal-throttle disqualification
- success-rate floor
- stability floor (`max_cv`)
- outlier ceiling
- minimum statistical viability floor
- methodology snapshot visibility
- missing/failed/unsupported distinctions
- confidence/qualifier honesty rules
- report caution language triggers

Recommended interpretation:

- these are scientific and trust floors, not user-preference knobs

Most important global rule:

- ACPM profiles must not redefine what counts as measurement-grade practical validity

## What May Vary by Profile

Recommended profile-specific levers in v1:

- metric weights within the rank-bearing set
- possibly which score-capable metrics are emphasized in recommendation interpretation, provided this remains explicit in the profile
- profile-specific report emphasis wording
- planner-side campaign ordering and escalation policy

Recommended non-goals for profile variability in v1:

- profile-specific safety floors
- profile-specific evidence sufficiency floors
- profile-specific uncertainty inflation/suppression
- profile-specific elimination meaning

Practical reading:

- `Balanced`: preserve current mixed practical weighting
- `T/S`: increase throughput weight and reduce latency weight, but keep latency in the score
- `TTFT`: increase latency weight and reduce throughput weight, but keep throughput floor pressure in the score

## Candidate v1 Models Considered

### 1. Weights only, global gates

Meaning:

- all profiles share one validity floor
- profiles differ only in composite ranking emphasis

Assessment:

- best fit for v1
- easiest to explain truthfully
- safest under current elimination semantics

### 2. Weights plus profile-specific tightened gates

Meaning:

- profiles share a common minimum floor
- some profiles additionally tighten a gate, such as TTFT tightening latency

Assessment:

- tempting, but risky under current semantics
- the repo would represent those configs as eliminated/failed, not merely less preferred
- can mislead users into reading preference as invalidity

### 3. Weights plus profile-specific relaxed gates

Meaning:

- T/S could allow worse TTFT or lower success/stability thresholds

Assessment:

- unacceptable for v1
- directly weakens trust floor and practical validity semantics
- likely to undermine scientific credibility

### 4. Distinct confidence policy per profile

Meaning:

- T/S could use a less conservative LCB, or TTFT a stricter one

Assessment:

- too risky for v1
- changes how much uncertainty the system penalizes, which is methodological conservatism rather than preference
- would be hard to explain cleanly to users and auditors

### 5. Distinct qualifier/claim language per profile

Meaning:

- profiles alter whether a result is called production-grade, validated, etc.

Assessment:

- unacceptable if it changes certainty thresholds
- acceptable only for profile-label explanation, not confidence inflation

## Recommended v1 Weight / Gate Policy

### Global fixed rules

Recommended:

- one shared validity and trust floor for all ACPM profiles
- all elimination gates remain globally fixed in v1
- all confidence/qualifier truth rules remain globally fixed in v1

That means:

- same elimination thresholds across `Balanced`, `T/S`, `TTFT`
- same treatment of eliminated vs unrankable
- same environment/trust caution behavior
- same recommendation-claim downgrade rules based on evidence quality and repeat strength

### Profile-specific weighting

Recommended:

- yes, this is the main profile-specific methodology lever in v1

Recommended design intent:

- `Balanced`: close to current `default_throughput_v1`, maybe with only modest rebalancing if needed
- `T/S`: throughput-heavy but not throughput-exclusive
- `TTFT`: latency-heavy but not latency-exclusive

Recommended constraint:

- every v1 profile should keep both throughput and latency represented in the composite

Reason:

- dropping one family entirely would make the recommendation semantics too brittle and too easy to misread as one-dimensional optimization

### Profile-specific gate behavior

Recommended v1 policy:

- no profile-specific gate changes in v1

Reason:

- under current repo semantics, gates mean “not valid / not acceptable / failed threshold”
- that is too strong a semantic tool for expressing user preference differences

If profile-specific gates are considered in a later phase, acceptable candidates would have to meet all of these conditions:

- they tighten, never relax, the global floor
- they correspond to a clearly disclosed practical requirement, not hidden taste
- they are reported as profile-defined eligibility requirements, not general scientific invalidity
- audit/report/explain surfaces can distinguish them from global trust floors

Given the current repo, that distinction does not yet exist cleanly. So v1 should not use profile-specific gates.

### Confidence / qualifier handling

Recommended v1 policy:

- keep confidence policy global
- keep recommendation qualifier logic global
- allow profile identity to be displayed in explanation/reporting, but not to change certainty rules

Meaning:

- `Balanced`, `T/S`, `TTFT` may change what wins
- they must not change when the system says “validated optimal,” “development-grade,” “best among tested,” or equivalent confidence-bearing language, except through evidence scope and repeat tier

## Trust and Product Risks

### If profile-specific behavior is too weak

Risk:

- the three ACPM profiles become cosmetic aliases over the same recommendation behavior

Effect:

- user expectations are violated
- ACPM feels fake or unresponsive

### If profile-specific behavior is too strong

Risk:

- profiles begin changing validity floors or certainty conservatism

Effect:

- recommendations may look scientific but are actually being shaped by hidden permissiveness or hidden strictness
- audit meaning becomes unstable

### If profile-specific behavior is opaque

Risk:

- users cannot tell whether a config lost because it was invalid, because it was noisy, or because the chosen profile cared less about that metric

Effect:

- scientific credibility drops
- report/explain surfaces become harder to trust

### Tempting but dangerous behaviors

Tempting but should be avoided in v1:

- relaxing latency gates for `T/S`
- relaxing throughput floors for `TTFT`
- profile-specific success-rate tolerance
- profile-specific thermal tolerance
- profile-specific minimum sample sufficiency
- profile-specific confidence aggressiveness

Why dangerous:

- each one changes trust floor or certainty floor, not just optimization preference

## Downstream Implementation Consequences

If this recommendation is adopted, later implementation should assume:

- ACPM needs distinct scoring profiles for `Balanced`, `T/S`, and `TTFT`
- those profiles should primarily differ by weights and possibly report emphasis metadata
- planner policy must not emulate profile behavior by secretly changing elimination thresholds
- repeat-tier sufficiency logic should be handled separately from profile identity
- report/audit surfaces should expose selected profile identity clearly
- machine handoff serialization can trust the scored winner under one shared validity floor

It also implies:

- future review of any proposal to add profile-specific gates should be treated as a higher-risk methodology change, not a routine tuning pass

## Questions Answered in This Pass

### What parts of recommendation judgment should stay global?

All scientific validity, safety, and trust floors.

### What parts may vary by profile?

Ranking emphasis and recommendation emphasis, not validity semantics.

### Are weights enough for v1?

Yes, with global gates and global confidence rules.

### Do profiles need different gate logic in v1?

No. That is the wrong tool for the current repo semantics.

### Should viability, trust, and safety floors remain identical across profiles?

Yes.

### What should confidence/qualifier handling do?

Remain global and evidence-driven, not profile-driven.

## Remaining Open Questions

### 1. What exact weight sets should `Balanced`, `T/S`, and `TTFT` use?

This pass settles that weights are the main safe lever, not what the exact numbers should be.

### 2. Should any profile-specific metric participation vary at all?

Current recommendation is to keep the same rank-bearing metric set in v1 and vary only weights, but this should be frozen explicitly.

### 3. How should repeat tiers map to recommendation claim strength?

This remains separate from profile identity and still needs its own policy decision.

### 4. Does TTFT need an explicit post-score recommendation floor distinct from elimination?

Possibly in a future phase, but not as an elimination gate under current semantics.

## Recommended Next Investigations

Recommended follow-ups:

- `ACPM-profile-weight-values-TARGET-INVESTIGATION.md`
- `ACPM-repeat-tier-sufficiency-policy-TARGET-INVESTIGATION.md`
- `ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`

Priority order:

1. `ACPM-profile-weight-values-TARGET-INVESTIGATION.md`
2. `ACPM-repeat-tier-sufficiency-policy-TARGET-INVESTIGATION.md`
3. `ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/policies/project.md`
- `.agent/policies/boundaries.md`
