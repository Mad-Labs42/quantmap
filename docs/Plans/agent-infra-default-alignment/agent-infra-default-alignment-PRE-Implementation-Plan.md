# Agent-Infra Default Alignment: Pre-Implementation Plan

**Date**: 2026-04-20  
**Objective**: Make agent-infra workflow the unavoidable, standard default for local development, IDE-agent work, and CI, eliminating hidden config/environment mismatches and test-time drift.

---

## Executive Summary

The pytest-cov issue (config assumed plugin, local drifted, CI masked it) is **emblematic of a systematic problem**: the repo has agent-infra guardrails and instructions but hasn't made them the **mandatory, frictionless default path**. This plan identifies 12 distinct drift points across 5 layers and recommends a **phased 3-pass implementation** that makes compliance automatic rather than aspirational.

**Key Finding**: Agent infrastructure exists and works, but it's **opt-in advisory** rather than **required enforcement**. Bootstrap, IDE behavior, dependency contracts, and CI workflows have evolved independently, creating risk multipliers for both local dev and review.

---

## Current-State Findings

### Drift Points Summary (12 Distinct Issues)

#### Layer 1: Interpreter Ownership & Selection
1. **No workspace interpreter pinned in .vscode/settings.json**  
   - Active interpreter: global `mise` Python 3.14.3  
   - .venv exists but not enforced as default  
   - IDE terminal may inherit system Python or unrelated environment  
   - **Risk**: Different Python versions between local CLI and test commands; global packages leak into reproducibility

2. **Global vs. workspace venv unclear**  
   - Workspace .venv contains correct tools but discovery is manual  
   - No `.vscode/settings.json` entry for `python.defaultInterpreterPath`  
   - Users may not know which Python is running their commands  
   - **Risk**: Silent misalignment between test and manual runs

#### Layer 2: Bootstrap / Install Contract
3. **Development tool declarations incomplete**  
   - pyproject.toml dev extras: `pytest>=9.0.0`, `pytest-cov>=6.0.0`, type stubs  
   - **Missing**: `mypy`, `ruff` (both used in dev/CI workflows, not declared)  
   - Memory artifact says they should be there; actual config omits them  
   - **Risk**: `pip install -e .[dev]` on fresh clone will not install mypy/ruff; developers will hit missing-tool errors

4. **CI masking missing dev tools**  
   - Ruff: runs as advisory (continue-on-error) without explicit install  
   - Mypy: explicitly installs via `pip install -U mypy` in digest job  
   - Result: CI works despite dev deps being incomplete; local dev fails silently  
   - **Risk**: "Works in CI, not locally" feedback loop; developers lose trust in local signal

5. **Requirements.txt vs. pyproject.toml duplication**  
   - Both exist; only pyproject.toml has dev extras  
   - requirements.txt is runtime-only and outdated  
   - Unclear which is canonical  
   - **Risk**: Confusion on bootstrap path; legacy fallback chosen over modern standard

#### Layer 3: Canonical Command Contract
6. **No single source of truth for dev commands**  
   - Preferred pytest: `python -m pytest -q` (defined in pyproject.toml addopts)  
   - Quickstart mentions: `pip install .` then `quantmap init` (product commands, not dev)  
   - Contributing guide mentions: `quantmap about`, `quantmap doctor`, `quantmap self-test` (CLI ops, not dev)  
   - Agent instructions mention: `python -m ruff check`, `python -m mypy` (tools exist but not declared)  
   - No canonical README section on "Developer Setup"  
   - **Risk**: Developers follow different paths; no single command-sequence that guarantees correctness

#### Layer 4: Local vs. CI Contract Parity
7. **CI install path vs. declared deps mismatch**  
   - CI: `python -m pip install -e .[dev]` (correct)  
   - Dev deps in pyproject.toml: incomplete (missing mypy, ruff)  
   - Result: CI would fail if it strictly relied on -e .[dev] for mypy/ruff; instead it compensates  
   - **Pattern from pytest-cov issue**: CI installs what local dev doesn't declare, masking the gap  
   - **Risk**: If ruff is ever removed from advisory → CI suddenly fails; developers have no local signal to warn them

