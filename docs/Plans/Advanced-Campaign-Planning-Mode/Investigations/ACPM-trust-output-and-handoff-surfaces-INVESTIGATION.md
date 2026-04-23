# ACPM Trust, Output, and Handoff Surfaces Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 trust/output/reporting/handoff surface model only

## Outcome

Recommended v1 surface model:

- keep ACPM trust-bearing state split across four ownership lanes:
  - execution truth in `RunPlan`, campaign/results tables, and existing campaign artifacts
  - methodology truth in persisted methodology snapshots
  - planner provenance in adjacent ACPM planning metadata
  - recommendation claim state in a separate ACPM recommendation record
- make human-facing surfaces read from those lanes instead of inventing new ACPM truth
- make machine handoff a derived serializer output from the recommendation record, never the recommendation authority itself
- keep `metadata.json` as the main structured export surface, but treat any ACPM section inside it as an export projection of persisted ACPM records, not the primary source record
- do not casually expand the current 4-artifact contract with a machine-handoff file until its output contract is explicitly decided

Best v1 surface posture:

- `campaign-summary.md` stays short and claim-controlled
- `run-reports.md` carries the fuller human-readable ACPM explanation
- `metadata.json` carries the structured export/audit projection
- `explain` stays derived and reader-oriented
- `compare` and audit surfaces stay methodology-first, with ACPM overlays only where the underlying methodology and recommendation records make them meaningful
- the machine handoff stays thin, derivative, and recommendation-status-gated

Strongest repo-grounded reason:

- the repo already treats methodology, artifacts, and report language as trust surfaces with explicit ownership. If ACPM blends planner identity, methodology weights, recommendation status, and machine handoff into one vague "smart result" layer, it will create hidden methodology drift and duplicate authority almost immediately.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `quantmap.py`
- `src/artifact_paths.py`
- `src/trust_identity.py`
- `src/export.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/explain.py`
- `src/compare.py`
- `src/report_compare.py`
- `src/audit_methodology.py`
- `src/runner.py`

Supporting ACPM investigations inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planning-metadata-schema-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-recommendation-record-contract-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-recommendation-status-policy-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-caveat-code-severity-policy-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-blast-radius-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-plan-contract-TARGET-INVESTIGATION.md`

Supporting trust/reporting docs inspected:

- `docs/MVP/quantmap_mvp_decisions_and_reporting_contract.md`
- `docs/AUDITS/4-11/Results-4-11/Audit-6.md`

Repo-governance surfaces inspected:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/policies/boundaries.md`

Validation used:

- targeted source/doc inspection
- one light proportional verification step after writing the report
- no product-code edits
- no broad validation theater

## Current Trust / Output / Reporting Surface Constraints

### 1. The repo already has a strict artifact contract

`src/artifact_paths.py` defines an approved 4-artifact campaign contract:

- `campaign-summary.md`
- `run-reports.md`
- `metadata.json`
- `raw-telemetry.jsonl`

It explicitly treats `scores.csv` as deprecated and folded into `metadata.json`.

Implication:

- ACPM should not smuggle a new machine-facing file into this contract without an explicit decision
- any new ACPM output seam has to respect that the repo intentionally narrowed formal outputs

### 2. `metadata.json` is already the machine-readable provenance/scoring artifact

`src/export.generate_metadata_json()` explicitly says `metadata.json` is the structured provenance and scoring record and the authoritative source for:

- campaign identity
- methodology/scoring provenance
- ranking outputs
- environment and telemetry summary
- artifact inventory
- warnings/limitations surfaced during the run

It already exports:

- methodology profile/version/weights/gates/anchors
- ranking winner, ranked configs, eliminated configs
- provenance source labels

Implication:

- if ACPM data is exported, `metadata.json` is the natural structured surface
- but it should project ACPM planning/recommendation records rather than becoming their only persistence home

### 3. Human-facing reports already separate short and detailed surfaces

`src/report.py` is intentionally compact and already claim-controls wording by run mode:

- custom: "best among tested," not a full recommendation
- quick: broad but shallow, confirm before deploying
- standard: development-grade, confirm before deploying
- full: strongest winner language

`src/report_campaign.py` is the detailed evidence report and already has strong natural seams for:

- methodology disclosure
- artifact index
- warnings/limitations
- resolved production commands

Implication:

