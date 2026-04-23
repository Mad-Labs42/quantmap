#!/usr/bin/env python
"""Generate normalized findings from pip-audit vulnerability output."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


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


def normalize_severity(value: str | None) -> str:
    sev = (value or "unknown").strip().lower()
    if sev in {"critical", "high", "medium", "low", "unknown"}:
        return sev
    return "unknown"


def extract_cve_severity(vuln: dict[str, Any]) -> str:
    # Best-effort extraction from common pip-audit advisory payload shapes.
    severity = vuln.get("severity")
    if isinstance(severity, str):
        return normalize_severity(severity)

    aliases = vuln.get("aliases")
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, dict):
                level = alias.get("severity")
                if isinstance(level, str):
                    return normalize_severity(level)

    via = vuln.get("via")
    if isinstance(via, list):
        for item in via:
            if isinstance(item, dict):
                level = item.get("severity") or item.get("cvss_severity")
                if isinstance(level, str):
                    return normalize_severity(level)

    return "unknown"


def normalize_vuln(dep_name: str, dep_version: str, vuln: dict[str, Any]) -> dict[str, Any]:
    vuln_id = str(vuln.get("id") or "unknown-vuln")
    fix_versions = vuln.get("fix_versions") if isinstance(vuln.get("fix_versions"), list) else []
    fix_hint = ", ".join(str(v) for v in fix_versions) if fix_versions else None
    description = str(vuln.get("description") or "")
    severity = extract_cve_severity(vuln)

    message = f"{dep_name} {dep_version}: {vuln_id}"
    if description:
        message = f"{message} - {' '.join(description.split())[:200]}"

    today = today_ymd()
    symbol = vuln_id
    return {
        "id": finding_id("pip-audit", vuln_id, dep_name, message, symbol),
        "rule": vuln_id,
        "tool_severity": severity,
        "file": dep_name,
        "line": None,
        "symbol_if_extractable": symbol,
        "message": message,
        "remediation_hint_if_available": fix_hint,
        "source_url_if_available": None,
        "first_seen": today,
        "last_seen": today,
    }


def parse_pip_audit_json(payload_text: str, max_findings: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    payload = json.loads(payload_text)

    deps: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("dependencies"), list):
            deps = [d for d in payload["dependencies"] if isinstance(d, dict)]
        elif isinstance(payload.get("results"), list):
            deps = [d for d in payload["results"] if isinstance(d, dict)]
    elif isinstance(payload, list):
        deps = [d for d in payload if isinstance(d, dict)]

    for dep in deps:
        name = str(dep.get("name") or dep.get("package") or "(unknown-package)")
        version = str(dep.get("version") or dep.get("installed_version") or "unknown")
        vulns = dep.get("vulns") if isinstance(dep.get("vulns"), list) else []
        for vuln in vulns:
            if len(findings) >= max_findings:
                return findings
            if isinstance(vuln, dict):
                findings.append(normalize_vuln(name, version, vuln))

    return findings


def build_doc(status: str, requirements: str | None, max_findings: int, findings: list[dict[str, Any]], note: str | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "status": status,
        "generated_at": utc_now_iso(),
        "requirements": requirements,
        "max_findings": max_findings,
        "tools": [
            {
                "name": "pip-audit",
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
    print(f"requirements: {doc.get('requirements')}")
    print(f"pip-audit: {len(doc['tools'][0]['findings'])} findings")
    if doc.get("note"):
        print(f"note: {doc['note']}")


def read_stdin_if_piped() -> str | None:
    if sys.stdin.isatty():
        return None
    data = sys.stdin.read()
    return data if data.strip() else None


def run_pip_audit(requirements: str | None) -> tuple[int, str, str] | tuple[None, str, str]:
    cmd = ["pip-audit", "--format", "json"]
    if requirements:
        cmd.extend(["-r", requirements])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return None, "", "pip-audit executable not found"
    except Exception as exc:
        return None, "", str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Digest pip-audit vulnerability output.")
    parser.add_argument("--requirements", help="Optional requirements file path to pass to pip-audit.")
    parser.add_argument("--json", action="store_true", help="Emit single-document JSON output.")
    parser.add_argument("--max-findings", type=int, default=500, help="Maximum findings to include.")
    args = parser.parse_args()

    max_findings = max(1, args.max_findings)

    stdin_payload = read_stdin_if_piped()
    if stdin_payload is not None:
        try:
            findings = parse_pip_audit_json(stdin_payload, max_findings)
            status = "ok" if findings else "no_data"
            emit(build_doc(status, args.requirements, max_findings, findings), args.json)
            return 0
        except Exception as exc:
            emit(
                build_doc("tool_unavailable", args.requirements, max_findings, [], note=f"Failed to parse pip-audit stdin JSON: {exc}"),
                args.json,
            )
            return 0

    rc, stdout, stderr = run_pip_audit(args.requirements)
    if rc is None:
        emit(
            build_doc("tool_missing", args.requirements, max_findings, [], note="pip-audit is not installed or unavailable."),
            args.json,
        )
        return 0

    try:
        findings = parse_pip_audit_json(stdout, max_findings)
    except Exception as exc:
        note = f"pip-audit output could not be parsed: {exc}"
        emit(build_doc("tool_unavailable", args.requirements, max_findings, [], note=note), args.json)
        return 0

    if rc not in {0, 1}:
        note = (stderr or stdout or "pip-audit returned an unexpected non-zero exit code").strip()[:300]
        emit(build_doc("tool_unavailable", args.requirements, max_findings, [], note=note), args.json)
        return 0

    status = "ok" if findings else "no_data"
    emit(build_doc(status, args.requirements, max_findings, findings), args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