8. **Digest jobs compensate for missing tools**  
   - mypy digest: `pip install -U mypy` (explicit late-binding install)  
   - pip-audit digest: `pip install -U pip-audit` (explicit late-binding install)  
   - These are essential diagnostic jobs that fail silently if tools are missing  
   - **Risk**: "Fresh clone" developer never sees mypy errors until CI; immediate feedback loop broken

#### Layer 5: Agent Entry Workflow
9. **Agent bootstrap chain not enforced for dev tasks**  
   - `.agent/instructions/agent_session_bootstrap.md` defines mandatory read-chain  
   - `.agent/reference/terminal_guardrails.md` defines guardrails for mutating commands  
   - These exist but are not linked from developer-facing docs  
   - No CI check enforces that agents follow the chain  
   - **Risk**: Agent sessions diverge in rigor; each new session re-learns the patterns

10. **No preflight smoke-check before local dev work**  
    - `python .agent/scripts/agent_surface_audit.py --strict` validates agent config  
    - `python .agent/scripts/agent_workflow_smokecheck.py` validates instruction chain  
    - CI runs surface audit; local dev does not  
    - No bootstrap script reminds dev to verify setup  
    - **Risk**: Local work may diverge from CI expectations; developers don't catch drift early

#### Layer 6: Docs / Bootstrap / Command Contract
11. **Developer setup instructions scattered and incomplete**  
    - README.md: mentions Phase 3 focus, skips dev setup details  
    - Quickstart.md: user-facing ("Run campaigns"), not developer setup  
    - Contributing.md: safety rules, but no "First Steps" setup sequence  
    - .env.example: product config (QUANTMAP_SERVER_BIN, QUANTMAP_MODEL_PATH)  
    - No single "Developer Setup" section linking to: Python version → venv → install → check tools → run tests  
    - **Risk**: New contributor has no canonical path; they guess, make mistakes, or ask

12. **No repo-native smoke-test on first shell open**  
    - IDE does not run preflight checks on workspace open  
    - Terminal does not source a `.venv` activate script that could verify readiness  
    - No `.agent/scripts/helpers/` script to audit local environment  
    - **Risk**: Developer can work for hours in misconfigured environment before discovering the issue

---

## Failure Mode Analysis (Pytest-Cov as Template)

The pytest-cov issue demonstrates a **systematic pattern**:

1. **Config assumes a tool** → `pyproject.toml` addopts assume `--cov=.`
2. **Local deps don't declare it** → dev deps missing `pytest-cov` (NOW FIXED, but pattern persists for mypy/ruff)
3. **CI compensates silently** → CI installs plugin explicitly, masking the gap
4. **Developer gets surprised** → local `pytest` works, CI "just works", but fresh clone fails
5. **Trust eroded** → developer doesn't know which path is canonical

**Other classes of failure lurking in same pattern**:

- Config assumes `mypy` → runs `python -m mypy .` in CI digest → not in dev deps
- Config assumes `ruff` → runs `python -m ruff check .` in CI → not in dev deps
- Config assumes pip in certain state → CI installs tools explicitly, masking old pip versions
- Config assumes Python 3.13 → CI specifies it; local .venv may be 3.12; silent version mismatch
- Config assumes .venv activated → global Python leaks into shell, masking issues

---

## Recommended Target Operating Model

### Core Contract

**Every developer follows one mandatory, frictionless path:**

```
1. Clone repo
2. python -m venv .venv
3. .venv\Scripts\activate (or .\\.venv\Scripts\Activate.ps1 on PowerShell)
4. python -m pip install --upgrade pip
5. python -m pip install -e .[dev]
6. python .agent/scripts/agent_surface_audit.py --strict  (verify setup)
7. python -m pytest -q  (verify tests pass)
```

