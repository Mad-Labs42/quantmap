# Agent-Infra Default Alignment: Phase 2 Implementation Plan

Date: 2026-04-20

## Objective

Make the repo-native dev contract the default operating path for QuantMap_agent before day-to-day work starts.

The contract must be enforced by repo-owned checks first, with VS Code as convenience only. Phase 2 should eliminate silent drift from wrong interpreters, global tooling, hidden IDE state, brittle pytest coverage checks, and ignored agent-infra paths.

## Current Confirmed State Relevant To Phase 2

- `README.md` defines the canonical setup path: create `.venv`, activate it, install `.[dev]`, run `verify_dev_contract.py`, then `python -m pytest -q`.
- `pyproject.toml` declares `pytest`, `pytest-cov`, `mypy`, `ruff`, and type stubs in `dev`.
- `.github/workflows/ci.yml` installs `.[dev]`, runs `verify_dev_contract.py`, then tests on `windows-latest` with Python `3.13`.
- `.agent/scripts/helpers/verify_dev_contract.py` exists, but:
  - prints non-ASCII symbols that can fail under Windows legacy console encodings;
  - does not report active interpreter ownership clearly;
  - does not require `.venv`;
  - uses coverage-enabled collect-only behavior for a plugin/config check;
  - can misclassify coverage SQLite/open failures as missing dev install.
- `.vscode/settings.json` exists locally and pins `${workspaceFolder}\\.venv\\Scripts\\python.exe`, but `.vscode/` is ignored.
- `.agent/`, `AGENTS.md`, and `docs/Plans/` are ignored by `.gitignore`, while agent scripts and docs are treated as operationally required by CI and onboarding.
- `docs/system/contributing.md` does not point contributors to the dev contract.
- `.github/pull_request_template.md` does not ask for dev-contract verification.
- `.agent/instructions/agent_session_bootstrap.md` and `.agent/instructions/agent_command_catalog.md` do not list `verify_dev_contract.py` as the first pre-work environment check.
- `changed_path_verify.py` uses `sys.executable`, so it inherits whatever interpreter the shell gave it.

## Decisions That Must Be Made Before Or During Implementation

1. Local Python minor vs CI:
   - Decision: warn only when local Python minor differs from CI `3.13`.
   - Rationale: `requires-python >=3.12` is the package contract; strict minor pinning would exceed current metadata and reduce portability.
   - Implementation: `verify_dev_contract.py --quick` emits a warning for non-3.13 local Python, but CI can pass `--ci` or equivalent to document expected behavior.

2. `.venv` ownership for local agent sessions:
   - Decision: blocking for local agent implementation work, warning/override-capable for CI and explicit advanced use.
   - Rationale: wrong-interpreter drift is the main class of failure Phase 2 is meant to stop.
   - Implementation: quick preflight fails if active `sys.executable` is outside repo `.venv` unless `--allow-non-venv` or CI detection is active.

3. VS Code settings policy:
   - Decision: track a minimal `.vscode/settings.json` as branch/repo contract for QuantMap_agent, not as the enforcement layer.
   - Rationale: VS Code is a primary day-to-day surface here, and default interpreter selection should travel with the repo. The repo checker remains authoritative.
   - Implementation: strip personal/editor-extension settings, keep only project-scoped settings needed for Python interpreter, terminal activation, search/watch excludes, and formatter/lint defaults already accepted by the branch.

4. Repo-native vs local/private agent-infra:
   - Repo-native defaults: `AGENTS.md`, `.agent/README.md`, `.agent/instructions/*`, `.agent/policies/*`, `.agent/reference/*`, `.agent/docs/dev-contract.md`, `.agent/scripts/*.py`, `.agent/scripts/helpers/*.py`, minimal `.vscode/settings.json`, `.github/instructions/quantmap-agent.instructions.md`.
   - Local/private/generated: `.agent/artifacts/*`, `.agent/handoffs/*`, personal notes, local checklists, editor-only preferences, human checkpoint docs unless explicitly requested.
   - Implementation: update `.gitignore` policy or force-track intentionally. Prefer ignore-rule changes over relying on force-add forever.

