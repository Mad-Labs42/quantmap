#!/usr/bin/env python
"""Generate normalized findings from GitHub CodeQL code-scanning alerts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from typing import Any

from _gh_client import GitHubAPIError, GitHubAuthError, GitHubRateLimitError, get_github_api

DEFAULT_REPO = "Mad-Labs42/quantmap"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_ymd() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_repo(repo: str) -> tuple[str, str]:
    if "/" not in repo:
        raise ValueError("--repo must be in OWNER/REPO format")
    owner, name = repo.split("/", 1)
    if not owner or not name:
        raise ValueError("--repo must be in OWNER/REPO format")
    return owner, name


def finding_id(tool_name: str, rule: str, file_path: str, message: str, symbol: str | None) -> str:
    canonical_tuple_json = json.dumps(
        [tool_name, rule, file_path, message, symbol or ""],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical_tuple_json.encode("utf-8")).hexdigest()[:16]
    return f"bg_{digest}"


def fetch_alerts(owner: str, repo: str, state: str, max_findings: int) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    page = 1

    while len(alerts) < max_findings:
        endpoint = (
            f"/repos/{owner}/{repo}/code-scanning/alerts"
            f"?state={state}&per_page=100&page={page}"
        )
        payload = get_github_api(
            endpoint,
            headers={
                "Accept": "application/vnd.github+json",
            },
        )
        if not isinstance(payload, list) or not payload:
            break

        alerts.extend([p for p in payload if isinstance(p, dict)])
        if len(payload) < 100:
            break
        page += 1

    return alerts[:max_findings]


def normalize_alert(alert: dict[str, Any]) -> dict[str, Any]:
    rule = alert.get("rule") if isinstance(alert.get("rule"), dict) else {}
    severity = str(rule.get("severity") or "note").lower()
    if severity not in {"error", "warning", "note"}:
        severity = "note"

    sec_sev = rule.get("security_severity_level")
    most_recent = alert.get("most_recent_instance") if isinstance(alert.get("most_recent_instance"), dict) else {}
    location = most_recent.get("location") if isinstance(most_recent.get("location"), dict) else {}

    file_path = str(location.get("path") or "(unknown)")
    line = location.get("start_line") if isinstance(location.get("start_line"), int) else None
    symbol = str(rule.get("id") or rule.get("name") or "") or None

    message_obj = most_recent.get("message") if isinstance(most_recent.get("message"), dict) else {}
    base_message = str(message_obj.get("text") or alert.get("html_url") or "Code scanning alert")
    base_message = " ".join(base_message.split())[:260]
    if sec_sev:
        message = f"{base_message} (security_severity={sec_sev})"
    else:
        message = base_message

    today = today_ymd()
    return {
        "id": finding_id("codeql", str(rule.get("id") or "codeql.alert"), file_path, message, symbol),
        "rule": str(rule.get("id") or "codeql.alert"),
        "tool_severity": severity,
        "file": file_path,
        "line": line,
        "symbol_if_extractable": symbol,
        "message": message,
        "remediation_hint_if_available": None,
        "source_url_if_available": alert.get("html_url"),
        "first_seen": today,
        "last_seen": today,
        "security_severity_if_available": sec_sev,
    }


def build_json_document(status: str, repo: str, state: str, max_findings: int, findings: list[dict[str, Any]], note: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": status,
        "generated_at": utc_now_iso(),
        "repo": repo,
        "state": state,
        "max_findings": max_findings,
        "tools": [
            {
                "name": "codeql",
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
    print(f"repo: {doc['repo']}")
    print(f"state: {doc['state']}")
    print(f"codeql: {len(doc['tools'][0]['findings'])} findings")
    if doc.get("note"):
        print(f"note: {doc['note']}")


def emit_no_data(status: str, repo: str, state: str, max_findings: int, note: str, as_json: bool) -> int:
    doc = build_json_document(status, repo, state, max_findings, [], note=note)
    if as_json:
        print(json.dumps(doc, indent=2))
    else:
        print_plain(doc)
        print(f"error: {note}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Digest GitHub CodeQL code scanning alerts.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Repository in OWNER/REPO format.")
    parser.add_argument("--state", default="open", help="Alert state selector (default: open).")
    parser.add_argument("--json", action="store_true", help="Emit single-document JSON output.")
    parser.add_argument("--max-findings", type=int, default=500, help="Maximum alerts to include.")
    args = parser.parse_args()

    max_findings = max(1, args.max_findings)

    try:
        owner, repo_name = parse_repo(args.repo)
        alerts = fetch_alerts(owner, repo_name, args.state, max_findings)
        findings = [normalize_alert(a) for a in alerts]
        status = "ok" if findings else "no_data"
        doc = build_json_document(status, args.repo, args.state, max_findings, findings)

        if args.json:
            print(json.dumps(doc, indent=2))
        else:
            print_plain(doc)

        return 0

    except GitHubAuthError as exc:
        return emit_no_data("auth_missing", args.repo, args.state, max_findings, f"GitHub auth failure: {exc}", args.json)
    except GitHubRateLimitError as exc:
        return emit_no_data("no_data", args.repo, args.state, max_findings, f"GitHub rate limit: {exc}", args.json)
    except GitHubAPIError as exc:
        message = str(exc)
        status = "scope_missing" if "Forbidden (403)" in message else "no_data"
        if status == "scope_missing":
            note = "Missing required GitHub scope: code-scanning:read or insufficient repository permission."
        else:
            note = f"GitHub API failure: {message}"
        return emit_no_data(status, args.repo, args.state, max_findings, note, args.json)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        return emit_no_data("no_data", args.repo, args.state, max_findings, f"CodeQL digest failure: {exc}", args.json)


if __name__ == "__main__":
    raise SystemExit(main())
