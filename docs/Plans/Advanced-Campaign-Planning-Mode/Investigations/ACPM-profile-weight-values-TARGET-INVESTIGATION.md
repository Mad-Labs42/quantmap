# ACPM Profile Weight Values Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 metric-set and weight-structure recommendation only

## Outcome

Recommended v1 ACPM scoring model:

- use the same explicit score-capable metric shape in all three profiles
- vary weights only
- keep stability / reliability / confidence signals out of the weighted composite
- treat `warm_ttft_p90_ms` as a global gate and methodology disclosure metric, not as a meaningful weighted ranking axis in v1

Recommended v1 weight vectors:

| Profile | warm_tg_median | warm_tg_p10 | warm_ttft_median_ms | warm_ttft_p90_ms | cold_ttft_median_ms | pp_median |
|---|---:|---:|---:|---:|---:|---:|
| `Balanced` | 0.25 | 0.15 | 0.35 | 0.00 | 0.20 | 0.05 |
| `T/S` | 0.35 | 0.25 | 0.15 | 0.00 | 0.10 | 0.15 |
| `TTFT` | 0.10 | 0.05 | 0.50 | 0.00 | 0.30 | 0.05 |

Best v1 reading:

- `Balanced` = practical mixed recommendation profile
- `T/S` = throughput-biased profile
- `TTFT` = responsiveness-biased profile

The strongest repo-grounded reason for this structure is that current scoring leverage is not symmetric across metrics. Throughput-style metrics use uncapped reference-based utilities and can exceed `1.0`, while TTFT utilities are capped in `[0,1]`. A nominally “balanced” profile therefore needs more latency weight than intuition alone would suggest if it is meant to behave as a real balanced lens.

## Scope / What Was Inspected

Policies/docs inspected:

- `.agent/policies/project.md`
- `.agent/policies/boundaries.md`
- `docs/system/trust_surface.md`
- `docs/system/architecture.md`
- `docs/playbooks/tuning.md`
- `README.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-to-governance-mapping-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-weight-and-gate-spec-TARGET-INVESTIGATION.md`

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

Targeted checks used:

- governance validation via `test_governance.py`
- direct utility-transform sanity checks with inline Python against `src.score._apply_utility_transform()`
- targeted synthetic ranking sanity check using representative throughput-heavy, mixed, and latency-heavy candidate profiles under proposed weights

## Current Relevant Scoring Constraints

### 1. Current runtime effectively assumes one six-metric score shape

Three separate code paths constrain profile metric participation:

- `score._split_by_rankability()` uses Registry-required and Registry-optional score metrics, not per-profile metric subsets
- `score.compute_scores()` hardcodes the six current score-capable columns into the ranking dataframe
- `report_campaign.py` renders a fixed six-row methodology weight table and falls back to legacy defaults if a key is absent

Implication:

- v1 ACPM should keep one explicit six-key profile shape across `Balanced`, `T/S`, and `TTFT`
- meaningfully different metric sets are not a clean fit for the current repo

### 2. Current transforms are mixed, so nominal weights are not equal leverage

Actual utility transforms in `score._apply_utility_transform()` are:

- `warm_tg_median` -> reference-based, anchor `30.0`, uncapped above `1.0`
- `warm_tg_p10` -> reference-based, anchor `25.0`, uncapped above `1.0`
- `pp_median` -> reference-based, anchor `500.0`, uncapped above `1.0`
- `warm_ttft_median_ms` -> saturating utility, `1.0` at `50 ms`, `0.0` at `500 ms`
- `cold_ttft_median_ms` -> saturating utility, `1.0` at `100 ms`, `0.0` at `2500 ms`
- `warm_ttft_p90_ms` -> threshold utility, `1.0` at or below `500 ms`, `0.0` above

Implication:

- throughput-style metrics can produce utility values above `1.0`
- latency-style metrics are capped at `1.0`
- nominally equal throughput and latency weights are not behaviorally equal

### 3. `warm_ttft_p90_ms` is currently a poor weighted ranking axis

The current global gate is `max_warm_ttft_p90_ms = 500.0`.
The current utility transform for `warm_ttft_p90_ms` is also thresholded at `500.0`.

That means any config that passes the gate receives the same utility contribution:

- `warm_ttft_p90_ms <= 500` -> utility `1.0`
- `warm_ttft_p90_ms > 500` -> already eliminated globally

Implication:

- a nonzero v1 score weight on `warm_ttft_p90_ms` mostly adds a constant offset to all passing configs
- this is mathematically weak and easy to misread as meaningful tail-latency ranking when it is really acting as a pass/fail gate duplicate

### 4. Stability and confidence are already accounted for outside raw weights

Current repo behavior already includes:

- global elimination on `warm_tg_cv`, `success_rate`, `thermal_events`, and outlier count
- LCB scoring in `_compute_config_lcb()`, which penalizes higher uncertainty
- report/explain confidence qualifiers from run mode, variance, and environment quality

Implication:

- putting variability or confidence-like signals directly into the composite in v1 would double-count uncertainty and muddy trust semantics

### 5. The default profile is throughput-biased even though it already includes latency

