#!/usr/bin/env python3
"""Validate instruction chain integrity and anti-over-ingestion safeguards.

This smoke check verifies that the documented workflow remains minimal and safe.
"""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED_FILES = {
    "AGENTS.md": [
        "Read this file first.",
        "Read `.agent/policies/*` only when required by the task.",
        "Do not preload README/docs/all policy files.",
        ".agent/reference/terminal_guardrails.md",
    ],
    ".agent/policies/routing.md": [
        "Do not read all `.agent/policies/*` files by default.",
        "If scope is unclear, read `routing.md`, then choose one best next file.",
    ],
    ".copilot/instructions/quantmap-agent.instructions.md": [
        "Use the canonical instruction file:",
        ".github/instructions/quantmap-agent.instructions.md",
    ],
    ".github/instructions/quantmap-agent.instructions.md": [
        "## First Reads",
        "Only the single .agent/policies file needed for the task",
        "## Response Structure",
        "## Escalation Thresholds",
        ".agent/reference/terminal_guardrails.md",
    ],
    ".agent/policies/workflow.md": [
        "Use only needed sections: Outcome, Changes, Verification, Risks, Questions, Next Step.",
        "If blocked only by user input, print Questions only.",
    ],
    ".agent/policies/tooling.md": [
        ".\\.venv\\Scripts\\python.exe .agent\\scripts\\agent_workflow_smokecheck.py",
    ],
    ".agent/instructions/agent_maintenance.md": [
        "## New Session Lock-In",
        ".agent/instructions/agent_session_bootstrap.md",
    ],
    ".agent/instructions/agent_session_bootstrap.md": [
        "## Mandatory Instruction Chain",
        "## Blocking Question Format",
        "## Standard Command Workflow",
        "## Script Intent (When to Use)",
    ],
}


def main() -> int:
    root = Path.cwd()
    failures: list[str] = []
    warnings: list[str] = []

    for rel, phrases in REQUIRED_FILES.items():
        path = root / rel
        if not path.exists():
            failures.append(f"missing file: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for phrase in phrases:
            if phrase not in text:
                failures.append(f"missing phrase in {rel}: {phrase}")

    settings_path = root / ".vscode" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            locations = settings.get("chat.instructionsFilesLocations", {})
            if not isinstance(locations, dict):
                failures.append(
                    "chat.instructionsFilesLocations must be an object containing {'.github/instructions': true}"
                )
            elif locations.get(".github/instructions") is not True:
                failures.append(
                    "chat.instructionsFilesLocations must include {'.github/instructions': true}"
                )
        except Exception as exc:
            failures.append(f"invalid settings json: {exc}")
    else:
        warnings.append(".vscode/settings.json not found")

    report = {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "warnings": warnings,
    }

    out_dir = root / ".agent" / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "agent_workflow_smokecheck.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"status: {report['status']}")
    if failures:
        print("failures:")
        for item in failures:
            print(f"  - {item}")
    if warnings:
        print("warnings:")
        for item in warnings:
            print(f"  - {item}")
    print(f"report: {out_path}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
