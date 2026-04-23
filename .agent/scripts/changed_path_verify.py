#!/usr/bin/env python3
r"""Run robust verification on changed paths.

Usage examples:
    .\.venv\Scripts\python.exe .agent/scripts/changed_path_verify.py
    .\.venv\Scripts\python.exe .agent/scripts/changed_path_verify.py --base-ref main --no-untracked
    .\.venv\Scripts\python.exe .agent/scripts/changed_path_verify.py --paths .agent/scripts/changed_path_verify.py .agent/instructions/agent_command_catalog.md
    .\.venv\Scripts\python.exe .agent/scripts/changed_path_verify.py --require-tests
    .\.venv\Scripts\python.exe .agent/scripts/changed_path_verify.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from textwrap import indent
from typing import Any

IGNORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "build",
    "dist",
    "artifacts",
    "results",
    "logs",
    "state",
    "quantmap.egg-info",
}

IGNORED_PATH_PREFIXES = {
    (".agent", "artifacts"),
    (".agent", "handoffs"),
}
REQUIRED_PYTHON_MINOR = (3, 13)
CANONICAL_DEVSTORE_PYTHON = Path("D:/.store/mise/data/installs/python/3.13.13/python.exe")


def run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def expected_venv_python(root: Path) -> Path:
    if sys.platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def expected_devstore_python() -> Path:
    return CANONICAL_DEVSTORE_PYTHON


def normalize_path(path: Path) -> str:
    try:
        return str(path.resolve()).casefold()
    except OSError:
        return str(path.absolute()).casefold()


def interpreter_snapshot(root: Path) -> dict[str, Any]:
    expected = expected_venv_python(root)
    devstore = expected_devstore_python()
    active = Path(sys.executable)
    is_repo_venv = normalize_path(active) == normalize_path(expected)
    is_required_minor = (sys.version_info.major, sys.version_info.minor) == REQUIRED_PYTHON_MINOR
    base_is_devstore = normalize_path(Path(sys.base_prefix)) == normalize_path(devstore.parent)
    return {
        "sys_executable": str(active),
        "sys_prefix": sys.prefix,
        "sys_base_prefix": sys.base_prefix,
        "python_version": sys.version.split()[0],
        "expected_venv_python": str(expected),
        "expected_venv_exists": expected.exists(),
        "expected_devstore_python": str(devstore),
        "expected_devstore_python_exists": devstore.exists(),
        "is_repo_venv": is_repo_venv,
        "is_required_python_minor": is_required_minor,
        "base_is_devstore": base_is_devstore,
    }


def write_report(root: Path, report: dict[str, Any]) -> Path:
    out_dir = root / ".agent" / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "changed_path_verify.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out_path


def gather_changed_files(
    root: Path, base_ref: str | None, include_untracked: bool
) -> list[str]:
    files: set[str] = set()

    def add_from_cmd(cmd: list[str]) -> None:
        rc, out, _ = run(cmd, root)
        if rc == 0 and out:
            for line in out.splitlines():
                p = line.strip().replace("\\", "/")
                if p:
                    files.add(p)

    if base_ref:
        add_from_cmd(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base_ref}...HEAD"]
        )

    add_from_cmd(["git", "diff", "--name-only", "--diff-filter=ACMR"])
    add_from_cmd(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"])

    if include_untracked:
        add_from_cmd(["git", "ls-files", "--others", "--exclude-standard"])

    return sorted(files)


def expand_input_paths(root: Path, raw_paths: list[str]) -> list[str]:
    files: set[str] = set()
    for raw in raw_paths:
        p = (root / raw).resolve()
        if not p.exists():
            continue
        if p.is_file():
            files.add(p.relative_to(root).as_posix())
            continue
        if p.is_dir():
            for child in p.rglob("*"):
                if child.is_file():
                    files.add(child.relative_to(root).as_posix())
    return sorted(files)


def is_ignored(path: Path) -> bool:
    parts = path.parts
    for prefix in IGNORED_PATH_PREFIXES:
        if len(parts) >= len(prefix) and parts[: len(prefix)] == prefix:
            return True
    return any(part in IGNORED_PARTS for part in path.parts)


def chunked(items: list[str], max_items: int = 80) -> list[list[str]]:
    return [items[i : i + max_items] for i in range(0, len(items), max_items)]


def infer_test_targets(
    root: Path, changed_py: list[str], max_tests: int
) -> tuple[list[str], bool]:
    targets: set[str] = set()
    truncated = False

    for rel in changed_py:
        p = Path(rel)
        name = p.name
        if name.startswith("test_") and name.endswith(".py"):
            targets.add(rel)
            continue

        stem = p.stem
        inferred_name = f"test_{stem}.py"

        direct_candidates = [
            Path(inferred_name),
            Path("tests") / inferred_name,
            Path("test") / inferred_name,
        ]
        for cand in direct_candidates:
            full = root / cand
            if full.exists() and full.is_file() and not is_ignored(cand):
                targets.add(cand.as_posix())

        for found in root.rglob(inferred_name):
            rel_found = found.relative_to(root)
            if not is_ignored(rel_found):
                targets.add(rel_found.as_posix())
            if len(targets) >= max_tests:
                truncated = True
                return sorted(targets), truncated

    sorted_targets = sorted(targets)
    if len(sorted_targets) > max_tests:
        truncated = True
        sorted_targets = sorted_targets[:max_tests]
    return sorted_targets, truncated


def format_tail(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return f"{text[-limit:]}\n...[truncated {len(text) - limit} chars]..."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-ref", default=None, help="Optional git ref for diff base"
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        default=None,
        help="Optional explicit file/dir paths to verify instead of git-detected changes",
    )
    parser.add_argument(
        "--no-untracked",
        action="store_true",
        help="Exclude untracked files from verification selection",
    )
    parser.add_argument(
        "--require-tests",
        action="store_true",
        help="Fail if no test targets are found",
    )
    parser.add_argument(
        "--max-test-files",
        type=int,
        default=25,
        help="Maximum number of inferred test files to run",
    )
    parser.add_argument(
        "--skip-tests", action="store_true", help="Skip pytest execution"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show selected checks only"
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Use CI semantics; do not require local repo .venv ownership",
    )
    args = parser.parse_args()

    root = Path.cwd()
    interpreter = interpreter_snapshot(root)
    include_untracked = not args.no_untracked
    failures: list[str] = []
    if not interpreter["is_required_python_minor"]:
        failures.append(
            "changed_path_verify.py requires Python "
            f"{REQUIRED_PYTHON_MINOR[0]}.{REQUIRED_PYTHON_MINOR[1]}.x. "
            f"Active: {interpreter['python_version']}."
        )
    if not args.ci and not interpreter["is_repo_venv"]:
        failures.append(
            "changed_path_verify.py must be launched with the repo .venv Python. "
            f"Active: {interpreter['sys_executable']}. "
            f"Expected: {interpreter['expected_venv_python']}."
        )
    if not args.ci and not interpreter["base_is_devstore"]:
        failures.append(
            "repo .venv must be anchored to canonical DevStore Python. "
            f"sys.base_prefix: {interpreter['sys_base_prefix']}. "
            f"Expected: {Path(interpreter['expected_devstore_python']).parent}."
        )
    if failures:
        report = {
            "base_ref": args.base_ref,
            "include_untracked": include_untracked,
            "interpreter": interpreter,
            "changed_files": [],
            "changed_python_files": [],
            "test_targets": [],
            "checks": [],
            "failures": failures,
            "warnings": [],
            "status": "fail",
        }
        out_path = write_report(root, report)
        print("status: fail")
        print(f"interpreter: {interpreter['sys_executable']}")
        print(f"python_version: {interpreter['python_version']}")
        print(f"expected_venv_python: {interpreter['expected_venv_python']}")
        print(f"expected_devstore_python: {interpreter['expected_devstore_python']}")
        print("failures:")
        for failure in failures:
            print(f"  - {failure}")
        print(f"report: {out_path}")
        return 1

    if args.paths:
        changed = expand_input_paths(root, args.paths)
    else:
        changed = gather_changed_files(root, args.base_ref, include_untracked)

    changed_existing = [p for p in changed if (root / p).exists()]
    changed_py = [
        p for p in changed_existing if p.endswith(".py") and not is_ignored(Path(p))
    ]

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not changed:
        warnings.append("No changed files detected.")

    if changed_py:
        for batch in chunked(changed_py):
            cmd = [sys.executable, "-m", "ruff", "check", *batch]
            checks.append({"name": "ruff", "cmd": cmd})

        compile_cmd = [sys.executable, "-m", "compileall", "-q", *changed_py]
        checks.append({"name": "compileall", "cmd": compile_cmd})

    test_targets: list[str] = []
    test_targets_truncated = False
    if not args.skip_tests:
        test_targets, test_targets_truncated = infer_test_targets(
            root, changed_py, args.max_test_files
        )

    if not args.skip_tests and test_targets:
        checks.append(
            {
                "name": "pytest",
                "cmd": [sys.executable, "-m", "pytest", "-q", *test_targets],
            }
        )
    elif not args.skip_tests and args.require_tests:
        failures.append("No test targets inferred and --require-tests was set.")
    elif not args.skip_tests and not test_targets:
        warnings.append("No focused test targets inferred; pytest was not run.")
    if test_targets_truncated:
        warnings.append(
            f"Test target selection hit the cap of {args.max_test_files}; pytest coverage may be partial."
        )

    check_results: list[dict[str, Any]] = []
    if args.dry_run:
        for check in checks:
            check_results.append(
                {"name": check["name"], "cmd": check["cmd"], "status": "dry-run"}
            )
    else:
        for check in checks:
            rc, out, err = run(check["cmd"], root)
            entry = {
                "name": check["name"],
                "cmd": check["cmd"],
                "exit_code": rc,
                "stdout": out,
                "stderr": err,
                "status": "pass" if rc == 0 else "fail",
            }
            check_results.append(entry)
            if rc != 0:
                failures.append(f"check failed: {check['name']} (exit code {rc})")

    report = {
        "base_ref": args.base_ref,
        "include_untracked": include_untracked,
        "interpreter": interpreter,
        "changed_files": changed,
        "changed_python_files": changed_py,
        "test_targets": test_targets,
        "checks": check_results,
        "failures": failures,
        "warnings": warnings,
        "status": "pass" if not failures else "fail",
    }

    out_path = write_report(root, report)

    print(f"status: {report['status']}")
    print(f"interpreter: {interpreter['sys_executable']}")
    print(f"interpreter_is_repo_venv: {interpreter['is_repo_venv']}")
    print(f"python_version: {interpreter['python_version']}")
    print(f"base_is_devstore: {interpreter['base_is_devstore']}")
    print(f"changed_files: {len(changed)}")
    print(f"changed_python_files: {len(changed_py)}")
    print(f"test_targets: {len(test_targets)}")
    if failures:
        print("failures:")
        for item in failures:
            print(f"  - {item}")
        for result in check_results:
            if result.get("status") != "fail":
                continue
            print(f"{result['name']} exit_code={result['exit_code']}")
            if result.get("stdout"):
                print("  stdout:")
                print(indent(format_tail(result["stdout"]), "    "))
            if result.get("stderr"):
                print("  stderr:")
                print(indent(format_tail(result["stderr"]), "    "))
    if warnings:
        print("warnings:")
        for item in warnings:
            print(f"  - {item}")
    print(f"report: {out_path}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