`default_throughput_v1.yaml` weights are:

- throughput family: `0.35 + 0.20 + 0.05 = 0.60`
- latency family: `0.20 + 0.10 + 0.10 = 0.40`

Under current transforms, the effective bias is stronger than the nominal split suggests because three throughput-related metrics are reference-based and uncapped.

Implication:

- `Balanced` should not simply copy the current default profile if the product intent is a genuinely mixed recommendation lens

### 6. Weight changes must stay coarse and auditable

The repo treats profile weights as trust-bearing methodology. Reports, methodology snapshots, and audit guidance all expose weight vectors directly.

Implication:

- coarse weight steps are preferable to overly precise decimal tuning
- v1 should avoid fake-precision vectors that imply validation the repo does not yet have

## Candidate Metric-set / Weight Models Considered

### 1. Same metric set, different weights

Meaning:

- all three profiles declare the same six explicit score keys
- ranking differences come only from weight changes

Assessment:

- best fit for current code and current trust model

### 2. Different metric set per profile

Meaning:

- e.g. `TTFT` drops throughput-side metrics, or `T/S` drops cold latency

Assessment:

- not recommended for v1
- conflicts with current rankability logic, score dataframe construction, and methodology rendering assumptions

### 3. Keep a meaningful nonzero `warm_ttft_p90_ms` weight

Meaning:

- preserve tail-latency presence in the composite as if it were a genuine ranking dimension

Assessment:

- misleading under current math
- the metric is already acting as a shared hard gate, so the weight would mostly consume score mass without helping ordering

### 4. Add stability / confidence-like metrics into the composite

Meaning:

- weight CV, success reliability, or uncertainty directly

Assessment:

- not recommended for v1
- duplicates current global gates and LCB logic
- weakens the clean line between validity, uncertainty, and preference ranking

### 5. Use the same metric set but zero-weight one metric explicitly

Meaning:

- preserve repo fit while admitting that one current score-capable metric is not giving useful discriminatory signal

Assessment:

- best fit for `warm_ttft_p90_ms` in v1
- explicit, auditable, and mathematically honest

## Recommended v1 Metric Set

Recommended v1 metric participation:

- use the same explicit six metric keys in all three profile files
- keep all six visible in methodology surfaces
- use positive weight on five metrics
- set `warm_ttft_p90_ms` to `0.00` in all three profiles

Recommended explicit metric keys:

- `warm_tg_median`
- `warm_tg_p10`
- `warm_ttft_median_ms`
- `warm_ttft_p90_ms`
- `cold_ttft_median_ms`
- `pp_median`

Recommended effective discriminative set:

- `warm_tg_median`
- `warm_tg_p10`
- `warm_ttft_median_ms`
- `cold_ttft_median_ms`
- `pp_median`

Why not drop `warm_ttft_p90_ms` entirely?

- current score/rank/report surfaces are still built around the six-key shape
- keeping the explicit key preserves methodology transparency
- zero-weighting is cleaner than pretending a gate-duplicate metric is contributing meaningful rank signal

## Recommended v1 Weights for Balanced / T/S / TTFT

### `Balanced`

Recommended weights:

- `warm_tg_median`: `0.25`
- `warm_tg_p10`: `0.15`
- `warm_ttft_median_ms`: `0.35`
- `warm_ttft_p90_ms`: `0.00`
- `cold_ttft_median_ms`: `0.20`
- `pp_median`: `0.05`

Why this fits:

- it is meaningfully more neutral than the current default profile
- it offsets current throughput-transform asymmetry by giving more nominal weight to latency
- it still preserves throughput floor and sustained throughput as major ranking signals
- it stays interpretable as one practical mixed-user profile, not a “latency first” profile in disguise

Practical reading:

- sustained throughput matters
- throughput floor matters
- typical and first-impression responsiveness matter enough to block a raw-throughput-only winner from always dominating

### `T/S`

Recommended weights:

- `warm_tg_median`: `0.35`
- `warm_tg_p10`: `0.25`
- `warm_ttft_median_ms`: `0.15`
- `warm_ttft_p90_ms`: `0.00`
- `cold_ttft_median_ms`: `0.10`
- `pp_median`: `0.15`

Why this fits:

- it preserves the repo’s current throughput-first lineage
- it rewards both peak sustained generation and worst-case throughput floor
- it still retains enough latency weight to avoid absurdly sluggish winners among otherwise valid configs
- it gives PP a larger but still bounded role as a secondary throughput-adjacent signal

Practical reading:

- pick the fastest still-practical config
- do not ignore responsiveness
- do not collapse into raw TG-only ranking

### `TTFT`

Recommended weights:

- `warm_tg_median`: `0.10`
- `warm_tg_p10`: `0.05`
- `warm_ttft_median_ms`: `0.50`
- `warm_ttft_p90_ms`: `0.00`
- `cold_ttft_median_ms`: `0.30`
- `pp_median`: `0.05`

Why this fits:

- it makes responsiveness genuinely primary under the current transform asymmetry
- it still keeps throughput present so the profile cannot drift into recommending barely-viable low-throughput configs simply because they are responsive
- it reflects that both warm interactive feel and cold first-impression latency matter for a TTFT-oriented lens