5. Phase 2 scope:
   - In scope: harden the contract checker, wire quick preflight into agent workflow, align minimal docs/templates, decide path policy, add coverage artifact hygiene.
   - Out of scope: broad pytest cleanup, pre-commit, Ruff-as-blocking CI, deleting `requirements.txt`, new helper proliferation, shell profile edits, methodology/runtime behavior changes.

## Workstreams

### 1. Harden `verify_dev_contract.py`

Target file:

- `.agent/scripts/helpers/verify_dev_contract.py`

Implementation:

- Replace all non-ASCII status output with ASCII-only text, for example `[OK]`, `[WARN]`, `[FAIL]`.
- Add argparse modes:
  - `--quick`: interpreter ownership, Python version, required imports/tool availability, no pytest collection.
  - `--full`: quick checks plus pytest config/collection checks.
  - Default should remain full for README/CI compatibility unless implementation decides to make default quick and update all callers in the same patch.
  - `--ci`: disables local `.venv` hard failure and records CI context.
  - `--allow-non-venv`: explicit escape hatch for advanced local workflows.
- Always print:
  - cwd;
  - `sys.executable`;
  - `sys.prefix`;
  - `sys.base_prefix`;
  - `VIRTUAL_ENV`;
  - expected repo `.venv` Python path;
  - whether active interpreter is owned by repo `.venv`.
- Add `.venv` ownership classification:
  - local quick/full: fail if not repo `.venv` and no override;
  - CI: report but do not fail;
  - missing `.venv`: fail locally with remediation.
- Keep Python version check as `>=3.12`; add warning if local minor differs from CI `3.13`.
- Split pytest checks:
  - plugin availability: use `python -m pytest --help` and confirm `--cov` is present.
  - default config sanity: run a separate full-mode command only after plugin check.
  - remove current fragile coverage-enabled `pytest --co -q` plugin check.
- Classify pytest/coverage failures:
  - unrecognized `--cov`;
  - import/plugin missing;
  - collection error;
  - coverage data/open/write error;
  - timeout;
  - unknown pytest failure with stderr tail.
- Make remediation specific to failure class.

Acceptance checks:

```powershell
python .agent/scripts/helpers/verify_dev_contract.py --quick
python .agent/scripts/helpers/verify_dev_contract.py --full
python -m ruff check .agent/scripts/helpers/verify_dev_contract.py
python -m compileall -q .agent/scripts/helpers/verify_dev_contract.py
```

Negative checks:

```powershell
python .agent/scripts/helpers/verify_dev_contract.py --quick
```

Run once from a known non-`.venv` interpreter and confirm it fails with a wrong-interpreter message, not a package-install guess.

Rollback / blast radius:

- Script-only behavior change. Roll back by restoring previous checker and removing new flags from docs/CI/bootstrap in the same revert.
- Main risk is breaking CI if `--ci` behavior is not wired when `.venv` is absent in GitHub Actions.

### 2. Decide And Apply Path Policy For `.agent`, `AGENTS.md`, `docs/Plans`, And `.vscode`

Target file:

- `.gitignore`

Implementation:

- Replace broad ignores with explicit generated/private ignores.
- Recommended policy:
  - track `AGENTS.md`;
  - track `.agent/README.md`, `.agent/docs/**`, `.agent/instructions/**`, `.agent/policies/**`, `.agent/reference/**`, `.agent/scripts/**`;
  - ignore `.agent/artifacts/**` and `.agent/handoffs/**`;
  - track `docs/Plans/**` if planning docs are part of this branch's workflow;
  - track `.vscode/settings.json` only;
  - ignore other `.vscode/*` files unless explicitly approved later.
- If the branch owner does not want these files tracked, record that as branch-only/private policy and do not describe them as repo-native defaults in docs.

Acceptance checks:

```powershell
git check-ignore -v AGENTS.md .agent/scripts/helpers/verify_dev_contract.py .agent/instructions/agent_session_bootstrap.md .vscode/settings.json docs/Plans/agent-infra-default-alignment/agent-infra-default-alignment-Phase2-Implementation-Plan.md
git status --short --ignored AGENTS.md .agent .vscode docs/Plans
```

