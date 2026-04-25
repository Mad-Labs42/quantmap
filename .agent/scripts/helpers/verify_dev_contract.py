#!/usr/bin/env python3
"""Verify the development environment contract for this repository.

This is development scaffolding. It verifies the active interpreter and
tooling used to develop QuantMap; it is not runtime/product behavior.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

REQUIRED_PYTHON_MINOR = (3, 13)
CANONICAL_DEVSTORE_PYTHON = Path("D:/.store/mise/data/installs/python/3.13.13/python.exe")
PYTEST_TIMEOUT_SECONDS = 30


@dataclass
class CheckResult:
    name: str
    status: str
    message: str


class ContractError(Exception):
    """Raised when a contract check fails."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def expected_venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def expected_devstore_python() -> Path:
    return CANONICAL_DEVSTORE_PYTHON


def normalize_path(path: Path) -> str:
    try:
        return str(path.resolve()).casefold()
    except OSError:
        return str(path.absolute()).casefold()


def tail(text: str, limit: int = 1200) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[-limit:]


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = PYTEST_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
        check=False,
    )


def classify_pytest_failure(result: subprocess.CompletedProcess[str]) -> str:
    combined = f"{result.stdout}\n{result.stderr}"
    lowered = combined.lower()
    if "unrecognized arguments" in lowered and "--cov" in lowered:
        return "pytest config references --cov but pytest-cov is unavailable"
    if "no module named pytest" in lowered:
        return "pytest is not importable in the active interpreter"
    if "coverage.exceptions.dataerror" in lowered or "couldn't use data file" in lowered:
        return "coverage data file open/write failure"
    if "permissionerror" in lowered or "permission denied" in lowered:
        return "filesystem permission failure during pytest"
    if "sqlite" in lowered and ("unable to open" in lowered or "database" in lowered):
        return "coverage/sqlite temp-file failure"
    if "collection" in lowered or "collected" in lowered:
        return "pytest collection/config failure"
    return "unknown pytest failure"


def check_python_version() -> CheckResult:
    version = sys.version_info
    found = f"{version.major}.{version.minor}.{version.micro}"
    if (version.major, version.minor) != REQUIRED_PYTHON_MINOR:
        raise ContractError(
            f"Python {found} found; repo development contract requires "
            f"{REQUIRED_PYTHON_MINOR[0]}.{REQUIRED_PYTHON_MINOR[1]}.x. "
            f"Recreate .venv with {expected_devstore_python()}, then run: "
            ".\\.venv\\Scripts\\python.exe -m pip install --no-user -e '.[dev]'"
        )
    return CheckResult("Python version", "ok", found)


def check_venv_ownership(
    root: Path, ci_mode: bool, allow_non_venv: bool
) -> CheckResult:
    expected = expected_venv_python(root)
    active = Path(sys.executable)
    expected_exists = expected.exists()
    active_matches = normalize_path(active) == normalize_path(expected)

    if active_matches:
        return CheckResult("Interpreter ownership", "ok", "active interpreter is repo .venv")
    if ci_mode or allow_non_venv:
        return CheckResult(
            "Interpreter ownership",
            "warn",
            f"non-repo interpreter accepted by override: {active}",
        )
    if not expected_exists:
        raise ContractError(
            f"Expected repo .venv Python not found at {expected}. "
            f"Run: & {expected_devstore_python()} -m venv .venv; "
            ".\\.venv\\Scripts\\python.exe -m pip install --no-user -e '.[dev]'"
        )
    raise ContractError(
        f"Active interpreter is not repo .venv. Active: {active}. Expected: {expected}. "
        "Run .\\.venv\\Scripts\\python.exe explicitly for local repo-health work."
    )


def check_devstore_anchor(ci_mode: bool) -> CheckResult:
    expected = expected_devstore_python()
    base = Path(sys.base_prefix)
    if ci_mode:
        return CheckResult(
            "DevStore anchor",
            "warn",
            "CI mode does not require local DevStore base",
        )
    if not expected.exists():
        raise ContractError(f"Canonical DevStore Python not found at {expected}.")
    if normalize_path(base) != normalize_path(expected.parent):
        raise ContractError(
            f"Repo .venv is not anchored to canonical DevStore Python. "
            f"sys.base_prefix: {base}. Expected: {expected.parent}. "
            f"Recreate .venv with: & {expected} -m venv .venv"
        )
    return CheckResult("DevStore anchor", "ok", str(expected.parent))


def check_tool_importable(tool_name: str, package_import_name: str | None = None) -> CheckResult:
    import_name = package_import_name or tool_name
    try:
        import_module(import_name)
    except ImportError as exc:
        raise ContractError(
            f"Tool '{tool_name}' is not importable in the active interpreter. "
            f"Import error: {exc}. "
            "Run: .\\.venv\\Scripts\\python.exe -m pip install --no-user -e '.[dev]'"
        ) from exc
    return CheckResult(tool_name, "ok", "importable")


