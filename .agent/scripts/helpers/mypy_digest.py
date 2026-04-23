#!/usr/bin/env python
"""Generate normalized findings from mypy output."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

LINE_PATTERN = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?P<severity>error|note):\s*(?P<msg>.*?)(?:\s*\[(?P<code>[^\]]+)\])?$",
    re.IGNORECASE,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_ymd() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def finding_id(tool_name: str, rule: str, file_path: str, message: str, symbol: str | None) -> str:
    canonical_tuple_json = json.dumps(
        [tool_name, rule, file_path, message, symbol or ""],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical_tuple_json.encode("utf-8")).hexdigest()[:16]
    return f"bg_{digest}"


def normalize_line(raw: str) -> dict[str, Any] | None:
    line = raw.strip()
    if not line:
        return None

    match = LINE_PATTERN.match(line)
    if not match:
        return None

    file_path = match.group("file")
    line_num = int(match.group("line"))
    severity = match.group("severity").lower()
    msg = " ".join((match.group("msg") or "").split())[:300]
    rule = match.group("code") or f"mypy.{severity}"

    today = today_ymd()
    return {
        "id": finding_id("mypy", rule, file_path, msg, None),
        "rule": rule,
        "tool_severity": "error" if severity == "error" else "note",
        "file": file_path,
        "line": line_num,
        "symbol_if_extractable": None,
        "message": msg,
        "remediation_hint_if_available": None,
        "source_url_if_available": None,
        "first_seen": today,
        "last_seen": today,
    }


def parse_mypy_output(output: str, max_findings: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for raw in output.splitlines():
        finding = normalize_line(raw)
        if finding is not None:
            findings.append(finding)
            if len(findings) >= max_findings:
                break
    return findings


def build_doc(status: str, paths: list[str], max_findings: int, findings: list[dict[str, Any]], note: str | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "status": status,
        "generated_at": utc_now_iso(),
        "paths": paths,
        "max_findings": max_findings,
        "tools": [
            {
                "name": "mypy",
                "tool_version_if_known": None,
                "findings": findings,
            }
        ],
    }
    if note:
        doc["note"] = note
    return doc


def emit(doc: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(doc, indent=2))
        return
    print(f"status: {doc['status']}")
    print(f"paths: {doc['paths']}")
    print(f"mypy: {len(doc['tools'][0]['findings'])} findings")
    if doc.get("note"):
        print(f"note: {doc['note']}")


def read_stdin_if_piped() -> str | None:
    if sys.stdin.isatty():
        return None
    data = sys.stdin.read()
    return data if data.strip() else None


def run_mypy(paths: list[str]) -> tuple[int | None, str, str]:
    cmd = [
        "mypy",
        "--hide-error-context",
        "--no-color-output",
        "--show-error-codes",
    ]
    if paths:
        cmd.extend(paths)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return None, "", "mypy executable not found"
    except Exception as exc:
        return None, "", str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Digest mypy output into canonical findings schema.")
    parser.add_argument("--paths", nargs="*", default=[], help="Optional paths for mypy; defaults to mypy config behavior when omitted.")
    parser.add_argument("--json", action="store_true", help="Emit single-document JSON output.")
    parser.add_argument("--max-findings", type=int, default=500, help="Maximum findings to include.")
    args = parser.parse_args()

    max_findings = max(1, args.max_findings)

    stdin_payload = read_stdin_if_piped()
    if stdin_payload is not None:
        findings = parse_mypy_output(stdin_payload, max_findings)
        status = "ok" if findings else "no_data"
        emit(build_doc(status, args.paths, max_findings, findings), args.json)
        return 0

    rc, stdout, stderr = run_mypy(args.paths)
    if rc is None:
        emit(build_doc("tool_missing", args.paths, max_findings, [], note="mypy is not installed or unavailable."), args.json)
        return 0

    combined = "\n".join(part for part in [stdout, stderr] if part)
    findings = parse_mypy_output(combined, max_findings)

    if findings:
        emit(build_doc("ok", args.paths, max_findings, findings), args.json)
        return 0

    if rc == 0:
        emit(build_doc("no_data", args.paths, max_findings, []), args.json)
        return 0

    note = (combined or "mypy failed before producing parseable findings").strip()[:300]
    emit(build_doc("no_data", args.paths, max_findings, [], note=note), args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
