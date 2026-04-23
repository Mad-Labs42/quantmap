# VS Code Python Interpreter Resolution Forensics

Date: 2026-04-20

Scope: workspace-environment investigation only. No product code was changed.

## Current Observed State

The repo contract is still the same one documented in the repository: local development is expected to use the repo-local `.venv`, anchored to DevStore Python 3.13.13 from `D:\.store\mise\data\installs\python\3.13.13\python.exe`.

What is actually on disk matches that contract:

- `D:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe` exists.
- `Resolve-Path .\.venv\Scripts\python.exe` resolves to `D:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe`.
- `.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick` passes.

VS Code, however, is not consistently resolving the configured default interpreter path from the workspace setting. The Python Environments extension logs a fallback from the configured relative path and reports repeated environment-resolution errors for `.venv\Scripts\python.exe`, even though auto-discovery and the Python extension still end up on the correct repo `.venv`.

## Exact Evidence Gathered

### Repo settings and task contract

Checked-in workspace settings still point at the repo-local interpreter:

- [`.vscode/settings.json`](../../../.vscode/settings.json)
  - Line 5: `task.allowAutomaticTasks = on`
  - Line 6: `python.defaultInterpreterPath = .venv\\Scripts\\python.exe`
  - Line 7: `python.terminal.activateEnvironment = true`
  - Line 8: `python.terminal.activateEnvInCurrentTerminal = true`
  - Line 9: `ruff.nativeServer = on`
  - Line 51: Sonar connected-mode project settings

- [`.vscode/tasks.json`](../../../.vscode/tasks.json)
  - Line 5: `QuantMap: Dev Contract Preflight`
  - Line 9: calls `.agent\\scripts\\helpers\\verify_dev_contract.py --quick`
  - Line 24: `QuantMap: Repair Dev Venv`
  - Line 33: rebuilds `.venv` from `D:\.store\mise\data\installs\python\3.13.13\python.exe`

The repo contract document still says the same thing:

- [`.agent/docs/dev-contract.md`](../../../.agent/docs/dev-contract.md)
  - Line 12: quick check uses `.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick`
  - Line 39: repair only when `.venv` is missing, locked, or fails interpreter/anchor checks
  - Line 85: recreate `.venv` from the canonical DevStore Python if the anchor is wrong

### User profile override

The VS Code user settings file under the roaming profile contains a conflicting `python.defaultInterpreterPath` entry:

- `C:\Users\PC\AppData\Roaming\Code\User\settings.json`
  - Line 323: `python.defaultInterpreterPath` is set to a quoted relative path string: `".venv\\Scripts\\python.exe"`

That is the strongest configuration-level anomaly. The workspace file is clean, but the user-profile setting is malformed enough to interfere with default-path resolution.

### Extension inventory

Installed and active Python-related extensions are present and match the current session:

- `charliermarsh.ruff@2026.40.0`
- `ms-python.debugpy@2025.18.0`
- `ms-python.python@2026.4.0`
- `ms-python.vscode-pylance@2026.2.1`
- `ms-python.vscode-python-envs@1.28.0`
- `sonarsource.sonarlint-vscode@5.1.0`

The Python extension package still contributes the interpreter command:

- `C:\Users\PC\.vscode\extensions\ms-python.python-2026.4.0-win32-x64\package.json`
  - Line 362: `python.setInterpreter`
  - Line 363: title for `python.setInterpreter`
  - Line 1356: `python.setInterpreter`
  - Line 1357: title for `python.setInterpreter`

So the command is not missing from the extension manifest. The issue is upstream of that: path resolution and environment selection, not a missing command contribution.

### Workspace storage / persistent state

The active workspaceStorage bucket exists and contains the expected Python extension state container:

- `C:\Users\PC\AppData\Roaming\Code\User\workspaceStorage\24ba10bd0e2704a8aa3c081e4a62200b\ms-python.python\pythonrc.py`

