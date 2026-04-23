# Agent-Infra Default Alignment: Implementation Plan — Phase 1 Only

**Date**: 2026-04-20  
**Scope**: Establish explicit, repo-native development/tooling contract; achieve local/CI parity; enable one canonical setup path.  
**Not in Phase 1**: VS Code interpreter pinning, terminal auto-activation, broad policy rewrites (deferred to Phase 2).

---

## Phase 1 Objectives

1. ✅ **Repo declares the real dev contract** — pyproject.toml lists all tools CI expects  
2. ✅ **Local and CI use the same bootstrap** — no hidden CI-only installs compensating for gaps  
3. ✅ **Environment/contract is checkable** — one repo-native script verifies expectations  
4. ✅ **Setup path is explicit and minimal** — README has one short canonical sequence  
5. ✅ **Default pytest works locally as in CI** — no `--cov` plugin surprises  

---

## Current-State Gaps (Concrete Evidence)

| Gap | Evidence | Impact |
|-----|----------|--------|
| **mypy not in dev deps** | `pyproject.toml` lists pytest, pytest-cov, types-stubs; no mypy | CI has `pip install -U mypy` in digest job; local has nothing |
| **ruff not in dev deps** | `pyproject.toml` does not list ruff | CI runs ruff via `-m` with no guarantee it's installed |
| **Late-binding mypy install** | `.github/workflows/ci.yml` line 173: `python -m pip install -U mypy` | Local dev has no signal; fresh clone fails silently |
| **No environment verification** | No script checks Python version, tool availability, addopts satisfaction | Developers work for hours before discovering misconfiguration |
| **README lacks dev setup** | README.md mentions quickstart (user-facing), no "Developer Setup" section | New contributor has no canonical path; invents own |
| **requirements.txt role unclear** | Both requirements.txt and pyproject.toml exist; only pyproject.toml has dev extras | Ambiguity on which is canonical |

---

## Phase 1 Workstreams (Ordered by Dependency)

### Workstream 1: Complete pyproject.toml Dev Contract

**Objective**: Declare all tools local dev and CI expect.

**Changes**:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=9.0.0",
    "pytest-cov>=6.0.0",
    "mypy>=1.13.0",              # ADD — required for type checking
    "ruff>=0.8.0",                # ADD — required for linting
    "types-psutil",
    "types-PyYAML",
    "pandas-stubs",
]
```

**Why**:
- Declares the contract explicitly in repo metadata  
- `pip install -e .[dev]` now guarantees all tools are available  
- CI can rely on this contract instead of compensating with late-binding installs  
- New developers know exactly what to install

**Verification**:
- Manually: `pip install -e .[dev]` → `python -m mypy --version` → `python -m ruff --version` both work

---

### Workstream 2: Create Repo-Native Environment Contract Check

**Objective**: One authoritative script that verifies local environment satisfies repo expectations.

**File**: `.agent/scripts/helpers/verify_dev_contract.py`

**Scope**: Script verifies:
- Python version is in declared range (3.12+)  
- Required tools are importable: mypy, ruff, pytest, pytest-cov  
- pytest can access coverage plugin (`--cov` flag works)  
- No other environment assumptions (e.g., doesn't check .venv location)

**Output**:
- Exit code 0 if all checks pass; print summary of tools found and versions  
- Exit code 1 if any check fails; print actionable remediation (which tool is missing, which version conflict exists)  
- Include guidance: "Run `pip install -e .[dev]` to install all dev tools"

**Design Rationale**:
- Repo-native (not IDE-specific, not shell-specific)  
- Runnable locally: `python .agent/scripts/helpers/verify_dev_contract.py`  
- Runnable in CI: same command, same expectations  
- Lightweight; no external dependencies; uses only stdlib and importlib  
- Produces JSON output option for CI artifact capture (optional, but design for it)

**Sample Implementation Strategy** (pseudocode; actual to be coded):
```python
def check_python_version():
    import sys
    if sys.version_info < (3, 12):
        raise ContractError(f"Python {sys.version_info.major}.{sys.version_info.minor} found; 3.12+ required")

def check_tool_importable(tool_name):
    try:
        __import__(tool_name)
    except ImportError:
        raise ContractError(f"Tool {tool_name} not importable; run: pip install -e .[dev]")

def check_pytest_addopts():
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", "--co", "-q"],
        capture_output=True,
        text=True
    )
    if "--cov" in result.stdout or "coverage" in result.stderr:
        # pytest recognizes --cov option; plugin is available
        return True
    raise ContractError("pytest --cov flag not recognized; pytest-cov plugin may not be installed")

