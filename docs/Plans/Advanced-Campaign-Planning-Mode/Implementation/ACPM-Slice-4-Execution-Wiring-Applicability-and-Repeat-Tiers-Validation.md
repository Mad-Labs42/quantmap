# ACPM Slice 4: Execution Wiring, Applicability, and Repeat Tiers - Validation

Date: 2026-04-23
Status: PASS
Validator: Codex
Precursor: `ACPM-Slice-4-Execution-Wiring-Applicability-and-Repeat-Tiers-Implementation-Plan.md`

---

## Outcome

Slice 4 was implemented within the planned file boundary and validated in the same turn.

Implemented behavior:

- ACPM policy ownership remains in `src/acpm_planning.py`.
- Slice 4 adds planner-owned applicability checks, repeat-tier compilation, fixed `1x` NGL scaffold support, and planner compilation into existing execution inputs.
- `ACPMPlannerOutput.to_execution_inputs()` now exposes `scoring_profile_name`.
- `src/runner.py` gained only a thin initial-scoring kwargs seam and forwards `profile_name` into `score_campaign(...)`.

No contradiction was found that required widening scope.

---

## Touched Files

- `src/acpm_planning.py`
- `src/runner.py`
- `test_acpm_slice1.py`
- `test_acpm_slice4.py`

---

## What Changed

### `src/acpm_planning.py`

Added Slice 4 planner-owned behavior only:

- repeat-tier constants and locked `1x` scaffold constants
- structural applicability result + applicability checker
- repeat-tier compiler
- minimal ACPM plan compiler
- additive `scoring_profile_name` in `to_execution_inputs()`

No recommendation logic, report/export/history/compare logic, or scoring-policy ownership was added.

### `src/runner.py`

Added only a thin score-kwargs helper and an optional `acpm_scoring_profile_name` pass-through:

- `_build_initial_score_kwargs(...)`
- `run_campaign(..., acpm_scoring_profile_name: str | None = None)`
- `score_campaign(...)` now receives `profile_name` through that helper

No `RunPlan` changes, no mode changes, and no broad runner refactor.

### `test_acpm_slice1.py`

Updated the existing planner-contract assertion to include the additive:

- `"scoring_profile_name": "acpm_balanced_v1"`

### `test_acpm_slice4.py`

Added focused Slice 4 tests for:

- repeat-tier compilation
- structural applicability
- planner-output execution inputs
- scaffold coverage policy
- thin runner score-profile pass-through

---

## Validation Commands And Results

### 1. Dev contract preflight

Command:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
```

Result: PASS

- interpreter is repo `.venv`
- DevStore anchor is correct
- `pytest`, `pytest-cov`, `mypy`, `ruff` are importable

### 2. Ruff on touched paths

Command:

```powershell
.\.venv\Scripts\python.exe -m ruff check src/acpm_planning.py src/runner.py test_acpm_slice1.py test_acpm_slice4.py
```

Result: PASS

- `All checks passed!`

### 3. Slice 4 focused tests

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q test_acpm_slice4.py
```

Result: PASS

- `11 passed in 1.68s`

### 4. Slice 1 + Slice 3 + Slice 4 regression

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q test_acpm_slice1.py test_acpm_slice3.py test_acpm_slice4.py
```

Result: PASS

- `36 passed in 2.00s`

### 5. Changed-path verification

Command:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths src/acpm_planning.py src/runner.py test_acpm_slice1.py test_acpm_slice4.py
```

Result: PASS

Observed output:

```text
status: pass
interpreter: D:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe
interpreter_is_repo_venv: True
python_version: 3.13.13
base_is_devstore: True
changed_files: 4
changed_python_files: 4
test_targets: 2
```

---

## Deferred Files Stayed Untouched

Command used:

```powershell
git diff --name-only -- src/score.py src/report.py src/report_campaign.py src/explain.py src/export.py src/compare.py src/audit_methodology.py src/governance.py src/run_plan.py src/db.py
```

Result: PASS

- command returned no file paths
- deferred files remained untouched
- `src/score.py` was not modified

---

## Definition Of Done Check

| Criterion | Status |
|---|---|
| ACPM policy ownership remains in `src/acpm_planning.py` | PASS |
| planner output exposes governed `scoring_profile_name` | PASS |
| applicability is structural-only | PASS |
| repeat tiers map only to existing run modes | PASS |
| fixed v1 `1x` NGL scaffold implemented in planner-owned code only | PASS |
| runner wiring stays thin | PASS |
| `src/score.py` untouched | PASS |
| no Slice 5 recommendation work added | PASS |
| no Slice 6 report/export/history/compare work added | PASS |
| Slice 4 tests pass | PASS |
| Slice 1 and Slice 3 regression remain green | PASS |
| ruff and changed-path verification pass | PASS |

---

## Deviations From Plan

None material.

Implementation matched the plan’s intended scope:

- planner logic stayed in `src/acpm_planning.py`
- runner integration stayed as a thin pass-through seam
- `src/score.py` stayed untouched

---

## Residual Notes

- Pytest emitted the known Windows atexit cleanup warning:
  `PermissionError: [WinError 5] Access is denied: ... pytest-current`
- This did not fail the test commands; all requested validation commands exited `0`.

---

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
