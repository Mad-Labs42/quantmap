# ACPM Slice 4: Execution Wiring, Applicability, and Repeat Tiers - PREP Implementation Plan

Date: 2026-04-23
Status: PRE plan only
Precursor: `ACPM-Slice-3-Governed-Profiles-and-Methodology-Labeling-Validation.md`

---

## Goal

Define the smallest safe Slice 4 that:

- turns the Slice 3 ACPM profile choice into a real execution/scoring input,
- adds planner-side applicability and repeat-tier compilation behavior,
- adds only the fixed `1x` NGL scaffold that the v1 baseline already locked,
- and keeps recommendation policy plus report/export/history work deferred.

---

## 1. Current Repo Truth for Where ACPM Profile Choice Would Enter Execution/Scoring

Validated starting point from Slice 3:

- Slice 3 added governed ACPM profile definitions and ACPM profile-loading/lookup support in `src/acpm_planning.py`.
- Slice 3 explicitly left `runner.py`, `score.py`, `report.py`, `report_campaign.py`, `explain.py`, `export.py`, `compare.py`, `audit_methodology.py`, `governance.py`, and `db.py` untouched.
- Slice 3 validation closes with: "Ready for Slice 4 (profile wiring into execution: `runner.py` / `score.py`)."

Repo-truth implication:

- ACPM profile identity already exists on the planner side.
- The missing seam is the handoff from planner output into the existing execution/scoring path.
- Slice 4 is the first slice that should bridge that gap.

What this means practically:

- `src/acpm_planning.py` is already the correct home for planner-owned profile selection and planner-budget compilation.
- The execution/scoring bridge should be as thin as possible and should terminate in the existing engine, not create a second ACPM execution path.
- `RunPlan` remains execution truth; Slice 4 should compile into existing execution/scoring inputs, not replace them.

---

## 2. Exact Slice 4 Scope vs. What Stays Deferred

### In Scope

Slice 4 should do only these things:

1. Wire ACPM-selected profile identity from planner output into the existing execution/scoring path.
2. Add planner-side applicability rules for conservative structural narrowing only.
3. Add planner-side repeat-tier compilation.
4. Add the fixed `1x` `NGL_sweep` scaffold already locked by the v1 baseline: `[10, 30, 50, 70, 90, 999]`.
5. Preserve explicit distinction between:
   - execution truth,
   - methodology truth,
   - planner provenance.

### Explicitly Deferred

These stay out of Slice 4:

- Slice 5 recommendation logic, recommendation record, status policy, caveat policy, and handoff gating.
- Slice 6 report, export, history, compare, and explain projection work.
- Any broad redesign of runner/report/export surfaces.
- Any ACPM-specific `run_mode`.
- Any profile-specific elimination gates.
- Any speculative pruning by live noise, guessed optimum, or profile preference.
- Any dynamic or topology-specific NGL scaffold variants beyond the locked v1 fixed `1x` scaffold.

---

## 3. Recommended File/Module Ownership

### Profile Wiring

Primary owner: `src/acpm_planning.py`

- Own planner-facing profile selection.
- Own the compiled execution/scoring handoff payload produced from ACPM planning output.
- Keep the mapping from ACPM profile identity to governed scoring-profile identity on the planner side.

Thin integration owner: `runner.py`

- Own the final pass-through into the existing execution/scoring call path.
- This should be a narrow plumbing change, not a new planner/policy owner.

Preferred `score.py` posture:

- Consumer only if a minimal input seam is needed.
- Do not move ACPM planner policy, applicability logic, repeat tiers, or scaffold policy into `score.py`.

### Applicability Rules

Owner: `src/acpm_planning.py`

- The matrix locks applicability as a planner behavior layer.
- Applicability must stay conservative and structural.
- It must run before profile/budget prioritization.

Applicability should cover only:

- campaign/candidate structural eligibility,
- planner-safe pruning from committed YAML semantics,
- rejection of cases where safe ACPM narrowing cannot be justified.

Applicability should not cover:

- recommendation policy,
- score interpretation,
- report wording,
- live-performance heuristics.

### Repeat-Tier Compilation

Owner: `src/acpm_planning.py`