if __name__ == "__main__":
    try:
        check_python_version()
        check_tool_importable("mypy")
        check_tool_importable("ruff")
        check_tool_importable("pytest")
        check_tool_importable("pytest_cov")
        check_pytest_addopts()
        print("✓ Environment contract verified")
        sys.exit(0)
    except ContractError as e:
        print(f"✗ Contract violation: {e}")
        sys.exit(1)
```

---

### Workstream 3: Remove CI Late-Binding Installs for Core Tools

**Objective**: CI should trust declared dev dependencies, not compensate for gaps.

**Changes to `.github/workflows/ci.yml`**:

1. **Remove explicit mypy install** (line 173):  
   Delete or comment out: `python -m pip install -U mypy`  
   Justification: mypy is now in declared dev deps; CI's `pip install -e .[dev]` guarantees it

2. **Ruff check: leave as-is (advisory, no install needed)**  
   CI runs `python -m ruff check .` already; ruff is now declared in dev deps, so it will be available  
   (Note: ruff remains advisory in CI; not changing severity in this phase)

3. **Add early contract verification** (new step after install, before tests):  
   Add CI job step:
   ```yaml
   - name: Verify dev environment contract
     shell: pwsh
     run: python .agent/scripts/helpers/verify_dev_contract.py
   ```
   Placement: After "Install package + test deps" step; before "Ruff check" step  
   Severity: Blocking (fail CI if contract not satisfied)

**Why**:
- Removes hidden compensation; contract is now explicit  
- Guarantees that any tool CI expects is declared upfront  
- If a new tool is added to CI, developer must add it to pyproject.toml first  
- Local developers see the same signal CI does

---

### Workstream 4: Establish Local/CI Bootstrap Parity

**Objective**: Same `pip install -e .[dev]` command works locally and in CI; no surprises.

**Changes**:

1. **CI `.yml` install step** — verify it uses `-e .[dev]` (already does; confirm):
   ```yaml
   - name: Install package + test deps
     shell: pwsh
     run: |
       if (Test-Path "pyproject.toml") {
         python -m pip install -e .[dev]
       } elseif (Test-Path "requirements.txt") {
         python -m pip install -r requirements.txt
       }
   ```
   **Action**: Leave as-is; this is already correct.

2. **requirements.txt role clarification** — document in comments:
   - Add comment to requirements.txt: `# Legacy / frozen snapshot. Use 'pip install -e .[dev]' for development.`
   - Do NOT delete in Phase 1 (breaking change risk); mark as deprecated

3. **Verify bootstrap sequence works end-to-end**:
   - Simulate fresh clone: delete .venv, delete egg-info, reinstall  
   - Run: `pip install -e .[dev]`  
   - Run: `python .agent/scripts/helpers/verify_dev_contract.py`  
   - Run: `python -m pytest -q`  
   - All should pass without fallback commands or workarounds

---

### Workstream 5: Update README with Canonical Developer Setup

**Objective**: One short, authoritative section that tells new developers exactly what to do.

**File**: `README.md`

**Addition** (new section, placed after current "Setup and Pulse Check" or in "Developer Quick Start" area):

```markdown
## Developer Setup (Local Development)

Before running tests or making changes, set up your development environment once:

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
# or: .venv\Scripts\activate.bat      # Windows CMD

# 2. Upgrade pip and install dev dependencies
python -m pip install --upgrade pip
python -m pip install -e .[dev]

# 3. Verify the environment is correct
python .agent/scripts/helpers/verify_dev_contract.py

# 4. Run tests to confirm everything works
python -m pytest -q
```

**Expected Output (Success)**:
```
✓ Environment contract verified
16 passed in 0.45s
```

If any step fails, the error message will indicate the fix (e.g., "run `pip install -e .[dev]` to install mypy").

### Running Tests Locally

Once setup is complete:

```powershell
# Run all tests
python -m pytest -q

# Run targeted tests
python -m pytest -q src/governance.py

# Type-check your changes
python -m mypy src/

# Lint your changes
python -m ruff check src/
```

