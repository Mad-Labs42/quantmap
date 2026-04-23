# ACPM NGL Scaffold Subset Policy Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 `NGL_sweep` `1x` scaffold subset policy only

## Outcome

Recommended v1 policy:

- allow exactly one predeclared `NGL_sweep` scaffold at `1x`
- make it fixed against the current committed `NGL_sweep.yaml` value ladder
- do not vary it by guessed VRAM tier, predicted optimum, or profile
- require full `NGL_sweep` coverage at `3x` and `5x`
- require full `NGL_sweep` coverage even at `1x` when the campaign is being used for explicit context-threshold recommendation semantics

Recommended v1 scaffold:

- `[10, 30, 50, 70, 90, 999]`

Why this is the best v1 fit:

- all values already exist in the committed YAML
- the subset is globally simple to explain: every other ordinal step plus the `999` sentinel
- it preserves ascending order
- it preserves the low edge, mid-curve, upper edge, and full-offload sentinel
- it saves real time without pretending to know the interior optimum

Recommended hard rule:

- the scaffold is a planner-budget shortcut only
- it is not a second applicability rule
- it is not a scoring shortcut
- it is not a model-specific prediction system

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/runner.py`
- `src/report.py`
- `src/run_plan.py`

Config surfaces inspected:

- `configs/campaigns/NGL_sweep.yaml`
- `configs/baseline.yaml`

Supporting ACPM investigations inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-applicability-and-pruning-rule-catalog-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-planner-policy-and-repeat-tier-matrix-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planner-narrowing-and-candidate-selection-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-run-mode-and-scope-authority-semantics-TARGET-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`

Validation used:

- targeted source/doc inspection
- one light proportional verification step confirming:
  - the live `NGL_sweep` values are still `[10, 20, 30, 40, 50, 60, 70, 80, 90, 999]`
  - the YAML still states values must remain ascending for early OOM-boundary termination semantics
  - the runner still enforces ascending-order correctness for `oom_boundary_sweep`
- no product-code edits

## Current `NGL_sweep` Repo Constraints

### 1. The current YAML ladder is explicit and ordered

`configs/campaigns/NGL_sweep.yaml` currently defines:

- `values: [10, 20, 30, 40, 50, 60, 70, 80, 90, 999]`
- `oom_boundary_sweep: true`
- `min_context_length: null`

It also explicitly says:

- values must be ascending
- `999` is the llama.cpp “all layers” sentinel

Implication:

- any scaffold must be a strict ordered subset of that exact committed list
- any scaffold that breaks ascending order is invalid

### 2. Runner semantics depend on ascending order

`runner.validate_campaign()` checks that `oom_boundary_sweep` values are ascending.  
`runner.run_campaign()` uses that ordering when it:

- continues after the first OOM
- confirms a VRAM boundary after 2 consecutive OOM failures
- marks remaining configs as `skipped_oom`

Implication:

- the scaffold cannot reorder values
- the scaffold should remain compatible with “grow upward until failure” semantics

### 3. The report already treats `NGL_sweep` as a curve, not just a winner table

`report._ngl_sweep_section()` currently expects:

- ordered NGL points
- a viable-point series for diminishing-returns analysis
- optional context-threshold recommendation via `min_context_length`

Implication:

- the scaffold must still leave enough structure to support a coarse curve reading
- but if explicit context-threshold recommendation is the purpose, full coverage is safer even at low budget

### 4. Current repo guidance already limits scaffolding to this one special case

The current ACPM chain already established:

- ordinary selected families should keep full YAML value coverage
- only `NGL_sweep` at `1x` is currently eligible for value scaffolding

Implication:

- this pass should optimize for clarity and auditability over cleverness

## Candidate Scaffold Models Considered

### 1. No scaffold at all

Meaning:

- always run full `NGL_sweep` values

Assessment:

- safest
- but leaves too much time savings on the table for the one v1 exception we explicitly allowed

