# ACPM Recommendation Status Policy Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 recommendation-status policy and allowed outputs only

## Outcome

Recommended v1 status policy:

- use four statuses, not two and not a large taxonomy
- separate:
  - a config leading under scoring
  - ACPM being willing to recommend it
  - ACPM withholding recommendation
- allow machine handoff only when ACPM is actually making a recommendation

Recommended v1 statuses:

- `strong_provisional_leader`
- `best_validated_config`
- `needs_deeper_validation`
- `insufficient_evidence_to_recommend`

Recommended core rule:

- `leading_config_id` may exist for any status
- `recommended_config_id` is only allowed for statuses that actually emit a recommendation
- `machine_handoff` is only allowed when `recommended_config_id` is present

That means:

- `strong_provisional_leader` -> recommendation allowed, handoff allowed
- `best_validated_config` -> recommendation allowed, handoff allowed
- `needs_deeper_validation` -> recommendation withheld, handoff withheld
- `insufficient_evidence_to_recommend` -> recommendation withheld, handoff withheld

This is the smallest durable set that matches existing repo caution language, the accepted Audit 6 vocabulary, and the recommendation-record contract without encouraging overclaiming.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/score.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/explain.py`
- `src/export.py`
- `src/compare.py`
- `src/report_compare.py`

Supporting docs inspected:

- `docs/AUDITS/4-11/Results-4-11/Audit-6.md`
- `docs/MVP/quantmap_mvp_decisions_and_reporting_contract.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-recommendation-record-contract-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-blast-radius-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `.agent/README.md`
- `.agent/policies/architecture.md`

Validation used:

- targeted source inspection only
- no product-code changes
- no broad validation theater; this pass is about policy, allowed outputs, and trust semantics

## Current Trust / Qualifier / Recommendation Constraints

### 1. Scoring already distinguishes winner truth from raw throughput truth

`src/score.py` already persists:

- `is_score_winner`
- `is_highest_tg`
- Pareto flags

Implication:

- the repo already accepts that “winner under scoring” is not the only relevant truth
- ACPM status policy should layer on top of that, not replace it

### 2. Report surfaces already vary how strongly they speak

`src/report.py` already uses different intensities:

- Custom:
  - best among tested
  - not a full recommendation
- Quick:
  - broad but shallow
  - confirm before deploying
- Standard:
  - development-grade
  - confirm before deploying
- Full:
  - validated optimal language

Implication:

- the repo already has a real pattern where the same score winner can support different allowed claims
- ACPM status policy should formalize that pattern instead of inventing a separate philosophy

### 3. Existing confidence policy is evidence-strength oriented

`docs/MVP/quantmap_mvp_decisions_and_reporting_contract.md` says:

- confidence shapes interpretation and recommendation strength
- confidence must reflect evidence strength, not just pass/fail validity

Implication:

- status policy must depend on evidence sufficiency and risk signals, not merely whether a winner exists

### 4. Explain surfaces already distinguish strong, moderate, and cautionary interpretations

`src/explain.py` uses:

- winner margin
- variance
- elimination context

to assign:

- `High`
- `Moderate`
- `Caution`

Implication:

- caveat-rich but compact status semantics fit the repo better than binary recommend/do-not-recommend logic

### 5. Audit 6 already proposed the strongest v1 vocabulary candidate

Accepted Audit 6 direction includes:

- `Strong Provisional Leader`
- `Best Validated Config`
- `Insufficient Evidence to Recommend`
- `Needs Deeper Validation`

Implication:

- the safest v1 policy is to adopt this accepted vocabulary unless the repo shape forces a simpler model
- the repo shape does not force a simpler model

### 6. Current machine-facing output does not have an independent trust policy

Current production-command and winner-projection behavior lives in report and config surfaces, not in a dedicated recommendation policy object.

Implication:

- ACPM status policy must explicitly decide when machine handoff is allowed
- otherwise machine output could become more authoritative than human trust language

## Candidate Status Models Considered

### 1. Two-status model: `recommended` / `withheld`

Assessment:

- too coarse

Why:

- collapses provisional and validated recommendation claims
- cannot distinguish “specific config leads but has red flags” from “evidence is insufficient overall”

### 2. Three-status model: `recommended` / `needs_deeper_validation` / `withheld`

Assessment:

- better than binary
- still too coarse

Why:

- still collapses provisional and validated recommendation claims
- “withheld” hides whether there is a meaningful leading config

### 3. Four-status model from accepted Audit 6

Statuses:

- `strong_provisional_leader`
- `best_validated_config`
- `needs_deeper_validation`
- `insufficient_evidence_to_recommend`

Assessment:

- best v1 fit

Why:

- smallest set that separates:
  - provisional recommendable
  - validated recommendable
  - specific-leader-but-not-yet-safe-to-recommend
  - general evidence insufficiency

### 4. Larger taxonomy with many subtypes

Assessment:

- overcomplicated for v1

Why:

- too much policy surface before implementation exists
- better handled through caveat codes rather than additional statuses

## Recommended v1 Recommendation-Status Policy

### Status 1: `strong_provisional_leader`

Meaning:

- a leading config exists
- ACPM is willing to tentatively recommend it as a likely strong starting point
- the recommendation is explicitly provisional, not validated

Allowed claim:

- “This is the strongest currently observed starting-point recommendation under the tested conditions.”

Not allowed:

- “validated best”
- “guaranteed optimum”
- “production-safe by default”

Typical qualifying conditions:

- a clear score-leading config exists
- no recommendation-blocking risk signals are present
- evidence is useful but not validation-grade
- examples:
  - shallow repeat density
  - reduced repetition
  - planner-bounded subset coverage
  - non-blocking environment/provenance caveats

Typical caveat-code class:

- cautionary but non-blocking

### Status 2: `best_validated_config`

Meaning:

- a leading config exists
- ACPM is willing to recommend it with the strongest v1 recommendation claim
- this is still “best validated among the tested conditions,” not universal optimum language

Allowed claim:

- “This is the best validated config observed under the tested conditions.”

Not allowed:

- universal or context-free optimum claims

Typical qualifying conditions:

- a clear score-leading config exists
- validation-grade sampling depth or repeat strength was used
- no recommendation-blocking risk signals are present
- evidence/provenance quality is materially stronger than provisional mode

Typical caveat-code class:

- may include mild informational caveats
- must not include recommendation-blocking caveats

### Status 3: `needs_deeper_validation`

Meaning:

- a leading config exists
- ACPM is not willing to recommend it yet
- the problem is not that all evidence is unusable
- the problem is that the leading config carries specific unresolved risk or instability signals

Allowed claim:

- “A leader exists, but ACPM is withholding recommendation until deeper validation resolves specific risks.”

Typical triggering conditions:

- config-specific risk signals such as:
  - thermal risk
  - high-latency tail risk
  - instability near important thresholds
  - other concrete recommendation-blocking warning conditions

Important distinction:

- this status means “there is a plausible leader, but it is not safe to promote yet”
- it is not the same as having no useful evidence at all

### Status 4: `insufficient_evidence_to_recommend`

Meaning:

- ACPM is not willing to recommend any config
- either no meaningful leader exists or the evidence is too ambiguous/weak to support a recommendation claim

Allowed claim:

- “Current evidence does not justify a recommendation.”

Typical triggering conditions:

- no rankable configs
- top candidates inside the noise band
- evidence sufficiency too weak
- material methodology/provenance incompleteness
- campaign-level ambiguity that prevents a defensible recommendation

Important distinction:

- this status is about general insufficiency or ambiguity, not a single red-flagged leader

## Allowed Fields/Outputs by Status

### `strong_provisional_leader`

Allowed:

- `leading_config_id`
- `recommended_config_id`
- `machine_handoff`
- cautionary `caveat_codes`

Not allowed:

- validated-strength wording

### `best_validated_config`

Allowed:

- `leading_config_id`
- `recommended_config_id`
- `machine_handoff`
- informational `caveat_codes`

Not allowed:

- caveat profiles that materially contradict validated status

### `needs_deeper_validation`

Allowed:

- `leading_config_id`
- `caveat_codes`
- compact evidence snapshot

Not allowed:

- `recommended_config_id`
- `machine_handoff`

### `insufficient_evidence_to_recommend`

Allowed:

- `leading_config_id` may be present if one numerically leads but the evidence is too ambiguous to promote it
- `caveat_codes`
- compact evidence snapshot

Not allowed:

- `recommended_config_id`
- `machine_handoff`

### General policy for `recommended_config_id`

`recommended_config_id` is allowed only for:

- `strong_provisional_leader`
- `best_validated_config`

It should be `null` for:

- `needs_deeper_validation`
- `insufficient_evidence_to_recommend`

## Machine-Handoff Allowance Policy

### Core rule

Machine handoff is allowed only when ACPM is actually making a recommendation.

That means:

- allowed for `strong_provisional_leader`
- allowed for `best_validated_config`
- withheld for `needs_deeper_validation`
- withheld for `insufficient_evidence_to_recommend`

### Why `needs_deeper_validation` should withhold handoff

This is the most important v1 policy choice.

Recommendation:

- withhold handoff for `needs_deeper_validation`

Reason:

- if ACPM says deeper validation is required, emitting a machine-ready config anyway would undercut the trust message
- it would encourage users and downstream tooling to treat a blocked recommendation like a soft recommendation
- that is exactly the kind of semantic leakage the repo has been trying to avoid

