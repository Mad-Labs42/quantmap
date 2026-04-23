# Agent-Infra Default Alignment: Phase 2 PRE-Implementation Plan

Date: 2026-04-20

## Objective

Determine how to make the repo-native development contract the default operating mode for day-to-day QuantMap work, especially VS Code and agent sessions, without relying on hidden IDE magic or shell-specific assumptions.

Phase 1 established the core contract: `pyproject.toml` declares dev tools, CI installs `.[dev]`, `README.md` documents setup, and `.agent/scripts/helpers/verify_dev_contract.py` checks tool availability and pytest coverage support. Phase 2 should make that contract harder to bypass before work starts.

## Current State

- Repo-native contract exists:
  - `README.md` documents `python -m venv .venv`, activation, `python -m pip install -e .[dev]`, `verify_dev_contract.py`, and `python -m pytest -q`.
  - `pyproject.toml` declares `pytest`, `pytest-cov`, `mypy`, `ruff`, and type stubs under `[project.optional-dependencies].dev`.
  - `.github/workflows/ci.yml` installs `.[dev]`, runs `verify_dev_contract.py`, then tests.
  - `.agent/docs/dev-contract.md` documents the same basic contract.
- VS Code local settings already point at `.venv`:
  - `.vscode/settings.json` has `python.defaultInterpreterPath = ${workspaceFolder}\\.venv\\Scripts\\python.exe`.
  - It does not define terminal activation behavior, VS Code tasks, or a dev-contract task.
  - `.vscode/` is ignored by `.gitignore`, so this setting is local convenience, not repo-enforced state.
- Terminal/session reality still drifts:
  - In this PowerShell session, default `python` resolves to `D:\.store\mise\data\shims\python.cmd`.
  - `sys.executable` is `D:\.store\mise\data\installs\python\3.14.3\python.exe`.
  - `VIRTUAL_ENV` is unset.
  - `.venv\Scripts\python.exe` exists, but the terminal does not default to it.
- The contract checker has useful coverage but not full ownership:
  - It checks Python >=3.12, importability of dev tools, pytest-cov availability, and default pytest collection.
  - It does not require the active interpreter to be `.venv`.
  - It does not compare local Python to CI's Python 3.13.
  - It does not detect global-tool leakage if global Python happens to have all packages installed.
- CI no longer has the original mypy late-binding compensation, but still has intentional advisory compensation:
  - `pip-audit` is installed late in the advisory digest step.
  - Ruff, syntax, coverage artifact generation, and digest jobs are advisory.
- Documentation now mostly agrees on setup, but not completely:
  - `README.md` and `.agent/docs/dev-contract.md` tell the repo-native story.
  - `docs/system/contributing.md` is operator/contributor guidance and does not link to the dev contract.
  - `.github/pull_request_template.md` asks for tests/manual validation and agent-surface review, but not dev-contract verification.
  - `.agent/instructions/agent_session_bootstrap.md` starts with `agent_surface_audit.py`, not environment contract verification.
  - `.agent/instructions/agent_command_catalog.md` does not list `verify_dev_contract.py`.

## Drift / Risk Points

1. VS Code interpreter pinning is currently ignored local state. If a developer clones the tracked branch, `.vscode/settings.json` may not exist unless private/local files are carried over.
2. Terminal activation is not guaranteed. The Python extension may select `.venv` for analysis/debugging while integrated terminals still run global/mise Python.
3. `verify_dev_contract.py` can fail on Windows before checking the contract because it prints Unicode symbols under a non-UTF-8 console encoding.
4. After forcing UTF-8 output, `verify_dev_contract.py` still failed in both global Python and `.venv` because pytest-cov could not open a `.coverage.*` SQLite data file during collect-only.
5. The checker reports the coverage-data failure as "pytest may not be working; run pip install -e .[dev]", which is misleading when dependencies are installed.
6. The checker does not prove interpreter ownership. A global Python with enough packages can pass most checks.
7. CI uses Python 3.13, while local `.venv` and global Python are currently 3.14.3. `requires-python >=3.12` permits that, but it is still a local-vs-CI behavior gap.
8. `.gitignore` ignores `.agent/`, `.vscode/`, `AGENTS.md`, and `docs/Plans/`. This makes several active governance and planning surfaces local/private by default, even when they are operationally important.
9. `.agent/README.md` does not list newer helpers such as `verify_dev_contract.py` and digest helpers, so the agent surface map is stale.
10. `requirements.txt` remains runtime-only and does not explain its relationship to `pyproject.toml`; developers could still choose it by habit and miss dev tooling.
11. Coverage artifacts are not ignored in `.gitignore` (`coverage.xml`, `.coverage*`), and pytest-cov currently writes/opens coverage data during collect-only.
12. The current contract checker invokes pytest in a way that can trigger coverage writes while trying to perform an environment check.

## Recommended Target State

### Repo-native default

