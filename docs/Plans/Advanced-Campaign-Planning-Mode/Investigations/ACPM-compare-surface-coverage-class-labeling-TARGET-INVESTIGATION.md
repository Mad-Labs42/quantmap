# ACPM Compare Surface Coverage Class Labeling Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 compare/report-history treatment of scaffolded vs full-ladder `NGL_sweep` evidence only

## Outcome

Recommended v1 policy:

- give compare/history a small explicit NGL coverage-class distinction rather than leaving scaffolded and full-ladder evidence implicit
- keep that distinction outside methodology compatibility grading
- render it as a dedicated compare-scope field plus a short limitation note when the compared runs differ
- preserve exact selected NGL values structurally for reconstruction, but only render them side by side in the human compare report when they are relevant

Best v1 compare model:

- preserve, per run:
  - `ngl_coverage_class`
  - `selected_ngl_values`
  - `coverage_authority`
  - optional scaffold label/policy ID when the class is `fixed_1x_scaffold`
- show a compact side-by-side coverage-class row in the compare context section
- show exact selected ladders side by side only when:
  - the coverage classes differ, or
  - either run is not `full_ladder_coverage`
- treat coverage-class difference as a compare limitation note, not as methodology mismatch and not as a second recommendation system

Strongest repo-grounded reason:

- current compare logic is methodology-first and winner-first. Without a separate coverage-class disclosure, scaffolded and full-ladder NGL evidence will be flattened into the same compare surface even though the repo already treats tested-scope truth as load-bearing.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/compare.py`
- `src/report_compare.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/run_plan.py`
- `src/trust_identity.py`
- `src/export.py`
- `configs/campaigns/NGL_sweep.yaml`

Supporting ACPM investigations inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-NGL-scaffold-subset-policy-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-NGL-report-and-audit-wording-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-trust-output-and-handoff-surfaces-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-recommendation-status-policy-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-caveat-code-severity-policy-TARGET-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`

Validation used:

- targeted source/doc inspection
- one light proportional verification step confirming where compare semantics, selected-value scope, and methodology/winner language currently live
- no product-code edits

## Current Compare / History Constraints

### 1. Compare is currently methodology-first and winner-first

`src/compare.py` currently builds comparison truth around:

- methodology compatibility
- environment deltas
- shared-config deltas
- winner-to-winner deltas
- elimination reach

`src/report_compare.py` then renders:

- a comparison scope table
- methodology warnings
- winner side-by-side metrics
- shared-config deltas
- an interpretation summary

Implication:

- compare currently has no native place for distinguishing scaffolded and full-ladder NGL evidence
- without a new bounded field, different coverage classes will be silently flattened

### 2. Methodology warnings are the wrong bucket for coverage-class difference

`src/compare.py` grades methodology by snapshot completeness, registry version match, and anchor drift. `src/report_compare.py` renders those as compatibility warnings.

Implication:

- NGL coverage class should not be injected into methodology mismatch logic
- doing so would falsely imply that scaffold use is methodology drift rather than execution-scope difference

### 3. The repo already preserves selected scope truth in `RunPlan`

`src/run_plan.py` and the persisted `run_plan_json` snapshot preserve:

- full campaign values
- selected values
- run mode

`src/trust_identity.py` loads that snapshot-first run-plan truth for later historical use.

Implication:

- compare/history does not need a giant second state system to reconstruct selected NGL ladders
- the missing seam is labeling and projection, not primary truth storage

### 4. Existing report surfaces already use bounded scope caveats

`src/report.py` and `src/report_campaign.py` already distinguish:

- custom subset truth
- quick full-coverage but shallow truth
- standard full-coverage but reduced-depth truth
- full highest-confidence truth

Implication:

- compare should follow the same style: compact scope disclosure plus limited wording adjustments
- compare should not become a giant methodology explainer

### 5. Current export/report-history surfaces can reconstruct scope, but not coverage class cleanly

`src/export.py` already writes structured metadata and `run_plan_json` already preserves selected values, but there is no dedicated compare-facing notion of:

- `full ladder coverage`
- `fixed 1x scaffold coverage`
- `ordinary custom subset coverage`

