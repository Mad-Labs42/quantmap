# CLI UX 4: ACPM Run Execution — Validation

Date: 2026-04-23

## Scope

Validation for the bounded CLI/UX fourth bundle defined in:

- `docs/Plans/CLI-UX/CLI-UX-4-ACPM-Run-Execution-PREP-Implementation-Plan.md`

Validated goals:

- `quantmap acpm run` execution surface with `--campaign`, `--profile`, `--tier`, `--validate`, `--dry-run`
- ACPM planning compiles through existing `compile_acpm_plan` and `to_execution_inputs`
- Execution flows through existing `runner.run_campaign`
- No changes to manual `quantmap run`, no new truth lanes, no DB/schema changes

## Changed Surfaces Validated

- `quantmap.py` — added `acpm run` subparser and `cmd_acpm_run` handler
- `test_cli_ux_acpm_run.py` — new test file (16 tests)

## Validation Commands

### Repo / changed-path checks

```powershell
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths quantmap.py test_cli_ux_acpm_run.py
.\.venv\Scripts\python.exe -m ruff check quantmap.py test_cli_ux_acpm_run.py
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_acpm_run.py
```

### Help smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py acpm --help
.\.venv\Scripts\python.exe quantmap.py acpm run --help
```

### Core operator-flow smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py acpm run --campaign NGL_sweep --profile Balanced --dry-run
.\.venv\Scripts\python.exe quantmap.py acpm run --campaign NGL_sweep --profile T/S --tier 3x --dry-run
```

## Results

### 1. Repo / changed-path validation

- `changed_path_verify.py`: PASS (2 changed files, 1 test target)
- `ruff check`: PASS
- `pytest`: PASS (16/16)

### 2. Help and discoverability

PASS. `acpm run` appears in `acpm --help`:

```
quantmap acpm --help
...
positional arguments:
  {info,plan,validate,run}
```

### 3. `acpm run --dry-run`

PASS. Dry run shows compiled plan:

```
ACPM Dry Run: NGL_sweep
━━━━━━━━━━━━━━━━━━━━━━━
  Campaign:   NGL_sweep
  Profile:     Balanced
  Tier:       1x
  Scope:      planner
  Values:     [10, 30, 50, 70, 90, 999]
  Cycles:     6
  Scoring:    acpm_balanced_v1
```

### 4. `acpm run --validate`

PASS. Validate runs pre-flight checks via existing `runner.validate_campaign`:

```
Running pre-flight validation...
QuantMap validation: NGL_sweep
...
Validation FAILED — fix errors above before running.
```

Exit code is 1 when model missing (expected in CI without model).

### 5. Error handling

PASS. Unknown campaign, profile, tier, non-applicable campaign all exit with appropriate errors.

### 6. Manual run regression

PASS. `quantmap run --help` unchanged.

## Out-of-Scope from PRE (Deferred)

- `--profile` / `--tier` flags on `quantmap run` → deferred to Bundle 5
- ACPM-specific `run_mode` → deferred
- DB/schema changes → none added
- Recommendation authority changes → none
- Scoring profile/gate changes → none
- Consumer surfaces (report/export/compare/explain) → unchanged

## Summary

| Check | Result |
|-------|--------|
| Changed-path validation | PASS |
| Ruff lint | PASS |
| Test suite | PASS (16/16) |
| Help discoverability | PASS |
| `acpm run --dry-run` | PASS |
| `acpm run --validate` | PASS |
| Error handling | PASS |
| Manual run regression | PASS |

**Status: PASS** — Bundle 4 complete.

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`