Expected after repo-native policy:

- required agent/default files are not ignored;
- `.agent/artifacts/` and `.agent/handoffs/` remain ignored.

Rollback / blast radius:

- Ignore policy changes can expose many previously hidden files. Before committing, inspect `git status --short --ignored` and stage only intended files.

### 3. Make Minimal VS Code Defaults Repo-Native

Target file:

- `.vscode/settings.json`

Implementation:

- Keep:
  - `python.defaultInterpreterPath = ${workspaceFolder}\\.venv\\Scripts\\python.exe`;
  - `python.terminal.activateEnvironment = true`;
  - Python formatter/lint defaults if intentionally shared;
  - search/watch excludes for repo-generated heavy paths.
- Remove or keep local-only:
  - Todo Tree custom tags/colors;
  - GitLens preferences;
  - SonarLint connected-mode project;
  - chat restore state;
  - personal extension preferences.
- Do not add `terminal.integrated.env.windows` to fake `VIRTUAL_ENV`.
- Do not add shell profile mutations.

Acceptance checks:

```powershell
python .agent/scripts/agent_surface_audit.py --strict
git diff -- .vscode/settings.json
```

Manual check:

- Open a fresh VS Code terminal and confirm activation is attempted.
- Still run `python .agent/scripts/helpers/verify_dev_contract.py --quick`; VS Code activation is not proof by itself.

Rollback / blast radius:

- If VS Code behavior becomes noisy, revert this file while keeping repo-native checker enforcement intact.

### 4. Add Pre-Work Environment Preflight To Agent Workflow

Target files:

- `.agent/instructions/agent_session_bootstrap.md`
- `.agent/instructions/agent_command_catalog.md`
- `.agent/README.md`
- `.agent/docs/dev-contract.md`
- Optional: `.agent/scripts/changed_path_verify.py`

Implementation:

- In `agent_session_bootstrap.md`, add first implementation-work command:

```powershell
python .agent/scripts/helpers/verify_dev_contract.py --quick
```

- Keep `agent_surface_audit.py --strict` as the agent-surface check after environment preflight.
- In `agent_command_catalog.md`, add a core command section for Dev Contract Preflight:
  - command;
  - quick/full modes;
  - local `.venv` failure semantics;
  - CI/override semantics;
  - expected remediation.
- Update `.agent/README.md` to list `scripts/helpers/verify_dev_contract.py`.
- Update `.agent/docs/dev-contract.md` to describe quick vs full mode and interpreter ownership.
- Optional `changed_path_verify.py` change only if narrow:
  - print active `sys.executable` and `.venv` ownership in its report; or
  - call `verify_dev_contract.py --quick` before lint/tests.
- Do not create a new preflight helper unless `verify_dev_contract.py` becomes too broad after the mode split.

Acceptance checks:

```powershell
python .agent/scripts/helpers/verify_dev_contract.py --quick
python .agent/scripts/agent_surface_audit.py --strict
python .agent/scripts/agent_workflow_smokecheck.py
python .agent/scripts/changed_path_verify.py --paths .agent/instructions/agent_session_bootstrap.md .agent/instructions/agent_command_catalog.md .agent/README.md .agent/docs/dev-contract.md
```

Rollback / blast radius:

- If checker semantics prove too strict, relax flags in bootstrap/catalog first; do not remove the checker entirely.

### 5. Align Human Workflow Surfaces Without Broad Rewrites

Target files:

- `README.md`
- `docs/system/contributing.md`
- `.github/pull_request_template.md`
- `requirements.txt`

Implementation:

- README:
  - update the setup block to use `verify_dev_contract.py --full` if the checker gains explicit modes;
  - add one sentence: use `.venv`; wrong-interpreter drift is a contract failure.
- Contributing:
  - add a short "Local Development Contract" subsection pointing to README Developer Setup and `.agent/docs/dev-contract.md`.
- PR template:
  - add one validation checkbox: dev contract verified.
  - do not add process-heavy checklists.