**Do not use**:
- Global Python interpreter (use `.venv`)
- `pip install requirements.txt` (use `pip install -e .[dev]`)
- Fallback pytest commands with `--cov=` workarounds (if default fails, run verify script first)
```

**Why**:
- Explicit, minimal sequence developers can copy-paste  
- Authoritative source of truth for bootstrap  
- Includes verification step that catches misconfigurations  
- Explains canonical commands (pytest, mypy, ruff)  
- Discourages workarounds/fallback commands

---

### Workstream 6: Document Dev Contract Explicitly

**Objective**: Make contract assumptions visible and checkable.

**New File**: `.agent/docs/dev-contract.md` (or append to agent guidance if preferred)

**Content** (brief, reference-style):

```markdown
# Development Environment Contract

## Tools Contract

All developers must have these tools available to run tests and validation:

| Tool | Version | Installed Via | Purpose |
|------|---------|---------------|---------|
| Python | 3.12+ | system/mise/pyenv | Runtime |
| pytest | >=9.0.0 | `pip install -e .[dev]` | Test runner |
| pytest-cov | >=6.0.0 | `pip install -e .[dev]` | Coverage measurement |
| mypy | >=1.13.0 | `pip install -e .[dev]` | Type checking |
| ruff | >=0.8.0 | `pip install -e .[dev]` | Linting |
| types-psutil, types-PyYAML, pandas-stubs | current | `pip install -e .[dev]` | Type stubs |

## Bootstrap Path

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
python .agent/scripts/helpers/verify_dev_contract.py
```

## Verification

Run locally before pushing:
```powershell
python .agent/scripts/helpers/verify_dev_contract.py  # verify setup
python -m pytest -q                                   # run tests
python -m mypy src/                                   # type-check
python -m ruff check src/                             # lint
```

## CI Contract

CI runs the same contract verification as local developers:
1. `pip install -e .[dev]` (install declared dependencies)
2. `verify_dev_contract.py` (check expectations are met)
3. Tests, linting, type-checking (all tools guaranteed available)

If CI fails on a tool, local developers see the same failure when running verify script locally.

## Troubleshooting

**"Tool not found" or "module not importable"**  
→ Run: `python -m pip install -e .[dev]`

**"pytest: --cov not recognized"**  
→ pytest-cov plugin not installed; run: `python -m pip install -e .[dev]`

**"Python version X.Y found; 3.12+ required"**  
→ Activate the .venv: `.venv\Scripts\Activate.ps1` (or equivalent on your shell)
```

**Why**:
- Makes contract assumptions explicit and discoverable  
- Single reference for tools, versions, bootstrap  
- Provides troubleshooting guidance  
- Can be linked from agent instructions, contributing guide, etc.

---

## Implementation Sequence (Recommended Order)

1. **Workstream 2** (first): Create `verify_dev_contract.py` script  
   - Takes ~1 hour; testable in isolation; no dependencies  
   - Once complete, developers can use it for self-diagnosis

2. **Workstream 1** (second): Update `pyproject.toml`  
   - Add mypy, ruff to dev deps  
   - Takes ~5 minutes; re-test with script from step 1  

3. **Workstream 3** (third): Update CI `.yml`  
   - Remove mypy late-binding install  
   - Add verify_dev_contract.py call  
   - Takes ~15 minutes; careful review to ensure no breakage

4. **Workstream 5** (fourth): Update README  
   - Add Developer Setup section  
   - Takes ~30 minutes (including testing the documented sequence works)

5. **Workstream 4** (verification): Confirm bootstrap parity  
   - Fresh clone test: delete .venv, re-run setup sequence  
   - Verify both local and CI use same install path  
   - Takes ~20 minutes

6. **Workstream 6** (documentation): Add contract doc  
   - Create `.agent/docs/dev-contract.md`  
   - Takes ~20 minutes

---

## Verification Strategy (Before and After)

### Before Implementation (Baseline)

Test these to understand current drift:

```powershell
# 1. Fresh venv: can we install and pass tests?
rm -r .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
python -m mypy src/ 2>&1 | Select-String "error" | Measure-Object  # Count errors
python -m pytest -q --maxfail=1

# 2. What does CI actually need?
grep -n "pip install" .github/workflows/ci.yml | Select-String "mypy|ruff|pytest"  # Find late-binding installs
```

### After Implementation (Verification)

1. **Verify script works**:
   ```powershell
   python .agent/scripts/helpers/verify_dev_contract.py
   # Expected: exit 0, ✓ Environment contract verified
   ```

2. **Verify dependencies are declared**:
   ```powershell
   python -m pip show mypy ruff pytest pytest-cov | Select-String "Name|Version"
   # Expected: all four show installed
   ```

3. **Verify pytest works without fallback**:
   ```powershell
   python -m pytest -q
   # Expected: runs with coverage measurement; no --cov-report errors
   ```