Practical reading:

- response feel comes first
- throughput still matters enough to preserve practical usability
- the global throughput floor remains the hard backstop against misleading low-output winners

## Mathematical / Product Risks

### 1. Mistaking nominal balance for behavioral balance

Risk:

- setting near-equal family weights and assuming that means equal influence

Why risky:

- reference-based throughput utilities can exceed `1.0`
- latency utilities are capped at `1.0`

Consequence:

- profiles can stay more throughput-biased than their weight table appears

### 2. Spending composite weight on `warm_ttft_p90_ms`

Risk:

- treating current tail-latency weight as meaningful rank signal

Why risky:

- under the current shared gate and threshold utility, it is mostly constant across passing configs

Consequence:

- fake precision
- less score mass available for truly discriminative dimensions

### 3. Over-weighting `pp_median`

Risk:

- turning a secondary throughput metric into a hidden primary winner driver

Why risky:

- `pp_median` is reference-based and uncapped above `1.0`
- the repo already introduced normalization work to prevent prompt-processing dominance from distorting conclusions

Consequence:

- rankings can drift toward a prompt-throughput proxy instead of user-visible practical performance

### 4. Dropping throughput or latency entirely

Risk:

- making any profile effectively one-dimensional

Why risky:

- product behavior becomes brittle
- user expectations may be overfit to a single headline metric
- audit/recommendation wording becomes harder to explain honestly

Consequence:

- `TTFT` can recommend configs that feel fast but are practically weak
- `T/S` can recommend configs that are technically valid but unpleasantly sluggish

### 5. Using overly precise decimals

Risk:

- weights like `0.273 / 0.147 / 0.318`

Why risky:

- the repo does not yet have the comparative validation depth to justify that precision

Consequence:

- methodology looks more scientifically settled than it really is

Recommended v1 discipline:

- use coarse `0.05` increments only

## Downstream Implementation Consequences

If this recommendation is adopted, later ACPM implementation should assume:

- all three profiles should define the same explicit six weight keys
- profile selection should change only the weight vector and associated planner policy
- `warm_ttft_p90_ms` remains important globally, but as a gate and methodology disclosure field rather than an effective v1 ranking term
- report/audit surfaces should present the full explicit vector, including `0.00` where used
- any future attempt to make profile-specific metric participation diverge should be treated as a higher-risk structural change because the current scorer does not expose a clean per-profile metric-set seam

It also implies:

- if later work wants `warm_ttft_p90_ms` to become a real ranking dimension again, the transform/gate relationship should be re-investigated first
- future planner logic should not try to “simulate” profile identity by changing metric participation implicitly

## Questions Answered in This Pass

### What rank-bearing metrics should ACPM profiles use in v1?

The same explicit six score-capable keys as the current scorer/reporter expects, with five positive-weight metrics and `warm_ttft_p90_ms` explicit at `0.00`.

### Should all three profiles use the same metric set?

Yes. Current repo structure strongly favors one shared score shape with different weights.

### Should throughput and TTFT remain present in all three profiles?

Yes. Both families should remain present in all three profiles, with emphasis changing rather than dropping a family entirely.

### Should stability / variability / confidence-like signals enter the composite directly?

No. They should remain outside the composite and continue to act through shared gates, LCB scoring, and qualifier/reporting logic.

### What is the best recommended v1 weight model?

`Balanced`

- `0.25 / 0.15 / 0.35 / 0.00 / 0.20 / 0.05`

`T/S`

- `0.35 / 0.25 / 0.15 / 0.00 / 0.10 / 0.15`

`TTFT`

- `0.10 / 0.05 / 0.50 / 0.00 / 0.30 / 0.05`

## Remaining Open Questions

### 1. Should `warm_ttft_p90_ms` stay zero-weighted beyond v1?

Under current gate/transform semantics, yes. If future methodology wants it rank-bearing again, the transform or gate relationship should be reconsidered explicitly.

### 2. Should `Balanced` remain distinct from the current default profile, or should the current default itself evolve?

This pass recommends distinct ACPM profile weights. Whether `default_throughput_v1` remains unchanged or is eventually reinterpreted is a separate governance decision.

### 3. Does `T/S` need a frozen acronym expansion and user definition before implementation?

Yes. The weight model is throughput-biased either way, but naming ambiguity should still be removed before user-facing implementation.

### 4. Should later ACPM report language explain that tail latency is enforced globally rather than weighted materially?

Probably yes, but that belongs to report/audit labeling work rather than this scoring-only pass.

## Recommended Next Investigations

Recommended follow-ups:

- `ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`
- `ACPM-repeat-tier-sufficiency-policy-TARGET-INVESTIGATION.md`
- `ACPM-profile-runtime-shape-compatibility-TARGET-INVESTIGATION.md`

Priority order:

1. `ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`
2. `ACPM-repeat-tier-sufficiency-policy-TARGET-INVESTIGATION.md`
3. `ACPM-profile-runtime-shape-compatibility-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/policies/project.md`
- `.agent/policies/boundaries.md`