I attempted to inspect `state.vscdb` directly to probe trust/interpreter keys, but the terminal quoting got in the way and did not yield a reliable result. I did not find any direct evidence from the logs that workspace trust was blocking startup, and the Python extension did activate, which already argues against a trust failure.

### VS Code logs

Python extension host log:

- `C:\Users\PC\AppData\Roaming\Code\logs\20260420T200008\window1\exthost\ms-python.python\Python.log`
  - `Active interpreter [d:\Workspaces\QuantMap_agent]: d:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe`
  - `EnvExt: Failed to resolve environment for .venv\Scripts\python.exe`
  - `User did not select a Python environment in Select Python Tool.`

Python language server / Pylance handoff log:

- `C:\Users\PC\AppData\Roaming\Code\logs\20260420T200008\window1\exthost\ms-python.python\Python Language Server.log`
  - `Setting pythonPath for service "QuantMap_agent": "d:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe"`
  - `defaultInterpreterPath '.venv\Scripts\python.exe' unresolvable, falling back to auto-discovery`
  - `QuantMap_agent: .venv (3.13.13) (source: autoDiscovery)`
  - repeated `Failed to execute Python to resolve info "C:\\.venv\\Scripts\\python.exe"`
  - `Setup appears hung during stage: envSelection`

Python environments discovery log:

- `C:\Users\PC\AppData\Roaming\Code\logs\20260420T200008\window1\exthost\ms-python.vscode-python-envs\Python Environments.log`
  - `defaultEnvManager ... ms-python.python:venv`
  - discovers `D:\.store\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe`
  - discovers `C:\Users\PC\AppData\Roaming\uv\python\cpython-3.13.11-windows-x86_64-none\python.exe`
  - discovers `C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe`
  - discovers `d:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe`
  - resolves the repo `.venv` successfully after fallback discovery

Pylance log:

- `C:\Users\PC\AppData\Roaming\Code\logs\20260420T200008\window1\exthost\ms-python.vscode-pylance` output
  - Pylance starts with the Python extension
  - sets `pythonPath` to `d:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe`
  - indexing completes successfully
  - one non-fatal note says dynamic editable-install resolution wants Python 3.13 or later, but this is informational noise in this session because the workspace interpreter is already 3.13.13

Python debugger log:

- `C:\Users\PC\AppData\Roaming\Code\logs\20260420T200008\window1\exthost\ms-python.debugpy\Python Debugger.log`
  - empty

SonarQube for IDE log:

- `C:\Users\PC\AppData\Roaming\Code\logs\20260420T200008\window1\exthost\SonarSource.sonarlint-vscode\SonarQube for IDE.log`
  - Java-based Sonar language server starts normally
  - analysis completes successfully
  - no Node-runtime failure appears in the log

### Terminal / shell checks

Commands run and results:

```powershell
Resolve-Path .\.venv\Scripts\python.exe
Get-Item .\.venv\Scripts\python.exe | Format-List FullName,Length,LastWriteTime
```

Result:

```text
Path
----
D:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe

FullName      : D:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe
Length        : 241152
LastWriteTime : 12/31/2023 7:00:00 PM
```

Verifier command:

```powershell
.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
```

Result:

```text
WARNING: [DevStore] CONTAMINATION: pip resolves to C:\Users\PC\AppData\Local\Programs\Python\Python313\Scripts\pip.exe
Environment:
  cwd: D:\Workspaces\QuantMap_agent
  sys.executable: D:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe
  sys.prefix: D:\Workspaces\QuantMap_agent\.venv
  sys.base_prefix: D:\.store\mise\data\installs\python\3.13.13
  VIRTUAL_ENV: <unset>
  expected .venv python: D:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe
  expected .venv exists: True
  canonical DevStore python: D:\.store\mise\data\installs\python\3.13.13\python.exe
  canonical DevStore python exists: True
  ci mode: False

[OK] Interpreter ownership: active interpreter is repo .venv
[OK] DevStore anchor: D:\.store\mise\data\installs\python\3.13.13
[OK] Python version: 3.13.13
[OK] pytest: importable
[OK] pytest-cov: importable
[OK] mypy: importable
[OK] ruff: importable

Environment contract: PASS (0 warning(s))
```