- ACPM should layer onto the existing short-vs-detailed report split
- it should not create a second parallel "ACPM report" product in v1

### 4. The methodology surface is already stronger than the recommendation surface

`src/report_campaign._section_methodology()` already renders:

- pre-committed elimination filters
- experiment profile name/version
- methodology evidence label
- full six-metric scoring weight table
- anchor governance details

`src/trust_identity.py` treats methodology snapshots as the trust-bearing historical authority.

Implication:

- ACPM profile/governance detail belongs with methodology disclosure, not in planner prose
- recommendation surfaces must point back to methodology truth rather than restating weights/gates as their own authority

### 5. Explain is already a derived interpretation surface

`src/explain.py` reads winners and trust context, then derives:

- `High` / `Moderate` / `Caution`
- winner margin interpretations
- watchlist/risk text
- methodology evidence notes

It does not own historical methodology truth or campaign truth.

Implication:

- ACPM explain behavior should remain derived
- it should read recommendation status, caveats, methodology evidence, and planner provenance, then summarize
- it should not persist its own ACPM-specific verdict objects

### 6. Compare and audit are currently winner/methodology-first

`src/compare.py` and `src/report_compare.py` currently compare:

- winner shifts
- shared-config deltas
- environment changes
- methodology compatibility

But `src/audit_methodology.py` currently returns only:

- methodology version
- anchors/references
- methodology snapshot ID
- capture quality/source

It does not yet carry:

- profile name/version
- weights
- gates

Implication:

- ACPM will stress a pre-existing gap in compare/audit fidelity
- if ACPM profile differences matter, compare/audit cannot keep treating anchors/version as sufficient methodology identity

### 7. Machine-facing output does not yet have a safe dedicated seam

Current machine-adjacent surfaces are things like:

- `configs.variable_value`
- `configs.resolved_command`
- report Appendix C production commands

Those are not recommendation records and were not designed to carry ACPM claim semantics.

Implication:

- ACPM machine handoff must not be scraped from markdown or inferred from existing command surfaces
- it needs a deliberate serializer seam derived from ACPM recommendation state

## Candidate Surface Models Considered

### 1. Report-centric model

Meaning:

- make markdown reports the main ACPM truth carrier
- derive export, explain, and handoff from report content

Assessment:

- reject

Why:

- report markdown is narrative output, not durable structured authority
- would create fragile scraping logic and duplicate policy wording
- highest risk of shadow methodology and human/machine drift

### 2. Export-centric model

Meaning:

- persist ACPM state only inside `metadata.json`
- let reports and explain read from exported JSON

Assessment:

- better than report-centric
- still not enough

Why:

- `metadata.json` is currently a campaign export artifact, not clearly the underlying ACPM source record
- would blur source-of-truth persistence with export projection
- compare/history/audit should not depend on an export regeneration path for ACPM truth

### 3. Planner/recommendation records plus derived surfaces

Meaning:

- persist ACPM planning metadata and recommendation record as their own durable records
- project them into reports, export, explain, compare, and handoff surfaces

Assessment:

- best v1 fit

Why:

- preserves ownership boundaries already established in prior ACPM investigations
- lets each surface stay derived and purpose-specific
- gives compare/history/audit a stable structured basis

### 4. Machine-handoff-centric model

Meaning:

- let the llama.cpp variables file become the practical ACPM output
- treat human-facing surfaces as explanation around it

Assessment:

- reject

Why:

- machine handoff is intentionally thinner than the recommendation claim
- it cannot safely carry status, caveats, methodology provenance, or audit meaning
- would make the machine surface more authoritative than the trust surface

## Recommended v1 Surface Model

### Core ownership rule

Use this ownership split consistently across every ACPM surface:

- execution truth comes from `RunPlan`, campaign rows, scores, and existing campaign artifacts
- methodology truth comes from methodology snapshots and their exported projections
- planner provenance comes from ACPM planning metadata
- recommendation claim truth comes from the ACPM recommendation record
- machine handoff is a serializer output derived from the recommendation record only when status allows it

### Surface-by-surface policy

#### 1. CLI surfaces

Recommended v1 policy:

- keep ACPM behind existing QuantMap surfaces rather than inventing a second user-facing result universe
- `run` should still produce normal campaign artifacts
- `explain`, `compare`, and `export` should gain ACPM-aware reading behavior only after ACPM records exist

CLI ownership:

- CLI owns invocation and display routing
- CLI does not own ACPM semantics or recompute recommendation logic

What should stay out:

- no CLI-only ACPM truth flags that are not persisted elsewhere
- no status logic encoded only in terminal copy

#### 2. `campaign-summary.md`

Recommended v1 policy:

- add a small ACPM summary block only when the campaign has ACPM planning/recommendation records
- keep it short and claim-controlled

It should show:

- ACPM used or not used
- profile label
- recommendation status
- recommended config ID only when status recommends
- a one-line caveat summary
- machine-handoff availability or withholding note

It should not show:

- full weight vector
- full narrowing provenance
- full caveat catalog
- planner internals

Reason:

- this surface is the reader-friendly front door and should not become a methodology dump

#### 3. `run-reports.md`

Recommended v1 policy:

- make this the main human-readable ACPM disclosure surface

It should show:

- the four-part labeling stack:
  - `Shared validity floor`
  - `Shared score shape`
  - `Profile weight lens`
  - `Planner policy`
- recommendation status with explicit allowed-claim wording
- caveat explanations
- concise narrowing rationale summary
- handoff availability status
- references back to methodology snapshot and recommendation source refs

It should not own:

- raw planner traces
- the authoritative recommendation record
- the authoritative methodology snapshot

Reason:

- this file already owns detailed human-readable evidence and methodology explanation

#### 4. `metadata.json`

Recommended v1 policy:

- extend it with ACPM export projections, not ACPM source-of-truth duplication

Recommended ACPM export blocks:

- `acpm_planning`
  - projection of adjacent planning metadata identifiers/versions and compact narrowing summary
- `acpm_recommendation`
  - projection of recommendation status, config refs, caveat codes, evidence snapshot, and source refs
- `acpm_handoff`
  - optional projection metadata only if handoff exists, such as format and availability

Important rule:

- the persisted ACPM planning metadata and recommendation record should remain the source records
- `metadata.json` should export them for audit/bundling convenience

#### 5. `explain`

Recommended v1 policy:

- explain should consume ACPM records and methodology evidence to produce reader-oriented summaries

It should speak about:

- what ACPM recommended or withheld
- why the claim level is provisional, validated, validation-limited, or withheld
- what profile lens was used
- what key caveats matter

It should not:

- invent a second status vocabulary
- turn caveats into a shadow status system
- restate the full methodology table by default

#### 6. `compare` and audit surfaces

Recommended v1 policy:

- keep campaign compare methodology-first
- add ACPM overlays only when both compared campaigns have ACPM records

They should compare:

- methodology compatibility, including ACPM-relevant profile/weights/gates identity once compare/audit seams are widened
- ACPM planning identity:
  - profile ID
  - planner policy ID/version
  - repeat tier
- recommendation outcome differences:
  - status change
  - leading config change
  - recommended config change
  - caveat deltas

They should not compare:

- machine handoff files as if they were primary evidence
- raw planner traces
- free-form report prose

#### 7. Machine-handoff surface

Recommended v1 policy:

- the handoff file should be a thin serializer output of `recommendation_record.machine_handoff`
- it should exist only when `recommendation_status` is one of the two recommending statuses
- it should contain only the variable-only llama.cpp projection

It should not own:

- recommendation status
- caveat interpretation
- profile/planner identity
- methodology truth

Critical trust rule:

- a machine handoff file must never exist when the human recommendation layer says recommendation is withheld

## What Each Surface Should Own

### Trust-bearing authorities

- `RunPlan` and existing campaign/runtime records own execution shape truth
- methodology snapshots own weights/gates/anchors/profile methodology truth
- ACPM planning metadata owns planner identity and bounded narrowing provenance
- ACPM recommendation record owns recommendation status, config refs, compact evidence, and caveat codes

### Derived readers/projections

- `campaign-summary.md` owns concise human summary wording
- `run-reports.md` owns detailed human-readable explanation
- `metadata.json` owns structured export projection
- `explain` owns narrative interpretation
- `compare` and audit outputs own comparison framing
- machine handoff owns delivery serialization only

### Explicitly out of scope for v1 surfaces

- full planner trace persistence
- finalist/rejected-candidate tables on every surface
- machine-handoff-specific policy independent from recommendation status
- a second ACPM-only report family
- allowing report markdown to serve as machine-readable recommendation truth

## Minimum Prep / Refactor Work Before Implementation