### Why provisional leaders may still permit handoff

Recommendation:

- allow handoff for `strong_provisional_leader`

Reason:

- the user explicitly wants ACPM to tentatively suggest a likely-best config when evidence supports doing so
- provisional status plus cautionary caveats is sufficient to preserve that honesty
- the handoff remains a suggested starting point, not a validated optimum claim

## Risks of Getting This Wrong

### 1. Overclaiming through machine output

If handoff is emitted for withheld statuses, the machine artifact will say “use this” while the human trust layer says “not yet.”

### 2. Collapsing provisional and validated recommendation claims

If the model uses only `recommended`, the repo loses the distinction that current run-mode/report language already works hard to preserve.

### 3. Hiding the difference between ambiguity and config-specific risk

If `needs_deeper_validation` and `insufficient_evidence_to_recommend` collapse into one withheld state, explain/audit surfaces lose a meaningful distinction.

### 4. Letting caveat codes become fake statuses

If caveat codes are used instead of statuses, readers will have to reverse-engineer policy from warning lists.

Status should answer:

- what claim is allowed

Caveat codes should answer:

- why that claim is limited

## Downstream Implementation Consequences

### 1. Recommendation status becomes the primary claim-control field

This gives reports, explain, export, and future machine serializers one shared answer to:

- how strongly may ACPM speak?

### 2. `leading_config_id` and `recommended_config_id` need to stay distinct

That distinction is required for withheld states to remain honest.

### 3. Caveat codes should be classed as blocking vs non-blocking

The exact caveat taxonomy can evolve later, but the status policy implies two operational classes:

- non-blocking caveats
  - compatible with recommendation emission
- recommendation-blocking caveats
  - force `needs_deeper_validation` or `insufficient_evidence_to_recommend`

### 4. Reports and explain surfaces should derive wording from status, not infer it ad hoc from winner plus run mode

This is one of the main benefits of formalizing status policy.

## Questions Answered in This Pass

### 1. What recommendation statuses should exist in v1?

Recommended four-status set:

- `strong_provisional_leader`
- `best_validated_config`
- `needs_deeper_validation`
- `insufficient_evidence_to_recommend`

### 2. What should each status mean, precisely?

- `strong_provisional_leader`
  - recommendable, but provisional
- `best_validated_config`
  - recommendable, with strongest v1 validation claim
- `needs_deeper_validation`
  - leader exists, but recommendation withheld due to specific risk signals
- `insufficient_evidence_to_recommend`
  - evidence too weak or ambiguous to recommend any config

### 3. What is the minimum status set that preserves trust and usability?

Four statuses.

Anything smaller collapses important distinctions.

### 4. How should policy distinguish leader existence from recommendation allowance?

Use:

- `leading_config_id` for the scoring lead
- `recommended_config_id` only when ACPM actually recommends

### 5. Should v1 use `recommended`, `needs_deeper_validation`, `withheld`, `no_recommendation`, or a better set?

Better set:

- the four-status Audit 6-aligned model above

### 6. Under what evidence conditions should each status be assigned?

- provisional when evidence is useful and non-blocking, but not validation-grade
- validated when evidence is strong and non-blocking
- deeper validation when a leader exists but specific config risks block promotion
- insufficient evidence when evidence is too weak or ambiguous overall

### 7. Is `recommended_config_id` allowed for every status?

No.

Only for:

- `strong_provisional_leader`
- `best_validated_config`

### 8. When is the machine-handoff block allowed?

Only when `recommended_config_id` is present.

### 9. Should `needs_deeper_validation` still permit a handoff?

Recommendation:

- no

### 10. How should caveat codes interact with status?

- status determines allowed claim strength
- caveat codes justify and refine that status

### 11. What policy best preserves QuantMap’s “suggested, not guaranteed optimum” philosophy?

The four-status model with handoff only for recommending statuses.

### 12. What is the best recommended v1 status policy, and why?

Best policy:

- four statuses
- explicit distinction between leader and recommendation
- handoff only when recommendation is truly emitted

Why:

- it matches existing repo caution semantics
- it aligns with accepted Audit 6 vocabulary
- it avoids overclaiming while still permitting tentative suggestions

## Remaining Open Questions

### 1. Which exact caveat codes should be classified as recommendation-blocking vs non-blocking in v1?

That is the main follow-up needed after this pass.

### 2. Should validated status require full-repeat equivalence only, or can another future validation path qualify?

This is a later policy refinement and does not block the v1 status set itself.

## Recommended Next Investigations

- `ACPM-caveat-code-severity-policy-TARGET-INVESTIGATION.md`
- `ACPM-validated-status-evidence-thresholds-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
