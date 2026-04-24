# CLI UX 6: Runtime Feedback and Onboarding — PRE Implementation Plan

Date: 2026-04-23
Status: PRE / planning only
Precondition: Bundle 5 validated

---

## 1. Context: Real User Feedback

A real ACPM run attempt revealed:

1. **Long quiet period after launch** — user cannot tell whether QuantMap is working, loading, stalled, or waiting
2. **Inconsistent runtime feedback** — some phases show progress, others go silent
3. **Output redirection confusion** — redirecting output to a file made terminal appear frozen
4. **No onboarding command** — new users lack a single polished starting point

CLI Audit 1 already identified:

- "`run --validate` mixes human output and logger output" (line 298-300)
- "console and logs are too intertwined" (line 325)
- "no shared progress vocabulary" (line 323)
- "no predictable 'what phase am I in?' structure" (line 324)

---

## 2. Current Repo Truth for Runtime Output

### What happens during `quantmap run`:

1. Campaign setup (logging starts)
2. Baseline YAML resolution
3. Campaign YAML loading
4. RunPlan compilation (existing, silent unless dry-run)
5. Telemetry server startup → **first quiet period** (llama-server loads model)
6. Warmup requests → **second quiet period** (backend compiles)
7. Per-cycle benchmarks → progress prints per config
8. Cooldown between configs → spinner with temperatures
9. Summary → result artifacts written

### Phase headers and progress currently in `runner.py`

- Cooldown spinner with live temperatures
- Per-cycle prints
- Config completion summaries
- Explicit telemetry startup check
- Preflight inspection

### What's missing

- No standard phase header model across validate/run/analyze/report
- No shared progress vocabulary (no unified "what phase am I in?")
- Loading phase not explicitly announced
- Model-load phase not explicitly announced
- Benchmarking phase not explicitly announced

---

## 3. Exact Bundle 6 Scope

### Runtime feedback improvements (in scope):

1. **Phase announcement** — explicit header for each major phase:
   - "Loading configuration..."
   - "Loading model..."
   - "Validating..."
   - "Benchmarking config X of Y..."
   - "Cooling down..."
   - "Writing artifacts..."

2. **Progress heartbeat** — periodic pulse during quiet phases:
   - One dot or spinner every N seconds
   - "Still alive" indicator

3. **Output redirection safety** — clearly warn or guide:
   - When redirection is active, mention log file location
   - Suggest `--log` or specify a log path
   - Or detect TTY and warn when redirecting

4. **Onboarding command** — new `quantmap onboard`:
   - Polished first-run sequence
   - Ask for/confirm folders
   - Check model paths
   - Check server readiness
   - Show telemetry status
   - Guide to first run

### What's explicitly out of scope:

- Not a giant wizard
- Not changing scoring/recommendation/filter policy
- Not changing ACPM truth lanes
- Not redesigning report generation
- Not verbose spam — just clean phase markers

---

## 4. Onboarding Command Proposal

### Name: `quantmap onboard`

Not `init` replacement — `init` stays for interactive lab setup.

`onboard` is for existing installation check and telemetry readiness confirmation.

### Proposed flow

```
$ quantmap onboard

QuantMap Onboarding Check
========================

[1/5] Lab directory...        OK: D:\.quantmap\lab
[2/5] Server binary...        OK: D:\.store\tools\llama.cpp\...\llama-server.exe
[3/5] Model shard 1...      OK: D:\.store\models\...\MiniMax-M2.5-...gguf
[4/5] Server reachability...  OK: server responding
[5/5] Telemetry setup...    OK: health check passed

Onboarding complete. Ready for benchmarking.

Next step:
  quantmap run --campaign <ID> --validate
  quantmap run --campaign NGL_sweep --profile Balanced --dry-run
```

### What `onboard` verifies

- Lab root exists and is writable
- Server binary present and executable
- Model shards present
- Server can start (health check)
- DB path reachable

---

## 5. Consistent Language / Output Rules

### Phase vocabulary

| Phase | Header | Progress indicator | Footer |
|-------|--------|------------------|--------|
| Config load | "Loading configuration..." | - | "OK" |
| Model load | "Loading model..." | spinner | "OK" |
| Validation | "Validating..." | dots | "PASS/FAIL" |
| Benchmarking | "Benchmarking config X/Y..." | "[====....]" | "complete" |
| Cooldown | "Cooling down..." | spinner | temperature |
| Write | "Writing artifacts..." | - | "done" |

### Style rules

- Phase headers: 2-3 words, clear verb + object
- Progress: 8-12 character width, filled/dots pattern
- Keep professional, serious tone
- No emoji during benchmark (save for status indicator only)
- Maximum one line every 2 seconds during quiet phases

---

## 6. Files/Surfaces Likely Affected

| File | Change Type | Rationale |
|------|------------|-----------|
| `src/runner.py` | Add phase headers | Runtime feedback |
| `src/ui.py` | Add progress helpers | Shared phase output |
| `quantmap.py` | Add onboard subparser | New onboarding command |
| `src/server.py` | Add health check | Onboard verification |
| `.agent/reference/command_reference.md` | Update | New command docs |

---

## 7. Explicit Out-of-Scope Items

- Giant wizard replacement for `init` — no
- ACPM truth-lane changes — none
- Scoring/policy changes — none
- Report redesign — none
- Verbose spamming — avoid

---

## 8. Blast Radius and Risks

### Blast radius (runtime behavior + new command)

- New phases in runner output
- New `onboard` command
- Small changes to progress display

### Risks

| Risk | Probability | Impact | Mitigant |
|------|-------------|--------|----------|
| Spammy output | Medium | Low | Limit to 1 line per 2 seconds |
| Onboard slow | Medium | Low | Fast health check, timeout 5s |
| Phase mismatch | Low | Medium | Match to existing runner phases |
| Log bleed through | Low | High | Clean separation in ui.py |

---

## 9. Smallest Strong Validation Plan

### Bounded validation commands

```powershell
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths quantmap.py src/runner.py src/ui.py
.\.venv\Scripts\python.exe -m ruff check quantmap.py src/runner.py src/ui.py
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_guided_shell.py test_cli_ux_acpm_entry.py test_cli_ux_acpm_run.py
```

### Help smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py --help
.\.venv\Scripts\python.exe quantmap.py onboard --help
```

### Runtime smoke (dry-run)

```powershell
.\.venv\Scripts\python.exe quantmap.py run --campaign NGL_sweep --dry-run 2>&1
.\.venv\Scripts\python.exe quantmap.py acpm run --campaign NGL_sweep --profile Balanced --dry-run 2>&1
```

### Onboard smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py onboard 2>&1
```

### Verification checks

- Phase headers appear in dry-run output
- No logger bleed-through in CLI output
- Onboard command exists and runs
- Help shows onboard command

---

## 10. Recommended Implementation Order

1. **Add phase headers to runner.py** — announce each phase
2. **Add progress heartbeat to ui.py** — shared progress utility
3. **Wire phase headers in runner** — wire up loading, model load, benchmark phases
4. **Add onboard command** — new subparser and handler
5. **Add onboard health check** — verify server can start
6. **Run validation pass** — bounded commands above
7. **Write validation report** — `CLI-UX-6-Runtime-Feedback-and-Onboarding-Validation.md`

---

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`