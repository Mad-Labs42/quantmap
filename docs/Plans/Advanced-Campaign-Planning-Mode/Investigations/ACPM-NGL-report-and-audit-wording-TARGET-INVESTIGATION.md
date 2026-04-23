# ACPM NGL Report and Audit Wording Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 wording and disclosure policy for scaffolded `NGL_sweep` runs only

## Outcome

Recommended v1 policy:

- disclose scaffolded `NGL_sweep` use explicitly anywhere a human or machine consumer could otherwise mistake it for full ladder coverage
- treat the fixed `1x` scaffold as a coverage-class disclosure, not as methodology truth, not as a recommendation authority, and not as a profile-specific scoring rule
- use short human-facing wording that says the run used a coarse ordered ladder sample, while preserving structured metadata that makes scaffolded and full-ladder evidence reconstructable in compare/history/audit flows
- keep recommendation status and caveat policy as the primary claim-control surfaces; scaffold wording may explain and cap claims, but must not become a shadow recommendation system
- preserve selected tested NGL values plus one stable scaffold identifier or policy label in audit/export surfaces, so later review can distinguish:
  - full ladder coverage
  - fixed `1x` scaffold coverage
  - any ordinary custom subset run

Best v1 wording posture:

- report surfaces should say "fixed `1x` scaffold" and "coarse ordered ladder sample"
- report surfaces should not say or imply "full NGL sweep", "complete ladder coverage", or "validated optimal NGL" for scaffolded runs
- compare/history surfaces should preserve scaffold-vs-full evidence class and should not silently treat them as interchangeable
- export/metadata should carry a compact structured disclosure plus the selected values already reflected by execution truth
- machine-handoff-adjacent wording, if present at all, should remain subordinate to recommendation status and should never imply stronger NGL validation than the evidence supports

Strongest repo-grounded reason:

- the repo already distinguishes between tested-subset truth, run-depth truth, methodology truth, and recommendation confidence. If scaffolded `NGL_sweep` wording blurs those lanes, ACPM will overstate coverage and quietly create compare/history drift.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `configs/campaigns/NGL_sweep.yaml`
- `src/runner.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/compare.py`
- `src/report_compare.py`
- `src/explain.py`

