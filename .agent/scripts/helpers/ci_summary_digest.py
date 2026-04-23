#!/usr/bin/env python
"""Generate normalized findings from GitHub Actions CI runs."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen

from _gh_client import (
    GitHubAPIError,
    GitHubAuthError,
    GitHubRateLimitError,
    get_github_api,
    resolve_github_token,
)

ADVISORY_STEP_MARKERS = [
    "ruff",
    "compileall",
    "python syntax check",
    "pytest",
]


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


def branch_from_pr(owner: str, repo: str, pr_number: int) -> str:
    pr = get_github_api(f"/repos/{owner}/{repo}/pulls/{pr_number}")
    if not isinstance(pr, dict):
        raise GitHubAPIError("unexpected PR payload")
    head_ref = ((pr.get("head") or {}).get("ref") or "").strip()
    if not head_ref:
        raise GitHubAPIError("could not resolve PR head branch")
    return head_ref


def select_run(owner: str, repo: str, run_id: int | None, branch: str | None) -> dict[str, Any]:
    if run_id is not None:
        run = get_github_api(f"/repos/{owner}/{repo}/actions/runs/{run_id}")
        if not isinstance(run, dict):
            raise GitHubAPIError("unexpected run payload")
        return run

    if not branch:
        raise ValueError("one selector is required: --run-id, --branch, or --pr")

    payload = get_github_api(f"/repos/{owner}/{repo}/actions/runs?branch={branch}&per_page=20")
    runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
    if not runs:
        raise GitHubAPIError(f"no workflow runs found for branch '{branch}'")
    return runs[0]


def list_jobs(owner: str, repo: str, run_id: int) -> list[dict[str, Any]]:
    payload = get_github_api(f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100")
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs", [])
    return jobs if isinstance(jobs, list) else []


def download_log_tail(owner: str, repo: str, run_id: int, tail_lines: int) -> str:
    token = resolve_github_token()
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
    req = Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "quantmap-agent",
        },
        method="GET",
    )
    with urlopen(req, timeout=20) as response:
        data = response.read()

    collected: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if not name.endswith(".txt"):
                continue
            text = zf.read(name).decode("utf-8", errors="replace")
            lines = text.splitlines()
            collected.extend(lines[-max(1, tail_lines):])

    return "\n".join(collected[-max(1, tail_lines):])


def advisory_step_name(step_name: str) -> bool:
    n = step_name.lower()
    return any(marker in n for marker in ADVISORY_STEP_MARKERS)


def normalize_log_lines(text: str) -> list[str]:
    findings: list[str] = []
    pattern = re.compile(r"(F\d{3}|E\d{3}|error|failed|traceback|warning)", re.IGNORECASE)
    for raw in text.splitlines():
        line = " ".join(raw.strip().split())
        if not line:
            continue
        if pattern.search(line):
            findings.append(line[:280])
    return findings


def make_finding(rule: str, severity: str, message: str, source_url: str | None = None) -> dict[str, Any]:
    tool_name = "github-actions-ci"
    file_path = "(ci-workflow)"
    symbol = None
    today = today_ymd()
    msg = " ".join(message.split())[:300]
    return {
        "id": finding_id(tool_name, rule, file_path, msg, symbol),
        "rule": rule,
        "tool_severity": severity,
        "file": file_path,
        "line": None,
        "symbol_if_extractable": symbol,
        "message": msg,
        "remediation_hint_if_available": None,
        "source_url_if_available": source_url,
        "first_seen": today,
        "last_seen": today,
    }


def build_json_document(repo: str, selector: dict[str, Any], run: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    status = "ok" if findings else "no_data"
    return {
        "status": status,
        "generated_at": utc_now_iso(),
        "repo": repo,
        "selector": selector,
        "run_id": run.get("id"),
        "run_html_url": run.get("html_url"),
        "tools": [
            {
                "name": "github-actions-ci",
                "tool_version_if_known": None,
                "findings": findings,
            }
        ],
    }


def print_plain(doc: dict[str, Any]) -> None:
    print(f"status: {doc['status']}")
    print(f"repo: {doc['repo']}")
    print(f"run_id: {doc.get('run_id')}")
    print(f"github-actions-ci: {len(doc['tools'][0]['findings'])} findings")


def main() -> int:
    parser = argparse.ArgumentParser(description="Digest GitHub Actions CI failures and advisory outputs.")
    parser.add_argument("--repo", required=True, help="Repository in OWNER/REPO format.")
    parser.add_argument("--pr", type=int, help="PR number selector.")
    parser.add_argument("--branch", help="Branch selector.")
    parser.add_argument("--run-id", type=int, help="Run ID selector.")
    parser.add_argument("--json", action="store_true", help="Emit single-document JSON output.")
    parser.add_argument("--log-tail-lines", type=int, default=80, help="Tail lines to parse from run logs.")
    args = parser.parse_args()

    selectors = [args.pr is not None, args.branch is not None, args.run_id is not None]
    if sum(selectors) == 0:
        print("error: provide one selector: --pr, --branch, or --run-id", file=sys.stderr)
        return 2

    try:
        owner, repo_name = parse_repo(args.repo)

        selected_branch = args.branch
        if args.pr is not None:
            selected_branch = branch_from_pr(owner, repo_name, args.pr)

        run = select_run(owner, repo_name, args.run_id, selected_branch)
        run_id = int(run["id"])
        jobs = list_jobs(owner, repo_name, run_id)

        findings: list[dict[str, Any]] = []
        for job in jobs:
            job_name = job.get("name") or "(unknown job)"
            for step in job.get("steps") or []:
                step_name = step.get("name") or "(unknown step)"
                outcome = (step.get("outcome") or "").lower()
                conclusion = (step.get("conclusion") or "").lower()
                is_advisory = advisory_step_name(step_name)

                if conclusion == "failure":
                    findings.append(
                        make_finding(
                            rule="gha.step.failed",
                            severity="failure",
                            message=f"Job '{job_name}' step '{step_name}' failed.",
                            source_url=run.get("html_url"),
                        )
                    )
                elif is_advisory and outcome == "failure" and conclusion in {"success", "neutral"}:
                    findings.append(
                        make_finding(
                            rule="gha.advisory.step.outcome_failure",
                            severity="advisory",
                            message=(
                                f"Advisory step '{step_name}' in job '{job_name}' reported failure output "
                                "under continue-on-error."
                            ),
                            source_url=run.get("html_url"),
                        )
                    )

        # Additional advisory evidence from log tail.
        log_tail = download_log_tail(owner, repo_name, run_id, max(1, args.log_tail_lines))
        for line in normalize_log_lines(log_tail)[:20]:
            findings.append(
                make_finding(
                    rule="gha.advisory.log.signal",
                    severity="advisory",
                    message=f"CI log tail signal: {line}",
                    source_url=run.get("html_url"),
                )
            )

        selector = {"pr": args.pr, "branch": selected_branch, "run_id": args.run_id}
        doc = build_json_document(args.repo, selector, run, findings)

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