- `requirements.txt`:
  - add a top comment that it is runtime-only and not the development bootstrap path.

Acceptance checks:

```powershell
python .agent/scripts/changed_path_verify.py --paths README.md docs/system/contributing.md .github/pull_request_template.md requirements.txt
```

Rollback / blast radius:

- Documentation-only changes; revert independently if wording overreaches the final path-policy decision.

### 6. Handle Coverage / PermissionError / Temp-File Hygiene

Target files:

- `.gitignore`
- `.agent/scripts/helpers/verify_dev_contract.py`
- Optional only if evidence requires: `pyproject.toml`

Implementation:

- Add generated coverage outputs to ignore policy:

```gitignore
.coverage
.coverage.*
coverage.xml
htmlcov/
```

- Remove coverage-enabled collect-only from the checker as part of Workstream 1.
- In full mode, classify coverage SQLite/open failures separately and report:
  - active interpreter;
  - cwd;
  - expected coverage file path if known;
  - stderr tail.
- Only investigate broader pytest temp cleanup if normal default `python -m pytest -q` still fails after checker changes.
- Do not change pytest addopts or coverage config unless the normal default test command is blocked.

Acceptance checks:

```powershell
python .agent/scripts/helpers/verify_dev_contract.py --full
python -m pytest -q
Get-ChildItem -Force -Filter ".coverage*"
git status --short --ignored .coverage coverage.xml htmlcov
```

Rollback / blast radius:

- Ignore additions are low-risk.
- Pytest/coverage config changes are higher-risk and should be deferred unless proven necessary.

### 7. CI/Local Parity Tightening

Target files:

- `.github/workflows/ci.yml`
- `.agent/scripts/helpers/verify_dev_contract.py`

Implementation:

- Keep CI install path as `python -m pip install -e .[dev]`.
- Update CI checker invocation to use explicit mode:

```powershell
python .agent/scripts/helpers/verify_dev_contract.py --full --ci
```

- Keep `pip-audit` late-bound advisory for Phase 2.
- Do not make Ruff blocking in Phase 2.
- Make CI/local difference explicit: CI need not run inside repo `.venv`; local agent sessions must.

Acceptance checks:

```powershell
python .agent/scripts/helpers/verify_dev_contract.py --full --ci
python .agent/scripts/changed_path_verify.py --paths .github/workflows/ci.yml .agent/scripts/helpers/verify_dev_contract.py
```

Rollback / blast radius:

- CI invocation change can be reverted independently if flags misbehave.

## Exact Target Files Likely To Change

Primary:

- `.agent/scripts/helpers/verify_dev_contract.py`
- `.agent/instructions/agent_session_bootstrap.md`
- `.agent/instructions/agent_command_catalog.md`
- `.agent/README.md`
- `.agent/docs/dev-contract.md`
- `.gitignore`
- `.vscode/settings.json`
- `README.md`
- `docs/system/contributing.md`
- `.github/pull_request_template.md`
- `.github/workflows/ci.yml`
- `requirements.txt`

Optional, only if kept narrow:

- `.agent/scripts/changed_path_verify.py`
- `pyproject.toml`

Do not create new docs beyond necessary updates to existing surfaces.

## Validation Strategy

Run after each edit batch:

```powershell
python -m ruff check <changed-python-files>
python -m compileall -q <changed-python-files>
python .agent/scripts/changed_path_verify.py --paths <changed-files>
```

Run after agent instruction/script changes:

```powershell
python .agent/scripts/agent_surface_audit.py --strict
python .agent/scripts/agent_workflow_smokecheck.py
```

Run after checker changes:

```powershell
python .agent/scripts/helpers/verify_dev_contract.py --quick
python .agent/scripts/helpers/verify_dev_contract.py --full
python .agent/scripts/helpers/verify_dev_contract.py --full --ci
```

Run final validation:

```powershell
python .agent/scripts/helpers/verify_dev_contract.py --quick
python .agent/scripts/helpers/verify_dev_contract.py --full
python .agent/scripts/agent_surface_audit.py --strict
python .agent/scripts/agent_workflow_smokecheck.py
python .agent/scripts/changed_path_verify.py --paths .agent/scripts/helpers/verify_dev_contract.py .agent/instructions/agent_session_bootstrap.md .agent/instructions/agent_command_catalog.md .agent/README.md .agent/docs/dev-contract.md .gitignore .vscode/settings.json README.md docs/system/contributing.md .github/pull_request_template.md .github/workflows/ci.yml requirements.txt
```

Also run:

```powershell
git check-ignore -v AGENTS.md .agent/scripts/helpers/verify_dev_contract.py .agent/instructions/agent_session_bootstrap.md .vscode/settings.json docs/Plans/agent-infra-default-alignment/agent-infra-default-alignment-Phase2-Implementation-Plan.md
git status --short --ignored AGENTS.md .agent .vscode docs/Plans
```

## Risks / Watch-outs

- Tightening `.venv` ownership can block agents until terminals are activated correctly. That is intended locally, but CI must use an explicit override.
- Unignoring `.agent/` and `docs/Plans/` may expose many local/private files. Stage narrowly.
- Tracking `.vscode/settings.json` is useful only if stripped to non-personal project defaults.
- Coverage errors can be permissions/file-lock issues, not dependency issues. Do not "fix" them by weakening the dev contract.
- `changed_path_verify.py` inherits `sys.executable`; if it does not call or report preflight, it can still run under the wrong interpreter.
- `agent_surface_audit.py` already checks `.vscode/settings.json`; any new tracked/minimal settings must keep audit expectations aligned.

## Explicit Deferrals

- No pre-commit hooks.
- No Ruff-as-blocking CI change.
- No deletion of `requirements.txt`.
- No shell profile edits or global PowerShell configuration.
- No new helper script unless extending `verify_dev_contract.py` proves unmaintainable.
- No broad pytest temp cleanup unless default `python -m pytest -q` remains blocked.
- No devcontainer/tox/nox matrix in Phase 2.
- No public/private branch governance rewrite beyond the ignore/path-policy changes needed here.

## Recommended Implementation Order

1. Harden `verify_dev_contract.py` output, modes, interpreter reporting, and pytest/coverage classification.
2. Update CI invocation to use explicit `--full --ci`.
3. Add local quick preflight to `agent_session_bootstrap.md` and document it in `agent_command_catalog.md`.
4. Update `.agent/README.md` and `.agent/docs/dev-contract.md`.
5. Decide/apply `.gitignore` path policy for `AGENTS.md`, `.agent/`, `.vscode/settings.json`, and `docs/Plans/`.
6. Reduce `.vscode/settings.json` to minimal tracked project defaults and add terminal activation.
7. Align README, contributing, PR template, and `requirements.txt`.
8. Add coverage artifact ignore rules and only investigate deeper pytest cleanup if default pytest still fails.
9. Run final validation and inspect ignored/tracked status before staging.

## Additional Issues Noticed While Planning

- `.agent/README.md` is stale: it omits `verify_dev_contract.py` and newer digest helpers already referenced by CI/scripts.
- `.agent/README.md` says `.agent/docs/dev-contract.md`, but the actual file read is `.agent/docs/dev-contract.md`; keep this path exact when updating.
- `.gitignore` currently hides the required implementation plan under `docs/*`.
- Current `.vscode/settings.json` contains personal/tool-extension settings that should not be part of a shared default.
- `verify_dev_contract.py` still contains Unicode output and a coverage-enabled collect-only check shape.
- `requirements.txt` has no comment explaining that it is not the dev bootstrap path.

## .agent Files Used This Turn

Full reads:

- `.agent/README.md`
- `.agent/instructions/agent_session_bootstrap.md`
- `.agent/instructions/agent_command_catalog.md`
- `.agent/scripts/helpers/verify_dev_contract.py`
- `.agent/docs/dev-contract.md`

Evidence searches / validation surface reads:

- `.agent/scripts/changed_path_verify.py`
- `.agent/scripts/agent_surface_audit.py`
- `.agent/scripts/agent_workflow_smokecheck.py`

Generated/verification artifact expected after this planning pass:

- `.agent/artifacts/changed_path_verify.json`
