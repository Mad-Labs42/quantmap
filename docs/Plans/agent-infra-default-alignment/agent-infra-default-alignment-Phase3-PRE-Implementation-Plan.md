# Agent-Infra Default Alignment: Phase 3 PRE-Implementation Plan

Date: 2026-04-20

## Executive Summary

Phase 2 made the development contract visible and checkable, but it still leaves too much room for command drift. The current local shell can run bare `python` from a global/mise shim while the intended repo interpreter is `.venv\Scripts\python.exe`. The checker catches that after it runs, but many docs and helper commands still teach or execute bare `python`.

Phase 3 should make the intended path deterministic by making the repo-owned local command surface explicitly call `.venv\Scripts\python.exe`, then treating `verify_dev_contract.py --quick` as the mandatory first gate for implementation work. This remains support scaffolding only. No QuantMap runtime/package behavior should depend on `.agent`, `.vscode`, CI, planning docs, or helper scripts.

Recommendation: implement in one narrow pass, with the checker/command-surface changes first and docs second. Stage only if the command wrapper/entrypoint design becomes larger than expected.

## Exact Root Problems

1. Bare `python` is still ambiguous.
   - PowerShell resolves bare `python` to `D:\.store\mise\data\shims\python.cmd`.
   - `cmd /c where python` finds the mise shim and global Python before the repo `.venv`.
   - `.venv\Scripts\python.exe` is correct but not the command most docs/scripts require.

2. Activation is treated as part of correctness.
   - README and `.agent/docs/dev-contract.md` still depend on `.\.venv\Scripts\Activate.ps1`.
   - `VIRTUAL_ENV` is unset even when invoking `.venv\Scripts\python.exe` directly.
   - Activation is shell behavior, not a repo-owned guarantee.

3. Existing helper scripts inherit the caller's interpreter.
   - `changed_path_verify.py` runs ruff/compileall/pytest through `sys.executable`.
   - That is good only if the helper itself was launched by the repo `.venv` Python.
   - Agent instructions still list `python .agent/...`, so the first command can be wrong before the checker gets a chance to fail.

4. There is no single repo-owned command facade.
   - Repo-health commands are spread across README, `.agent/docs/dev-contract.md`, `.agent/instructions/agent_session_bootstrap.md`, `.agent/instructions/agent_command_catalog.md`, CI, and PR template.
   - Humans and agents can choose subtly different spellings for the same health checks.

5. CI and local are intentionally different but not named as such.
   - CI uses setup-python 3.13 and does not run inside repo `.venv`.
   - Local uses `.venv` and currently warns on Python 3.14.3 vs CI 3.13.
   - That difference is acceptable only if local commands are deterministic.

6. VS Code is convenience, not enforcement.
   - `.vscode/settings.json` pins `.venv` and enables terminal activation, but that does not control PowerShell/cmd outside VS Code or already-open terminals.
   - It still contains `sonarlint.connectedMode.project`, which is not a minimal interpreter/default-path setting.

7. Support-infra visibility is improved but still noisy.
   - `.agent/`, `AGENTS.md`, `.vscode/`, and `docs/Plans/` are now visible as untracked scaffolding.
   - Generated `.agent/artifacts`, `.agent/handoffs`, `.coverage`, and `coverage.xml` remain ignored.
   - This is directionally right, but staging policy must stay deliberate.

## Recommended Design Direction

Use explicit repo-owned interpreter paths for local scaffolding commands:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths <paths>
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check <paths>
```

Keep CI explicitly different:

```powershell
python .agent/scripts/helpers/verify_dev_contract.py --full --ci
```

Do not try to make activation, VS Code, PATH order, or shell profiles the source of truth. They can remain convenience layers. The repo-owned source of truth is the explicit `.venv` Python plus the dev-contract checker.

Prefer extending existing helper surfaces over new files. A new wrapper is justified only if it materially reduces command variance. If added, it should live under `.agent/scripts/` or `.agent/scripts/helpers/`, remain development-only, and never be imported by QuantMap runtime code.

## Ordered Workstreams For Implementation

### 1. Make Local Command Examples Explicitly Use `.venv`

Update existing support surfaces so local development examples use `.venv\Scripts\python.exe` instead of bare `python` after bootstrap.

Likely files:

- `README.md`
- `.agent/docs/dev-contract.md`
- `.agent/instructions/agent_session_bootstrap.md`
- `.agent/instructions/agent_command_catalog.md`
- `.github/instructions/quantmap-agent.instructions.md`
- `.github/pull_request_template.md`
- `requirements.txt` comment if it keeps a development note

Acceptance:

- No local implementation-work command in these surfaces relies on bare `python`.
- CI examples keep bare `python` only when paired with `--ci`.
- Product/operator commands such as `quantmap doctor` remain untouched.

### 2. Make Preflight The First Mandatory Local Gate

The first implementation command should be:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
```