def check_pytest_cov_plugin(root: Path) -> CheckResult:
    try:
        result = run_command(
            [sys.executable, "-m", "pytest", "--help"], cwd=root, timeout=15
        )
    except subprocess.TimeoutExpired as exc:
        raise ContractError(
            "pytest --help timed out while checking pytest-cov availability"
        ) from exc

    combined = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        raise ContractError(
            f"{classify_pytest_failure(result)} while running pytest --help. "
            f"stderr tail: {tail(result.stderr)}"
        )
    if "--cov" not in combined:
        raise ContractError(
            "pytest-cov plugin option '--cov' was not present in pytest --help. "
            "Run: .\\.venv\\Scripts\\python.exe -m pip install --no-user -e '.[dev]'"
        )
    return CheckResult("pytest-cov plugin", "ok", "--cov option available")


def check_pytest_config_collect(root: Path) -> CheckResult:
    command = [sys.executable, "-m", "pytest", "-o", "addopts=", "--collect-only", "-q", "--no-cov"]
    try:
        result = run_command(command, cwd=root)
    except subprocess.TimeoutExpired as exc:
        raise ContractError("pytest collection timed out with coverage disabled") from exc

    if result.returncode == 0:
        collected = tail(result.stdout, limit=160).replace("\n", "; ")
        return CheckResult("pytest config collection", "ok", collected or "collection passed")

    classification = classify_pytest_failure(result)
    raise ContractError(
        f"{classification} during pytest collection with coverage disabled. "
        f"Exit code: {result.returncode}. stderr tail: {tail(result.stderr)}"
    )


def print_environment(root: Path, ci_mode: bool) -> None:
    expected = expected_venv_python(root)
    devstore = expected_devstore_python()
    print("Environment:")
    print(f"  cwd: {Path.cwd()}")
    print(f"  sys.executable: {sys.executable}")
    print(f"  sys.prefix: {sys.prefix}")
    print(f"  sys.base_prefix: {sys.base_prefix}")
    print(f"  VIRTUAL_ENV: {os.environ.get('VIRTUAL_ENV', '<unset>')}")
    print(f"  expected .venv python: {expected}")
    print(f"  expected .venv exists: {expected.exists()}")
    print(f"  canonical DevStore python: {devstore}")
    print(f"  canonical DevStore python exists: {devstore.exists()}")
    print(f"  ci mode: {ci_mode}")
    print()


def emit_result(result: CheckResult) -> None:
    label = result.status.upper()
    print(f"[{label}] {result.name}: {result.message}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify QuantMap development environment contract.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true", help="Run interpreter and import checks only.")
    mode.add_argument("--full", action="store_true", help="Run quick checks plus pytest config checks.")
    parser.add_argument("--ci", action="store_true", help="Use CI semantics; do not require repo .venv ownership.")
    parser.add_argument(
        "--allow-non-venv",
        action="store_true",
        help="Allow non-repo interpreter ownership for advanced local scenarios.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = repo_root()
    ci_mode = args.ci or os.environ.get("CI", "").lower() == "true"
    full_mode = args.full or not args.quick

    print_environment(root, ci_mode=ci_mode)

    checks = [
        (
            "Interpreter ownership",
            lambda: check_venv_ownership(root, ci_mode, args.allow_non_venv),
        ),
        ("DevStore anchor", lambda: check_devstore_anchor(ci_mode)),
        ("Python version", check_python_version),
        ("pytest", lambda: check_tool_importable("pytest")),
        ("pytest-cov", lambda: check_tool_importable("pytest-cov", "pytest_cov")),
        ("mypy", lambda: check_tool_importable("mypy")),
        ("ruff", lambda: check_tool_importable("ruff")),
    ]
    if full_mode:
        checks.extend(
            [
                ("pytest-cov plugin", check_pytest_cov_plugin),
                ("pytest config collection", check_pytest_config_collect),
            ]
        )

    if full_mode:
        checks = [
            (
                name,
                (lambda func=func: func(root))
                if name in {"pytest-cov plugin", "pytest config collection"}
                else func,
            )
            for name, func in checks
        ]

    failures: list[tuple[str, str]] = []
    warnings = 0

    for check_name, check_func in checks:
        try:
            result = check_func()
            if result.status == "warn":
                warnings += 1
            emit_result(result)
        except ContractError as exc:
            failures.append((check_name, str(exc)))
            print(f"[FAIL] {check_name}: {exc}")

    print()
    if failures:
        print("Environment contract: FAIL")
        print(
            "Remediation: use .\\.venv\\Scripts\\python.exe and run "
            ".\\.venv\\Scripts\\python.exe -m pip install --no-user -e '.[dev]'."
        )
        return 1

    print(f"Environment contract: PASS ({warnings} warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