Supporting ACPM investigations inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-NGL-scaffold-subset-policy-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-trust-output-and-handoff-surfaces-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-planner-policy-and-repeat-tier-matrix-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-applicability-and-pruning-rule-catalog-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-recommendation-record-contract-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-recommendation-status-policy-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-caveat-code-severity-policy-TARGET-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`

Validation used:

- targeted source/doc inspection
- one light proportional verification step confirming the live NGL ladder, ordered/OOM-boundary semantics, and current report/export/compare wording surfaces
- no product-code edits

## Current NGL / Trust-Language / Compare / Export Constraints

### 1. The live `NGL_sweep` contract is an ordered ladder with OOM-boundary semantics

`configs/campaigns/NGL_sweep.yaml` currently defines:

- `values: [10, 20, 30, 40, 50, 60, 70, 80, 90, 999]`
- `oom_boundary_sweep: true`
- `min_context_length: null`

`src/runner.py` validates ascending order and uses that order to confirm an OOM boundary and mark later points `skipped_oom`.

Implication:

- wording must respect that the scaffold is still sampling an ordered ladder, not inventing a different campaign
- wording must not imply full ladder exhaustiveness when only the fixed scaffold was run

### 2. The repo already has strong precedent for subset-truth wording

`src/report.py` and `src/report_campaign.py` already distinguish:

- custom subset truth: best among tested values only
- quick depth truth: broad but shallow
- standard depth truth: development-grade
- full depth truth: strongest winner language

They already warn when untested values may change the result.

Implication:

- scaffolded NGL wording should extend an existing repo pattern, not introduce a new rhetorical framework
- the correct tone is "top tested within this disclosed coverage class," not "smart planner found the right answer"

### 3. Current NGL reporting assumes a curve, but not necessarily a full proof

`src/report.py` already treats `NGL_sweep` as a ladder/curve surface, with ordered rows, diminishing-returns analysis, and optional context-threshold recommendation when `min_context_length` is set.

Implication:

- scaffold wording must preserve the idea that the ladder was sampled in order
- but if the ladder was scaffolded, the wording must downgrade any claim from full curve coverage to coarse curve sampling

### 4. Compare/report surfaces do not currently preserve coverage-class distinctions

`src/report_compare.py` focuses on winner shifts, methodology compatibility, shared-config intersections, and environment deltas. It does not currently preserve a distinction between:

- full ladder evidence
- scaffolded ladder evidence
- arbitrary custom subsets

Implication:

- ACPM v1 needs a coverage-class disclosure policy or compare/history will falsely flatten materially different evidence classes

### 5. `metadata.json` is already the natural export/audit projection surface

`src/export.py` describes `metadata.json` as the authoritative structured provenance/scoring export for campaign identity, methodology provenance, ranking outputs, environment summary, artifacts, and warnings/limitations.

Implication:

- scaffold disclosure should project into structured metadata here
- but it should still derive from execution truth plus ACPM policy metadata rather than becoming a shadow methodology record

### 6. Prior ACPM findings already constrain the wording

The current ACPM chain already settled that:

- the fixed `1x` scaffold is a planner-budget shortcut only
- it is not applicability truth
- it is not a scoring shortcut
- full `NGL_sweep` coverage is still required at `3x` and `5x`
- full `NGL_sweep` coverage is still required at `1x` when `min_context_length` is non-null
- recommendation status and caveat policy remain the primary claim-control surfaces

Implication:

- wording must disclose scaffold use without turning the scaffold into a second recommendation policy or a second scoring system

## Candidate Wording / Disclosure Models Considered

### 1. Value-list-only disclosure

Meaning:

- rely on selected NGL values alone
- do not add any explicit scaffold wording

Assessment:

- reject

Why:

- too easy for human readers to miss
- too thin for compare/history consumers
- does not distinguish fixed ACPM scaffold use from arbitrary custom subsetting

### 2. Human prose only

Meaning:

- add reader-facing disclosure lines
- do not preserve a stable structured scaffold label or evidence-class marker

Assessment:

- reject

Why:

- too weak for audit/history/compare reconstruction
- encourages later semantic drift across surfaces

### 3. Structured policy ID only

Meaning:

- preserve only a stable scaffold/policy identifier
- let readers infer meaning elsewhere

Assessment:

- reject for human-facing surfaces

Why:

- too opaque for reports
- makes trust language feel magical or internal

### 4. Short disclosure plus structured coverage marker

Meaning:

- human-facing surfaces get a short plain-language disclosure line
- audit/export surfaces preserve a stable scaffold label or policy ID plus the selected values

Assessment:

- best v1 fit

Why:

- human readers get clear truth-language
- compare/history/audit can reconstruct what happened
- the wording stays bounded and does not become a prose-heavy shadow methodology

## Recommended v1 Scaffolded-NGL Wording Policy

### Core policy

For any scaffolded `NGL_sweep` run, surfaces should disclose three facts:

1. the run used the fixed ACPM `1x` NGL scaffold rather than full ladder coverage
2. the tested NGL values were a coarse ordered ladder sample
3. any NGL conclusion is limited to the sampled ladder and should not be phrased as if full ladder validation occurred

### Preferred terms

Use terms like:

- `fixed 1x scaffold`
- `coarse ordered ladder sample`
- `selected ladder values`
- `full ladder coverage` for the non-scaffold case
- `top tested NGL in this scaffolded run`
- `provisional` when recommendation status or caveat policy requires it

### Terms to avoid

Do not use:

- `full NGL sweep` for scaffolded runs
- `complete ladder coverage`
- `validated optimal NGL`
- `best NGL overall`
- `confirmed optimum`
- `full boundary coverage` unless the actual full ladder and OOM-boundary evidence justify that claim

### Policy on direct scaffold naming

Best v1 practice:

- human-facing surfaces should name the scaffold in plain language
- audit/export surfaces should preserve a short stable scaffold label or policy ID
- selected tested values should remain visible or reconstructable from execution/config artifacts

This is better than relying on values alone because it distinguishes:

- ACPM's fixed declared scaffold
- an arbitrary custom subset
- full ladder coverage

## Human-Facing Report Wording Guidance

### What report surfaces must disclose

At minimum, any human-facing surface that summarizes or interprets scaffolded `NGL_sweep` results should disclose:

- that a fixed `1x` scaffold was used
- that it sampled the ladder coarsely rather than covering the full ladder
- the tested values, either inline or in an adjacent table/list already present
- that stronger NGL coverage exists in the full-ladder case

### Recommended report-language pattern

Recommended v1 pattern near the NGL section or recommendation statement:

- "This run used the fixed ACPM `1x` NGL scaffold, a coarse ordered ladder sample rather than full ladder coverage."
- "Tested NGL values: `10, 30, 50, 70, 90, 999`."
- "Treat any NGL leader here as the top tested point in the scaffolded ladder, not as proof that the full ladder optimum has been validated."

### How it should affect recommendation phrasing

If scaffolded NGL contributes to a recommending status:

- recommendation wording should stay consistent with the status model
- scaffold wording should cap the NGL-specific claim, not replace the status

Safe pattern:

- "The recommended config includes the top tested NGL from the fixed scaffolded ladder sample."

Unsafe pattern:

- "ACPM identified the optimal NGL."

### Confidence wording

Scaffold wording should lower NGL-specific certainty language without inventing a second confidence system.

Best v1 rule:

- keep overall confidence and recommendation status in their existing authority lane
- add one bounded coverage disclosure line when scaffolding occurred
- if the recommendation already has provisional or validation caveats, scaffold wording should reinforce those limits rather than layering on a second independent verdict

## Compare / Audit / History Wording Guidance

### What these surfaces must preserve

Compare/history/audit surfaces should preserve enough information to answer:

- was this NGL evidence based on full ladder coverage or the fixed `1x` scaffold
- which ladder values were actually tested
- was scaffold use planner-directed rather than user-directed custom scope

### Recommended compare/history policy

Scaffolded and full-ladder NGL runs should not be treated as the same evidence class.

Best v1 disclosure model:

- show or preserve a compact coverage-class field such as:
  - `ngl_coverage: full_ladder`
  - `ngl_coverage: fixed_1x_scaffold`
  - `ngl_coverage: custom_subset`
- if a compare surface is human-readable, add a short note when the compared runs differ in NGL coverage class

Recommended compare wording:

- "NGL evidence class differs between these runs: one used the fixed `1x` scaffold and the other used full ladder coverage."

This matters because otherwise compare/history can incorrectly flatten:

- leader
- recommended
- validated

into one misleading claim sequence.

### Audit posture

Audit surfaces should be terse and reconstructable, not chatty.

Best v1 audit disclosure:

- preserve the scaffold label or policy ID
- preserve selected tested values
- preserve the fact that this was planner-budget narrowing, not applicability narrowing
- preserve the recommendation status/caveat outcome separately

## Export / Metadata Wording Guidance

### What export surfaces should own

Export/metadata should own the structured disclosure needed for reconstruction, not long explanatory prose.

Best v1 export policy:

- keep the selected tested values in execution/config truth
- add a compact structured scaffold disclosure projection
- optionally include one short human-readable disclosure string for downstream consumers that do not render richer context

### Recommended metadata shape direction

At minimum, export/metadata should preserve:

- whether scaffold coverage was used
- the stable scaffold label or policy ID
- the coverage class
- selected tested values, directly or by reference to the executed values already exported
- whether full ladder coverage was required but not used should never occur in valid v1 ACPM output, because those cases were already ruled out upstream

Recommended human-readable metadata wording:

- "NGL coverage used the fixed ACPM `1x` scaffold rather than full ladder coverage."

What not to do:

- do not restate methodology truth as if the scaffold were a scoring method
- do not add long narrative explanation blocks that compete with reports

## Machine-Handoff-Adjacent Wording Guidance

### General rule

The machine handoff should stay derived from recommendation status and recommendation record rules, not from NGL wording.

### v1 wording policy

If a machine-handoff-adjacent surface mentions scaffolded NGL at all:

- it should do so only as a bounded disclosure
- it should never imply that machine handoff itself upgrades the evidence class

Safe pattern:

- "The handoff reflects the recommended config selected from the tested scaffolded ladder sample."

Unsafe pattern:

- "The handoff contains the validated NGL setting."

### Ownership rule

Recommendation status remains the gate for whether handoff exists.

Scaffold wording may explain why a recommendation is provisional or limited, but it must not become an alternate handoff-allowance mechanism.

## Risks of Getting This Wrong

- thin wording will make scaffolded runs look equivalent to full-ladder NGL evidence
- vague wording will let planner-budget policy masquerade as applicability truth or methodology truth
- overly strong copy will collapse "leader", "recommended", and "validated" into one claim
- metadata that is too thin will make later compare/audit reconstruction unreliable
- metadata that is too verbose will create a shadow reporting system
- inconsistent wording across report, compare, and export surfaces will create hidden trust drift even if the underlying execution is correct

## Downstream Implementation Consequences

- report surfaces need one bounded disclosure seam for scaffolded `NGL_sweep` coverage
- compare/history surfaces need a compact NGL coverage-class distinction rather than pure winner-only comparison
- export/metadata needs a small structured projection for scaffold policy/coverage class
- recommendation/explain surfaces should read that disclosure as supporting context only, not as a new authority lane
- no new giant prose framework is required; the work is mostly about adding one consistent disclosure vocabulary and one compact structured evidence-class marker

## Questions Answered in This Pass

### What report surfaces must disclose when the fixed `1x` scaffold was used

- any surface summarizing or interpreting NGL results must say that fixed scaffold coverage was used and that it is not full ladder coverage

### What terms should and should not be used

- prefer `fixed 1x scaffold`, `coarse ordered ladder sample`, and `top tested NGL`
- avoid `full NGL sweep`, `validated optimal NGL`, and similar exhaustive language

### How to distinguish coarse sample from full coverage

- use a short disclosure line in human-facing reports and a stable coverage-class marker in structured surfaces

### How scaffold use should affect recommendation phrasing

- it should cap NGL-specific certainty and reinforce provisional/limited language when applicable, but recommendation status remains primary

### What compare/history surfaces must preserve

- the NGL coverage class, scaffold label/policy ID, and selected values or a reliable route to reconstruct them

### Whether surfaces should name the scaffold directly, use a policy ID, or rely only on values

- use both: plain-language naming for humans, stable label/policy ID for audit/export, and selected values for reconstructability

## Remaining Open Questions

- whether the compare surface should show only a compact `coverage class differs` note or also render the exact selected NGL ladders side-by-side
- whether the export surface should expose both a human-readable disclosure string and a structured scaffold field, or only the structured field plus selected values
- whether a dedicated scaffold-related caveat code is needed, or whether the coverage-class disclosure alone is sufficient in v1

## Recommended Next Investigations

- `ACPM-compare-surface-coverage-class-labeling-TARGET-INVESTIGATION.md`
- `ACPM-report-surface-recommendation-phrasing-alignment-TARGET-INVESTIGATION.md`
- `ACPM-export-metadata-projection-for-coverage-class-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`
