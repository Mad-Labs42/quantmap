# CLI UX 3: ACPM Entry and Invocation Ergonomics — Validation

Date: 2026-04-23

## Scope

Validation for the bounded CLI/UX third bundle defined in:

- `docs/Plans/CLI-UX/CLI-UX-3-ACPM-Entry-and-Invocation-PREP-Implementation-Plan.md`

Validated goals:

- `quantmap acpm` entry surface with `plan`, `validate`, `info` subcommands
- ACPM profile discovery via `quantmap acpm info`
- Plan preview without execution via `quantmap acpm plan`
- Input validation without execution via `quantmap acpm validate`
- Post-run hint enhancement in runner.py

No new execution path, DB/schema change, or truth-lane change was introduced.

## Changed Surfaces Validated

- `quantmap.py`
- `src/ui.py`
- `src/runner.py`
- `test_cli_ux_acpm_entry.py`

## Validation Commands

### Repo / changed-path checks

```powershell
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths quantmap.py src/ui.py src/runner.py test_cli_ux_acpm_entry.py
.\.venv\Scripts\python.exe -m ruff check quantmap.py src/ui.py src/runner.py test_cli_ux_acpm_entry.py
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_acpm_entry.py
```

### Help smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py --help
.\.venv\Scripts\python.exe quantmap.py acpm --help
.\.venv\Scripts\python.exe quantmap.py acpm info
.\.venv\Scripts\python.exe quantmap.py acpm info --profile Balanced
.\.venv\Scripts\python.exe quantmap.py acpm plan --campaign NGL_sweep --profile Balanced
.\.venv\Scripts\python.exe quantmap.py acpm validate --campaign NGL_sweep --profile Balanced
```

## Results

### 1. Repo / changed-path validation

- `changed_path_verify.py`: PASS (4 changed files, 1 test target)
- `ruff check` on touched Python paths: PASS
- `pytest -q test_cli_ux_acpm_entry.py`: PASS (13 passed)

### 2. Help and discoverability

PASS. `acpm` appears in top-level help as a subcommand:

```
quantmap --help
...
artifacts           Discover artifact paths and status for a campaign
acpm                ACPM planner entry: plan, validate, and profile discovery
```

`quantmap acpm --help` shows subcommands:

```
quantmap acpm --help
...
positional arguments:
  {info,plan,validate}  ACPM subcommands
```

### 3. ACPM info subcommand

PASS. `quantmap acpm info` lists all profiles:

```
Balanced — Mixed practical recommendation lens. Ranking balances throughput and latency.
T/S (Throughput/Speed) — Throughput-biased lens. Prioritizes sustained token generation rate and floor.
TTFT — Latency-biased lens. Prioritizes warm and cold first-token responsiveness.
```

`quantmap acpm info --profile Balanced` shows profile details:

```
Profile ID:     Balanced
Display name:   Balanced
Lens:           Mixed practical recommendation lens. Ranking balances throughput and latency.
Scoring profile: acpm_balanced_v1
```

### 4. ACPM plan subcommand

PASS. Plan preview shows scaffolded experiment grid:

```
╔══════════════════════════════╗
║   ACPM Plan: NGL_sweep       ║
╠══════════════════════════════╣
║ Profile:    Balanced         ║
║ Tier:       1x              ║
║ Experiments: 6              ║
╠══════════════════════════════╣
║ n_gpu_layers: 10, 30, 50, 70, 90, 999
╚══════════════════════════════╝
```

### 5. ACPM validate subcommand

PASS. Validation exits 0 for ACPM-applicable campaigns with valid profile/tier:

```
quantmap acpm validate --campaign NGL_sweep --profile Balanced --tier 1x
→ exit code 0
```

Validation exits 1 for non-applicable campaigns:

```
quantmap acpm validate --campaign B_low_sample --profile Balanced
→ Campaign 'B_low_sample' is not ACPM-applicable: unsupported_variable
→ exit code 1
```

### 6. Runner.py post-run hint

PASS. Runner now shows hint after campaign completion:

```
Run `quantmap acpm plan --campaign <ID> --profile <name>` to preview the next planned scope.
```

## Out-of-Scope from PRE (Deferred)

- `quantmap acpm run` execution surface → separate follow-on bundle
- `quantmap run --profile <name>` flag → separate follow-on bundle
- `quantmap run --tier <n>x` flag → separate follow-on bundle
- New truth lanes or execution semantics

## Summary

| Check | Result |
|-------|--------|
| Changed-path validation | PASS |
| Ruff lint | PASS |
| Test suite | PASS (13/13) |
| Help discoverability | PASS |
| `acpm info` | PASS |
| `acpm plan` | PASS |
| `acpm validate` | PASS |
| Runner hint | PASS |

**Status: PASS** — Bundle 3 complete. Execution wiring deferred to follow-on.