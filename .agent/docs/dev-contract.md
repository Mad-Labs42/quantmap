# Dev Contract

## Purpose

This repository treats the Python package metadata as the source of truth for local development and CI. A fresh clone should be able to install the full development toolchain without hidden fallback installs.

## Canonical Bootstrap

```powershell
& D:\.store\mise\data\installs\python\3.13.13\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-user --upgrade pip
.\.venv\Scripts\python.exe -m pip install --no-user -e '.[dev]'
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --full
.\.venv\Scripts\python.exe -m pytest -q
```

The local `.venv` is the repo-owned execution target. It must be created from the DevStore-managed Python 3.13 target above; `py -3.13`, shell activation, global `python`, and global `pip` are not the local contract.

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
