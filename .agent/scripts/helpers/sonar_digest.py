#!/usr/bin/env python
"""Generate normalized findings from SonarCloud issues, hotspots, and quality gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SONAR_BASE_URL = "https://sonarcloud.io"
DEFAULT_PROJECT_KEY = "Mad-Labs42_quantmap"
DEFAULT_ORGANIZATION = "mad-labs42"
VALID_SEVERITIES = {"BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"}


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


def sonar_get(path: str, token: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode(params)
    url = f"{SONAR_BASE_URL}{path}?{query}"
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "quantmap-agent",
        },
        method="GET",
    )
    with urlopen(req, timeout=20) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    severity = str(issue.get("severity") or "INFO").upper()
    if severity not in VALID_SEVERITIES:
        severity = "INFO"

    component = str(issue.get("component") or "")
    file_path = component.split(":", 1)[1] if ":" in component else (component or "(unknown)")
    line = (issue.get("textRange") or {}).get("startLine")
    rule = str(issue.get("rule") or "sonar.issue")
    message = " ".join(str(issue.get("message") or "").split())[:300]
    symbol = (issue.get("textRange") or {}).get("hash")
    source_url = issue.get("url")

    today = today_ymd()
    return {
        "id": finding_id("sonarcloud", rule, file_path, message, str(symbol) if symbol else None),
        "rule": rule,
        "tool_severity": severity,
        "file": file_path,
        "line": line if isinstance(line, int) else None,
        "symbol_if_extractable": str(symbol) if symbol else None,
        "message": message or "(empty sonar issue message)",
        "remediation_hint_if_available": None,
        "source_url_if_available": source_url,
        "first_seen": today,
        "last_seen": today,
    }


def normalize_hotspot(hotspot: dict[str, Any]) -> dict[str, Any]:
    # Hotspots do not carry Sonar issue severities directly; use MAJOR as conservative default.
    severity = "MAJOR"
    component = str(hotspot.get("component") or "")
    file_path = component.split(":", 1)[1] if ":" in component else (component or "(unknown)")
    line = hotspot.get("line")
    rule = str(hotspot.get("ruleKey") or "sonar.hotspot")
    probability = str(hotspot.get("vulnerabilityProbability") or "")
    status = str(hotspot.get("status") or "")
    message = f"Hotspot status={status or 'UNKNOWN'} probability={probability or 'UNKNOWN'}"
    symbol = hotspot.get("key")
    source_url = hotspot.get("url")

    today = today_ymd()
    return {
        "id": finding_id("sonarcloud", rule, file_path, message, str(symbol) if symbol else None),
        "rule": rule,
        "tool_severity": severity,
        "file": file_path,
        "line": line if isinstance(line, int) else None,
        "symbol_if_extractable": str(symbol) if symbol else None,
        "message": message,
        "remediation_hint_if_available": None,
        "source_url_if_available": source_url,
        "first_seen": today,
        "last_seen": today,
    }


def normalize_quality_gate(gate: dict[str, Any], project_key: str) -> dict[str, Any]:
    project_status = gate.get("projectStatus") if isinstance(gate, dict) else {}
    status = str((project_status or {}).get("status") or "UNKNOWN")
    severity = "CRITICAL" if status == "ERROR" else "MINOR"
    message = f"Quality gate status: {status}"
    today = today_ymd()
    return {
        "id": finding_id("sonarcloud", "sonar.quality_gate", "(quality-gate)", message, project_key),
        "rule": "sonar.quality_gate",
        "tool_severity": severity,
        "file": "(quality-gate)",
        "line": None,
        "symbol_if_extractable": project_key,
        "message": message,
        "remediation_hint_if_available": None,
        "source_url_if_available": f"{SONAR_BASE_URL}/summary/new_code?id={project_key}",
        "first_seen": today,
        "last_seen": today,
    }


def build_json_document(
    status: str,
    project_key: str,
    organization: str,
    max_findings: int,
    findings: list[dict[str, Any]],
    note: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": status,
        "generated_at": utc_now_iso(),
        "project_key": project_key,
        "organization": organization,
        "max_findings": max_findings,
        "tools": [
            {
                "name": "sonarcloud",
                "tool_version_if_known": None,
                "findings": findings,
            }
        ],
    }
    if note:
        out["note"] = note
    return out


def print_plain(doc: dict[str, Any]) -> None:
    print(f"status: {doc['status']}")
    print(f"project_key: {doc['project_key']}")
    print(f"organization: {doc['organization']}")
    print(f"sonarcloud: {len(doc['tools'][0]['findings'])} findings")
    if doc.get("note"):
        print(f"note: {doc['note']}")


def emit_no_data(status: str, project_key: str, organization: str, max_findings: int, note: str, as_json: bool) -> int:
    doc = build_json_document(status, project_key, organization, max_findings, [], note=note)
    if as_json:
        print(json.dumps(doc, indent=2))
    else:
        print_plain(doc)
        print(f"error: {note}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Digest SonarCloud issues, hotspots, and quality gate status.")
    parser.add_argument("--project-key", default=DEFAULT_PROJECT_KEY, help="Sonar project key.")
    parser.add_argument("--organization", default=DEFAULT_ORGANIZATION, help="Sonar organization key.")
    parser.add_argument("--json", action="store_true", help="Emit single-document JSON output.")
    parser.add_argument("--max-findings", type=int, default=500, help="Maximum findings to include.")
    args = parser.parse_args()

    token = os.environ.get("SONAR_TOKEN")
    if not token:
        return emit_no_data(
            "auth_missing",
            args.project_key,
            args.organization,
            max(1, args.max_findings),
            "SONAR_TOKEN environment variable is not set.",
            args.json,
        )

    max_findings = max(1, args.max_findings)

    try:
        issues_payload = sonar_get(
            "/api/issues/search",
            token,
            {
                "organization": args.organization,
                "componentKeys": args.project_key,
                "resolved": "false",
                "ps": min(500, max_findings),
                "p": 1,
            },
        )
        hotspots_payload = sonar_get(
            "/api/hotspots/search",
            token,
            {
                "organization": args.organization,
                "projectKey": args.project_key,
                "status": "TO_REVIEW,REVIEWED",
                "ps": min(500, max_findings),
                "p": 1,
            },
        )
        gate_payload = sonar_get(
            "/api/qualitygates/project_status",
            token,
            {
                "organization": args.organization,
                "projectKey": args.project_key,
            },
        )

        findings: list[dict[str, Any]] = []

        for issue in (issues_payload.get("issues") or []):
            if len(findings) >= max_findings:
                break
            if isinstance(issue, dict):
                findings.append(normalize_issue(issue))

        for hotspot in (hotspots_payload.get("hotspots") or []):
            if len(findings) >= max_findings:
                break
            if isinstance(hotspot, dict):
                findings.append(normalize_hotspot(hotspot))

        if len(findings) < max_findings:
            findings.append(normalize_quality_gate(gate_payload, args.project_key))

        status = "ok" if findings else "no_data"
        doc = build_json_document(status, args.project_key, args.organization, max_findings, findings)

        if args.json:
            print(json.dumps(doc, indent=2))
        else:
            print_plain(doc)

        return 0

    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in {401, 403}:
            return emit_no_data(
                "auth_missing",
                args.project_key,
                args.organization,
                max_findings,
                f"SonarCloud authentication failed (HTTP {exc.code}).",
                args.json,
            )
        if exc.code == 429:
            return emit_no_data(
                "no_data",
                args.project_key,
                args.organization,
                max_findings,
                "SonarCloud rate limit encountered (HTTP 429).",
                args.json,
            )
        return emit_no_data(
            "no_data",
            args.project_key,
            args.organization,
            max_findings,
            f"SonarCloud HTTP error {exc.code}: {body[:200]}",
            args.json,
        )
    except URLError as exc:
        return emit_no_data(
            "no_data",
            args.project_key,
            args.organization,
            max_findings,
            f"SonarCloud network error: {exc.reason}",
            args.json,
        )
    except json.JSONDecodeError as exc:
        return emit_no_data(
            "no_data",
            args.project_key,
            args.organization,
            max_findings,
            f"SonarCloud response parse failure: {exc}",
            args.json,
        )
    except Exception as exc:
        return emit_no_data(
            "no_data",
            args.project_key,
            args.organization,
            max_findings,
            f"SonarCloud digest failure: {exc}",
            args.json,
        )


if __name__ == "__main__":
    raise SystemExit(main())
