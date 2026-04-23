#!/usr/bin/env python3
r"""Preflight terminal command safety checks.

Usage:
    .\.venv\Scripts\python.exe .agent\scripts\helpers\terminal_preflight_check.py --shell powershell --command ".\.venv\Scripts\python.exe -m pytest -q"
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PreflightRule:
    name: str
    pattern: str
    reason: str
    fix: str


POWERSHELL_BLOCK_RULES = [
    PreflightRule(
        name="bash-heredoc",
        pattern=r"<<\s*['\"]?[A-Za-z_][A-Za-z0-9_\-]*['\"]?",
        reason="Bash heredoc syntax detected in a PowerShell command.",
        fix="Use a PowerShell here-string (@' ... '@ or @\" ... \"@), or write a temporary script file.",
    ),
    PreflightRule(
        name="bash-and-operator",
        pattern=r"(^|\s)&&($|\s)",
        reason="Bash-style && operator detected.",
        fix="Use '; if ($LASTEXITCODE -ne 0) { ... }' or separate validated commands in PowerShell.",
    ),
    PreflightRule(
        name="bash-or-operator",
        pattern=r"(^|\s)\|\|($|\s)",
        reason="Bash-style || operator detected.",
        fix="Use PowerShell conditional logic instead of Bash operators.",
    ),
]


def run_preflight(shell: str, command: str) -> dict[str, object]:
    shell_l = shell.strip().lower()
    findings: list[dict[str, str]] = []

    if shell_l in {"powershell", "pwsh"}:
        for rule in POWERSHELL_BLOCK_RULES:
            if re.search(rule.pattern, command, flags=re.IGNORECASE):
                findings.append(
                    {
                        "rule": rule.name,
                        "reason": rule.reason,
                        "fix": rule.fix,
                    }
                )

    return {
        "ok": len(findings) == 0,
        "shell": shell_l,
        "command": command,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shell", default="powershell")
    parser.add_argument("--command", required=True)
    args = parser.parse_args()

    result = run_preflight(args.shell, args.command)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
