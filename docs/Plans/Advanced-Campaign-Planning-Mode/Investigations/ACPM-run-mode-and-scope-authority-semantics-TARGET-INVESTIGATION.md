# ACPM Run Mode and Scope Authority Semantics Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 run-mode truth and scope-authority semantics only

## Outcome

Recommended v1 semantic model:

- keep `RunPlan` as the execution-truth object
- keep ACPM planner identity outside `RunPlan`
- add a bounded, generic scope-authority truth to `RunPlan`
- do not reuse current `custom` semantics for planner-directed ACPM narrowing
- do not create ACPM-specific run-mode values just to carry planner identity

Minimum durable v1 policy:

- `run_mode` should describe execution depth / repetition semantics
- partial-vs-full coverage should come from actual scope facts already in `RunPlan`
  - `selected_values`
  - `all_campaign_values`
  - `coverage_fraction`
  - `untested_values`
- who selected that scope should be captured separately as a generic scope-authority concept in `RunPlan`

Recommended generic values:

- `system_defined`
- `user_directed`
- `planner_directed`

Bottom line:

- ACPM partial scope is not current `custom`
- metadata-only is not enough
- the cleanest repo fit is a two-axis truth model:
  - execution depth via `run_mode`
  - scope authority via a separate `RunPlan` field

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/run_plan.py`
- `src/runner.py`
- `quantmap.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/trust_identity.py`

Supporting docs inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-plan-contract-TARGET-INVESTIGATION.md`
- `docs/Design Memo's/Advanced-Campaign-Planning-Mode-ADR/Adaptive-Campaign-Planning-Mode-v1-Design.md`

Repo-governance surfaces inspected:

- `.agent/README.md`
- `.agent/policies/architecture.md`

Validation used:

- targeted source inspection only
- no product-code changes
- no broad test theater; this pass is semantics and ownership mapping

## Current Run-Mode and Scope Semantics

### 1. `run_mode` currently bundles depth and scope meaning together

`src/run_plan.py` explicitly defines:

- `full`
  - complete campaign
  - all values
  - full intended schedule
- `standard`
  - complete campaign
  - all values
  - reduced repetition
- `quick`
  - complete campaign
  - all values
  - shallow repetition
- `custom`
  - user-directed exact scope
  - targeted run
  - honest about what was and was not tested

That means current repo semantics are not just about schedule depth. They also encode:

- whether coverage is full or partial
- whether the partiality was user-directed

### 2. Current scope distinction is hard-wired around CLI intent

Today the repo distinguishes:

- user-directed partial scope
  - `--values`
  - resolves to `run_mode="custom"`
  - gets custom effective run IDs like `__v30_80`
  - gets targeted/sparse wording
  - gets `filter_overrides={"min_valid_warm_count": 1}`
- system-defined full-coverage reduced-depth scope
  - `--mode quick`
  - `--mode standard`
  - both imply all campaign values
  - both get namespaced effective IDs like `__quick` and `__standard`
- default full coverage
  - no `--mode` and no `--values`
  - resolves to `full`

The CLI also enforces that `--mode` and `--values` are mutually exclusive.

Repo meaning:

- `--mode` means "choose a depth for the full campaign value list"
- `--values` means "user chose a subset"

### 3. Current user-facing wording depends on that bundle being true

`src/report.py`, `src/report_campaign.py`, validation, and dry-run all encode:

- `custom` means user-directed subset
- `quick` means complete coverage, broad but shallow
- `standard` means complete coverage, reduced repetition
- `full` means complete coverage, highest-confidence

This is not only cosmetic. The wording influences:

- winner labels
  - "best tested config" vs "winner"
- recommendation strength
- scope caveats
- claims about coverage
- audit/history interpretation of what kind of run occurred

### 4. Other restricted execution forms are not first-class scope-authority modes

Other repo behaviors exist, but they do not currently define new scope-authority categories:

- `resume`
  - re-entry behavior, not scope authority
- baseline override / namespaced lab roots
  - identity/environment choice, not scope authority
- YAML or mode-level filter overrides
  - scoring viability behavior, not execution scope
- runtime early exits like OOM boundary
  - execution outcome, not planned scope authority

So today there is only one first-class partial-scope authority:

- user-directed `custom`

## Candidate Semantic Models Considered

### 1. Reuse existing `custom` semantics for ACPM partial scope

Meaning:

- planner-directed subset execution would still be labeled `custom`

Assessment:

- reject

Why it is unsafe:

- current `custom` explicitly means user-directed scope
- current `custom` also carries sparse-data behavior and wording
- reports would incorrectly say the user chose the subset
- history would blur planner choice with user choice
- `custom` currently relaxes `min_valid_warm_count` in a way ACPM may not always want

### 2. Add ACPM-specific run-mode values

Examples:

- `adaptive`
- `planner_targeted`
- `acpm_partial`

Assessment:

- reject for v1

Why it is unsafe:

- it mixes planner identity into execution mode
- it duplicates meaning that should live in adjacent ACPM metadata
- it would spread ACPM-specific branching across runner/report/history surfaces
- it weakens the current contract rule that `RunPlan` should stay generic and engine-facing

### 3. Encode the truth only in adjacent metadata

Meaning:

- leave `RunPlan` unchanged
- let ACPM sidecar metadata explain planner-directed partial scope

Assessment:

- reject

Why it is insufficient:

- live runner, validate, dry-run, and report surfaces currently branch on `RunPlan` semantics directly
- `run_plan_json` is persisted as run-start identity
- if `RunPlan` still says `custom`, history and reports will be wrong before adjacent metadata is ever consulted

### 4. Extend run-mode semantics to include planner-directed partial scope

Meaning:

- broaden `run_mode` itself to encode both depth and scope authority for ACPM

Assessment:

- better than metadata-only
- still not the cleanest model

Why it is risky:

- it keeps two semantic axes fused into one field
- it would force growing mode taxonomies as new authorities appear
- it encourages downstream code to keep treating a single mode token as full truth

### 5. Add a separate scope-authority concept and keep planner identity adjacent

Meaning:

- `run_mode` remains execution-depth truth
- coverage remains derivable from actual selected-vs-all facts
- scope authority becomes its own generic field in `RunPlan`
- ACPM profile/policy stays in adjacent metadata

Assessment:

- best v1 fit

Why it works:

- separates execution shape from who chose it
- keeps planner identity out of the engine-facing object
- gives report/history surfaces enough truth to avoid lying

## Recommended v1 Run-Mode / Scope-Authority Policy

### Core policy

Use a two-axis truth model.

Axis 1:

- `run_mode` = resolved execution depth / repetition semantics

Axis 2:

- `scope_authority` = who selected the actual scope

Coverage truth:

- derived from `selected_values`, `all_campaign_values`, `coverage_fraction`, and `untested_values`

Planner identity:

- remains in adjacent ACPM metadata

### Recommended semantic reading

For existing manual flows:

- `full` + `system_defined` + full coverage
  - current Full meaning
- `standard` + `system_defined` + full coverage
  - current Standard meaning
- `quick` + `system_defined` + full coverage
  - current Quick meaning
- `custom` + `user_directed` + partial coverage
  - current Custom meaning

For ACPM partial flows:

- repetition tier resolves to execution depth
- coverage is partial because selected values/configs are a subset
- scope authority is `planner_directed`
- ACPM profile/policy remains outside `RunPlan`

Most important constraint:

- ACPM partial scope must not be represented as "user-directed custom" when the planner chose it

### Why this is the minimum durable solution

It preserves:

- honest execution truth
- honest user-facing wording
- clean audit/history meaning
- repo fit with the existing `RunPlan`-centered contract

It also avoids:

- ACPM-specific mode proliferation
- planner identity leaking into execution mode
- metadata-only truth that arrives too late to fix runner/report semantics

## What Should Live in `RunPlan` vs Adjacent Metadata

### In `RunPlan`

Keep only generic execution-truth semantics:

- `run_mode`
- actual selected scope
- actual schedule
- coverage facts
- generic scope authority

Recommended new truth inside `RunPlan`:

- `scope_authority`

Recommended meaning:

- `system_defined`
  - scope came from built-in engine mode behavior over the full campaign
- `user_directed`
  - scope was narrowed by explicit user choice
- `planner_directed`
  - scope was narrowed by ACPM planner logic before execution

### In adjacent metadata

Keep planner identity and planner reasoning outside `RunPlan`:

- ACPM enabled/planner identity
- ACPM profile
- planner policy
- planner rationale
- planner-stage omissions or narrowing rationale

Rule:

- if it answers "which planner and why?" it belongs outside `RunPlan`
- if it answers "what actually ran, and who selected that scope?" it belongs in `RunPlan`