The repo contract should remain the source of truth:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
python .agent/scripts/helpers/verify_dev_contract.py
python -m pytest -q
```

The Phase 2 target is not "VS Code makes everything work." The target is "the repo can prove the environment is correct, and VS Code makes the correct path easier."

### Interpreter ownership

- The canonical interpreter is `.venv`.
- A pre-work check should warn or fail when `sys.prefix` / `sys.executable` is outside the repo `.venv`, unless an explicit override is provided for CI or advanced use.
- The checker should print the active interpreter and `VIRTUAL_ENV` every run.
- Python version policy should be explicit:
  - Either require local Python to match CI minor version 3.13, or allow `>=3.12` and label non-CI minor versions as warnings.
  - Recommended: warning only for Phase 2; strict CI-minor pinning can be deferred unless version drift causes observed failures.

### VS Code workspace behavior

- Track only minimal, project-scoped VS Code settings if the branch is meant to carry default behavior:
  - `python.defaultInterpreterPath`
  - `python.terminal.activateEnvironment = true`
  - search/watch excludes
  - formatter/lint integration if already desired
- Avoid forcing `terminal.integrated.env.windows` to fake `VIRTUAL_ENV`; that can desynchronize PATH and Python.
- Prefer a repo task or documented command for verification over auto-running scripts on workspace open.
- If `.vscode/` remains intentionally ignored/private, do not rely on it in the default contract; document it as optional local convenience.

### Terminal/session behavior

- The shell should not be trusted implicitly.
- Every agent session should run a lightweight environment contract/preflight check before edits, or at least before first verification.
- A terminal profile/task can activate `.venv`, but the repo-native checker must still catch drift when the terminal does not.
- The default command style should remain `python -m <tool>` from the active interpreter, after proving the active interpreter.

### Agent/session bootstrap behavior

- `agent_session_bootstrap.md` should add an early environment-contract step before `agent_surface_audit.py` for implementation work.
- `agent_command_catalog.md` should list `verify_dev_contract.py` as a core command.
- `changed_path_verify.py` should either:
  - call the contract checker first in a cheap mode, or
  - clearly report the active interpreter and whether it is inside `.venv`.
- Do not make agent sessions depend on VS Code settings. Agents should be able to prove the environment from the shell alone.

### Drift detection and recovery

- `verify_dev_contract.py` should become the single pre-work environment gate and should distinguish:
  - wrong interpreter
  - missing dev install
  - pytest plugin missing
  - pytest collection failure
  - coverage data write/open failure
  - console encoding failure
- Recovery messages should map to the actual failure:
  - wrong interpreter -> activate `.venv` or run `.venv\Scripts\python.exe`
  - missing package -> `python -m pip install -e .[dev]`
  - coverage write failure -> inspect permissions, cleanup stale coverage files, or set safe coverage data path
  - encoding failure -> set UTF-8 mode or avoid non-ASCII output

## Proposed Workstreams

### Workstream 1: Harden `verify_dev_contract.py`

- Replace Unicode status glyphs with ASCII-safe output or explicitly configure UTF-8-safe printing.
- Always print active interpreter, `sys.prefix`, `base_prefix`, `VIRTUAL_ENV`, cwd, and whether `.venv\Scripts\python.exe` exists.
- Add `.venv` ownership check with a CI/override escape hatch.
- Split checks into:
  - `--quick`: interpreter + import/tool checks only, no pytest collection writes.
  - default/full: includes pytest collection/config checks.
- Improve pytest failure diagnostics by including stderr tail and the detected failure class.
- Avoid using a coverage-enabled collect-only command as the plugin check. Prefer `python -m pytest --help` for `--cov` support and reserve collection for a separate check.

### Workstream 2: Decide tracked vs local VS Code policy

- If VS Code defaults are part of the branch contract, unignore and track a minimal `.vscode/settings.json`.
- If they are local-only, remove Phase 2 language that treats them as repo guarantees.
- Recommended: track minimal `.vscode/settings.json` only if this branch is intended to own custom agent/dev infrastructure. Keep personal/editor-specific settings out.
- Add `python.terminal.activateEnvironment = true` if tracking VS Code settings.
- Defer tasks/launch profiles unless there is an observed need.

### Workstream 3: Add shell/agent preflight entry point

- Add a repo-native preflight command that wraps or calls `verify_dev_contract.py --quick`.
- Recommended placement: extend existing `verify_dev_contract.py` first; avoid adding another helper until the mode split is not enough.
- Update `agent_session_bootstrap.md` to require the quick preflight before implementation work.
- Update `agent_command_catalog.md` with the command and expected failure semantics.
- Consider updating `changed_path_verify.py` to surface interpreter path before running lint/tests.

### Workstream 4: Align docs without broad rewrites

- Link `docs/system/contributing.md` to `README.md` Developer Setup and `.agent/docs/dev-contract.md`.
- Add one PR-template checkbox for dev-contract verification.
- Clarify `requirements.txt` as runtime-only/legacy if it remains.
- Update `.agent/README.md` to list `verify_dev_contract.py` and currently present digest helpers if those are part of active agent surface.

### Workstream 5: Coverage/temp-file hygiene

- Add `.coverage*` and `coverage.xml` to ignore rules if coverage output is local/generated.
- Investigate why coverage cannot open `.coverage.*` on this Windows workspace.
- Keep this as an infra hygiene subtask unless it blocks normal `python -m pytest -q`.
- Do not fold broad pytest temp cleanup work into interpreter/default alignment unless the same failure reproduces in the default test command.

### Workstream 6: CI/local parity review

- Keep CI using `python -m pip install -e .[dev]`.
- Keep `pip-audit` as late-bound advisory unless the project wants vulnerability scanning to be part of every local dev install.
- Decide whether local Python should warn on non-3.13 because CI is currently 3.13.
- Make the contract checker's CI behavior explicit so local checks and CI checks differ only by documented override flags.

## Recommended Order

1. Harden `verify_dev_contract.py` output and diagnostics.
2. Add `.venv` ownership detection in warning mode, then decide whether to make it blocking outside CI.
3. Remove coverage-enabled collect-only from the plugin check; add a separate full pytest config check with useful stderr.
4. Decide whether `.vscode/settings.json` should be tracked or explicitly local-only.
5. Add minimal VS Code terminal activation convenience only after the repo-native checker is reliable.
6. Update agent bootstrap/catalog to require the pre-work contract check.
7. Update README/contributing/PR-template references.
8. Track coverage/temp-file hygiene separately if the coverage SQLite failure persists.

## Open Questions / Unknowns

1. Should this branch intentionally track `.agent/`, `.vscode/`, `AGENTS.md`, and `docs/Plans/`, or are these meant to remain private/local infrastructure?
2. Should local development require the same Python minor version as CI (`3.13`), or is `>=3.12` with a warning sufficient?
3. Should `.venv` ownership be a hard failure for all local agent sessions, or a warning with explicit override?
4. Is the coverage SQLite failure reproducible in a clean terminal and normal `python -m pytest -q`, or only during contract-check collect-only?
5. Is `pip-audit` intentionally late-bound advisory tooling, or should it be declared in a separate optional dependency group?

## Explicit Deferrals

- Do not add pre-commit hooks in Phase 2.
- Do not make Ruff blocking in CI as part of this phase.
- Do not delete `requirements.txt`; clarify its role first.
- Do not add broad VS Code tasks/launch/debug profiles until minimal settings and preflight are stable.
- Do not create multiple new helper scripts if `verify_dev_contract.py` can be extended cleanly.
- Do not force shell profile edits or machine-global PowerShell configuration.
- Do not solve unrelated pytest temp cleanup unless it blocks the default dev contract.

## Risks / Watch-outs

- Tracking `.vscode/settings.json` can help VS Code users but may surprise non-Windows or non-VS Code users if it contains Windows-only assumptions.
- Auto-activation can create a false sense of safety; the checker still needs to prove interpreter ownership.
- A hard `.venv` requirement may be too strict for CI, devcontainers, tox/nox, or future cross-platform work unless an override is designed.
- Coverage-enabled pytest checks can mutate repo-local files during "verification" and may fail for file-lock/permission reasons unrelated to dependency health.
- The current `.gitignore` can hide exactly the files this agent-infra work depends on.
- Console encoding is a real Windows failure mode for agent scripts; ASCII output is safer for governance helpers.

## Adjacent Issues Noted

- `.agent/README.md` is stale relative to the actual helper set; it does not mention `verify_dev_contract.py` or several digest helpers now referenced by CI and scripts.
- `.gitignore` ignores `docs/Plans/`, so this requested PRE plan is ignored by default unless added with force or the ignore policy changes.
- `.gitignore` ignores `.agent/`, while CI references `.agent/scripts/...`; that can be correct for a private/local branch, but it is not compatible with treating `.agent` as repo-native in a public branch without force-tracking or ignore changes.
- The investigation command search accidentally matched K.I.T./TO-DO tracker paths; no tracker files were intentionally opened for planning, but future searches should exclude `docs/system/TO-DO.md`, `docs/system/known_issues_tracker.md`, and `docs/K.I.T.-&-ToDo/**`.

## Recommendation

Proceed directly to a Phase 2 Implementation Plan. No further broad investigation is needed.

The implementation plan should be narrow and ordered around reliability first:

1. Fix `verify_dev_contract.py` so it is ASCII-safe, diagnostic, and capable of detecting wrong-interpreter drift.
2. Decide tracked vs local `.vscode` policy before adding more workspace behavior.
3. Add pre-work environment preflight to agent bootstrap/catalog only after the checker is trustworthy.
4. Treat coverage/temp-file failure and `.gitignore` policy as explicit Phase 2 decisions or separate infra hygiene tasks, not silent side quests.
