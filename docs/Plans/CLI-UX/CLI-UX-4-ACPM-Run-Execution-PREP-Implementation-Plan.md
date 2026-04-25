# CLI UX 4: ACPM Run Execution — PRE Implementation Plan

Date: 2026-04-23
Status: PRE / planning only
Precondition: Bundle 3 validated

---

## 1. Current Repo Truth After Bundle 3

### Parser surface

Current subcommands: `run`, `doctor`, `init`, `self-test`, `status`, `rescore`, `audit`, `list`, `about`, `compare`, `explain`, `explain-compare`, `export`, `artifacts`, `acpm`.

`acpm` subcommands: `info`, `plan`, `validate`. No `run` subcommand yet.

### ACPM structural truth (source of truth for execution)

- `src/acpm_planning.py` exposes:
  - `compile_acpm_plan(campaign, profile_name, repeat_tier)` → returns `RunPlan`-compatible dict with `scope_authority`, `campaign_values`, `profile_name`, `repeat_tier`, `n_runs`
  - `check_campaign_applicability(campaign)` → applicability rules
  - `get_acpm_profile_info(profile_name)` → profile metadata
  - `V1_ACPM_PROFILE_IDS`, `REPEAT_TIER_1X`, `REPEAT_TIER_3X`, `REPEAT_TIER_5X`

- `src/runner.py:run_campaign(...)` already accepts:
  - `acpm_planning_metadata: dict | None = None`
  - `acpm_scoring_profile_name: str | None = None`
  - `scope_authority: str | None = None`

### Existing `quantmap run` contract

`quantmap run --campaign <ID> --mode {full,standard,quick} --values <comma-separated> --validate` calls:

- `runner.validate_campaign(campaign_id, values_override, baseline_path, mode_flag)`
- `runner.run_campaign(campaign_id, dry_run, resume, cycles_override, requests_per_cycle_override, values_override, baseline_path, mode_flag)`

### Consumer surfaces (trust boundaries)

- `src/report.py` / `src/report_campaign.py` → read persisted recommendation truth
- `src/export.py` → read structured export
- `src/compare.py` → read comparison data
- `src/explain.py` → read evidence

### Constraint from Handoff Doc

> Keep projections projection-only; do not re-derive recommendation policy in consumers
> RunPlan stays execution truth

---

## 2. Exact `acpm run` Scope

Goal: Add `quantmap acpm run` subcommand that compiles an ACPM plan and executes it via existing `runner.run_campaign`.

### Command surface

```
quantmap acpm run --campaign <ID> --profile <name> [--tier {1x|3x|5x}] [--validate] [--dry-run]
```

Equivalently, these must NOT change:

- `quantmap run --campaign <ID>` continues to work as before (no new required flags)
- No new `--profile` or `--tier` flags on `quantmap run`

### Execution flow (Wiring Point)

1. Parse `--campaign`, `--profile`, `--tier`, `--validate`, `--dry-run`
2. Load campaign YAML from `configs/campaigns/<ID>.yaml`
3. Validate profile/tier against `V1_ACPM_PROFILE_IDS`, `_ALL_TIERS`
4. Check applicability via `check_campaign_applicability(campaign)`
5. Compile ACPM plan via `compile_acpm_plan(campaign, profile_name, repeat_tier)` → returns plan dict
6. If `--validate`: run pre-flight checks, exit 0/1, skip execution
7. Extract execution parameters from plan dict:
   - `campaign_values` → `values_override`
   - `repeat_tier` → derive cycles (1x→1, 3x→3, 5x→5)
   - `scope_authority` → pass to `run_campaign(scope_authority=...)`
   - `profile_name` → pass to `run_campaign(acpm_scoring_profile_name=...)`
   - `planning_metadata` → pass to `run_campaign(acpm_planning_metadata=...)`
8. Call `runner.run_campaign(campaign_id, ...)` with extracted parameters
9. Let `runner.run_campaign` handle persistence of planning metadata and scoring profile

### Validation-only flow

If `--validate` flag present, skip step 8 and run pre-flight only:

1. Parse campaign, profile, tier
2. Check applicability
3. Call `runner.validate_campaign(campaign_id, values_override, baseline_path, mode_flag=None)`
4. Exit code 0 if all checks pass, 1 otherwise

This reuses exact `runner.validate_campaign` — no new validation logic.

---

## 3. Exact Files/Surfaces Likely Affected

### Files to add/edit

| File | Change | Rationale |
|------|--------|----------|
| `quantmap.py` | Add `run` subparser + `cmd_acpm_run` handler | New CLI entry point |
| `src/ui.py` | Add `render_acpm_run_result()` (optional) | Result summarization |
| `test_cli_ux_acpm_run.py` | New test file | Acceptance test for `acpm run` |

### Files already wired (no change needed)

| File | Status | Rationale |
|------|--------|----------|
| `src/runner.py` | Already wired | `run_campaign` accepts the ACPM params |
| `src/acpm_planning.py` | Already wired | `compile_acpm_plan` returns valid dict |

### Consumer surfaces (must not change)

- `src/report.py` — reads persisted truth, no change
- `src/export.py` — reads structured export, no change
- `src/compare.py` — reads comparison data, no change
- `src/explain.py` — reads evidence, no change

---

## 4. Explicit Out-of-Scope Items

- No new `--profile` / `--tier` flags on `quantmap run` → deferred to Bundle 5
- No ACPM-specific `run_mode` → violates handoff constraint
- No new DB tables or schema changes → runner handles metadata as JSON blobs
- No recommendation authority changes → ACPM owns evaluation, runner persists record
- No scoring weight/gate changes → governed profiles are the authority
- No change to `quantmap run` semantics for existing campaigns
- No new truth lanes — `RunPlan` stays execution truth

---

## 5. Blast Radius and Risks

### Blast radius (local to ACPM namespace)

- New subparser `acpm run`
- New test file
- Optional UI render helper

### Risks

| Risk | Probability | Impact | Mitigant |
|------|-------------|--------|----------|
| Wrong profile passed to scoring | Low | High | Validate profile/tier in CLI handler before wiring |
| Planning metadata lost on failure | Low | Medium | Runner writes snapshot inside `run_campaign`, not after |
| `--validate` diverges from actual run | Low | High | Reuse existing `runner.validate_campaign` directly |
| Recommendation authority leaked | Low | Critical | No consumer changes; runner owns persistence |

### Trust boundary: `RunPlan` is execution truth

- `quantmap acpm run` compiles a plan → passes dict to `runner.run_campaign`
- `runner.run_campaign` owns execution, persistence, recommendation evaluation
- Consumers read persisted truth only

---

## 6. Validation Plan

### Bounded validation pass commands

```powershell
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths quantmap.py src/ui.py test_cli_ux_acpm_run.py
.\.venv\Scripts\python.exe -m ruff check quantmap.py src/ui.py test_cli_ux_acpm_run.py
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_acpm_run.py
```

### Help smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py acpm --help
.\.venv\Scripts\python.exe quantmap.py acpm run --help
```

### Core operator-flow smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py acpm run --campaign NGL_sweep --profile Balanced --validate
.\.venv\Scripts\python.exe quantmap.py acpm run --campaign NGL_sweep --profile Balanced --tier 1x --validate
.\.venv\Scripts\python.exe quantmap.py acpm run --campaign NGL_sweep --profile T/S --dry-run
```

### Verification checks

- `quantmap acpm run --validate` exits 0 for valid inputs
- `--validate` reuses existing runner validation logic
- `--dry-run` produces no side effects
- Execution flow passes correct params to `runner.run_campaign`
- `quantmap run --campaign NGL_sweep` still works (regression test)

---

## 7. Recommended Implementation Order

1. **Add subparser**: `quantmap.py` — add `run` to `acpm_subparsers`, wire arguments
2. **Add handler**: `cmd_acpm_run(...)` — compile plan, extract params, call runner
3. **Add UI helper**: `src/ui.py` — optional result render
4. **Add tests**: `test_cli_ux_acpm_run.py` — smoke + regression
5. **Run validation pass** — bounded commands above
6. **Write validation report**: `CLI-UX-4-ACPM-Run-Execution-Validation.md`

---

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`