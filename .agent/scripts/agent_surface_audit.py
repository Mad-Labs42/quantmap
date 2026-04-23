#!/usr/bin/env python3
r"""Audit repository agent surfaces for drift and missing controls.

Usage:
    .\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py
    .\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py --strict
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_FILES = [
    "AGENTS.md",
    ".agent/policies/routing.md",
    ".agent/policies/tooling.md",
    ".agent/policies/workflow.md",
    ".agent/policies/testing.md",
    ".github/instructions/quantmap-agent.instructions.md",
    ".copilot/instructions/quantmap-agent.instructions.md",
    ".agent/instructions/agent_maintenance.md",
    ".agent/instructions/agent_command_catalog.md",
    ".agent/instructions/agent_session_bootstrap.md",
    ".vscode/settings.json",
    ".agent/scripts/changed_path_verify.py",
    ".agent/scripts/generate_agent_handoff.py",
    ".agent/scripts/agent_workflow_smokecheck.py",
    ".agent/scripts/helpers/terminal_preflight_check.py",
    ".agent/scripts/helpers/terminal_guardrail_selftest.py",
    ".agent/reference/terminal_guardrails.md",
    ".vscode/tasks.json",
]

REQUIRED_SETTINGS = {
    "chat.instructionsFilesLocations": {
        ".github/instructions": True,
    },
    "task.allowAutomaticTasks": "on",
    "ruff.nativeServer": "on",
}

REQUIRED_SECTIONS = {
    "AGENTS.md": [
        "## Automation Boundaries",
        "## Terminal Guardrails (VS Code and Antigravity only)",
        "## When to Stop and Ask",
        "## Code Style Expectations",
        "## Response Token Discipline",
        "## Output",
    ],
    ".github/instructions/quantmap-agent.instructions.md": [
        "## First Reads",
        "## Auto Lint and Correctness",
        "## Impact Propagation Rules",
        "## Automation and Script Placement",
        "## Terminal Failure Handling (VS Code and Antigravity only)",
        "## Response Structure",
        "## Escalation Thresholds",
    ],
    ".agent/policies/workflow.md": [
        "## Stop-and-Ask Rules",
        "## Patch Strategy",
        "## Reporting Back",
    ],
    ".agent/policies/testing.md": [
        "## Validation Expectations",
        "## Verified Means",
        "## Not Verified Means",
        "## Testing Rules",
    ],
    ".agent/policies/tooling.md": [
        "## Read Strategy",
        "## Command Strategy",
        "## Context Pruning Safety",
    ],
    ".agent/reference/terminal_guardrails.md": [
        "## Scope",
        "## Pre-Mutation Safety Checks",
        "## Failure Handling Protocol",
        "## Guardrail Self-Test (Proof)",
    ],
}

MIN_SIZE_CHARS = {
    "AGENTS.md": 4000,
    ".github/instructions/quantmap-agent.instructions.md": 4100,
    ".agent/policies/workflow.md": 2300,
    ".agent/policies/testing.md": 900,
    ".agent/policies/tooling.md": 2250,
    ".agent/reference/terminal_guardrails.md": 1650,
    ".agent/policies/routing.md": 650,
}

REQUIRED_SECTION_MIN_BULLETS = {
    "AGENTS.md": {
        "## When to Stop and Ask": 5,
    },
    ".agent/reference/terminal_guardrails.md": {
        "## Failure Handling Protocol": 3,
    },
}

CANONICAL_POINTER_PATH = ".github/instructions/quantmap-agent.instructions.md"
POINTER_FILE = ".copilot/instructions/quantmap-agent.instructions.md"
POINTER_FORBIDDEN_MARKERS = [
    "## Scope and Safety",
    "## First Reads",
    "## Escalation Thresholds",
    "## Output Contract",
]

REQUIRED_POLICY_PHRASES = {
    "AGENTS.md": [
        "Escalate and ask when:",
        "Auto-lint after each edit batch on touched files before continuing.",
        "Run a correctness check appropriate to each changed path before claiming success.",
        "Never omit critical facts, risks, assumptions, blockers, or required user questions to save tokens.",
    ],
    ".github/instructions/quantmap-agent.instructions.md": [
        "Only the single .agent/policies file needed for the task",
        "Auto-run lint on touched files after each edit batch and fix findings before proceeding.",
        "Perform at least one correctness check per changed behavior path",
        "Available sections: Outcome, Changes, Verification, Risks, Questions, Next Step.",
        "Ask before proceeding when:",
    ],
    ".agent/policies/workflow.md": [
        "Always ask before proceeding when:",
        "Run at least one correctness check suited to the changed behavior before claiming completion.",
        "Use only needed sections: Outcome, Changes, Verification, Risks, Questions, Next Step.",
        "Do not claim success without verification.",
    ],
    ".agent/policies/testing.md": [
        "Lint touched files after each edit batch; treat lint failures as blocking",
        "Re-check dependent call paths when contracts, names, signatures, or outputs change.",
    ],
    ".agent/policies/tooling.md": [
        "Do not read K.I.T./TO-DO tracker files unless the user asks to read or update them.",
        ".\\.venv\\Scripts\\python.exe .agent\\scripts\\agent_surface_audit.py --strict",
        ".\\.venv\\Scripts\\python.exe .agent\\scripts\\agent_workflow_smokecheck.py",
    ],
    ".agent/reference/terminal_guardrails.md": [
        "Never use Bash heredoc syntax (`<<`) in PowerShell commands.",
        '.\\.venv\\Scripts\\python.exe .agent\\scripts\\helpers\\terminal_preflight_check.py --shell powershell --command "<command>"',
        ".\\.venv\\Scripts\\python.exe .agent\\scripts\\helpers\\terminal_guardrail_selftest.py",
    ],
}

REQUIRED_TASK_LABELS = {
    "QuantMap: Dev Contract Preflight",
    "QuantMap: Repair Dev Venv",
}


def normalize_spaces(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_header(value: str) -> str:
    text = value.strip()
    if text.startswith("##"):
        text = text[2:]
    return normalize_spaces(text).lower()


def check_interpreter_path(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower().replace("/", "\\")
    return ".venv" in normalized and normalized.endswith("python.exe")


def extract_h2_headers(text: str) -> list[str]:
    headers: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            headers.append(match.group(1))
    return headers


def section_block_lines(text: str, header: str) -> list[str]:
    lines = text.splitlines()
    wanted = normalize_header(header)
    start_idx = None
    for idx, line in enumerate(lines):
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match and normalize_header(match.group(1)) == wanted:
            start_idx = idx + 1
            break
    if start_idx is None:
        return []

    block: list[str] = []
    for line in lines[start_idx:]:
        if re.match(r"^##\s+", line):
            break
        block.append(line)
    return block


def parse_routing_dispatch_targets(text: str) -> set[str]:
    targets: set[str] = set()
    in_rules = False
    for line in text.splitlines():
        if line.strip().lower() == "rules:":
            in_rules = True
            continue
        if in_rules:
            continue
        match = re.match(r"^\s*-\s+.*->\s*`([a-zA-Z0-9_.-]+\.md)`\s*$", line)
        if match:
            targets.add(match.group(1).lower())
    return targets


def add_issue(
    target_lines: list[str],
    target_items: list[dict[str, str]],
    category: str,
    rel: str,
    detail: str,
    hint: str,
) -> None:
    target_lines.append(f"[{category}] {rel}: {detail}")
    target_items.append(
        {
            "category": category,
            "file": rel,
            "detail": detail,
            "hint": hint,
        }
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict", action="store_true", help="Exit non-zero on failures"
    )
    args = parser.parse_args()

    root = Path.cwd()
    failures: list[str] = []
    warnings: list[str] = []
    failure_items: list[dict[str, str]] = []
    warning_items: list[dict[str, str]] = []
    remediation_hints: dict[str, str] = {
        "missing-file": "Restore the required file or update REQUIRED_FILES only when intentionally removing a control.",
        "missing-section": "Restore the missing section/header or adjust REQUIRED_SECTIONS when the change is intentional.",
        "size-floor": "Review truncation risk; if shrink is intentional, update MIN_SIZE_CHARS with a rationale.",
        "settings": "Align workspace settings with audit requirements.",
        "routing-drift": "Align routing dispatch targets with policy files on disk.",
        "pointer-drift": "Keep the .copilot instruction file as a thin pointer to the canonical .github file.",
        "missing-phrase": "Restore the required invariant phrase or replace with a stable equivalent in REQUIRED_POLICY_PHRASES.",
    }

    for rel in REQUIRED_FILES:
        path = root / rel
        if not path.exists():
            add_issue(
                failures,
                failure_items,
                "missing-file",
                rel,
                "required file not found",
                remediation_hints["missing-file"],
            )

    for rel, min_chars in MIN_SIZE_CHARS.items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        size = len(text)
        if size < min_chars:
            add_issue(
                failures,
                failure_items,
                "size-floor",
                rel,
                f"content length {size} below minimum {min_chars}",
                remediation_hints["size-floor"],
            )

    for rel, sections in REQUIRED_SECTIONS.items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        actual_headers = {
            normalize_header(header) for header in extract_h2_headers(text)
        }
        for section in sections:
            normalized_required = normalize_header(section)
            if normalized_required not in actual_headers:
                add_issue(
                    failures,
                    failure_items,
                    "missing-section",
                    rel,
                    f"missing section header: {section}",
                    remediation_hints["missing-section"],
                )

    for rel, section_map in REQUIRED_SECTION_MIN_BULLETS.items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for section, min_bullets in section_map.items():
            block = section_block_lines(text, section)
            if not block:
                continue
            bullet_count = sum(1 for line in block if re.match(r"^\s*-\s+\S", line))
            if bullet_count < min_bullets:
                add_issue(
                    failures,
                    failure_items,
                    "missing-section",
                    rel,
                    f"section '{section}' has {bullet_count} bullet lines; requires at least {min_bullets}",
                    remediation_hints["missing-section"],
                )

    for rel, phrases in REQUIRED_POLICY_PHRASES.items():
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for phrase in phrases:
            if phrase not in text:
                add_issue(
                    failures,
                    failure_items,
                    "missing-phrase",
                    rel,
                    f"missing required phrase: {phrase}",
                    remediation_hints["missing-phrase"],
                )

    routing_path = root / ".agent" / "policies" / "routing.md"
    if routing_path.exists():
        routing_text = routing_path.read_text(encoding="utf-8", errors="replace")
        dispatch_targets = parse_routing_dispatch_targets(routing_text)
        policy_files = {
            path.name.lower()
            for path in (root / ".agent" / "policies").glob("*.md")
            if path.name.lower() != "routing.md"
        }
        if not dispatch_targets:
            add_issue(
                failures,
                failure_items,
                "routing-drift",
                ".agent/policies/routing.md",
                "no dispatch targets parsed from routing map",
                remediation_hints["routing-drift"],
            )
        for missing in sorted(dispatch_targets - policy_files):
            add_issue(
                failures,
                failure_items,
                "routing-drift",
                ".agent/policies/routing.md",
                f"dispatch references missing policy file: {missing}",
                remediation_hints["routing-drift"],
            )
        for unreferenced in sorted(policy_files - dispatch_targets):
            add_issue(
                failures,
                failure_items,
                "routing-drift",
                ".agent/policies/routing.md",
                f"policy file on disk is not routed: {unreferenced}",
                remediation_hints["routing-drift"],
            )

    pointer_path = root / POINTER_FILE
    if pointer_path.exists():
        pointer_text = pointer_path.read_text(encoding="utf-8", errors="replace")
        line_count = len(pointer_text.splitlines())
        if CANONICAL_POINTER_PATH not in pointer_text:
            add_issue(
                failures,
                failure_items,
                "pointer-drift",
                POINTER_FILE,
                f"missing canonical pointer path: {CANONICAL_POINTER_PATH}",
                remediation_hints["pointer-drift"],
            )
        if "Use the canonical instruction file:" not in pointer_text:
            add_issue(
                failures,
                failure_items,
                "pointer-drift",
                POINTER_FILE,
                "missing pointer preface line: 'Use the canonical instruction file:'",
                remediation_hints["pointer-drift"],
            )
        if line_count > 20 or len(pointer_text) > 1200:
            add_issue(
                failures,
                failure_items,
                "pointer-drift",
                POINTER_FILE,
                f"pointer file should remain thin (lines={line_count}, chars={len(pointer_text)})",
                remediation_hints["pointer-drift"],
            )
        for marker in POINTER_FORBIDDEN_MARKERS:
            if marker in pointer_text:
                add_issue(
                    failures,
                    failure_items,
                    "pointer-drift",
                    POINTER_FILE,
                    f"pointer file contains canonical policy section marker: {marker}",
                    remediation_hints["pointer-drift"],
                )

    settings_path = root / ".vscode" / "settings.json"
    if settings_path.exists():
        try:
            settings = load_json(settings_path)
        except Exception as exc:
            add_issue(
                failures,
                failure_items,
                "settings",
                ".vscode/settings.json",
                f"invalid json ({exc})",
                remediation_hints["settings"],
            )
            settings = {}

        for key, expected in REQUIRED_SETTINGS.items():
            if key not in settings:
                add_issue(
                    failures,
                    failure_items,
                    "settings",
                    ".vscode/settings.json",
                    f"missing setting key: {key} (expected {expected!r})",
                    remediation_hints["settings"],
                )
                continue
            actual = settings[key]
            if isinstance(expected, dict):
                if not isinstance(actual, dict):
                    add_issue(
                        failures,
                        failure_items,
                        "settings",
                        ".vscode/settings.json",
                        f"setting mismatch: {key} expected object, got {type(actual).__name__}",
                        remediation_hints["settings"],
                    )
                    continue
                for subkey, subexpected in expected.items():
                    if actual.get(subkey) != subexpected:
                        add_issue(
                            failures,
                            failure_items,
                            "settings",
                            ".vscode/settings.json",
                            f"setting mismatch: {key}.{subkey} expected {subexpected!r}, got {actual.get(subkey)!r}",
                            remediation_hints["settings"],
                        )
            elif actual != expected:
                add_issue(
                    failures,
                    failure_items,
                    "settings",
                    ".vscode/settings.json",
                    f"setting mismatch: {key} expected {expected!r}, got {actual!r}",
                    remediation_hints["settings"],
                )

        interpreter_path = settings.get("python.defaultInterpreterPath")
        if not check_interpreter_path(interpreter_path):
            add_issue(
                failures,
                failure_items,
                "settings",
                ".vscode/settings.json",
                "python.defaultInterpreterPath must contain '.venv' and end with 'python.exe'",
                remediation_hints["settings"],
            )

        py = settings.get("[python]")
        if not isinstance(py, dict):
            add_issue(
                failures,
                failure_items,
                "settings",
                ".vscode/settings.json",
                "missing [python] editor block",
                remediation_hints["settings"],
            )
        else:
            if py.get("editor.defaultFormatter") != "charliermarsh.ruff":
                add_issue(
                    failures,
                    failure_items,
                    "settings",
                    ".vscode/settings.json",
                    "python formatter is not charliermarsh.ruff",
                    remediation_hints["settings"],
                )

        search_exclude = settings.get("search.exclude", {})
        for must in [
            "**/.venv",
            "**/.pytest_cache",
            "**/.ruff_cache",
            "**/results",
            "**/.agent/artifacts",
            "docs/system/known_issues_tracker.md",
            "docs/system/TO-DO.md",
            "docs/K.I.T.-&-ToDo/**",
        ]:
            if (
                not isinstance(search_exclude, dict)
                or search_exclude.get(must) is not True
            ):
                add_issue(
                    warnings,
                    warning_items,
                    "settings",
                    ".vscode/settings.json",
                    f"recommended search.exclude missing: {must}",
                    "Add the recommended search.exclude entry to reduce noisy context.",
                )

    tasks_path = root / ".vscode" / "tasks.json"
    if tasks_path.exists():
        try:
            tasks_doc = load_json(tasks_path)
            tasks = tasks_doc.get("tasks", [])
        except Exception as exc:
            add_issue(
                failures,
                failure_items,
                "settings",
                ".vscode/tasks.json",
                f"invalid json ({exc})",
                remediation_hints["settings"],
            )
            tasks = []

        labels = {
            task.get("label")
            for task in tasks
            if isinstance(task, dict) and isinstance(task.get("label"), str)
        }
        for label in sorted(REQUIRED_TASK_LABELS - labels):
            add_issue(
                failures,
                failure_items,
                "settings",
                ".vscode/tasks.json",
                f"missing task label: {label}",
                remediation_hints["settings"],
            )

        preflight = next(
            (
                task
                for task in tasks
                if isinstance(task, dict)
                and task.get("label") == "QuantMap: Dev Contract Preflight"
            ),
            {},
        )
        if isinstance(preflight, dict):
            command_value = preflight.get("command", "")
            args_value = preflight.get("args", [])
            task_parts: list[str] = []
            if isinstance(command_value, str):
                task_parts.append(command_value)
            if isinstance(args_value, list):
                task_parts.extend(str(item) for item in args_value)
            elif isinstance(args_value, str):
                task_parts.append(args_value)

            task_text = " ".join(task_parts).replace("/", "\\").lower()

            if (
                ".\\.venv\\scripts\\python.exe" not in task_text
                and ".venv\\scripts\\python.exe" not in task_text
            ):
                add_issue(
                    failures,
                    failure_items,
                    "settings",
                    ".vscode/tasks.json",
                    "preflight task must run .\\.venv\\Scripts\\python.exe",
                    remediation_hints["settings"],
                )
            if ".agent\\scripts\\helpers\\verify_dev_contract.py" not in task_text:
                add_issue(
                    failures,
                    failure_items,
                    "settings",
                    ".vscode/tasks.json",
                    "preflight task must call verify_dev_contract.py",
                    remediation_hints["settings"],
                )
            if "--quick" not in task_text:
                add_issue(
                    failures,
                    failure_items,
                    "settings",
                    ".vscode/tasks.json",
                    "preflight task must call verify_dev_contract.py with --quick",
                    remediation_hints["settings"],
                )
            run_options = preflight.get("runOptions", {})
            if (
                not isinstance(run_options, dict)
                or run_options.get("runOn") != "folderOpen"
            ):
                add_issue(
                    warnings,
                    warning_items,
                    "settings",
                    ".vscode/tasks.json",
                    "preflight task should run on folderOpen",
                    "Set runOptions.runOn to folderOpen for deterministic startup preflight.",
                )

    report = {
        "failures": failures,
        "warnings": warnings,
        "failure_items": failure_items,
        "warning_items": warning_items,
        "summary": {
            "failure_count": len(failures),
            "warning_count": len(warnings),
        },
        "status": "pass" if not failures else "fail",
    }

    out_dir = root / ".agent" / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "agent_surface_audit.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if report["status"] == "pass":
        print(f"audit: PASS (0f failures, {len(warnings)}w warnings)")
    else:
        print(f"audit: FAIL ({len(failures)}f failures, {len(warnings)}w warnings)")

    if failures:
        print("failures:")
        for item in failures:
            print(f"  - {item}")
    if warnings:
        print("warnings:")
        for item in warnings:
            print(f"  - {item}")

    if failures or warnings:
        active_categories = {item["category"] for item in failure_items} | {
            item["category"] for item in warning_items
        }
        if active_categories:
            print("remediation:")
            for category in sorted(active_categories):
                hint = remediation_hints.get(category)
                if hint:
                    print(f"  - [{category}] {hint}")

    print(f"report: {out_path}")

    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