### 2. Very sparse scaffold

Examples:

- `[10, 50, 999]`
- `[10, 40, 999]`

Assessment:

- reject

Why:

- too few points for a meaningful coarse curve
- too high an interior-optimum miss risk
- too thin for diminishing-returns interpretation

### 3. Adaptive scaffold by VRAM tier

Meaning:

- choose different subsets based on GPU VRAM or model fit guesses

Assessment:

- reject for v1

Why:

- comments in the YAML mention VRAM-tier examples, but they are not the live committed execution contract
- this would reintroduce a second applicability-like system
- too easy to overfit to one machine/model class

### 4. Fixed every-other-step scaffold plus sentinel

Meaning:

- choose every other committed step and retain `999`

Assessment:

- best v1 fit

Why:

- simple and globally explainable
- preserves low, middle, and upper regions of the committed ladder
- auditable and deterministic

## Recommended v1 `NGL_sweep` Scaffold Policy

### Exact scaffold

Recommended scaffold:

- `[10, 30, 50, 70, 90, 999]`

Selection rule:

- take every other ordinary ordered ladder value from the current committed list
- always retain the `999` full-offload sentinel

### Why this exact subset

It preserves:

- low edge:
  - `10`
- coarse interior sweep:
  - `30`
  - `50`
  - `70`
- upper non-sentinel edge:
  - `90`
- full-offload sentinel:
  - `999`

It avoids:

- invented values
- interpolated values
- machine-specific branch tables
- interior-optimum prediction logic

It is also easy to explain in audit/history language:

- “ACPM used the fixed `1x` NGL scaffold: every other committed ladder step plus `999`.”

## Fixed vs Conditional Policy

### Recommended v1 answer

Use one fixed global scaffold for the current committed `NGL_sweep` family.

Do not vary it by:

- profile
- GPU VRAM tier
- current telemetry noise
- model file size
- guessed fit or guessed optimum

### One small explicit condition that may disable the scaffold

The scaffold may be disabled, forcing full coverage, when:

- `min_context_length` is non-null for the effective campaign definition

Reason:

- current report semantics use the tested table to choose the fastest config that still meets the required context threshold
- coarse subsetting here would raise the chance of missing the true best qualifying NGL

This is a small, explicit, repo-grounded condition tied to current human-facing recommendation semantics, not a heuristic prediction system.

## When the Scaffold Is Allowed

The scaffold is allowed only when all of the following are true:

- `NGL_sweep` is already applicable under the lower applicability layer
- repeat tier is `1x`
- the effective `NGL_sweep` values still match the current canonical ordered ladder
  - `[10, 20, 30, 40, 50, 60, 70, 80, 90, 999]`
- `oom_boundary_sweep` semantics are still active
- `min_context_length` is `null`
- ACPM is using scaffolding as planner-budget policy, not as a recommendation-strength shortcut

## When Full `NGL_sweep` Coverage Is Required

Full coverage is required when any of the following are true:

- repeat tier is `3x`
- repeat tier is `5x`
- `min_context_length` is non-null
- the committed `NGL_sweep` value ladder has changed from the current canonical list
- ordering cannot be guaranteed
- a future version adds new report or recommendation semantics that rely on a denser NGL curve

Recommended conservative fallback:

- if ACPM cannot prove scaffold safety cleanly, use full `NGL_sweep` coverage

## YAML / Order / OOM Semantics That Must Be Preserved

- selected scaffold values must remain in ascending order
- `999` must remain the last selected value
- scaffold coverage must preserve the meaning of upward sweep toward the full-offload sentinel
- runner OOM-boundary behavior must remain unchanged
- scaffold policy must not reinterpret:
  - `oom`
  - `skipped_oom`
  - boundary confirmation

Important note:

- a scaffolded run may naturally produce fewer opportunities to mark tail values as `skipped_oom`
- that is acceptable only because the scaffold is explicitly narrower and must be labeled as such
- it must not be presented as if it had proved the same tail coverage as the full ladder

## What Must Be Recorded in Planner Metadata

Because `RunPlan` already records:

- `all_campaign_values`
- `selected_values`
- `coverage_fraction`

planner metadata does not need to duplicate the chosen values.

What it must record:

- that scaffold narrowing was applied
- that the policy used was the fixed `NGL_sweep` `1x` scaffold
- that this was planner-directed, not user-directed
- compact reason codes such as:
  - `ngl_fixed_scaffold_1x`
  - `repeat_tier_limits_scope`
  - `ordered_oom_boundary_preserved`

Recommended minimum extra provenance:

- scaffold policy ID
- scaffold policy version
- campaign family ID the scaffold was applied to

## What Would Make the Scaffold Too Risky for v1

Any of the following:

- fewer than 6 selected points on the current 10-value ladder
- dropping the `999` sentinel
- choosing values not present in committed YAML
- adapting the scaffold to inferred VRAM tiers or guessed fit classes
- adapting the scaffold differently per profile
- using measured partial results to refine the same `1x` scaffold mid-run
- using the scaffold when `min_context_length` is non-null
- presenting a scaffolded result as equivalent to full-curve coverage in reports or audit/history surfaces

## Risks of Getting This Wrong

### 1. Hidden interior-optimum loss

If the scaffold is too sparse, ACPM may miss the practical best NGL value and still look orderly.

### 2. Hidden drift into model-specific heuristics

If the scaffold starts varying by VRAM/model guesses, it stops being a simple budget policy and becomes a shadow applicability/search system.

### 3. Misleading OOM-boundary meaning

If scaffolded runs are described like full runs, users may overread what was actually proven about the upper tail.

### 4. Hard-to-audit behavior

If the scaffold rule is not globally fixed and clearly named, later compare/history surfaces will struggle to reconstruct why coverage changed.

## Downstream Implementation Consequences

- ACPM needs one explicit scaffold policy constant or registry entry for `NGL_sweep` `1x`
- the planner should only apply it after applicability has already selected `NGL_sweep`
- the planner should fall back to full NGL coverage automatically whenever the enabling conditions are not satisfied
- report/export/history surfaces should be able to say:
  - fixed scaffold used
  - full ladder not executed
  - recommendation remains provisional at that tier

## Questions Answered in This Pass

### 1. What exact scaffold values are recommended?

- `[10, 30, 50, 70, 90, 999]`

### 2. Should the scaffold be fixed globally or vary?

Fixed globally for the current committed ladder, with one small disabling condition:

- require full coverage when `min_context_length` is non-null

### 3. What YAML/order/OOM semantics must be preserved?

Ascending order, `999` as sentinel, and unchanged `oom_boundary_sweep` interpretation.

### 4. When should full values still be required?

- always at `3x` and `5x`
- at `1x` whenever context-threshold recommendation semantics are active
- whenever the committed ladder or ordering assumptions are no longer exactly the current ones

### 5. What must be recorded in planner metadata?

That the fixed `NGL_sweep` `1x` scaffold policy was applied, why it was allowed, and that it was planner-directed.

### 6. What makes the scaffold too risky for v1?

Adaptive heuristics, denser semantic claims than the evidence supports, omission of `999`, or any move toward guessed interior optima.

## Remaining Open Questions

- Should report/export surfaces name the scaffold directly as “fixed every-other-step ladder plus `999`,” or should they expose only the policy ID and the selected values already present in `RunPlan`?
- If the committed `NGL_sweep` ladder changes later, should ACPM refuse scaffolding until this policy is re-approved, or should there be a position-based fallback rule in a future version?

## Recommended Next Investigations

- `ACPM-NGL-report-and-audit-wording-TARGET-INVESTIGATION.md`
- `ACPM-scaffold-policy-versioning-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`