Implication:

- v1 needs one stable coverage-class distinction, otherwise later history/audit consumers must reverse-engineer intent from raw values alone

## Candidate Compare Labeling Models Considered

### 1. No explicit compare labeling

Meaning:

- keep compare winner/methodology-only
- rely on selected values elsewhere for forensic reconstruction

Assessment:

- reject

Why:

- too easy for normal compare reading to overstate equivalence
- later audit remains possible but human-facing compare becomes misleading

### 2. Methodology-warning reuse

Meaning:

- report coverage-class differences as methodology warnings

Assessment:

- reject

Why:

- scaffold use is not methodology truth
- this would collapse scope difference into the wrong trust lane

### 3. Compact class note only

Meaning:

- add a single `coverage class differs` note
- do not render exact selected ladders in compare

Assessment:

- too thin by itself

Why:

- sufficient for quick reading
- insufficient for bounded audit reconstruction inside the compare artifact itself
- does not let readers see how narrow the difference actually was

### 4. Full side-by-side ladder tables by default

Meaning:

- always render exact selected ladders for both campaigns in compare

Assessment:

- reject for v1 default

Why:

- too chatty for normal compare usage
- turns compare into a second report

### 5. Coverage-class field plus conditional ladder detail

Meaning:

- always show compact coverage class
- show exact selected ladders only when relevant

Assessment:

- best v1 fit

Why:

- keeps compare readable
- preserves enough context for audit-friendly interpretation
- avoids building a compatibility matrix or giant prose layer

## Recommended v1 Compare-Surface Coverage-Class Policy

### Core policy

For NGL-relevant compare/history surfaces, preserve and expose:

- whether each run had:
  - `full_ladder_coverage`
  - `fixed_1x_scaffold_coverage`
  - `custom_subset_coverage`
- the selected NGL values used by each run
- whether the narrowing authority was:
  - planner-directed fixed scaffold
  - user-directed custom subset
  - ordinary full campaign scope

### Minimum structured distinction compare/history must preserve

Minimum durable v1 fields:

- `ngl_coverage_class`
- `selected_ngl_values`
- `coverage_authority`

Recommended extra field when scaffolded:

- `ngl_scaffold_policy_id` or equally stable short scaffold label

Why this is the minimum safe set:

- `ngl_coverage_class` gives the compact interpretive bucket
- `selected_ngl_values` preserves exact reconstruction
- `coverage_authority` distinguishes planner-budget scaffolding from user-directed custom scope

### Human-facing compare rendering rule

Recommended compare rendering:

- always show one compact side-by-side row:
  - `NGL coverage class | Full ladder coverage | Fixed 1x scaffold coverage`
- show exact selected ladders in one additional compact row only when:
  - the classes differ, or
  - either side is not full coverage

This is better than either extreme:

- better than note-only because it preserves concrete evidence
- better than full tables because it stays bounded

## How to Distinguish Scaffolded vs Custom Subset Coverage

### Policy

The human compare surface should not force readers to infer intent from values alone.

Best v1 distinction:

- `fixed 1x scaffold coverage` means planner-directed fixed ACPM subset
- `custom subset coverage` means user-directed exact-scope subset
- `full ladder coverage` means all committed ladder values were tested for that run mode

### Why values alone are not enough

The ladder `[10, 30, 50, 70, 90, 999]` could theoretically appear as a raw subset without telling the reader whether it was:

- the governed ACPM fixed scaffold
- a user custom run
- some future internal subset

Implication:

- compare/history needs explicit class plus authority, not just values

## When Coverage-Class Difference Should Affect Comparison Wording

### What it should affect

Coverage-class difference should soften:

- winner-comparison wording
- NGL-specific comparison claims
- interpretation phrasing about direct equivalence

Recommended safe pattern:

- "The compared runs differ in NGL coverage class, so NGL-specific conclusions are directional rather than directly equivalent."

### What it should not affect

Coverage-class difference should not automatically become:

- methodology mismatch
- score incompatibility
- recommendation-status logic
- a second compare scoring system

### Strength rule

Best v1 policy:

- if coverage classes match, normal compare wording may proceed
- if coverage classes differ, compare should keep the same methodology grade but add a scope-limitation note and avoid strongest equivalence language

Practical implication:

- "winner changed" is still reportable
- "winner changed under directly equivalent NGL coverage" is not

## Field vs Note vs Warning Policy

### Recommended classification

Coverage class should be:

- a dedicated compare field
- plus a limitation note when the compared classes differ

It should not be:

- a methodology warning by default
- a recommendation caveat
- a free-floating prose paragraph with no structured anchor

### When it should escalate

Coverage-class difference becomes warning-like only if compare cannot reconstruct the selected values or authority cleanly.

Reason:

- the real trust problem then becomes audit weakness, not merely scope difference

## Safest v1 Human-Facing Wording Pattern

### Preferred wording

Recommended bounded pattern in the compare report:

- `NGL coverage class: fixed 1x scaffold coverage vs full ladder coverage`
- `Selected NGL values: 10, 30, 50, 70, 90, 999 vs 10, 20, 30, 40, 50, 60, 70, 80, 90, 999`
- `Interpretation note: NGL evidence classes differ. Compare winner and shared-config findings normally, but treat NGL-specific equivalence claims as limited to the tested ladders.`

### Terms to prefer

- `coverage class`
- `fixed 1x scaffold coverage`
- `custom subset coverage`
- `full ladder coverage`
- `selected NGL values`
- `scope limitation`

### Terms to avoid

- `methodology mismatch` for scaffold/full differences alone
- `equivalent NGL evidence` when classes differ
- `fully comparable` with no qualification
- `validated against the same ladder` unless both ladders are actually the same

## History / Audit Preservation Guidance

### What history surfaces must preserve

For later compare and audit reconstruction, history-grade surfaces should preserve:

- coverage class
- selected values
- authority
- scaffold label or policy ID when applicable

### What should stay derived

Human compare wording should stay derived from those fields.

Do not persist:

- long interpretive prose
- alternate winner authority
- a separate compatibility matrix

## Risks of Getting This Wrong

- scaffolded and full-ladder NGL evidence will appear more interchangeable than they are
- compare will imply direct equivalence where only directional comparison is justified
- later audit will have to reverse-engineer intent from raw values and may fail to distinguish planner-directed scaffold from custom subset
- coverage class could accidentally drift into a second methodology or recommendation system if it is placed in the wrong lane
- over-rendering selected ladders everywhere will make compare noisy and reduce clarity

## Downstream Implementation Consequences

- compare needs a compact NGL coverage-class seam in its structured result
- compare markdown needs one new context row and one conditional selected-values row
- history/export surfaces need a stable way to reconstruct class, selected values, and authority
- no broad compatibility matrix is required
- no giant prose section is required

## Questions Answered in This Pass

### Should compare show only a compact note or also exact selected ladders

- both, but bounded: always show compact class; show exact ladders only when classes differ or either side is non-full

### What minimum structured distinction must compare/history preserve

- `ngl_coverage_class`, `selected_ngl_values`, and `coverage_authority`

### How should planner-directed scaffold and user-directed custom subset be distinguished

- with explicit coverage class and authority, not by values alone

### When should coverage-class difference affect wording strength

- when compare makes NGL-specific equivalence claims; it should soften those claims but not rewrite methodology grade

### Should coverage-class difference be treated as a warning, limitation, note, or separate field

- a dedicated field plus limitation note; warning only if reconstruction is weak or missing

### What is the safest v1 human-facing wording pattern

- compact class disclosure, conditional value row, and one short interpretation note about limited NGL equivalence

## Remaining Open Questions

- whether compare should render the selected-value row only when classes differ, or whenever either side is non-full even if both are the same scaffold class
- whether the scaffold field should expose a human-readable label only, or both a label and a stable policy ID
- whether future non-NGL ACPM family subsets should reuse the same `coverage_class` pattern or get a more general scope-class surface later

## Recommended Next Investigations

- `ACPM-history-surface-scope-and-coverage-projection-TARGET-INVESTIGATION.md`
- `ACPM-compare-result-structure-scope-limitation-policy-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`
