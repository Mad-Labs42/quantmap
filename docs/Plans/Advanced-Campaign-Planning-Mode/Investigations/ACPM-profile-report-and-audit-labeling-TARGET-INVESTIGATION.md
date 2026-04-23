# ACPM Profile Report and Audit Labeling Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 profile/report/explain/export/audit representation policy only

## Outcome

Recommended v1 policy:

- treat ACPM profile identity as a visible methodology lens, not as hidden planner flavor text
- keep one explicit four-part labeling model across all surfaces:
  - `Shared validity floor`
  - `Shared score shape`
  - `Profile weight lens`
  - `Planner policy`
- show the full explicit ACPM weight vector in:
  - detailed human-facing methodology surfaces
  - export/audit-facing structured metadata
- do not dump the full vector into short summary or default explain headlines
- represent zero-weight metrics such as `warm_ttft_p90_ms` explicitly as:
  - present in the shared score shape
  - `0.00` in the weight vector
  - still enforced by the shared validity floor when applicable
- make the wording explicit that `Balanced`, `T/S`, and `TTFT` are preference lenses over the same pass/fail truth rules, not different scientific validity systems
- require export/audit metadata to preserve both:
  - trust-bearing methodology fields
  - non-truth-bearing planner policy fields

Best v1 reading:

- reports and explain surfaces should stay understandable first
- export and audit surfaces should stay reconstructable first
- neither surface class should hide the ACPM profile semantics that materially influence winner selection

The strongest repo-grounded reason for this policy is that QuantMap already treats profile identity, weights, gates, anchors, and evidence quality as trust-surface material. If ACPM profile choice changes what passing config wins, that fact cannot live only in planner behavior or vague report copy without making the system look less forensic than it is.

## Scope / What Was Inspected

Docs and prior ACPM investigations inspected:

- `README.md`
- `docs/system/architecture.md`
- `docs/system/trust_surface.md`
- `docs/system/methodology_lifecycle.md`
- `docs/system/database_schema.md`
- `docs/playbooks/compare.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-to-governance-mapping-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-weight-and-gate-spec-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-weight-values-TARGET-INVESTIGATION.md`

Code and schema surfaces inspected:

- `src/trust_identity.py`
- `src/governance.py`
- `src/score.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/explain.py`
- `src/export.py`
- `src/audit_methodology.py`
- `src/compare.py`
- `src/report_compare.py`
- `src/db.py`
- `configs/profiles/default_throughput_v1.yaml`

Validation used for this pass:

- direct source inspection of current report/export/explain/audit code paths
- direct inspection of persisted methodology snapshot fields and current artifact/report wiring
- no product-code edits or runtime behavior changes

## Current Relevant Report / Export / Explain / Audit Constraints

### 1. Methodology identity is already trust-bearing and snapshot-first

`trust_identity.py` loads persisted methodology snapshots as the historical authority and exposes:

- `profile_name`
- `profile_version`
- `weights`
- `gates`
- `anchors`
- evidence labels such as `snapshot_complete`, `legacy_partial_methodology`, and `current_input_explicit`

`methodology_lifecycle.md` and `trust_surface.md` explicitly say reports, explain, compare, and export should read historical methodology from snapshots rather than silently consulting live files.

Implication:

- ACPM profile identity must be visible as methodology, not only as planner behavior

### 2. The detailed human report already has a natural methodology surface

`report_campaign._section_methodology()` already renders:

- pre-committed elimination filters
- experiment profile name/version/family
- methodology evidence label
- full six-row scoring weight table
- anchor governance table

Implication:

- `run-reports.md` is already the correct place for full ACPM methodology disclosure
- ACPM should extend this surface, not invent a parallel disclosure channel

### 3. The compact campaign summary is intentionally thinner

`report.py` currently exposes only a brief methodology note:

- methodology evidence label
- experiment profile name/version
- methodology snapshot ID

It does not show:

- full weights
- gates
- score-shape semantics
- planner policy

Implication:

- the short report should not become a methodology dump
- it still needs a concise ACPM lens label so users do not mistake ACPM output for a default profile result

### 4. Export surfaces already carry most trust-bearing methodology fields

`export.generate_metadata_json()` includes:

- `methodology.profile_name`
- `methodology.profile_version`
- `methodology.methodology_version`
- `methodology.source`
- `methodology.weights`
- `methodology.eligibility_filters`
- `methodology.anchors`

`export._write_manifest()` also stores the full `run_methodology_identity` blob in the `.qmap` bundle metadata.

Implication:

- export is already structurally close to what ACPM needs for methodology traceability
- the largest missing export/audit gap is planner-policy capture and an explicit shared-shape/shared-floor label

### 5. Explain currently exposes evidence quality, but not profile semantics

`explain.py` currently adds:

- methodology evidence label
- execution environment evidence
- telemetry provider evidence

It does not add:

- experiment profile name
- weight-lens summary
- shared validity-floor statement

Implication:

- explain is currently too thin for ACPM
- without a profile lens statement, ACPM recommendations risk sounding magical or default-ish

### 6. Audit and compare surfaces are currently under-disclosing methodology differences

Repo docs and playbooks say comparison compatibility depends on identical scoring rules, weights, and gates.

Current code is thinner:

- `audit_methodology.py` returns version + anchors, but not profile name, weights, or gates
- `compare.grade_methodology()` grades compatibility using version/capture quality/anchors only
- `report_compare.py` renders anchor drift only, not profile or weight/gate drift

Implication:

- current audit semantics are already narrower than the repo’s stated methodology-comparison model
- ACPM will make this gap visible quickly if profile identity is not added to audit/compare surfaces

### 7. Methodology snapshots already persist the score-bearing part of ACPM semantics

`methodology_snapshots` stores:

- `profile_name`
- `profile_version`
- `profile_yaml_content`
- `registry_yaml_content`
- `weights_json`
- `gates_json`
- `anchors_json`
- source paths/hashes
- capture quality/source

Implication:

- the trust-bearing ACPM scoring side already has a natural persistence home
- planner policy does not yet

### 8. Current reporting semantics sharply distinguish validity, ranking, and confidence

The repo already separates:

- elimination and truth-invalidated exclusions
- ranking and winner choice
- run-mode confidence/claim language
- methodology evidence quality

Implication:

- ACPM labeling must preserve those lines
- profile differences cannot be described as if they change pass/fail truth, safety, or certainty thresholds

## Candidate Labeling / Representation Models Considered

### 1. Profile name only

Meaning:

- show `Balanced`, `T/S`, or `TTFT` as a single label
- keep weights and planner behavior mostly implicit

Assessment:

- too thin for QuantMap’s trust posture
- makes winner differences look magical
- does not tell users whether differences came from ranking weights, shared gates, or planning policy

### 2. Full raw methodology everywhere

Meaning:

- show the entire weight vector, gates, anchors, and planner data on every human-facing surface

Assessment:

- too noisy for summaries and default explain output
- overloads the user before it clarifies anything
- weak fit with the repo’s existing layered report style

### 3. Layered representation with a stable label set

Meaning:

- every surface uses the same semantic buckets
- short surfaces show concise labels and one-line clarifications
- detailed/audit surfaces show full structured detail

Assessment:

- best fit for current repo structure
- keeps human-facing artifacts readable
- keeps audit/export surfaces reconstructable

### 4. Planner-branded ACPM with methodology mostly hidden

Meaning:

- emphasize ACPM as orchestration
- underplay or omit scoring-profile identity in reports/explain/export

Assessment:

- unacceptable for v1
- conflicts with the repo’s methodology snapshot model
- would blur what is trust-bearing versus what is search behavior

## Recommended v1 Representation Policy

### Core labeling model