**After this sequence, developer is ready to work:**
- All declared deps installed (including mypy, ruff, pytest, pytest-cov)
- Workspace .venv is active interpreter
- Agent-infra guardrails are known to be working
- Dev commands all use canonical paths

### Layer-by-Layer Targets

#### Layer 1: Interpreter Ownership (Mandatory)
- `.vscode/settings.json` explicitly pins `python.defaultInterpreterPath` to `.venv/Scripts/python.exe`
- Terminal auto-activation: `.vscode/settings.json` includes `"terminal.integrated.env.windows": { "VIRTUAL_ENV": "${workspaceFolder}/.venv" }`
- PowerShell profile in `.vscode/settings.json` auto-activates .venv on shell open (VS Code-scoped only)
- Developer docs: one sentence: "VS Code will auto-select .venv as your interpreter and activate it in terminals."

#### Layer 2: Bootstrap / Install Contract (Mandatory)
- Add `mypy>=1.13.0` and `ruff>=0.8.0` to `[project.optional-dependencies].dev` in pyproject.toml
- Remove requirements.txt entirely OR clearly mark it as deprecated/legacy
- Create `.agent/scripts/helpers/verify_dev_environment.py`: checks Python version, .venv, installed packages, read-only
- CI .yml: add `verify_dev_environment.py` as first step before tests (smoke-check)
- Bootstrap docs: one true sequence (see target operating model above)

#### Layer 3: Canonical Command Contract (Mandatory)
- README.md: add "Developer Setup" section with exact commands (copy from target operating model)
- Contributing.md: link to README Developer Setup, add subsection "Running Tests Locally"
- Add .agent/scripts/helpers/local_dev_checklist.md: checklist for before-first-PR (one per session, not burden-some)
- All agent instructions: reference "see README Developer Setup" rather than inventing paths
- Command contract: one path for each tool:
  - Lint: `python -m ruff check <paths>`
  - Type-check: `python -m mypy <paths>`
  - Test: `python -m pytest -q <paths>`
  - Verify: `python .agent/scripts/changed_path_verify.py`

#### Layer 4: Local vs. CI Parity (Mandatory)
- CI `.yml` `Install package + test deps` step: ONLY `python -m pip install -e .[dev]` (no late-binding installs)
- CI `.yml` `Ruff check` step: remove `continue-on-error: true` → fail if ruff not available (blocking)
- CI `.yml` `mypy digest` step: remove explicit `pip install -U mypy` → rely on -e .[dev]
- CI `.yml` `pip-audit digest` step: add to dev deps OR keep as late-binding install (document why)
- All diagnostic jobs: fail fast if tools are not available (no silent skip)
- CI output: if install step succeeds, all tools are guaranteed available

#### Layer 5: Agent Entry Workflow (Mandatory)
- `.agent/instructions/agent_session_bootstrap.md`: add explicit link to README Developer Setup
- `.agent/instructions/agent_command_catalog.md`: add section "Pre-work Checklist" with exact commands
- `.agent/scripts/helpers/preflight_dev_check.py`: new script that verifies .venv, tools, git state before agent work
- CI: add early `preflight_dev_check.py` step (smoke-test for agent infra)
- Agent instructions: no local dev work without running preflight check first

#### Layer 6: Docs / Bootstrap (Mandatory)
- README.md: new section "⚙️ Developer Setup" (150 words max, exact commands, expected output)
- Contributing.md: new subsection "Local Development Workflow" linking to README
- docs/system/contributing.md: new section "Testing Your Changes" with canonical commands
- Create `.vscode/README.vscode.md`: explains interpreter pinning, venv activation, why it matters
- .env.example: add comment section "# Developer Setup (product vs. test environment)"

#### Layer 7: Guardrails & Smoke Checks (Advisory → Enforcement)
- Add `.agent/scripts/helpers/verify_dev_environment.py`: run on every shell open (non-blocking digest)
- Create `test_environment_contract.py`: unit test that verifies pyproject.toml matches CI expectations
- Create `.vscode/launch.json`: Python debug profile that auto-activates .venv and checks contract
- PR template: add checkbox "Environment contract verified (ran preflight check locally)"