### Must-do prep

1. Create a clean ACPM reader seam for non-execution surfaces.

Why:

- report/export/explain/compare should read ACPM planning/recommendation records through one adapter layer rather than each surface querying ad hoc blobs or re-deriving policy

2. Widen compare/audit methodology identity beyond anchors/version only.

Why:

- ACPM profile/weight differences will make current compare/audit methodology checks too thin
- this is already a repo-fit issue even before ACPM output wiring

3. Decide and codify the machine-handoff output seam before writing it.

Why:

- the current 4-artifact contract is explicit and guarded
- ACPM needs a deliberate decision on whether the handoff file is:
  - outside the formal campaign artifact contract
  - a separately registered delivery artifact
  - or a future formal artifact expansion

4. Add one consistent ACPM projection contract for report/export surfaces.

Why:

- without a shared projection shape, `campaign-summary.md`, `run-reports.md`, `metadata.json`, and `explain` will drift in names, wording, and field meaning

### Nice-to-have later

1. Richer compare rendering for ACPM-vs-ACPM recommendation changes.
2. Dedicated explain subcommands or ACPM-specific explain views.
3. More detailed audit diffing of narrowing rationale.
4. Additional handoff serializers beyond the variable-only llama.cpp projection.

## Risks of Getting This Wrong

### 1. Shadow methodology

If report/export/recommendation surfaces restate weights, gates, or profile meaning independently from methodology snapshots, ACPM will create a second methodology system in practice even if not in code.

### 2. Shadow recommendation authority

If the machine handoff file exists independently of recommendation status, operators will treat the handoff as the real answer and human trust surfaces as optional commentary.

### 3. Compare drift

If compare/audit keep using thin methodology identity while ACPM changes profile/weight lenses, campaign comparisons will look more trustworthy than they really are.

### 4. Wording overclaim

If short human-facing surfaces collapse:

- score leader
- recommended config
- validated config

into the same language, ACPM will overstate certainty and understate evidence limits.

### 5. Duplicate-state rot

If ACPM state is persisted in too many places independently, later maintenance will devolve into trying to guess which surface owns the truth after status, caveat, or methodology changes.

## Downstream Implementation Consequences

- report code should read ACPM projections, not own recommendation policy
- export code should serialize ACPM projections, not become the ACPM persistence layer
- explain code will need structured ACPM inputs so it can remain derived
- compare/audit will need methodology identity widening before ACPM compare semantics are trustworthy
- artifact-path decisions for machine handoff must be settled before serializer implementation

## Questions Answered in This Pass

### 1. How should ACPM appear across human-facing and machine-facing surfaces?

As one derived layer over existing QuantMap artifacts, with separate authoritative inputs for methodology, planning provenance, recommendation status, and handoff projection.

### 2. What should each major surface own?

- short report: concise claim-controlled summary
- detailed report: human-readable ACPM explanation
- export: structured ACPM projection
- explain: derived narration
- compare/audit: methodology-first comparison plus ACPM overlay
- handoff: delivery serialization only

### 3. What should stay derived rather than independently persisted?

- human-facing wording
- explain narratives
- compare prose
- export layout
- handoff file contents

### 4. Where should truth come from?

- execution truth: `RunPlan` and campaign/runtime records
- methodology truth: methodology snapshots
- planner identity/provenance: ACPM planning metadata
- recommendation claim truth: ACPM recommendation record

### 5. What minimum prep/refactor work is required?

- a shared ACPM reader/projection seam
- widened compare/audit methodology identity
- an explicit machine-handoff output contract

## Remaining Open Questions

- Should the machine-handoff file remain outside the formal 4-artifact contract in v1, or should ACPM introduce a separate registered delivery-artifact family?
- What exact structured projection shape should `metadata.json` use for `acpm_planning`, `acpm_recommendation`, and any handoff availability block so export, compare, and explain stay aligned?
- Should `campaign-summary.md` show handoff availability as a binary note only, or should it also expose the recommended variable count for operator clarity?
- How much ACPM-specific compare output belongs in the default compare report versus a later ACPM-aware compare mode?

## Recommended Next Investigations

- `ACPM-machine-handoff-output-contract-TARGET-INVESTIGATION.md`
- `ACPM-compare-and-audit-surface-contract-TARGET-INVESTIGATION.md`
- `ACPM-export-projection-shape-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/policies/boundaries.md`