Use these exact conceptual buckets across all ACPM surfaces:

- `Shared validity floor`
  - meaning: global trust/safety/viability/elimination/confidence constraints that do not vary across `Balanced`, `T/S`, and `TTFT`
- `Shared score shape`
  - meaning: the shared six-key ACPM v1 metric shape used in all three profiles
- `Profile weight lens`
  - meaning: the selected ACPM profile’s weight vector over that shared shape
- `Planner policy`
  - meaning: the paired orchestration behavior used to gather evidence, explicitly not the scoring authority

Recommended wording rule:

- if a statement affects who wins among passing configs, it belongs under methodology
- if a statement affects how ACPM searched or escalated, it belongs under planner policy

### Report surfaces

Recommended v1 policy for `campaign_summary` and `run-reports.md`:

- `campaign_summary` should show:
  - selected ACPM profile
  - one-line profile meaning
  - one-line statement that shared validity rules remained unchanged
  - pointer to `run-reports.md` / `metadata.json` for full weights
- `run-reports.md` should show:
  - selected ACPM profile
  - methodology evidence label
  - the shared validity floor table
  - the shared score shape
  - the full explicit weight vector
  - a separate planner policy block labeled as non-score-bearing

Recommended v1 wording:

- “Profile choice changes how passing configs are ranked, not what counts as valid evidence.”

### Explain surfaces

Recommended v1 policy:

- default explain output should add:
  - selected ACPM profile label
  - one sentence explaining the chosen lens
  - one sentence stating shared validity rules stayed fixed
- evidence mode should add:
  - methodology evidence label
  - compact profile-weight summary or pointer to the detailed report
  - planner policy ID/summary only if it materially helps reconstruct search behavior

Do not:

- print the full weight vector in the default explain headline
- let explain imply that `TTFT` or `T/S` changed pass/fail truth

### Export / artifact metadata

Recommended v1 policy:

- structured export surfaces should carry the full ACPM methodology vector
- they should also explicitly separate methodology from planner metadata

Recommended metadata split:

- `methodology`
  - trust-bearing
  - profile name/version
  - methodology version/source
  - shared score shape ID / metric key list
  - full weights
  - shared gates / shared constraints snapshot
  - anchors
- `planner`
  - not trust-bearing for ranking truth
  - planner policy ID/version
  - repeat-strength tier
  - planner summary or policy hash

### Audit surfaces

Recommended v1 policy:

- audit output must show whether two campaigns used:
  - the same ACPM profile
  - the same shared score shape
  - the same shared validity floor
  - the same weight vector
  - the same planner policy

Recommended compare-grade rule for ACPM v1:

- different ACPM profiles should be treated as methodology mismatch for score-level comparison
- minor revisions within the same profile family may be warnings if the repo explicitly defines that policy later
- planner-policy differences alone should not masquerade as methodology mismatch, but they should still be disclosed

This is the safest fit with current repo philosophy:

- profile weights are conclusion-shaping
- planner policy is acquisition-shaping

## Human-facing Clarity Guidance

### 1. Always state the shared truth floor

Every ACPM human-facing surface should make one fact obvious:

- `Balanced`, `T/S`, and `TTFT` do not change what counts as valid, safe, or trustworthy evidence in v1

Recommended reusable sentence:

- “All ACPM v1 profiles use the same validity, trust, and elimination rules; profile choice changes ranking emphasis only.”

### 2. Use “lens” language, not “mode” language that implies a separate universe

Recommended:

- `Balanced lens`
- `T/S lens`
- `TTFT lens`
- `ranking emphasis`
- `shared validity floor`

Avoid:

- “different measurement mode”
- “different truth mode”
- “different pass/fail standard”

### 3. Keep short surfaces concise

For compact human surfaces:

- show the chosen profile
- show the one-line meaning
- show the shared-floor disclaimer
- do not dump full tables unless the surface is explicitly methodology-oriented

