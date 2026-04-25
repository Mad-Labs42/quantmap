# CLI UX 6: Runtime Feedback — PRE Implementation Plan

Date: 2026-04-23
Status: PRE / planning only
Precondition: Bundle 5 validated

---

## 1. Context: Real User Feedback

A real ACPM run attempt:

```
acpm run --campaign NGL_sweep --profile Balanced --tier 1x
```

Resulted in:

- 6 configs × 6 cycles × 6 requests = 216 total requests
- First config: `n_gpu_layers=10`
- Each request: ~1.5–2 minutes
- Redirected output made terminal appear frozen
- User could not tell whether QuantMap was working, loading, or stalled

CLI Audit 1 already identified:

- "`run --validate` mixes human output and logger output"
- "no shared progress vocabulary"
- "no predictable 'what phase am I in?' structure"

---

## 2. Current Runtime Output Truth

### What happens during `quantmap run`

1. Campaign setup (logging starts)
2. Baseline YAML resolution
3. Campaign YAML loading
4. RunPlan compilation (silent unless dry-run)
5. Telemetry server startup → **first quiet period**
6. Warmup requests → **second quiet period**
7. Per-cycle benchmarks → progress prints
8. Cooldown between configs → spinner with temps
9. Summary → artifacts written

### Existing progress in `runner.py`

- Cooldown spinner with live temperatures
- Per-cycle prints
- Config completion summaries
- Telemetry startup check
- Preflight inspection

### What's missing

- No phase header for loading/config
- No phase header for model load
- No phase header for benchmark start
- No pre-execution runtime size disclosure
- No estimated duration language

---

## 3. Exact Runtime Feedback Scope

### In scope (this bundle):

1. **Phase headers** — explicit announcement for each phase:
   - "Loading configuration..."
   - "Loading model..." / "Starting server..."
   - "Validating..."
   - "Benchmarking config X of Y (n_gpu_layers=Z)..."
   - "Cooling down..."
   - "Writing artifacts..."

2. **Runtime size disclosure** — before execution begins (cautious language):
   ```
   Execution plan:
     Configs:     6
     Cycles:      6 per config
     Requests:   6 per cycle
     Total:      216 requests
     First:      n_gpu_layers=10
   
   Duration: estimate unavailable until first request completes.
   Timing will display after config 1 finishes.
   ```

3. **Progress heartbeat** — during quiet phases:
   - One dot every 2 seconds during server startup
   - Clear phase context

4. **Output redirection guidance** — document in help:
   ```
   Note: Redirected output (>) hides live progress.
   To monitor redirected output in another terminal:
     Get-Content "<path>" -Tail 80 -Wait
   ```

### Out of scope (deferred to later bundles):

- `quantmap onboard` command
- Wizard/setup flow
- Folder selection
- Server health-check command
- Onboarding UX
- Truth-lane changes
- Scoring/policy changes

---

## 4. Likely Files/Functions Affected

| File | Change | Rationale |
|------|--------|-----------|
| `src/runner.py` | Add phase headers | Announce each phase |
| `src/ui.py` | Add progress helpers | Shared output utilities |
| `quantmap.py` | Update run epilog | Output redirection tip |

### Functions to modify

- `run_campaign()` — add phase headers around startup, model load, benchmark
- `validate_campaign()` — add phase headers
- `ui.py` — add `print_phase_header()`, `print_runtime_disclosure()`

---

## 5. Explicit Out-of-Scope Items

- Onboarding command — deferred
- Wizard/setup flow — deferred
- Folder selection — deferred
- Server health check — deferred
- Truth-lane changes — none
- Scoring/recommendation/policy — none

---

## 6. Blast Radius and Risks

### Blast radius (runtime output only)

- Text additions to runner output
- New phase headers
- Runtime disclosure block

### Risks

| Risk | Probability | Impact | Mitigant |
|------|-------------|--------|----------|
| Spam during benchmark | Low | Low | Only header per config |
| Duration estimate wrong | Medium | Low | Use "approximately" language |
| Logger bleeds through | Low | High | Keep operator output separate |

---

## 7. Validation Plan

### Bounded validation commands

```powershell
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths src/runner.py src/ui.py quantmap.py
.\.venv\Scripts\python.exe -m ruff check src/runner.py src/ui.py quantmap.py
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_guided_shell.py test_cli_ux_acpm_run.py
```

### Help smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py run --help
.\.venv\Scripts\python.exe quantmap.py acpm run --help
```

### Dry-run smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py run --campaign NGL_sweep --dry-run 2>&1
.\.venv\Scripts\python.exe quantmap.py acpm run --campaign NGL_sweep --profile Balanced --dry-run 2>&1
```

### Verification checks

- Phase headers appear in dry-run output
- Runtime disclosure appears before dry-run execution
- No logger bleed-through in CLI output
- Help includes output redirection tip

---

## 8. Implementation Order

1. **Add progress utilities to ui.py** — `print_phase_header()`, `print_runtime_disclosure()`
2. **Add phase headers to runner.py** — wire loading, server start, benchmark phases
3. **Add runtime disclosure** — show config/cycle/request counts before run
4. **Update run epilog** — add output redirection tip
5. **Run validation pass** — bounded commands above
6. **Write validation report** — `CLI-UX-6-Runtime-Feedback-Validation.md`

---

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`