## Risks of Getting This Wrong

### 1. Misleading user-intent history

If ACPM partial scope is labeled `custom`, the repo will say the user chose a subset when they did not.

### 2. Methodology drift by semantic leakage

If ACPM identity is pushed into run modes, planner identity starts to look like part of execution truth or methodology truth.

That would blur:

- execution semantics
- planner semantics
- governed scoring semantics

### 3. Unsafe wording drift across reports

Current report logic assumes:

- `custom` => best among user-tested subset
- `quick` / `standard` => all values were tested

If ACPM partial runs reuse those labels without a new authority distinction, human-facing artifacts will become misleading.

### 4. Metadata-only truth that cannot correct live surfaces

If scope authority exists only beside `RunPlan`, validate/dry-run/report paths that use `RunPlan` directly will still tell the wrong story.

## Downstream Implementation Consequences

### 1. This requires a bounded `RunPlan` adjustment, not metadata-only

At minimum, `RunPlan` needs a generic scope-authority truth because current live surfaces already depend on it for wording and history.

### 2. Current `mode_label` / `mode_description` can no longer be treated as complete truth by themselves

Once ACPM exists, those labels are only truthful when interpreted together with:

- scope authority
- actual coverage

### 3. Runner validation and dry-run wording will need the same two-axis interpretation

These surfaces currently encode:

- `custom` = user-directed sparse subset
- `quick` / `standard` = full coverage

That logic will need to branch on scope authority plus actual scope facts, not run mode alone.

### 4. Report and export surfaces are affected because history currently persists only `run_mode` plus the run-plan snapshot

The good news:

- `trust_identity` already loads `run_plan_json`
- adding a generic scope-authority truth to `RunPlan` will automatically give history/export surfaces a durable execution-truth hook

## Questions Answered in This Pass

### 1. What do current run-mode and scope semantics mean today?

They currently bundle:

- execution depth
- coverage truth
- and, in the `custom` case, user authority

### 2. Where does the repo currently distinguish user-directed partial scope, system-defined modes, and other restricted execution?

It clearly distinguishes:

- `custom` for user-directed subset scope
- `quick` / `standard` / `full` for built-in full-coverage modes

Other restrictions like resume, baseline override, and filter overrides are not treated as first-class scope-authority semantics.

### 3. Why does ACPM partial coverage create semantic pressure?

Because it introduces a new truth:

- partial coverage chosen by the planner, not the user

The current model has no honest place for that distinction.

### 4. What candidate representations were considered?

Considered:

- reuse `custom`
- add ACPM-specific run modes
- metadata-only truth
- broaden run-mode semantics
- separate scope-authority concept

### 5. Which options would blur user intent, planner intent, or execution truth?

Unsafe:

- reusing `custom`
- ACPM-specific run modes
- metadata-only truth

### 6. What is the minimum durable v1 solution?

Minimum durable solution:

- keep `RunPlan`
- add generic scope authority to it
- keep planner identity adjacent
- derive full-vs-partial coverage from actual selected-vs-all facts

### 7. Does this require a bounded `RunPlan` adjustment, a metadata-only solution, or both?

It requires:

- a bounded `RunPlan` adjustment
- plus adjacent planner metadata for ACPM identity

Metadata-only is not enough.

### 8. What downstream surfaces are affected?

Affected:

- `src/run_plan.py`
- `src/runner.py`
- `src/report.py`
- `src/report_campaign.py`
- historical identity via `src/trust_identity.py`
- export/history surfaces that consume `run_plan_json`

### 9. What is the best recommended v1 policy?

Best policy:

- two-axis truth model
- `run_mode` for depth
- generic `scope_authority` for who chose scope
- planner identity outside `RunPlan`

## Remaining Open Questions

### 1. Should legacy `custom` remain as a literal run mode or eventually become a derived presentation label?

This is worth a follow-up, but it does not block the semantic conclusion of this pass.

### 2. Does ACPM ever need planner-directed full coverage in v1, and if so, should that still carry `planner_directed` authority even when `coverage_fraction == 1.0`?

This is a smaller follow-up semantics question rather than a blocker to the main model.

## Recommended Next Investigations

- `ACPM-legacy-custom-mode-compatibility-TARGET-INVESTIGATION.md`
- `ACPM-planner-directed-full-coverage-semantics-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
