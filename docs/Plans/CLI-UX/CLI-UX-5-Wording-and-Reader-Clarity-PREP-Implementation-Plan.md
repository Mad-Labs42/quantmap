# CLI UX 5: Wording and Reader Clarity — PRE Implementation Plan

Date: 2026-04-23
Status: PRE / planning only
Precondition: Bundles 1-4 validated

---

## 1. Current Repo Truth After CLI/UX Bundles 1-4

### Command Surface

```
quantmap {run,doctor,init,self-test,status,rescore,audit,list,about,compare,explain,explain-compare,export,artifacts,acpm}
acpm {info,plan,validate,run}
```

### ACPM Structural Truth (unchanged)

- 3 governed profiles: `Balanced`, `T/S`, `TTFT`
- Repeat tiers: `1x`, `3x`, `5x`
- ACPM planning metadata persisted adjacent to execution truth
- Recommendation truth lives in its own lane

### Bundle 4 Ending State

- All ACPM entry/invocation commands wired
- Help text exists for all subcommands
- Banners and render blocks for ACPM surfaces
- Post-run hints point to `acpm plan`

### Known Remaining Problems (from CLI Audit 1)

- Help text is one-line, rarely teaches mental model
- No examples in CLI help
- No command relationships shown
- No safety class indication (read-only vs. mutating)
- `compare`, `explain-compare`, `audit` overlap but don't read like a family
- `status`, `doctor`, `self-test` all check "health" with different scopes
- Not-found messages lack remediation hints
- Inconsistent terminology (e.g., "validation" vs. "pre-flight")
- Truncated campaign IDs hard to copy from `list`
- `self-test` wording overstates measurement readiness

---

## 2. Exact Bundle 5 Scope

Deep wording and reader-clarity pass across all user-facing CLI language.

**In scope:**

1. **Help text expansion** — add mental model, command relationships, safety class, examples
2. **Error/not-found messages** — add remediation hints, close-match suggestions
3. **Status/label consistency** — unify terminology across commands
4. **Confirmation wording** — clarify read-only vs. mutating
5. **ACPM output wording** — ensure consistent terminology
6. **Next-action hints** — ensure consistency and utility

**Not in scope:**

- New commands — none
- Truth-lane changes — none
- Report/design redesign — wholesale changes not in scope
- Scoring/recommendation/filter policy — no changes

---

## 3. User-Facing Language Surfaces to Inspect

| Surface | Files to Inspect |
|---------|-----------------|
| Top-level help | `quantmap.py` argparser epilog |
| Subcommand help | Each subparser description/epilog |
| Banners/headings | `src/ui.py:print_banner` |
| Status output | `src/ui.py`, `quantmap.py:cmd_status` |
| Readiness output | `src/doctor.py`, `src/selftest.py`, `src/diagnostics.py` |
| Validation messages | `src/runner.py:validate_campaign`, `src/ui.py` |
| Error messages | `quantmap.py`, `src/*.py` |
| Artifact wording | `src/artifact_paths.py`, `src/runner.py` |
| ACPM output | `src/ui.py:render_acpm_*`, `quantmap.py:cmd_acpm_*` |
| Recommendation status | `src/acpm_recommendation.py` (where CLI-adjacent) |
| List output | `src/list.py` |

---

## 4. Wording Principles / Style Rules

### Core Principles

1. **Teach the mental model** — help text should explain *why* and *when*, not just *what*
2. **Show command relationships** — group related commands, show family hierarchy
3. **Indicate safety** — mark commands as read-only, validating, or mutating
4. **Provide remediation** — every error should suggest the next reasonable step
5. **Be consistent** — same concept = same word; different concept = different word

### Style Rules

- Use active voice for actions, passive for status
- Prefer "verify" over "check" for read-only operations
- Prefer "execute" over "run" when referring to non-CLI execution
- Use "validation" as the umbrella term, "pre-flight" as subset
- Include one realistic example in each subcommand help
- Truncate only when necessary; provide full values on request
- Capitalize banners consistently (`Sentence case` with initial caps)
- Use emoji sparingly and consistently (only for state indication)

### Problem Categories to Fix

| Category | Problem | Fix |
|----------|--------|-----|
| Shallow help | `--help` is one-line | Add 1-2 sentence description, example |
| No examples | No command examples | Add one realistic example per subcommand |
| No relationships | Commands don't show family | Add "see also" cross-references |
| Overlap | status/doctor/self-test unclear | Add scope annotation to help |
| Not-found dumb | No remediation | Add `quantmap list` hint, close matches |
| Inconsistent terms | "validation" vs "pre-flight" | Pick one term, alias the other |
| Truncation | IDs hard to copy | Show full ID in footer or `--long` flag |
| self-test overstatement | Claims "measurement readiness" | Scope to "tool integrity" |