- The matrix locks repeat tier as planner-budget behavior, not methodology or gating behavior.
- Repeat-tier compilation should map planner budget choice into existing execution-depth semantics without inventing ACPM-only run modes.

### Fixed `1x` NGL Scaffold

Owner: `src/acpm_planning.py`

- Keep the locked scaffold catalog/policy definition with the planner.
- Treat it as planner-side scope compilation plus planner provenance.
- Do not spread scaffold ownership into reporting or scoring modules in this slice.

Thin consumer impact:

- `runner.py` may need the selected compiled scope.
- report/export/history/compare surfaces should remain deferred consumers.

---

## 4. Main Risks / Blast Radius

### Primary Risks

- Planner policy leaks into execution truth.
  `RunPlan` must remain execution truth; ACPM planning metadata remains adjacent provenance.

- ACPM profile wiring turns into a second scoring system.
  Slice 4 should select a governed scoring profile, not invent ACPM-only scoring semantics.

- Applicability becomes hidden preference pruning.
  The matrix explicitly forbids pruning ordinary YAML values by profile preference, live noise, or guessed optimum.

- Repeat tier gets confused with methodology or gating.
  Repeat tier is planner budget behavior only.

- The fixed `1x` scaffold gets mistaken for full evidence.
  Slice 4 may compile the scaffold, but must preserve the groundwork for later coverage-class honesty.

- Scope creeps into Slice 5 or Slice 6.
  Recommendation authority and user-facing projection work remain out of scope here.

### Blast Radius Summary

Smallest safe blast radius:

- planner/orchestrator seam in `src/acpm_planning.py`,
- thin execution/scoring pass-through in `runner.py`,
- only the smallest score-side acceptance seam if strictly required,
- focused tests for the new planner-to-execution contract.

Avoid widening Slice 4 into:

- report/export/history/compare,
- recommendation policy,
- DB/storage redesign,
- broad runner refactors.

---

## 5. Smallest Strong Validation / Test Plan

The validation plan for Slice 4 should stay narrow and contract-focused.

### New Focused Tests

- ACPM planner output compiles a governed scoring-profile selection that can be handed to the existing execution/scoring path.
- Applicability rules only enforce conservative structural pruning.
- Repeat-tier compilation maps planner budget choice onto existing execution-depth semantics without adding ACPM-specific run modes.
- `1x` NGL compilation uses only the locked fixed scaffold.
- `3x` and `5x` preserve the locked expectation of fuller NGL coverage behavior.

### Regression Expectations

- Slice 1 contract behavior remains valid.
- Slice 3 governed profile behavior remains valid.
- No recommendation/report/export/history/compare tests should need to change in Slice 4.

### Verification Standard

The implementation slice should finish with:

- focused planner/contract tests for Slice 4,
- re-run of Slice 1 and Slice 3 ACPM tests,
- changed-path verification on touched paths,
- confirmation that deferred files outside the planned thin wiring seam remain untouched.

---

## 6. Recommended Implementation Order

1. Extend the planner contract in `src/acpm_planning.py` so ACPM-selected profile choice compiles into an execution/scoring handoff payload.
2. Add conservative applicability rules in `src/acpm_planning.py`, keeping them structural and YAML-backed only.
3. Add repeat-tier compilation in `src/acpm_planning.py`, mapped onto existing execution-depth semantics.
4. Add the fixed `1x` `NGL_sweep` scaffold in `src/acpm_planning.py` and keep it explicitly planner-owned.
5. Add the thinnest possible `runner.py` wiring so the compiled ACPM profile selection actually reaches the existing scoring path.
6. Add only the minimal score-side acceptance change if runner integration proves it is strictly required.
7. Run focused Slice 4 tests plus Slice 1 and Slice 3 regression.

This order keeps planner policy local first, then adds only the minimum engine wiring needed to make Slice 4 real.

---

## Slice Boundary Reminder

Slice 4 should end when ACPM can:

- select a governed profile,
- compile safe applicability and repeat-tier behavior,
- compile the fixed `1x` scaffold where applicable,
- and hand those results into the existing execution/scoring engine.

Slice 4 should not try to finish:

- recommendation claim authority,
- machine handoff policy,
- or ACPM-aware report/export/history/compare projections.

---

## Agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
