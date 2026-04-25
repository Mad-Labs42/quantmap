# ACPM Slice 6: Projections and Consumer Surfaces - PREP Implementation Plan

Date: 2026-04-23
Status: PRE plan only
Precursor: `ACPM-Slice-5-Recommendation-Authority-and-Caveat-Contract-Validation.md`

---

## Goal

Define the smallest safe final slice that projects existing ACPM truth into report, export, history, compare, and explain surfaces without reopening planner, scoring, or recommendation-authority logic.

---

## 1. Current Repo Truth After Slice 5

Validated Slice 5 state:

- ACPM recommendation authority now exists as a dedicated post-scoring record in `src/acpm_recommendation.py`.
- Recommendation truth is persisted through `campaigns.recommendation_record_json` in `src/db.py`.
- `src/runner.py` writes that record through a thin post-scoring seam.
- Slice 5 explicitly did not modify report, export, history, compare, or explain surfaces.

Repo-truth implication:

- The remaining work is now projection only.
- Execution truth, planner provenance, methodology truth, effective filter-policy truth, and recommendation claim truth already have distinct owners.
- Slice 6 should consume those existing lanes and must not create a new ACPM truth lane.

---

## 2. Exact Slice 6 Scope vs Deferred

### In Scope

Slice 6 should do only these things:

1. Project existing recommendation authority into report/export/history/compare/explain surfaces.
2. Surface the distinction between:
   - `leading_config_id`
   - `recommended_config_id`
3. Surface recommendation status, caveat qualifiers, and handoff-readiness as read-only consumer output.
4. Preserve already-locked coverage/scope limitation disclosure where recommendation status or NGL coverage needs context.
5. Keep consumer projections compact and structured first, with short derived wording only where a human-facing surface requires it.

### Explicitly Deferred

These stay out of Slice 6:

- any Slice 5 authority-logic changes in `src/acpm_recommendation.py`
- any planner redesign in `src/acpm_planning.py`
- any score redesign in `src/score.py`
- any new recommendation statuses, caveat classes, or handoff policy
- any new persisted truth lane or broad schema redesign
- any broad report/export/compare UX rewrite
- any standalone machine-handoff serializer or artifact family unless separately requested

---

## 3. Best Module / File Ownership

### Authority Owners That Must Stay Fixed

- `src/acpm_recommendation.py` remains the sole owner of recommendation status/caveat/handoff policy.
- `src/db.py` remains the persistence/read seam for the recommendation record.
- `src/runner.py` remains the write seam only.

### Consumer Owners

- Report projection belongs in the existing report surfaces.
  Best owners: `src/report.py` and `src/report_campaign.py`

- Export and history-grade projection belong in the existing export/history reader surface.
  Best owner: `src/export.py`

- Compare projection belongs in the compare reader surface.
  Best owner: `src/compare.py`

- Explain projection belongs in the evidence-first explain reader surface.
  Best owner: `src/explain.py`

### Ownership Rule

Each consumer should read existing structured truth and render it for that surface.

Consumers should not:

- recalculate recommendation status
- reinterpret caveat policy
- infer recommendation authority from prose
- store new shadow recommendation fields as canonical truth

---

## 4. Risks / Blast Radius

### Primary Risks

- Consumer surfaces start re-deriving recommendation logic instead of reading the persisted authority record.
- Compare/history/export surfaces become a second report instead of exposing small durable fields.
- Human-facing wording collapses `leading_config_id` and `recommended_config_id` into one claim.
- Projection work silently widens into authority redesign because legacy/null rows were not handled as consumers.
- Different surfaces phrase the same status/caveat truth inconsistently enough to look like competing policies.

### Blast Radius Summary

Smallest safe Slice 6 blast radius:

- existing report surfaces
- existing export/history projection surface
- existing compare surface
- existing explain surface
- focused tests for consumer projections

Avoid widening into:

- planner logic
- scoring logic
- recommendation authority logic
- DB authority redesign

---

## 5. Smallest Strong Validation Plan

Validation should prove that Slice 6 is reading, not owning.

### Core Checks

- report surfaces display recommendation status and caveats from the persisted authority record
- export/history surfaces emit compact projection fields from existing truth lanes only
- compare surfaces preserve recommendation and coverage-class distinctions without inventing new authority
- explain surfaces surface recommendation evidence and limitations from persisted truth
- legacy/null rows degrade safely without fabricating ACPM authority

### Regression Expectations

- Slice 5 recommendation tests remain unchanged and passing
- no recommendation-policy changes are needed to make projections work
- no planner or score files need changes

### Validation Shape

Smallest strong validation should include:

- focused per-surface projection tests
- legacy/null-row projection tests
- Slice 5 regression on recommendation authority behavior
- changed-path verification on touched paths
- explicit confirmation that `src/acpm_recommendation.py` authority behavior was not changed

---

## 6. Recommended Implementation Order

1. Add the smallest shared read/projection seam needed so consumer modules can read recommendation truth consistently without owning it.
2. Update report surfaces to render recommendation status/caveat/handoff disclosures.
3. Update export/history projection to expose compact structured recommendation and coverage fields.
4. Update compare surfaces to show recommendation and coverage distinctions without turning compare into another report.
5. Update explain surfaces to expose the same truth as evidence-first reader output.
6. Add focused projection tests, then rerun Slice 5 regression validation.

This keeps authority fixed first, projections second, and surface-specific wording last.

---

## Slice Boundary Reminder

Slice 6 should end when ACPM consumers can read and project:

- recommendation status
- leading versus recommended config distinction
- caveat qualifiers
- handoff readiness
- coverage/scope limitations where relevant

Slice 6 should not try to:

- redefine recommendation authority
- add new planner/scoring behavior
- invent new persisted truth
- build a broad narrative redesign across all user-facing surfaces

---

## Agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
