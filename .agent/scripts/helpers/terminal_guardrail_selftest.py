#!/usr/bin/env python3
"""Self-test terminal guardrails with repeatable scenarios.

Writes:
    .agent/artifacts/terminal_guardrail_proof.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TypedDict

HELPERS_DIR = Path(__file__).resolve().parent
if str(HELPERS_DIR) not in sys.path:
    sys.path.insert(0, str(HELPERS_DIR))

from terminal_preflight_check import run_preflight  # noqa: E402


class SelfTestCase(TypedDict):
    name: str
    shell: str
    command: str
    expect_ok: bool


def find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".agent").exists():
            return current
        current = current.parent
    raise RuntimeError("Could not find repo root (.agent not found)")


def main() -> int:
    root = find_repo_root()
    cases: list[SelfTestCase] = [
        {
            "name": "reject-heredoc-1",
            "shell": "powershell",
            "command": "python - <<'PY'\nprint('x')\nPY",
            "expect_ok": False,
        },
        {
            "name": "reject-heredoc-2",
            "shell": "pwsh",
            "command": "cat <<EOF > tmp.txt",
            "expect_ok": False,
        },
        {
            "name": "reject-bash-and",
            "shell": "powershell",
            "command": ".\\.venv\\Scripts\\python.exe -m ruff check . && .\\.venv\\Scripts\\python.exe -m pytest -q",
            "expect_ok": False,
        },
        {
            "name": "reject-bash-or",
            "shell": "powershell",
            "command": ".\\.venv\\Scripts\\python.exe -m ruff check . || echo fail",
            "expect_ok": False,
        },
        {
            "name": "allow-safe-command",
            "shell": "powershell",
            "command": ".\\.venv\\Scripts\\python.exe .agent\\scripts\\agent_surface_audit.py --strict",
            "expect_ok": True,
        },
    ]

    results = []
    all_passed = True
    for case in cases:
        out = run_preflight(case["shell"], case["command"])
        passed = out["ok"] == case["expect_ok"]
        all_passed = all_passed and passed
        results.append(
            {
                "name": case["name"],
                "expect_ok": case["expect_ok"],
                "actual_ok": out["ok"],
                "passed": passed,
                "findings": out["findings"],
            }
        )

    failed_cases = [case for case in results if not case["passed"]]
    report = {
        "status": "pass" if all_passed else "fail",
        "total_cases": len(results),
        "passed_cases": len(results) - len(failed_cases),
        "failed_cases": len(failed_cases),
        "cases": results,
    }

    out_path = root / ".agent" / "artifacts" / "terminal_guardrail_proof.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"status: {report['status']}")
    print(f"cases: {report['passed_cases']}/{report['total_cases']} passed")
    if failed_cases:
        print("failed_cases:")
        for case in failed_cases:
            print(
                f"  - {case['name']}: expected_ok={case['expect_ok']} actual_ok={case['actual_ok']}"
            )
            for finding in case["findings"]:
                print(
                    f"    - {finding['rule']}: {finding['reason']} -> {finding['fix']}"
                )
    print(f"report: {out_path}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
