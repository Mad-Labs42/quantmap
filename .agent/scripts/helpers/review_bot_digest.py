#!/usr/bin/env python
"""Generate normalized findings from CodeRabbit and Copilot PR review comments."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

from _gh_client import GitHubAPIError, GitHubAuthError, GitHubRateLimitError, get_github_api

BOT_TO_TOOL = {
    "coderabbitai[bot]": "coderabbit",
    "github-copilot[bot]": "copilot",
}


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


def normalize_message(text: str) -> str:
    msg = " ".join((text or "").strip().split())
    if not msg:
        return "(empty review comment)"
    return msg[:300]


def extract_symbol(text: str) -> str | None:
    match = re.search(r"`([^`]+)`", text or "")
    return match.group(1) if match else None


def finding_id(tool_name: str, rule: str, file_path: str, message: str, symbol: str | None) -> str:
    canonical_tuple_json = json.dumps(
        [tool_name, rule, file_path, message, symbol or ""],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical_tuple_json.encode("utf-8")).hexdigest()[:16]
    return f"bg_{digest}"


def current_branch() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        branch = result.stdout.strip()
        return branch or None
    except Exception:
        return None


def infer_pr_number(owner: str, repo: str) -> int | None:
    branch = current_branch()
    if not branch:
        return None
    endpoint = f"/repos/{owner}/{repo}/pulls?state=open&head={owner}:{branch}&per_page=1"
    pulls = get_github_api(endpoint)
    if isinstance(pulls, list) and pulls:
        return int(pulls[0]["number"])
    return None


def fetch_review_comments(owner: str, repo: str, pr_number: int, max_comments: int) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    page = 1
    while len(comments) < max_comments:
        endpoint = (
            f"/repos/{owner}/{repo}/pulls/{pr_number}/comments"
            f"?per_page=100&page={page}"
        )
        payload = get_github_api(endpoint)
        if not isinstance(payload, list) or not payload:
            break
        comments.extend(payload)
        if len(payload) < 100:
            break
        page += 1
    return comments[:max_comments]


def normalize_findings(comments: list[dict[str, Any]], open_only: bool) -> dict[str, list[dict[str, Any]]]:
    today = today_ymd()
    out: dict[str, list[dict[str, Any]]] = {"coderabbit": [], "copilot": []}

    for comment in comments:
        login = (comment.get("user") or {}).get("login", "")
        tool_name = BOT_TO_TOOL.get(login)
        if not tool_name:
            continue

        # Best-effort unresolved filter: position=None commonly indicates outdated context.
        if open_only and comment.get("position") is None:
            continue

        file_path = (comment.get("path") or "").strip()
        if not file_path:
            file_path = "(unknown)"
        message = normalize_message(comment.get("body") or "")
        symbol = extract_symbol(comment.get("body") or "")
        rule = f"pr_review_comment:{comment.get('subject_type', 'line')}"
        severity = "open_comment" if comment.get("position") is not None else "outdated_comment"

        finding = {
            "id": finding_id(tool_name, rule, file_path, message, symbol),
            "rule": rule,
            "tool_severity": severity,
            "file": file_path,
            "line": comment.get("line"),
            "symbol_if_extractable": symbol,
            "message": message,
            "remediation_hint_if_available": None,
            "source_url_if_available": comment.get("html_url"),
            "first_seen": today,
            "last_seen": today,
        }
        out[tool_name].append(finding)

    return out


def build_json_document(repo: str, pr_number: int, open_only: bool, max_comments: int, findings: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    has_data = bool(findings["coderabbit"] or findings["copilot"])
    return {
        "status": "ok" if has_data else "no_data",
        "generated_at": utc_now_iso(),
        "repo": repo,
        "pr": pr_number,
        "open_only": open_only,
        "max_comments": max_comments,
        "tools": [
            {
                "name": "coderabbit",
                "tool_version_if_known": None,
                "findings": findings["coderabbit"],
            },
            {
                "name": "copilot",
                "tool_version_if_known": None,
                "findings": findings["copilot"],
            },
        ],
    }


def print_plain(doc: dict[str, Any]) -> None:
    print(f"status: {doc['status']}")
    print(f"repo: {doc['repo']}")
    print(f"pr: {doc['pr']}")
    print(f"open_only: {doc['open_only']}")
    for tool in doc["tools"]:
        print(f"{tool['name']}: {len(tool['findings'])} findings")


def main() -> int:
    parser = argparse.ArgumentParser(description="Digest CodeRabbit and Copilot PR review comments.")
    parser.add_argument("--repo", required=True, help="Repository in OWNER/REPO format.")
    parser.add_argument("--pr", type=int, help="Pull request number (optional; inferred from branch when omitted).")
    parser.add_argument("--json", action="store_true", help="Emit single-document JSON output.")
    parser.add_argument(
        "--open-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include only unresolved/open comments (default: true).",
    )
    parser.add_argument("--max-comments", type=int, default=500, help="Maximum comments to inspect.")
    args = parser.parse_args()

    try:
        owner, repo_name = parse_repo(args.repo)
        pr_number = args.pr if args.pr else infer_pr_number(owner, repo_name)
        if not pr_number:
            print("error: no PR context available; provide --pr NUMBER.", file=sys.stderr)
            return 2

        comments = fetch_review_comments(owner, repo_name, pr_number, max(1, args.max_comments))
        findings = normalize_findings(comments, args.open_only)
        doc = build_json_document(args.repo, pr_number, args.open_only, args.max_comments, findings)

        if args.json:
            print(json.dumps(doc, indent=2))
        else:
            print_plain(doc)

        return 0

    except GitHubAuthError as exc:
        print(f"error: auth failure: {exc}", file=sys.stderr)
        return 2
    except GitHubRateLimitError as exc:
        print(f"error: rate limit: {exc}", file=sys.stderr)
        return 2
    except GitHubAPIError as exc:
        print(f"error: github api: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