### 4. Make zero-weight metrics explicit, not invisible

Recommended human-facing treatment for `warm_ttft_p90_ms` in v1:

- show it in the full weight table with `0.00`
- add a role note such as:
  - `zero-weight in ranking`
  - `still enforced by shared latency ceiling`

Why this is the right balance:

- hiding it suggests the metric disappeared
- showing only `0%` without role text makes users think it was forgotten

### 5. Prefer role text over raw math alone

Detailed methodology tables should not stop at `Metric | Weight`.

Recommended v1 columns:

- `Metric`
- `Weight`
- `Ranking role`
- `Constraint role`

This is especially important for:

- `warm_ttft_p90_ms`
- any future metric that is visible but non-differentiating

## Audit / Export Traceability Guidance

### Required fields to reconstruct ACPM use later

Minimum required v1 metadata:

- `acpm_profile_name`
- `acpm_profile_version`
- `acpm_profile_display_label`
- `methodology_version`
- `methodology_evidence_label`
- `shared_score_shape_id`
- `shared_score_metric_keys`
- `weights_in_force`
- `shared_constraints_id` or equivalent stable label
- `shared_gates_in_force`
- `anchors_in_force`
- `planner_policy_id`
- `planner_policy_version`
- `planner_policy_summary_or_hash`
- `repeat_strength_tier`
- `methodology_snapshot_id`

### What already exists vs what is missing

Already present or mostly present:

- profile name/version
- methodology version/evidence label
- weights
- gates
- anchors
- snapshot ID
- source paths/hashes

Missing or not explicit enough for ACPM:

- planner policy identity
- explicit shared score-shape identity
- explicit shared-constraints identity
- a clean methodology-vs-planner split in structured artifacts

### Audit report expectations

Recommended audit output should answer, in plain terms:

- Were the same shared truth-bearing constraints used?
- Was the same score shape used?
- Was the same profile lens used?
- Were the same weights used?
- Was the same planner policy used?

Current repo gap:

- compare/audit code does not yet answer those questions fully

## Risks of Getting This Wrong

### 1. If labeling is too thin

Risk:

- ACPM feels magical
- users cannot tell whether recommendations changed because of ranking preference or because truth rules changed

Consequence:

- trust erosion
- harder peer review
- misleading “same campaign, different answer” perception

### 2. If labeling is too noisy

Risk:

- short reports and explain output become methodology walls of text

Consequence:

- users skip the important parts
- the shared-floor message gets buried

### 3. If labeling is too vague

Risk:

- profiles can be mistaken for different scientific validity systems

Consequence:

- pass/fail truth gets blurred with user preference
- QuantMap looks less rigorous than its actual model

### 4. If surfaces disagree

Risk:

- report, explain, export, and audit say different things about the same ACPM run

Consequence:

- the repo’s forensic posture breaks at the communication layer even if the math is correct

### 5. If audit remains anchor-only

Risk:

- compare/audit could call two ACPM runs “compatible” even when profile weights differ materially

Consequence:

- mathematically different recommendation lenses may be presented as directly comparable
- this is the biggest v1 audit hazard exposed by ACPM

## Downstream Implementation Consequences

If this recommendation is adopted, later implementation should assume:

- `report.py` needs a concise ACPM lens disclosure, not a full vector dump
- `report_campaign.py` should become the detailed ACPM methodology surface
- `explain.py` should surface profile lens + shared-floor text, not just methodology evidence quality
- `export.py` should add a planner block and explicit score-shape/shared-constraint identifiers
- methodology snapshot persistence likely needs a companion place for planner-policy identity
- `audit_methodology.py`, `compare.py`, and `report_compare.py` should compare profile/weights/gates, not anchors only
- a single repo-owned terminology set should be reused across report/export/explain/audit copy so the same ACPM run is described consistently

Recommended implementation priority after this investigation:

1. freeze the labeling vocabulary
2. upgrade structured export/audit metadata
3. update detailed report
4. update compact summary and explain surfaces
5. align compare/audit grading with the repo’s stated methodology semantics

## Questions Answered in This Pass

### 1. Where do methodology/profile identity, scoring semantics, qualifiers, explanation text, artifact metadata, and audit traces already appear?

They already appear across:

- `trust_identity.py` and `methodology_snapshots`
- `report_campaign.py` methodology section
- `report.py` methodology note
- `export.py` metadata.json and bundle manifest
- `explain.py` trust-evidence attachment
- `audit_methodology.py`, `compare.py`, and `report_compare.py`

### 2. What current report/export/explain surfaces need ACPM profile information?

All of these:

- compact campaign summary
- detailed run report
- default explain output
- explain evidence mode
- metadata.json
- `.qmap` manifest metadata
- compare/audit surfaces

### 3. How should ACPM profile identity be labeled?

Using four stable buckets:

- shared validity floor
- shared score shape
- profile weight lens
- planner policy

### 4. Should the full weight vector be shown in human-facing artifacts, audit/export surfaces, both, or neither?

Both, but with surface-appropriate density:

- yes in detailed human-facing methodology surfaces
- yes in export/audit metadata
- no in short summary and default explain headline

### 5. How should zero-weight metrics such as `warm_ttft_p90_ms` be represented?

Show them explicitly with:

- the metric present in the shared shape
- `0.00` weight
- a role note explaining it is non-rank-bearing in v1 but still globally enforced as a shared constraint when applicable

### 6. How should ACPM reports/explanations clarify preference lens vs pass/fail truth?

By stating explicitly that:

- profile choice changes ranking emphasis among passing configs
- global validity, trust, safety, elimination, and confidence rules remain shared

### 7. What metadata is required for later reconstruction?

At minimum:

- ACPM profile ID/version
- weights in force
- planner policy in force
- shared constraints/gates in force
- shared score-shape identity
- methodology evidence/snapshot identity

### 8. What repo-fit risks appear if labeling is too thin, noisy, vague, or inconsistent?

Thin:

- magical recommendations

Noisy:

- unusable human surfaces

Vague:

- blurred validity vs preference semantics

Inconsistent:

- report/explain/export/audit contradiction and trust loss

### 9. What is the best recommended v1 labeling policy?

A layered policy:

- concise lens disclosure in short human surfaces
- full explicit methodology disclosure in detailed human surfaces
- full explicit structured metadata in export/audit surfaces
- strict separation between shared truth-bearing constraints and profile/planner variation

## Remaining Open Questions

### 1. What exact human-facing expansion should `T/S` use?

The acronym is still semantically ambiguous enough that user-facing copy should be frozen before implementation.

### 2. Where should planner policy be persisted?

This pass concludes it must be captured, but the cleanest persistence home still needs to be frozen:

- methodology snapshot companion field
- campaign-start snapshot field
- metadata-only artifact field

### 3. What exact compare-grade policy should govern intra-family methodology drift?

This pass recommends:

- different ACPM profiles = mismatch

But the repo still needs a precise rule for cases like:

- same ACPM profile name, small weight revision
- same scoring profile, planner policy changed only

## Recommended Next Investigations

Recommended follow-ups:

- `ACPM-profile-compare-and-audit-grade-policy-TARGET-INVESTIGATION.md`
- `ACPM-planner-policy-snapshot-shape-TARGET-INVESTIGATION.md`
- `ACPM-profile-copy-and-glossary-TARGET-INVESTIGATION.md`

Priority order:

1. `ACPM-profile-compare-and-audit-grade-policy-TARGET-INVESTIGATION.md`
2. `ACPM-planner-policy-snapshot-shape-TARGET-INVESTIGATION.md`
3. `ACPM-profile-copy-and-glossary-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/instructions/agent_session_bootstrap.md`
- `.agent/reference/terminal_guardrails.md`