4. **Simulate CI locally**:
   ```powershell
   rm -r .venv
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e .[dev]
   python .agent/scripts/helpers/verify_dev_contract.py
   python -m pytest -q
   # Expected: all pass
   ```

5. **Inspect CI `.yml` for compensations**:
   ```powershell
   grep -n "pip install -U" .github/workflows/ci.yml
   # Expected: no `pip install -U mypy` or `pip install -U ruff`; only diagnostic tools that are explicitly late-binding
   ```

---

## What's NOT in Phase 1 (Deferred to Phase 2+)

| Item | Why Deferred | Phase |
|------|-------------|-------|
| VS Code interpreter pinning | Repo should work without IDE assumptions; IDE convenience is Phase 2 | Phase 2 |
| Terminal auto-activation | Shell-specific; Phase 1 focuses on repo contract, not shell behavior | Phase 2 |
| Ruff as blocking gate | Current CI runs ruff as advisory; making it blocking may surface noise; defer until noise is cleaned | Phase 3 |
| Pre-commit hooks | Nice-to-have; Phase 1 focuses on contract, not workflow automation | Phase 3 |
| Policy/instruction rewrites | Agent infra is sound; Phase 1 focuses on dev contract, not agent policy | Phase 2+ |
| requirements.txt deletion | Legacy file; keep for now to avoid breaking external tooling; document as deprecated | Phase 3 |

---

## Risks & Mitigations

| Risk | Mitigation | Severity |
|------|-----------|----------|
| **Adding mypy/ruff to dev deps may break old .venvs** | Document: "Run `pip install -e .[dev]` again"; one-line PR note | Low |
| **Verify script fails on unexpected configs** | Script designed to be liberal in detection; includes fallback remediation guidance | Low |
| **CI verify step adds 5–10 seconds** | Script is lightweight (~50–100 lines, pure Python); cached pip checks; acceptable | Low |
| **New contributor still misses setup section** | Mitigate by: linking from CONTRIBUTING.md, adding as PR checklist, agent bootstrap guidance | Medium |
| **Hidden local/CI drift still possible** | Mitigate by: routine verify script runs, Phase 2 preflight integration with agent checks | Medium |

---

## Success Criteria

✅ **Phase 1 is complete when**:

1. pyproject.toml dev dependencies include mypy, ruff, pytest, pytest-cov  
2. `verify_dev_contract.py` exists and correctly checks all expectations  
3. CI `.yml` removes late-binding mypy install; adds contract verification step  
4. README.md has concise "Developer Setup" section with exact commands  
5. Fresh clone + README sequence → local `pytest -q` works without fallback or workarounds  
6. CI contract verification step passes before tests run  
7. `.agent/docs/dev-contract.md` exists and is discoverable  

✅ **Local/CI parity confirmed**:
- Local: `pip install -e .[dev]` + `verify_dev_contract.py` → success  
- CI: same sequence, same success signal  
- No hidden compensation in CI; all tools explicitly declared

---

## Files to Modify (Phase 1)

| File | Change | Complexity |
|------|--------|------------|
| `pyproject.toml` | Add mypy, ruff to dev deps | Trivial |
| `.agent/scripts/helpers/verify_dev_contract.py` | Create script | Low (~80 lines) |
| `.github/workflows/ci.yml` | Remove mypy install; add verify step | Low (~10 lines change) |
| `README.md` | Add Developer Setup section | Low (~40 lines) |
| `.agent/docs/dev-contract.md` | Create reference doc | Low (~60 lines) |

---

## Deferred: Future Phases

**Phase 2** (Follow-on work):
- VS Code settings for interpreter pinning
- Terminal auto-activation convenience
- Preflight integration with agent bootstrap

**Phase 3** (Longer-term):
- Ruff as blocking CI gate (after noise cleanup)
- Pre-commit hooks for local dev
- requirements.txt deprecation/removal

---

## Conclusion

Phase 1 focuses on the core problem: **making the repo-native contract explicit and verifiable**. The contract is enforced by declared dependencies in pyproject.toml and verified by a repo-native script. Local developers follow the same bootstrap as CI; no hidden compensations. One README section gives new developers a clear path.

This is minimal, concrete, and addresses the root cause of the pytest-cov issue: **repo metadata was incomplete; local dev and CI were making different assumptions; verification was invisible**.

Phase 1 unblocks all downstream phases by establishing the repo as the source of truth.
