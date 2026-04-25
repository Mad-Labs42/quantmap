# ACPM Slice 4: Execution Wiring, Applicability, and Repeat Tiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire ACPM-selected governed profiles into the existing execution/scoring path while adding planner-owned applicability, repeat-tier compilation, and the fixed v1 `1x` NGL scaffold.

**Architecture:** Keep ACPM policy ownership in `src/acpm_planning.py`. Keep execution/scoring integration to a thin pass-through in `src/runner.py`; do not add ACPM-specific `run_mode` values and do not widen into Slice 5 recommendation work or Slice 6 projection work.

**Tech Stack:** Python 3.13, existing QuantMap planner/runner/score seams, pytest, ruff

---

## Exact Touched Files

- Modify: `src/acpm_planning.py`
- Modify: `src/runner.py`
- Modify: `test_acpm_slice1.py`
- Create: `test_acpm_slice4.py`

## Explicitly Untouched Files

- `src/score.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/explain.py`
- `src/export.py`
- `src/compare.py`
- `src/audit_methodology.py`
- `src/governance.py`
- `src/run_plan.py`
- `src/db.py`

---

### Task 1: Planner-Owned Slice 4 Policy In `src/acpm_planning.py`

**Files:**
- Modify: `src/acpm_planning.py`

- [ ] Add locked Slice 4 constants:
  - `REPEAT_TIER_1X = "1x"`
  - `REPEAT_TIER_3X = "3x"`
  - `REPEAT_TIER_5X = "5x"`
  - `NGL_SCAFFOLD_1X = [10, 30, 50, 70, 90, 999]`
  - coverage-class / scaffold-policy labels needed for planner provenance only

- [ ] Add planner-owned helpers only in this file:
  - `compile_repeat_tier(...)`
  - `check_campaign_applicability(...)`
  - one small planner compilation entrypoint that turns campaign semantics + profile + repeat tier into `ACPMPlannerOutput`

- [ ] Keep applicability structural-only:
  - allowed: committed-YAML eligibility and conservative narrowing
  - forbidden: profile-preference pruning, live-noise pruning, guessed-optimum pruning

- [ ] Map repeat tiers onto existing execution depth only:
  - `1x -> quick`
  - `3x -> standard`
  - `5x -> full`
  - no ACPM-specific `run_mode`

- [ ] Extend `ACPMPlannerOutput.to_execution_inputs()` to include:
  - existing structural execution keys
  - `scoring_profile_name`
  - no recommendation/report/export/history fields

- [ ] Keep the module boundary honest:
  - planner policy lives here
  - no recommendation logic
  - no report/export/history/compare logic
  - no score interpretation logic

**Per-file edit plan:**

- Update the module docstring so it still forbids recommendation/report/handoff ownership, but now allows planner compilation behavior.
- Add the repeat-tier and fixed-scaffold constants near the existing ACPM profile registry.
- Add one frozen applicability result type if needed for clean rule outcomes.
- Add the small pure helper functions for applicability and repeat-tier compilation.
- Add one planner compilation entrypoint that produces `ACPMPlannerOutput`.
- Update `to_execution_inputs()` to include the governed `scoring_profile_name`.

---

### Task 2: Thin Runner Wiring In `src/runner.py`

**Files:**
- Modify: `src/runner.py`

- [ ] Add only the thinnest ACPM-aware scoring pass-through needed for initial scoring.

- [ ] Pass the compiled governed scoring-profile name from runner inputs into:
  - `score_campaign(..., profile_name=<compiled_acpm_profile>)`

- [ ] Keep runner ownership narrow:
  - accept compiled ACPM execution/scoring input
  - forward it
  - do not own applicability rules
  - do not own repeat-tier policy
  - do not own scaffold policy

- [ ] Do not modify:
  - mode semantics
  - `RunPlan`
  - filter-policy ownership
  - report/export/history behavior

**Per-file edit plan:**

- Add one optional runner input for the compiled scoring-profile name.
- Thread that input only to the `score_campaign(...)` call site.
- If a tiny helper is needed for testability, keep it local to score-call argument assembly only.
- Do not add planner decision logic anywhere in `src/runner.py`.

---

### Task 3: Update Existing Slice 1 Contract Test

**Files:**
- Modify: `test_acpm_slice1.py`

- [ ] Update `test_acpm_planner_contract_compiles_only_structural_execution_inputs` so the expected execution-input dict now includes:
  - `"scoring_profile_name": "acpm_balanced_v1"`

- [ ] Keep the rest of the Slice 1 contract intact:
  - `run_mode`
  - `scope_authority`
  - `selected_values`
  - `selected_config_ids`

**Per-file edit plan:**

- Change only the assertion shape for `to_execution_inputs()`.
- Do not widen Slice 1 tests into runner/report/recommendation concerns.

---

### Task 4: Add Focused Slice 4 Test Suite

**Files:**
- Create: `test_acpm_slice4.py`

- [ ] Add planner-policy tests:
  - `test_compile_repeat_tier_1x_uses_locked_ngl_scaffold`
  - `test_compile_repeat_tier_3x_maps_to_standard`
  - `test_compile_repeat_tier_5x_maps_to_full`
  - `test_compile_repeat_tier_rejects_unknown_repeat_tier`
  - `test_applicability_accepts_valid_structural_campaign`
  - `test_applicability_rejects_unknown_or_unsupported_variable`
  - `test_applicability_does_not_prune_by_profile_preference`

