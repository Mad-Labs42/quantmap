# CLI UX 5: Wording and Reader Clarity — Validation

Date: 2026-04-23

## Scope

Validation for the bounded CLI/UX fifth bundle defined in:

- `docs/Plans/CLI-UX/CLI-UX-5-Wording-and-Reader-Clarity-PREP-Implementation-Plan.md`

Validated goals:

- Help text expansion with mental model, examples, command relationships, safety class
- Error/not-found messages with remediation hints
- Status/label consistency across commands
- Next-action hints consistency
- ACPM output wording consistency
- self-test wording scope clarification

No new commands, truth-lane changes, or report redesign.

## Changed Surfaces Validated

- `quantmap.py` — epilog expansions (TOP_LEVEL_EPILOG, RUN_EPILOG, DOCTOR_EPILOG, STATUS_EPILOG, SELFTEST_EPILOG, LIST_EPILOG, ACPM_EPILOG)
- `test_cli_ux_guided_shell.py` — updated test for new epilog format

## Validation Commands

### Repo / changed-path checks

```powershell
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths quantmap.py test_cli_ux_guided_shell.py
.\.venv\Scripts\python.exe -m ruff check quantmap.py
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_guided_shell.py test_cli_ux_acpm_entry.py test_cli_ux_acpm_run.py test_cli_ux_artifact_discovery.py
```

### Help smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py --help
.\.venv\Scripts\python.exe quantmap.py run --help
.\.venv\Scripts\python.exe quantmap.py doctor --help
.\.venv\Scripts\python.exe quantmap.py self-test --help
.\.venv\Scripts\python.exe quantmap.py status --help
.\.venv\Scripts\python.exe quantmap.py acpm --help
.\.venv\Scripts\python.exe quantmap.py acpm run --help
```

### Not-found regression

```powershell
.\.venv\Scripts\python.exe quantmap.py explain DOES_NOT_EXIST 2>&1
```

## Results

### 1. Repo / changed-path validation

- `changed_path_verify.py`: PASS (2 changed files, 1 test target)
- `ruff check`: PASS
- `pytest`: PASS (39/39)

### 2. Help text expansion

PASS. Top-level help now includes:

- Primary workflow (numbered steps 1-5)
- Command family groupings: Health, Campaign, History, ACPM
- "Run `quantmap <cmd> --help` for details"

### 3. Run help with safety warning

PASS. Includes examples and safety notice:

```
Safety: This command modifies state (creates campaign artifacts).
```

### 4. self-test help scoped correctly

PASS. Now explicitly states:

```
This is NOT measurement readiness. It only verifies that the tooling itself is functional.
Use `quantmap doctor` to verify model and server readiness.
```

### 5. Not-found remediation hints

PASS. Existing hints retained and consistent across commands.

### 6. ACPM help expansion

PASS. Now includes full examples and tip:

```
Tip: Use `--validate` (validation) before running to catch input errors.
```

## Out-of-Scope from PRE

- New commands — none added
- Report redesign — none
- Truth-lane changes — none
- Scoring/policy changes — none

## Summary

| Check | Result |
|-------|--------|
| Changed-path validation | PASS |
| Ruff lint | PASS |
| Test suite | PASS (39/39) |
| Top-level help | PASS (workflow + family) |
| Run help | PASS (examples + safety) |
| self-test help | PASS (scoped to tooling) |
| Not-found hints | PASS |
| ACPM help | PASS |

**Status: PASS** — Bundle 5 complete.

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`