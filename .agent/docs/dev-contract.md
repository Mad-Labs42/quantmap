# Dev Contract

## Purpose

This repository treats the Python package metadata as the source of truth for local development and CI. A fresh clone should be able to install the full development toolchain without hidden fallback installs.

## Normal Day-To-Day Workflow

Normal local work assumes `.venv` already exists and starts with the quick contract check:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
```

VS Code exposes this as the `QuantMap: Dev Contract Preflight` task and runs it on folder open when automatic tasks are allowed. If the check passes, continue using `.\.venv\Scripts\python.exe` for local repo-health commands. Shell activation, global `python`, and global `pip` are not correctness signals.
If quick preflight fails because `.venv` is missing or drifted, folder-open preflight performs one self-heal rebuild and reruns the quick check.

First open still requires VS Code workspace trust before any workspace task can execute. After trust is granted, startup preflight runs automatically from checked-in workspace settings.

## Canonical Repair / Rebuild

```powershell
$workspace = (Resolve-Path '.').Path
$venv = Join-Path $workspace '.venv'
Get-CimInstance Win32_Process |
  Where-Object {
    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($venv, [System.StringComparison]::OrdinalIgnoreCase)) -or
    ($_.Name -match '^(python|pythonw|ruff|mypy|dmypy)\.exe$' -and $_.CommandLine -and $_.CommandLine.IndexOf($venv, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

if (Test-Path $venv) { Remove-Item -LiteralPath $venv -Recurse -Force }
& D:\.store\mise\data\installs\python\3.13.13\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-user --upgrade pip
.\.venv\Scripts\python.exe -m pip install --no-user -e '.[dev]'
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --full
.\.venv\Scripts\python.exe -m pytest -q
```

Use repair/rebuild only when `.venv` is missing, locked, or fails interpreter/anchor checks. VS Code exposes the same procedure as the `QuantMap: Repair Dev Venv` task.

## Declared Dev Tools

| Tool | Declared By | Used For |
| --- | --- | --- |
| `pytest` | `pyproject.toml` `[project.optional-dependencies].dev` | Test execution |
| `pytest-cov` | `pyproject.toml` `[project.optional-dependencies].dev` | Coverage flags and XML output |
| `mypy` | `pyproject.toml` `[project.optional-dependencies].dev` | Type checking |
| `ruff` | `pyproject.toml` `[project.optional-dependencies].dev` | Linting |
| `types-psutil` | `pyproject.toml` `[project.optional-dependencies].dev` | Type checking support |
| `types-PyYAML` | `pyproject.toml` `[project.optional-dependencies].dev` | Type checking support |
| `pandas-stubs` | `pyproject.toml` `[project.optional-dependencies].dev` | Type checking support |

## Verification

Run the contract checker after installing dependencies or changing the development environment:

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --full
```

Quick mode verifies:

- the active local interpreter is the repo `.venv`
- Python is 3.13.x
- the repo `.venv` is anchored to `D:\.store\mise\data\installs\python\3.13.13`
- `pytest` imports from the active interpreter
- `pytest-cov` imports from the active interpreter
- `mypy` imports from the active interpreter
- `ruff` imports from the active interpreter

Full mode also verifies:

- `pytest --cov` is recognized
- pytest collection works with coverage disabled for the config probe

## Troubleshooting

If the contract check fails, reinstall the dev dependencies from the active environment:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-user -e '.[dev]'
```

If the Python version or DevStore anchor is wrong, recreate the virtual environment with the canonical DevStore interpreter:

```powershell
& D:\.store\mise\data\installs\python\3.13.13\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-user -e '.[dev]'
```