Python-related extension inventory from VS Code:

```text
charliermarsh.ruff@2026.40.0
ms-python.debugpy@2025.18.0
ms-python.python@2026.4.0
ms-python.vscode-pylance@2026.2.1
ms-python.vscode-python-envs@1.28.0
sonarsource.sonarlint-vscode@5.1.0
```

## Confirmed Facts vs Assumptions

Confirmed:

1. The repo-local `.venv\Scripts\python.exe` exists and resolves on disk.
2. The repo contract still expects DevStore Python 3.13.13 via mise into the repo `.venv`.
3. The repo contract passes under `.venv\Scripts\python.exe`.
4. VS Code has the Python extension stack installed and active.
5. The Python extension manifest still contributes `python.setInterpreter`.
6. The Python Environments extension logs a failed resolution of `.venv\Scripts\python.exe` before falling back to auto-discovery.
7. Auto-discovery still ends up selecting the repo `.venv`.
8. SonarQube for IDE is active and healthy in this session; its logs do not show a Node-related failure.

Assumptions:

1. The malformed user-profile `python.defaultInterpreterPath` is the primary trigger for the bad default-path resolution, because the logs align with that failure mode.
2. Workspace trust is not the blocker, because the Python extension and Pylance both activated and the repo task ran.
3. The workspaceStorage database may contain stale interpreter state, but there is not yet direct proof of corruption.

## Timeline / Recent Changes That Matter

Relevant recent state from the logs:

1. At session start, Python Environments discovered the repo `.venv` and also found system/uv-managed Pythons.
2. The workspace-level `python.defaultInterpreterPath` should have been `.venv\Scripts\python.exe`, but the Python Environments log says that path was unresolvable and fell back to auto-discovery.
3. The same session still selected the repo `.venv` and Pylance attached to it.
4. Later, the Python log shows `EnvExt: Failed to resolve environment for .venv\Scripts\python.exe` and a user warning that no environment was selected in the Select Python Tool.
5. SonarQube logs show normal startup and analysis, which makes the concurrent editor-noise explanation plausible but not causal.

## Root-Cause Candidates Ranked

### 1. Malformed user-profile `python.defaultInterpreterPath` override

Likelihood: very high

Why:

- The user settings file contains `python.defaultInterpreterPath` with embedded quotes around a relative path.
- The Python Environments log explicitly says `.venv\Scripts\python.exe` is unresolvable and falls back to auto-discovery.
- The extension still eventually lands on the repo `.venv`, which is consistent with a bad default-path string rather than a missing environment.

Blast radius:

- VS Code interpreter selection, Command Palette selection, terminal activation hints, and possibly any extension that queries the Python environment service.

### 2. Stale VS Code interpreter state in workspaceStorage

Likelihood: medium

Why:

- There is active workspaceStorage for `ms-python.python`.
- The logs show repeated resolution attempts and a brief `envSelection` hang.
- However, the extension recovers to the correct `.venv`, so this looks more like stale noise than the primary failure.

Blast radius:

- Interpreter selection UI and any cached environment metadata.

### 3. Python Environments extension bug / regression in fallback handling

Likelihood: medium-low

Why:

- The extension emits `Failed to execute Python to resolve info` for the relative path and logs `Setup appears hung during stage: envSelection`.
- But the same extension then successfully discovers and resolves the repo `.venv`, so any bug here appears limited to the fallback path rather than total failure.

Blast radius:

- Interpreter enumeration and default-path resolution, especially when a malformed relative path is present.

### 4. Shell-path contamination for `pip` / global Python313 tools

Likelihood: low as root cause; medium as background risk

Why:

- The repo verifier warns that `pip` resolves to `C:\Users\PC\AppData\Local\Programs\Python\Python313\Scripts\pip.exe`.
- That is real contamination, but the repo verifier still passes and the VS Code Python services are using the repo `.venv`.

