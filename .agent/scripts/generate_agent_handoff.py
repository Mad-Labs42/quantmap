#!/usr/bin/env python3
r"""Generate a concise, robust handoff artifact for agent continuity.

Usage:
    .\.venv\Scripts\python.exe .agent\scripts\generate_agent_handoff.py
    .\.venv\Scripts\python.exe .agent\scripts\generate_agent_handoff.py --title "Phase handoff"
    .\.venv\Scripts\python.exe .agent\scripts\generate_agent_handoff.py --question "Need decision on schema migration"
    .\.venv\Scripts\python.exe .agent\scripts\generate_agent_handoff.py --output-md docs/CHECKPOINTS-HANDOFFS/agent-HO-99.md
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HANDOFF_DIR = Path(".agent") / "handoffs"
HANDOFF_PREFIX = "agent-HO-"


def run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def collect_git_snapshot(root: Path) -> dict[str, Any]:
    rc, git_dir, git_err = run(["git", "rev-parse", "--git-dir"], root)
    if rc != 0:
        message = git_err or git_dir or "git repository not found"
        raise SystemExit(f"error: not a git repository at {root}\n{message}")

    _, branch, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    _, status_short, _ = run(["git", "status", "--short"], root)
    _, numstat, _ = run(["git", "diff", "--numstat"], root)
    _, cached_numstat, _ = run(["git", "diff", "--cached", "--numstat"], root)
    _, untracked, _ = run(["git", "ls-files", "--others", "--exclude-standard"], root)
    _, commits, _ = run(["git", "log", "--oneline", "-n", "10"], root)

    changed_files: list[dict[str, Any]] = []
    for block in [numstat, cached_numstat]:
        if not block:
            continue
        for line in block.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            add_s, del_s, path = parts
            add_n = int(add_s) if add_s.isdigit() else 0
            del_n = int(del_s) if del_s.isdigit() else 0
            changed_files.append(
                {
                    "path": path.replace("\\", "/"),
                    "added": add_n,
                    "deleted": del_n,
                }
            )

    untracked_files = [
        p.replace("\\", "/") for p in untracked.splitlines() if p.strip()
    ]

    return {
        "branch": branch or "unknown",
        "status_short": status_short.splitlines() if status_short else [],
        "changed_files": changed_files,
        "untracked_files": untracked_files,
        "recent_commits": commits.splitlines() if commits else [],
    }


def summarize_verification(
    audit: dict[str, Any] | None, verify: dict[str, Any] | None
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "agent_surface_audit": "missing",
        "changed_path_verify": "missing",
        "warnings": [],
    }

    if audit:
        summary["agent_surface_audit"] = audit.get("status", "unknown")
        for item in audit.get("warnings", []):
            summary["warnings"].append(f"agent_surface: {item}")

    if verify:
        summary["changed_path_verify"] = verify.get("status", "unknown")
        for item in verify.get("warnings", []):
            summary["warnings"].append(f"changed_verify: {item}")

    return summary


def next_handoff_stem(base_dir: Path) -> str:
    pattern = re.compile(r"^agent-HO-(\d+)$")
    max_n = 0
    if base_dir.exists():
        for path in base_dir.glob(f"{HANDOFF_PREFIX}*"):
            if path.suffix.lower() not in {".md", ".json"}:
                continue
            match = pattern.match(path.stem)
            if not match:
                continue
            max_n = max(max_n, int(match.group(1)))
    return f"{HANDOFF_PREFIX}{max_n + 1}"


def render_md(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# {payload['title']}")
    lines.append("")
    lines.append(f"Generated: {payload['generated_at_utc']}")
    lines.append("")

    lines.append("## Outcome")
    lines.append(payload["outcome"])
    lines.append("")

    lines.append("## Changes")
    changed = payload["git"].get("changed_files", [])
    if changed:
        for item in changed:
            lines.append(f"- {item['path']} (+{item['added']}/-{item['deleted']})")
    else:
        lines.append("- No tracked file diffs detected.")

    untracked = payload["git"].get("untracked_files", [])
    if untracked:
        lines.append("- Untracked files:")
        for p in untracked:
            lines.append(f"  - {p}")
    lines.append("")

    lines.append("## Verification")
    ver = payload["verification"]
    lines.append(f"- Agent surface audit: {ver['agent_surface_audit']}")
    lines.append(f"- Changed-path verify: {ver['changed_path_verify']}")
    if ver.get("warnings"):
        lines.append("- Warnings:")
        for w in ver["warnings"]:
            lines.append(f"  - {w}")
    lines.append("")

    lines.append("## Risks")
    if payload.get("risks"):
        for risk in payload["risks"]:
            lines.append(f"- {risk}")
    else:
        lines.append("- NA")
    lines.append("")

    lines.append("## Questions")
    if payload.get("questions"):
        for q in payload["questions"]:
            lines.append(f"- {q}")
    else:
        lines.append("- NA")
    lines.append("")

    lines.append("## Next Step")
    lines.append(
        payload.get(
            "next_step",
            "Run changed-path verification and proceed with focused follow-up.",
        )
    )
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="Agent Handoff")
    parser.add_argument(
        "--question",
        action="append",
        default=[],
        help="Blocking question to include in handoff",
    )
    parser.add_argument(
        "--risk",
        action="append",
        default=[],
        help="Known risk to include in handoff",
    )
    parser.add_argument(
        "--next-step",
        default="Review Questions and execute the next scoped change with changed-path verification.",
    )
    parser.add_argument(
        "--output-md",
        default=None,
        help="Markdown output path",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="JSON output path",
    )
    args = parser.parse_args()

    root = Path.cwd()
    audit = read_json_if_exists(
        root / ".agent" / "artifacts" / "agent_surface_audit.json"
    )
    verify = read_json_if_exists(
        root / ".agent" / "artifacts" / "changed_path_verify.json"
    )

    payload: dict[str, Any] = {
        "title": args.title,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": collect_git_snapshot(root),
        "verification": summarize_verification(audit, verify),
        "questions": args.question,
        "risks": args.risk,
        "next_step": args.next_step,
        "outcome": "Handoff generated for continuity with branch state, verification status, and open decisions.",
    }

    handoff_dir = root / HANDOFF_DIR
    handoff_stem = next_handoff_stem(handoff_dir)

    out_json = root / (args.output_json or str(handoff_dir / f"{handoff_stem}.json"))
    out_md = root / args.output_md if args.output_md else None

    out_json.parent.mkdir(parents=True, exist_ok=True)
    if out_md is not None:
        out_md.parent.mkdir(parents=True, exist_ok=True)

    if out_md is not None:
        out_md.write_text(render_md(payload), encoding="utf-8")
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("status: pass")
    print(f"handoff_id: {out_json.stem}")
    print(f"markdown: {out_md if out_md is not None else 'skipped'}")
    print(f"json: {out_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
