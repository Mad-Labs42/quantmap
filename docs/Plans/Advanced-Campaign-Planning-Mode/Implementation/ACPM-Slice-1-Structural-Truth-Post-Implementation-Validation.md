# ACPM Slice 1 Structural Truth Post-Implementation Validation

## Outcome

Slice 1 structural truth prep is implemented. ACPM now has a dedicated planner contract module, `RunPlan` records generic `scope_authority`, campaign-start snapshots can persist nullable adjacent ACPM planning metadata, and runner integration is limited to optional structural handoff parameters.

## Changes

- Added `src/acpm_planning.py` for ACPM planner-facing contracts and validation only.
- Added `scope_authority` constants, resolver, legacy snapshot reader, and snapshot serialization to `src/run_plan.py`.
- Added nullable `campaign_start_snapshot.acpm_planning_metadata_json` and schema migration v13 in `src/db.py`.
- Added optional `acpm_planning_metadata` snapshot capture in `src/telemetry.py`.
- Added optional `scope_authority` and `acpm_planning_metadata` handoff parameters to `src/runner.py`.
- Added focused Slice 1 tests in `test_acpm_slice1.py`.

## Verification

- `.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick` -> PASS.
- `.\.venv\Scripts\python.exe -m ruff check src\acpm_planning.py src\run_plan.py src\db.py src\telemetry.py src\runner.py test_acpm_slice1.py` -> PASS.
- `.\.venv\Scripts\python.exe -m pytest -q test_acpm_slice1.py` -> PASS, 9 tests.
- `.\.venv\Scripts\python.exe -m pytest -q test_acpm_slice1.py test_artifact_contract.py --basetemp .\.pytest-tmp-acpm-slice1` -> PASS, 19 tests.
- `.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths src\acpm_planning.py src\run_plan.py src\db.py src\telemetry.py src\runner.py test_acpm_slice1.py` -> PASS.

## Risks / watch-outs

- `src/db.py` and `src/runner.py` had pre-existing uncommitted edits before this slice; this pass preserved them.
- `changed_path_verify.py` passed but captured the known Windows pytest temp cleanup warning when it ran pytest without repo-local `--basetemp`.
- This slice intentionally does not implement planner heuristics, ACPM profiles, effective filter-policy truth, recommendation records, reports, export, compare, explain, or machine handoff.

## Open questions only if genuinely blocking next slice

NA.

## `.agent` files used this turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/policies/boundaries.md`

## Files created/edited

- `src/acpm_planning.py`
- `src/run_plan.py`
- `src/db.py`
- `src/telemetry.py`
- `src/runner.py`
- `test_acpm_slice1.py`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Implementation/ACPM-Slice-1-Structural-Truth-Post-Implementation-Validation.md`