- [ ] Add planner-output tests:
  - `test_planner_output_execution_inputs_include_scoring_profile_name`
  - `test_planner_output_execution_inputs_preserve_existing_structural_keys`
  - `test_compile_plan_1x_sets_scaffold_coverage_policy`

- [ ] Add thin runner-wiring test:
  - `test_runner_initial_scoring_passes_profile_name_through`

**Per-file edit plan:**

- Keep the file ACPM-slice-local.
- Prefer pure-function tests for applicability and repeat-tier compilation.
- For runner wiring, test only the argument-assembly seam or direct pass-through seam; do not execute a full campaign.
- Do not add recommendation/report/export/history assertions.

---

## Exact Tests To Add / Update

### Update

- `test_acpm_slice1.py`
  - `test_acpm_planner_contract_compiles_only_structural_execution_inputs`

### Add

- `test_acpm_slice4.py::test_compile_repeat_tier_1x_uses_locked_ngl_scaffold`
- `test_acpm_slice4.py::test_compile_repeat_tier_3x_maps_to_standard`
- `test_acpm_slice4.py::test_compile_repeat_tier_5x_maps_to_full`
- `test_acpm_slice4.py::test_compile_repeat_tier_rejects_unknown_repeat_tier`
- `test_acpm_slice4.py::test_applicability_accepts_valid_structural_campaign`
- `test_acpm_slice4.py::test_applicability_rejects_unknown_or_unsupported_variable`
- `test_acpm_slice4.py::test_applicability_does_not_prune_by_profile_preference`
- `test_acpm_slice4.py::test_planner_output_execution_inputs_include_scoring_profile_name`
- `test_acpm_slice4.py::test_planner_output_execution_inputs_preserve_existing_structural_keys`
- `test_acpm_slice4.py::test_compile_plan_1x_sets_scaffold_coverage_policy`
- `test_acpm_slice4.py::test_runner_initial_scoring_passes_profile_name_through`

---

## Exact Validation Commands

Run in this order:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
.\.venv\Scripts\python.exe -m ruff check src/acpm_planning.py src/runner.py test_acpm_slice1.py test_acpm_slice4.py
.\.venv\Scripts\python.exe -m pytest -q test_acpm_slice4.py
.\.venv\Scripts\python.exe -m pytest -q test_acpm_slice1.py test_acpm_slice3.py test_acpm_slice4.py
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths src/acpm_planning.py src/runner.py test_acpm_slice1.py test_acpm_slice4.py
```

Expected outcome:

- ruff clean
- Slice 4 tests pass
- Slice 1 and Slice 3 regression stays green
- changed-path verification exits `0`

---

## Rollback Boundaries

- If applicability or repeat-tier work starts requiring recommendation status, caveat policy, or handoff logic:
  stop and roll back to planner-only Slice 4 scope.

- If planner work starts requiring report/export/history/compare changes:
  stop and roll back to planner + thin runner wiring only.

- If runner wiring starts requiring broad restructuring:
  roll back to a single optional pass-through input plus a single score-call-site change.

- If implementation appears to require `src/score.py` edits:
  pause first.
  Current plan assumes `src/score.py` already accepts the needed `profile_name` seam and should remain untouched.

- If any change pressures `RunPlan` or introduces ACPM-specific `run_mode` values:
  stop and revert that branch of work; that is outside Slice 4.

---

## Implementation Order

1. Update `src/acpm_planning.py` constants and pure helpers.
2. Add planner compilation entrypoint in `src/acpm_planning.py`.
3. Extend `ACPMPlannerOutput.to_execution_inputs()` with `scoring_profile_name`.
4. Update `test_acpm_slice1.py` for the additive execution-input key.
5. Create `test_acpm_slice4.py` for planner and thin-runner coverage.
6. Add the thin `src/runner.py` scoring-profile pass-through.
7. Run ruff, focused Slice 4 tests, Slice 1 + Slice 3 regression, then changed-path verification.

---

## Crisp Definition Of Done

Slice 4 is done only when all of the following are true:

- ACPM policy ownership remains in `src/acpm_planning.py`.
- ACPM-selected profile identity compiles to a governed `scoring_profile_name`.
- Planner output exposes that compiled `scoring_profile_name` in `to_execution_inputs()`.
- Applicability is implemented as conservative structural narrowing only.
- Repeat tiers compile to existing run modes only: `quick`, `standard`, `full`.
- The fixed v1 `1x` NGL scaffold is implemented exactly once and only in planner-owned code.
- `src/runner.py` forwards the compiled scoring-profile name into `score_campaign(...)` with no broad runner refactor.
- `src/score.py` remains untouched.
- No Slice 5 recommendation logic is added.
- No Slice 6 report/export/history/compare work is added.
- `test_acpm_slice4.py` passes.
- `test_acpm_slice1.py` and `test_acpm_slice3.py` remain green.
- `ruff check` and `changed_path_verify.py` pass on touched paths.

---

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