---

## 5. Specific Problem Statements

### Problem 1: Top-level help is shallow

Current:
```
quantmap --help
...
run                 Execute or validate a benchmark campaign
doctor              Perform environment health checks
```

Desired: Help should teach the primary workflow and show command relationships.

### Problem 2: Subcommand help lacks examples

Current: `quantmap run --help` shows flags but not run-mode semantics.

Desired: At least one realistic example showing common use.

### Problem 3: Not-found lacks remediation

Current: `quantmap explain wrong_id` → "Campaign not found"

Desired: "Campaign not found. Did you mean X? Run `quantmap list` to see available campaigns."

### Problem 4: status/doctor/self-test overlap unclear

Current: All three check "health" with no clear distinction.

Desired: Help text should explicitly state scope difference.

### Problem 5: self-test wording overstates readiness

Current: "ENVIRONMENT READY" implies measurement readiness.

Desired: Scope to "tooling integrity verified" or similar.

### Problem 6: ACPM validate vs. run --validate vs. pre-flight

Current: Multiple validation-related terms, unclear relationship.

Desired: Unify terminology or document the relationship.

### Problem 7: List truncation

Current: Campaign IDs truncated, hard to copy for later commands.

Desired: Show full IDs in footer or provide copyable format.

---

## 6. Files Likely Affected

| File | Change Type | Rationale |
|------|------------|-----------|
| `quantmap.py` | Edit argparser descriptions/epilogs | Help text expansion |
| `src/ui.py` | Edit banner templates | Wording consistency |
| `src/doctor.py` | Edit help/output | Scope clarification |
| `src/selftest.py` | Edit help/output | Scope to tooling |
| `src/list.py` | Edit output | Full ID visibility |
| `src/artifact_paths.py` | Edit not-found messages | Remediation hints |

---

## 7. Explicit Out-of-Scope Items

- New commands — none
- New `--profile` / `--tier` flags on manual `run` — deferred
- ACPM-specific `run_mode` — deferred
- Report wholesale redesign — not in scope
- DB/schema changes — none
- Truth-lane changes — none
- Scoring/recommendation/filter policy — none

---

## 8. Blast Radius and Risks

### Blast Radius (local wording only)

- All help text changes are additive
- Error messages are text-only
- No behavioral changes

### Risks

| Risk | Probability | Impact | Mitigant |
|------|-------------|--------|----------|
| Help text bloat | Medium | Low | Keep to 1-2 sentences + 1 example |
| Terminology drift | Medium | Medium | Document chosen terms explicitly |
| Inconsistent changes | Low | High | Add terminology checklist to validation |

---

## 9. Smallest Strong Validation Plan

### Bounded validation commands

```powershell
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths quantmap.py src/ui.py src/doctor.py src/selftest.py src/list.py
.\.venv\Scripts\python.exe -m ruff check quantmap.py src/ui.py src/doctor.py src/selftest.py src/list.py
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_*.py
```

### Help smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py --help
.\.venv\Scripts\python.exe quantmap.py run --help
.\.venv\Scripts\python.exe quantmap.py status --help
.\.venv\Scripts\python.exe quantmap.py doctor --help
.\.venv\Scripts\python.exe quantmap.py self-test --help
.\.venv\Scripts\python.exe quantmap.py list --help
.\.venv\Scripts\python.exe quantmap.py acpm --help
.\.venv\Scripts\python.exe quantmap.py acpm run --help
```

### Not-found regression

```powershell
.\.venv\Scripts\python.exe quantmap.py explain DOES_NOT_EXIST 2>&1
.\.venv\Scripts\python.exe quantmap.py run --campaign DOES_NOT_EXIST --validate 2>&1
```

### Terminology check

```powershell
.\.venv\Scripts\python.exe quantmap.py acpm validate --campaign NGL_sweep --profile Balanced 2>&1
.\.venv\Scripts\python.exe quantmap.py run --campaign NGL_sweep --validate 2>&1
```

Verify consistent use of "validation" vs. "pre-flight."

---

## 10. Recommended Implementation Order

1. **Catalog all user-facing strings** — dump all help text, banners, error messages to a checklist
2. **Apply terminology rules** — pick one term per concept, create alias map
3. **Expand top-level help** — add workflow guidance, command relationships
4. **Expand subcommand help** — add example, scope annotation, "see also"
5. **Fix not-found messages** — add remediation hints
6. **Fix self-test wording** — scope to tooling integrity
7. **Fix list truncation** — add full IDs in footer
8. **Run validation pass** — bounded commands above
9. **Write validation report** — `CLI-UX-5-Wording-and-Reader-Clarity-Validation.md`

---

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`