---

## Proposed Implementation Sequence (Phased)

### Phase 1: Foundation (Blocking, Day 1)
**Goal**: Make the install contract airtight and verify it works.

**Changes**:
1. Add `mypy>=1.13.0`, `ruff>=0.8.0` to pyproject.toml dev extras
2. Update CI .yml: remove late-binding `pip install -U mypy` from digest jobs
3. Update CI .yml: change `Ruff check` from advisory to blocking
4. Create `.agent/scripts/helpers/verify_dev_environment.py` (smoke-check script)
5. Update README.md: add "Developer Setup" section with exact commands and expected output
6. Verify locally: `pip install -e .[dev]` → all tools available → tests pass

**Verification**:
- Fresh clone + commands in README = working dev environment
- CI test job succeeds with only `pip install -e .[dev]`
- Agent surface audit passes

**Risk**: CI may briefly red if ruff is run as blocking and finds issues (acceptable; addresses drift)

### Phase 2: Interpreter Pinning (Medium Priority, Day 2-3)
**Goal**: Make .venv the mandatory default interpreter, eliminate silent Python version mismatches.

**Changes**:
1. Add Python interpreter path to `.vscode/settings.json` (or `.devcontainer.json` if used)
2. Create `.vscode/tasks.json`: define "Activate .venv" task with terminal auto-activation
3. Update `.agent/instructions/agent_session_bootstrap.md`: reference venv activation
4. Create `.vscode/README.vscode.md`: explain why interpreter pinning matters
5. Add `test_environment_contract.py`: verify Python version, venv activation, tool availability

**Verification**:
- Open workspace in VS Code → venv auto-activated in terminal
- `which python` / `Get-Command python` shows .venv/Scripts/python.exe
- Test runs use correct interpreter version

**Risk**: Windows/Mac/Linux path differences in venv activation; mitigate with OS-specific .vscode settings

### Phase 3: Agent-Infra Integration (Polish, Day 4)
**Goal**: Close the loop: agents know the canonical workflow, preflight checks are standard.

**Changes**:
1. Add `.agent/scripts/helpers/preflight_dev_check.py`: verify .venv, git state, dirty files before agent work
2. Update `.agent/scripts/agent_session_bootstrap.md`: link to README, mention preflight check
3. Update `.agent/scripts/helpers/changed_path_verify.py`: auto-call verify_dev_environment at start (non-blocking)
4. Add `.agent/scripts/helpers/ci_bootstrap_smoke_check.py`: run as first CI step
5. Create CI `bootstrap-check` job: runs before test job; fails if deps don't match expectations
6. Update PR template: add checkbox for environment contract verification
7. Create `docs/contributing/developer-setup.md`: complete guide with troubleshooting

**Verification**:
- Agent starts session → runs preflight check → warns on config drift
- CI `bootstrap-check` job catches missing tools before tests run
- PR template reminds reviewers to ask about local setup if tests fail
- Fresh clone → exact sequence in README → everything works

**Risk**: Preflight checks are non-blocking by default; document when to escalate if contract is broken

---

## Risks & Tradeoffs

### Risk: Over-Enforcement Breaks New Contributors
- **Mitigation**: Phase 2 preflight checks are non-blocking (warnings, not failures); Phase 1 ensures tools are declared upfront
- **Rationale**: Let contributors work; catch drift early; escalate to developer if test fails

### Risk: .vscode Settings Break Cross-OS Setup
- **Mitigation**: Use `${workspaceFolder}` and PowerShell-native activation; test on Windows first (project constraint)
- **Rationale**: QuantMap is Windows-first; CI runs on windows-latest

### Risk: Existing Developers May Have Stale Environments
- **Mitigation**: Phase 1 makes install contract explicit; developers re-run `pip install -e .[dev]`
- **Rationale**: One sentence in PR template: "Please re-run pip install -e .[dev] to pick up new dev tools"