Blast radius:

- Confusing terminal behavior when the user types bare `pip`, but not the interpreter-resolution bug itself.

### 5. SonarQube for IDE / Node runtime issue

Likelihood: very low

Why:

- Sonar logs show a healthy Java server start and successful analysis.
- No Node-runtime error appears in the captured log.
- This is concurrent noise, not the interpreter failure.

Blast radius:

- Sonar analysis only, if it were failing. It is not failing here.

### 6. `uv` involvement

Likelihood: very low

Why:

- `uv`-managed Python installs are discovered by the environment service, but the active selection still resolves to the repo `.venv`.
- There is no evidence that `uv` is selected or controlling the broken path.

Blast radius:

- Mostly discovery noise unless the user intentionally selects a `uv` environment.

## Blast Radius

Repo-side:

- None yet. No repository code or config was changed.

Machine-side:

- Potentially the user-profile VS Code settings file under the roaming profile.
- Potentially cached VS Code state in the workspaceStorage database.

VS Code-side:

- Python interpreter selection UI.
- Default interpreter resolution.
- Terminal activation hints and related environment discovery.

Extension-side:

- `ms-python.vscode-python-envs` default-path resolution and fallback behavior.
- `ms-python.python` selection UI state.

## Recommended Next Steps, In Order

1. Remove or correct the user-profile `python.defaultInterpreterPath` override so only the checked-in workspace setting governs the repo.
2. Restart VS Code so the Python Environments extension and the command registry rebuild from a clean settings graph.
3. Reopen the workspace and confirm the Python log no longer reports `defaultInterpreterPath '.venv\Scripts\python.exe' unresolvable`.
4. If the warning persists, clear the workspaceStorage bucket for this workspace and retest interpreter selection.
5. Only if the issue still persists after the settings reset and cache refresh should the Python extension stack itself be treated as suspect.

## Narrowest Safe Fix Options

1. Remove the quoted `python.defaultInterpreterPath` from the VS Code user settings file.
2. Keep the repo setting unchanged and let the workspace setting own the interpreter path.
3. If cached state still interferes after that, clear only the workspaceStorage entry for this workspace, not the whole VS Code user profile.

## Other Issues Noticed During Inspection

1. The repo verifier reports shell contamination: bare `pip` resolves to the global Python313 Scripts directory instead of the repo environment.
2. The WSL extension-server directory is missing for the Ubuntu distro on this machine, but that is unrelated to the Python interpreter issue in this Windows workspace.
3. SonarLint is active in the workspace and operating normally; it is noisy but not causal here.

## Most Likely Story

VS Code is not actually missing the repo interpreter. The repo `.venv` exists, the DevStore anchor is correct, the repo-native contract passes, and the Python extension stack is installed and active.

The failure began because VS Code had a user-profile `python.defaultInterpreterPath` override that was malformed enough to make the relative path look unresolvable. The Python Environments extension then fell back to auto-discovery, which still found the repo `.venv`, so the workspace mostly recovered. That is why the failure looks intermittent and confusing: the underlying repo interpreter is fine, but the settings graph is not.

The SonarQube extension, `uv` discoveries, and the `pip` contamination warning are all secondary noise. The first thing that must be fixed is the malformed user-profile interpreter-path override; if the warning survives that, then stale workspaceStorage is the next thing to clear.

## .agent Files Used During This Turn

- [`.agent/README.md`](../../../.agent/README.md)
- [`.agent/policies/routing.md`](../../../.agent/policies/routing.md)
- [`.agent/docs/dev-contract.md`](../../../.agent/docs/dev-contract.md)
- [`.agent/scripts/helpers/verify_dev_contract.py`](../../../.agent/scripts/helpers/verify_dev_contract.py)
- [`.agent/scripts/agent_surface_audit.py`](../../../.agent/scripts/agent_surface_audit.py)