Use full mode for setup/CI validation:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --full
```

Acceptance:

- Agent bootstrap and command catalog make quick preflight first.
- The command hard-fails on wrong local interpreter.
- No implementation checklist starts with `agent_surface_audit.py` before environment preflight.

### 3. Decide Whether To Add A Repo-Owned Command Facade

Investigate during implementation whether docs-only command normalization is enough. If not, add one narrow existing-surface extension:

Option A, preferred first: no new helper; standardize on explicit `.venv\Scripts\python.exe`.

Option B, justified if variance remains high: add a single `.agent/scripts/dev.py` facade with subcommands:

- `preflight`
- `verify-changed`
- `audit-agent`
- `smoke-agent`
- `test`
- `lint`

Rules for Option B:

- The facade must re-exec or invoke repo `.venv\Scripts\python.exe`.
- It must not import product/runtime modules.
- It must not replace product CLI behavior.
- It must fail loudly if `.venv` is missing.

Acceptance:

- Either all local command docs use explicit `.venv` commands, or the facade becomes the only documented local repo-health entrypoint.

### 4. Harden `changed_path_verify.py` Against Wrong Launchers

Current `changed_path_verify.py` uses `sys.executable`, so it is deterministic only after correct launch.

Recommended narrow fix:

- At startup, detect whether `sys.executable` is repo `.venv`.
- For local mode, hard-fail if not.
- Add `--ci` or `--allow-non-venv` only if CI needs it.
- Include interpreter path and ownership in `.agent/artifacts/changed_path_verify.json`.

Acceptance:

- Launching with bare global `python` fails before lint/tests.
- Launching with `.venv\Scripts\python.exe` runs checks as today.

### 5. Clean Minimal VS Code Defaults

Keep VS Code as convenience only:

- keep `python.defaultInterpreterPath`;
- keep `python.terminal.activateEnvironment`;
- keep search/watch excludes and Python formatting if project-owned;
- remove `sonarlint.connectedMode.project` from shared `.vscode/settings.json` unless explicitly deemed repo-owned.

Acceptance:

- `.vscode/settings.json` contains only project-safe defaults.
- No plan or doc claims VS Code activation is the enforcement mechanism.

### 6. Make Bootstrap Single-Path And Non-Competing

Canonical local bootstrap should be:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --full
.\.venv\Scripts\python.exe -m pytest -q
```

Open decision: whether to require Python 3.13 locally or continue warning on non-3.13. For deterministic Phase 3, prefer Python 3.13 as the canonical bootstrap target while keeping `requires-python >=3.12` as the product/package compatibility declaration.

Acceptance:

- README and `.agent/docs/dev-contract.md` have one setup story.
- `requirements.txt` remains runtime-only and not a dev bootstrap path.
- CI does not contain fallback install branches that imply `requirements.txt` is equivalent to `.[dev]`.

### 7. Review CI Compensation And Advisory Jobs

CI currently installs `.[dev]`, runs full contract with `--ci`, then runs tests. Good.

Remaining compensation:

- fallback to `requirements.txt` if `pyproject.toml` is absent;
- late `pip-audit` install in an advisory digest;
- advisory ruff/syntax/coverage/digest jobs.

Recommendation:

- Remove the `requirements.txt` fallback in CI; this repo has `pyproject.toml`.
- Keep `pip-audit` late-bound unless it becomes a local mandatory health command.
- Keep advisory digest jobs advisory unless their outputs become gates.

Acceptance:

- CI has one bootstrap path: install `.[dev]`.
- No CI branch suggests runtime requirements are a dev-contract substitute.

## What Should Hard-Fail Vs Warn-Only

Hard-fail locally:

- missing `.venv`;
- active interpreter is not repo `.venv`;
- missing dev dependency or pytest plugin;
- pytest addopts/plugin mismatch;
- `changed_path_verify.py` launched outside `.venv`;
- agent workflow smoke/audit failures after instruction changes;
- command facade, if added, cannot find `.venv`.

Warn-only locally:

- Python minor differs from CI until the project explicitly adopts local 3.13-only bootstrap;
- `VIRTUAL_ENV` is unset while `sys.executable` is correct `.venv\Scripts\python.exe`;
- advisory external services/digests unavailable.

Hard-fail in CI:

- `.[dev]` install failure;
- `verify_dev_contract.py --full --ci` failure;
- test failure;
- agent surface audit failure.

Warn/advisory in CI:

- ruff/syntax/digest jobs only if intentionally retained as advisory;
- pip-audit network/tool failure unless vulnerability scanning becomes a gate.

## Risks / Tradeoffs

- Explicit `.venv\Scripts\python.exe` commands are Windows-specific. That matches the current repo/CI center of gravity, but cross-platform docs would need parallel commands later.
- Requiring local Python 3.13 increases determinism but may require rebuilding `.venv`; keep it a planned decision, not an accidental break.
- A command facade reduces token waste and variance, but it is another helper to maintain. Try command normalization first.
- Removing CI fallback to `requirements.txt` is stricter but clearer; it reinforces that runtime deps are not the dev contract.
- Hard-failing wrong interpreter will interrupt agents more often at first. That is the desired failure mode.

## Anything That Should Explicitly NOT Be Done

- Do not change QuantMap runtime code under `src/`, product CLI behavior, package entrypoints, scoring, telemetry, reporting, or user workflows.
- Do not make QuantMap import `.agent`, `.vscode`, CI config, or helper scripts.
- Do not use shell profiles, machine-global PowerShell config, or PATH mutation as correctness.
- Do not rely on VS Code activation as proof.
- Do not add broad pytest cleanup unless default `.venv\Scripts\python.exe -m pytest -q` is blocked.
- Do not introduce pre-commit, tox, nox, devcontainers, or cross-platform abstraction in this phase.
- Do not make advisory external-service digests mandatory local commands.

## Support Scaffolding Vs Product

Support scaffolding:

- `AGENTS.md`
- `.agent/**` except generated artifacts/handoffs
- `.vscode/settings.json`
- `.github/workflows/*`
- `.github/instructions/*`
- `.github/pull_request_template.md`
- `docs/Plans/**`
- development setup sections in README/contributing
- helper scripts for contract checks, audits, smokechecks, and changed-path verification

Product/runtime surface:

- `src/**`
- `quantmap.py`, `rescore.py`
- package metadata needed for installing/running QuantMap
- runtime configs/data required by users
- user-facing docs/playbooks that describe operating QuantMap

Boundary rule:

- Phase 3 may touch package metadata only if required to make the dev contract explicit.
- Phase 3 must not make shipped QuantMap behavior depend on development scaffolding.

## Drift / Repeatability Threats To Watch

- A future helper adds `python -m tool` examples and bypasses `.venv`.
- A future CI job installs a missing tool late, masking an undeclared dev dependency.
- A future pytest addopts change assumes a plugin not declared in `.[dev]`.
- A future agent launches `changed_path_verify.py` with global Python; checks then run under the wrong `sys.executable`.
- VS Code selected interpreter and integrated terminal interpreter diverge.
- Local Python 3.14 passes while CI 3.13 fails due version-specific behavior.
- Generated support artifacts become visible or staged accidentally after ignore-rule changes.

## Implementation Staging Recommendation

Do Phase 3 in one narrow implementation pass if the repo chooses explicit `.venv\Scripts\python.exe` command normalization.

Stage it only if adding a command facade becomes necessary:

1. Stage A: normalize docs/instructions/scripts to explicit `.venv` launcher and harden `changed_path_verify.py`.
2. Stage B: add a facade only if command variance remains too high after Stage A.

## Lean Validation For This Investigation

Evidence commands used in this pass:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --full
.\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py --strict
.\.venv\Scripts\python.exe .agent\scripts\agent_workflow_smokecheck.py
Get-Command python
python -c "import os,sys; ..."
.\.venv\Scripts\python.exe -c "import os,sys; ..."
cmd /c "where python && python -c ..."
```

Plan validation should run changed-path verification on this file.