### Risk: Late-Binding Tool Installs (pip-audit, etc.) Conflict with Declared Deps
- **Mitigation**: Document policy: diagnostic tools can late-bind if they're not core to dev workflow
- **Rationale**: pip-audit, CodeQL, SonarCloud are advisory; pytest/mypy/ruff are mandatory

### Risk: CI Bootstrap Check Adds Time
- **Mitigation**: Minimal script (< 100 lines); cached pip check; run in parallel with linting
- **Rationale**: Catches drift early; prevents cascading failures later

---

## Likely Future Failure Modes (Anticipatory)

### Pattern 1: New Tool Assumed But Not Declared (Repeat of pytest-cov)
- **Detection**: CI digest job tries to import a tool → fails silently → developers never see signal
- **Prevention**: CI bootstrap check must verify all tools CI uses are in declared deps
- **Watch-out**: When adding new CI digest job, add tool to dev deps first

### Pattern 2: Python Version Drift
- **Detection**: Workspace .venv is 3.12; CI runs 3.13; type stubs are version-specific
- **Prevention**: Pin Python version in pyproject.toml, .vscode settings, and CI workflow
- **Watch-out**: `requires-python` in pyproject.toml should match CI matrix; lint this constraint

### Pattern 3: Interpreter Activation Not Inherited by Subshells
- **Detection**: Developer runs `python -m pytest` → uses global Python; test failures are mysterious
- **Prevention**: No subshells; always explicit `.venv\Scripts\python.exe -m <tool>`
- **Watch-out**: Guard against users creating wrapper scripts that bypass venv

### Pattern 4: Global Tools Satisfy Repo Contracts
- **Detection**: Developer installs `ruff` globally; local work passes; CI runs different version → different results
- **Prevention**: Terminal guardrails should error if wrong Python is active; agent checks interpreter
- **Watch-out**: Add `test_environment_contract.py` that fails if non-.venv Python is used

### Pattern 5: Stale .venv Not Updated After pyproject.toml Changes
- **Detection**: Dev adds new dep to pyproject.toml; forgets to re-run `pip install -e .[dev]`; tests fail
- **Prevention**: Git hook or pre-commit check that reminds on pyproject.toml changes
- **Watch-out**: Phase 1 avoids this by making install explicit in README; Phase 3 adds soft guardrails

---

## Open Questions

1. **Should requirements.txt be deleted or kept as deprecated fallback?**
   - Current state: exists, not used (dev uses pyproject.toml; CI uses pyproject.toml)
   - Recommendation: Delete in Phase 1; if needed later, can recreate from pyproject.toml
   - Impact: Removes ambiguity; forces all paths through pyproject.toml

2. **What is the policy for late-binding diagnostic tool installs?**
   - Current state: mypy, pip-audit install themselves in CI digest jobs
   - Options: (A) Move all to dev deps; (B) Keep late-binding, document in CI policy
   - Recommendation: Option A for core tools (mypy, ruff); Option B for advisory (pip-audit, CodeQL digest)
   - Impact: Cleaner bootstrap contract; dev deps grow slightly

