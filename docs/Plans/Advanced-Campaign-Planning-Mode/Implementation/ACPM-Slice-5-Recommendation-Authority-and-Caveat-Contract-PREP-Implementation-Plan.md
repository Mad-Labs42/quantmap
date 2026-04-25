# ACPM Slice 5: Recommendation Authority and Caveat Contract - PREP Implementation Plan

Date: 2026-04-23
Status: PRE plan only
Precursor: `ACPM-Slice-4-Execution-Wiring-Applicability-and-Repeat-Tiers-Validation.md`

---

## Goal

Define the smallest safe Slice 5 that establishes ACPM recommendation authority: the recommendation record shape, the status policy, the caveat policy, and the machine-handoff readiness boundary, without widening into Slice 6 projection work.

---

## 1. Current Repo Truth After Slice 4

Validated Slice 4 state:

- `src/acpm_planning.py` now owns ACPM planner policy for profile selection, applicability, repeat-tier compilation, and fixed `1x` NGL scaffold handling.
- `src/runner.py` only gained a thin pass-through seam that forwards ACPM-selected `profile_name` into the existing scoring path.
- `src/score.py` remains the scoring engine and remains untouched.
- Slice 4 deliberately did not add recommendation authority, recommendation status, caveat classification, or machine-handoff gating.
- Slice 4 also left report/export/history/compare/explain surfaces untouched.

Repo-truth implication:

- Execution truth, methodology truth, planner provenance, and effective filter-policy truth are now separated enough to add the next authority lane: recommendation claim truth.
- The remaining missing seam is not scoring itself; it is the post-scoring authority that decides what ACPM is allowed to claim and when machine handoff is allowed.
- The baseline and matrix still treat recommendation record/status as a true blocker before recommendation-grade claims.

---

## 2. Exact Slice 5 Scope vs. Deferred

### In Scope

Slice 5 should do only these things:

1. Define one post-scoring recommendation record as the recommendation-claim authority.
2. Define the four locked statuses:
   - `strong_provisional_leader`
   - `best_validated_config`
   - `needs_deeper_validation`
   - `insufficient_evidence_to_recommend`
3. Define the distinction between:
   - `leading_config_id`
   - `recommended_config_id`
4. Define compact caveat policy as governed qualifiers subordinate to status.
5. Define machine-handoff readiness as a contract boundary, not as a serializer/output surface.
6. Persist the recommendation authority through one clear repo-owned seam.

### Explicitly Deferred

These stay out of Slice 5:

- Slice 6 report/export/history/compare/explain projections.
- Human-facing wording for recommendation display.
- Machine-handoff file/artifact serialization.
- Any broad compare/export redesign.
- Any planner-policy redesign in `src/acpm_planning.py`.
- Any score-weight or gate redesign.
- Any ACPM-specific execution/run-mode changes.

---

## 3. Best Module / File Ownership

### Recommendation Contract and Policy

Best owner: new dedicated module, `src/acpm_recommendation.py`

This module should own:

- recommendation record schema/validation
- recommendation status policy
- caveat policy
- handoff-readiness predicate

Why this is the best boundary:

- the matrix explicitly separates recommendation claim truth from execution, methodology, planner provenance, and report prose
- recommendation policy should not live in `src/acpm_planning.py`, `src/runner.py`, or `src/score.py`
- a dedicated module keeps status/caveat logic from becoming scattered or silently re-derived by consumers

### Persistence Home

Best owner: `src/db.py`

`src/db.py` should own the physical persistence seam for the recommendation record. The exact physical storage can be decided inside Slice 5 implementation, but it should be:

- post-scoring
- single-source
- adjacent to other persisted truth lanes
- not stored in planner metadata
- not stored in methodology snapshots

### Write Path

Best owner: `src/runner.py`

`src/runner.py` is the correct thin write seam because it already coordinates the post-run scoring path. Slice 5 should keep runner ownership narrow:

- call recommendation evaluation after scoring
- persist the resulting record
- do not move policy ownership into runner

### Explicit Non-Owners

These should not own recommendation authority in Slice 5:

- `src/acpm_planning.py`: planner provenance only
- `src/score.py`: scoring only
- `src/report.py`, `src/report_campaign.py`, `src/explain.py`, `src/export.py`, `src/compare.py`: consumer surfaces only, deferred to Slice 6

---

## 4. Risks / Blast Radius

### Primary Risks

- Recommendation truth leaks into planner metadata.
  That would create shadow recommendation authority and break the truth-lane split.

- Recommendation truth leaks into report prose or handoff output before the authority seam exists.
  That would make projections act like owners.

- Status and caveat policy become two competing decision systems.
  The matrix locks status as the primary claim-control field; caveats must remain qualifiers.

- `leading_config_id` and `recommended_config_id` collapse into one field.
  That would erase the repo’s distinction between score leader and allowed recommendation.

- Machine handoff is allowed without an actual recommendation-grade outcome.
  The baseline explicitly forbids that.

### Blast Radius Summary

Smallest safe Slice 5 blast radius:

- one new dedicated recommendation-policy module
- one DB persistence seam
- one thin runner write/evaluation seam
- focused tests around record/status/caveat/handoff-readiness behavior

Avoid widening into:

- planner redesign
- score redesign
- report/export/history/compare/explain changes
- serializer/artifact work

---

## 5. Smallest Strong Validation Plan

The validation plan for Slice 5 should stay contract-focused.

### Core Checks

- recommendation record can be built and validated as a distinct truth object
- all four statuses behave according to the locked policy
- `leading_config_id` and `recommended_config_id` remain distinct
- caveat policy is additive to status, not a second status system
- machine-handoff readiness is false unless `recommended_config_id` exists and status allows it
- persistence round-trip preserves the recommendation record without moving it into planner/methodology truth

### Regression Expectations

- Slice 4 planner/execution wiring remains unchanged
- `src/score.py` remains untouched
- no Slice 6 consumer files need to change for Slice 5 validation

### Validation Shape

Smallest strong validation should include:

- focused recommendation-contract tests
- focused persistence/write-path tests
- Slice 4 regression on the recommendation-adjacent path
- changed-path verification on touched paths
- explicit confirmation that Slice 6 consumer files stayed untouched

---

## 6. Recommended Implementation Order

1. Define the recommendation record contract and status/caveat/handoff-readiness policy in a dedicated recommendation module.
2. Add the DB persistence seam for a single post-scoring recommendation record.
3. Add the thinnest possible runner integration to evaluate and persist recommendation authority after scoring.
4. Add focused tests for record shape, statuses, caveats, and handoff readiness.
5. Add persistence/write-path tests.
6. Run focused Slice 5 tests, then Slice 4 regression, then changed-path verification.

This keeps authority policy local first, persistence second, and runner wiring last.

---

## Slice Boundary Reminder

Slice 5 should end when ACPM has:

- a persisted recommendation record
- governed recommendation statuses
- governed caveat qualifiers
- a machine-handoff readiness boundary

Slice 5 should not try to finish:

- handoff serialization
- report/export/history/compare/explain projections
- human-facing recommendation wording

---

## Agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
