# CLI UX 1: Guided Run Shell Validation

Date: 2026-04-23

## Scope

Validation for the bounded CLI/UX first bundle defined in:

- `docs/Plans/CLI-UX/CLI-UX-1-Guided-Run-Shell-PREP-Implementation-Plan.md`

Validated goals:

- clearer top-level and subcommand help
- consistent next-action hints on the core operator path
- better campaign/artifact discoverability inside existing outputs
- readiness wording cleanup
- parser/doc contract alignment

No new command family, ACPM namespace, parser-tree redesign, DB/schema change, or truth-lane change was introduced.

## Changed Surfaces Validated

- `quantmap.py`
- `src/runner.py`
- `src/doctor.py`
- `src/diagnostics.py`
- `src/selftest.py`
- `src/ui.py`
- `.agent/reference/command_reference.md`
- `test_cli_ux_guided_shell.py`

## Validation Commands

### Repo / changed-path checks

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths quantmap.py src\runner.py src\doctor.py src\diagnostics.py src\selftest.py src\ui.py .agent\reference\command_reference.md test_cli_ux_guided_shell.py
.\.venv\Scripts\python.exe -m ruff check quantmap.py src\runner.py src\doctor.py src\diagnostics.py src\selftest.py src\ui.py test_cli_ux_guided_shell.py
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_guided_shell.py
```

### Help smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py --help
.\.venv\Scripts\python.exe quantmap.py run --help
.\.venv\Scripts\python.exe quantmap.py doctor --help
.\.venv\Scripts\python.exe quantmap.py status --help
.\.venv\Scripts\python.exe quantmap.py self-test --help
.\.venv\Scripts\python.exe quantmap.py list --help
```

### Core operator-flow smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py --plain status
.\.venv\Scripts\python.exe quantmap.py --plain doctor
.\.venv\Scripts\python.exe quantmap.py --plain self-test
.\.venv\Scripts\python.exe quantmap.py --plain run --campaign B_low_sample --validate
.\.venv\Scripts\python.exe quantmap.py --plain list
```

## Results

### 1. Repo / changed-path validation

- `verify_dev_contract.py --quick`: PASS
- `changed_path_verify.py`: PASS
- `ruff check` on touched Python paths: PASS
- `pytest -q test_cli_ux_guided_shell.py`: PASS (`4 passed`)

Note:

- `pytest` emitted a Windows temp-cleanup `PermissionError` during interpreter shutdown after the test run completed. Exit code remained `0`; this did not invalidate the pass.

### 2. Help and discoverability

PASS.

Observed help improvements:

- top-level help now includes a clear `Start here:` workflow
- `run --help` now frames validate/run usage with concrete examples
- `doctor --help`, `status --help`, `self-test --help`, and `list --help` now describe operator intent instead of bare command labels
- `self-test --help` now explicitly states that tooling integrity is not model readiness
- `.agent/reference/command_reference.md` now matches the current parser more closely and no longer documents stale `doctor --mode quick`

### 3. Next-action guidance

PASS.

Observed next-action blocks now appear on:

- `status`
- `doctor`
- `self-test`
- `run --validate`
- `list`
- `run` completion path via implementation review and targeted test coverage

Observed command-path behavior:

- `status` ended with `quantmap doctor` and `quantmap run --campaign <ID> --validate` when blocked
- `doctor` ended with a compact next-step block instead of stopping at the status label
- `self-test` ended with a tooling-scoped next-step block
- `run --validate` ended with remediation-oriented next actions
- `list` ended with explain/compare/export follow-ups

### 4. Campaign / artifact discoverability

PASS, with one in-scope refinement during validation.

Initial validation showed that the Rich table could still ellipsize campaign IDs in a normal-width terminal. The implementation was tightened without widening scope:

- compacted table headers
- changed overflow behavior for key columns
- added exact post-table lines for:
  - `Recent campaign IDs: ...`
  - `Recent summaries: ...`

Final observed output now exposes exact IDs and summary filenames even when the table itself is width-constrained.

### 5. Readiness wording cleanup

PASS.

Observed wording changes:

- `self-test` now reports `TOOLING READY` instead of `ENVIRONMENT READY`
- `status` remains a readiness pulse for the operator shell
- `doctor` remains the environment diagnostic authority
- `run --validate` remains the campaign preflight surface

This preserves the intended split between tooling integrity, environment readiness, and run-readiness.

### 6. Real environment outcomes during smoke

These were environment findings, not regressions from the CLI/UX bundle:

- `status`: blocked
- `doctor`: blocked
- `run --campaign B_low_sample --validate`: failed preflight

Blocking causes observed on this machine:

- configured GGUF shard path missing at `QUANTMAP_MODEL_PATH`
- HWiNFO shared memory unavailable, so telemetry provider readiness is blocked for current-run CPU thermal safety

These are pre-existing readiness issues and the new shell wording surfaced them more clearly.

## Deviations From PRE Plan

No material deviation.

One small in-scope refinement was made during validation:

- `list` gained explicit `Recent campaign IDs` and `Recent summaries` footer lines after the first smoke showed that table-only rendering could still hide exact values on narrower terminals

This stayed within the PRE-plan intent of improving discoverability inside existing outputs and did not add any new command surface.

## `.agent` Files Used This Turn

- `.agent/README.md`
- `.agent/policies/routing.md`
- `.agent/policies/workflow.md`
- `.agent/policies/testing.md`
- `.agent/policies/tooling.md`
- `.agent/reference/command_reference.md`
- `.agent/scripts/helpers/verify_dev_contract.py`
- `.agent/scripts/changed_path_verify.py`

## Validation Conclusion

The first bounded CLI/UX bundle is validated.

It improved shell coherence on the existing command tree without widening the tree, without touching ACPM ownership, and without changing truth-lane behavior.