3. **Should preflight checks block local work or warn?**
   - Current state: Not implemented yet
   - Options: (A) Blocking (agent won't start if drift detected); (B) Non-blocking digest
   - Recommendation: Non-blocking by default; blocking only for critical gaps (e.g., .venv missing)
   - Impact: Balances safety with developer friction

4. **Should VS Code settings be repo-committed or ignored?**
   - Current state: `.vscode/settings.json` is repo-committed with limited config
   - Issue: Personal IDE settings may conflict; some developers use other editors
   - Recommendation: Commit only safe, project-scoped settings (interpreter path, yaml schema); allow personal overrides
   - Impact: Reduces configuration friction; keeps project intent clear

5. **How to ensure CI bootstrap check doesn't become stale?**
   - Current state: Would be new; maintainability risk
   - Options: (A) Part of agent_surface_audit; (B) Standalone script with explicit maintenance cadence
   - Recommendation: Integrate with agent_surface_audit.py; make it part of standard CI artifact review
   - Impact: Reduces maintenance surface; links to existing agent governance

---

## Implementation Recommendation: Phased (3 Pass)

**Why Not One Pass?**
- Phase 1 is strictly necessary; can be done immediately; unblocks developers
- Phase 2 requires testing on Windows (OS-specific .vscode config); benefits from Phase 1 working first
- Phase 3 is polish; Phase 1 + 2 are sufficient for MVP

**Why 3 Distinct Phases?**
- Each phase can be tested independently before merging
- Phase 1 → test suite passes (immediate feedback)
- Phase 2 → developers report venv activation works (2-3 days of use)
- Phase 3 → agent sessions are more rigorous (long-term metric)

**Recommended Timeline**:
- Phase 1: 1-2 hours (add deps, update CI, update docs)
- Phase 2: 4-6 hours (test .vscode config on multiple shells, create tasks/README, test Windows path handling)
- Phase 3: 3-4 hours (integrate with agent_surface_audit, create preflight helpers, update templates)
- **Total**: ~0.5-1.0 day of implementation work; verifies across 2-3 days of developer use

---

## Success Criteria

### Phase 1 (Foundation)
- ✅ Fresh clone + commands in README = working dev environment
- ✅ `python -m pip install -e .[dev]` installs mypy, ruff, pytest, pytest-cov
- ✅ CI test job succeeds; ruff check is now blocking (not advisory)
- ✅ Zero developers hit "tool not found" error on fresh clone

### Phase 2 (Interpreter Pinning)
- ✅ VS Code auto-selects .venv interpreter on workspace open
- ✅ Developer terminal auto-activates .venv (PowerShell and CMD tested)
- ✅ `which python` confirms .venv Python is active
- ✅ `test_environment_contract.py` passes (Python version, venv activation, tools)

### Phase 3 (Agent Integration)
- ✅ Preflight checks run at agent start; catch config drift
- ✅ PR template reminds reviewers about environment setup
- ✅ CI bootstrap check catches missing tools before tests
- ✅ Zero PRs with "Works locally, fails in CI" messaging (or messaging includes "re-run pip install -e .[dev]")

---

## Implementation Ownership

- **Phase 1** (Foundation): Minimal; edit pyproject.toml, CI .yml, README
- **Phase 2** (Interpreter): Test .vscode settings on Windows CLI, PowerShell, CMD shells
- **Phase 3** (Integration): Create/integrate agent scripts; coordinate with agent governance cadence

---

## Files to Modify (By Phase)

### Phase 1
- `pyproject.toml`: add mypy, ruff to dev deps
- `.github/workflows/ci.yml`: remove late-binding install; make ruff blocking
- `README.md`: add Developer Setup section
- `.agent/scripts/helpers/verify_dev_environment.py`: new script

### Phase 2
- `.vscode/settings.json`: add python.defaultInterpreterPath, terminal env, ps profile
- `.vscode/README.vscode.md`: new guide
- `test_environment_contract.py`: new test
- `.agent/instructions/agent_session_bootstrap.md`: link to README

### Phase 3
- `.agent/scripts/helpers/preflight_dev_check.py`: new script
- `.agent/scripts/helpers/ci_bootstrap_smoke_check.py`: new script
- `.agent/scripts/agent_session_bootstrap.md`: reference preflight
- `.github/pull_request_template.md`: add environment checkbox
- `docs/contributing/developer-setup.md`: new guide

---

## Conclusion

The agent-infra alignment work is **achievable, low-risk, and high-value**. Current infra is sound; the gap is **making it mandatory and frictionless**. Phase 1 is critical and urgent (blocks the pytest-cov pattern from repeating); Phases 2-3 are refinements that pay dividends over time.

**Success means**: "Clone, copy-paste 4 commands from README, run tests, everything works." No guessing, no stack-overflow searches, no "works locally but fails in CI" surprises.
