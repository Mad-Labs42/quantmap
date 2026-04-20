#!/usr/bin/env python
"""Refresh BUG-GATE-HIT-LIST JSON/MD from digest artifacts or local digest runs."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

HELPERS_DIR = Path(__file__).resolve().parent / "helpers"


def gh_get_github_api(endpoint: str) -> dict[str, Any]:
    if str(HELPERS_DIR) not in sys.path:
        sys.path.insert(0, str(HELPERS_DIR))
    import _gh_client  # type: ignore

    return _gh_client.get_github_api(endpoint)


def gh_resolve_token() -> str:
    if str(HELPERS_DIR) not in sys.path:
        sys.path.insert(0, str(HELPERS_DIR))
    import _gh_client  # type: ignore

    return _gh_client.resolve_github_token()

TOOLS_ORDER = ["coderabbit", "copilot", "github-actions-ci", "sonarcloud", "codeql", "pip-audit", "mypy"]
ARTIFACT_BY_TOOL = {
    "review": "digest-review-bot.json",
    "ci": "digest-ci-summary.json",
    "sonar": "digest-sonar.json",
    "codeql": "digest-codeql.json",
    "pip_audit": "digest-pip-audit.json",
    "mypy": "digest-mypy.json",
}

OUT_JSON = Path("docs/K.I.T.-&-ToDo/BUG-GATE-HIT-LIST.json")
OUT_MD = Path("docs/K.I.T.-&-ToDo/BUG-GATE-HIT-LIST.md")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_ymd() -> str:
    return now_utc().strftime("%Y-%m-%d")


def parse_iso_z(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_repo_from_remote() -> str:
    result = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    url = result.stdout.strip()
    if not url:
        raise ValueError("unable to infer repository from remote.origin.url")

    # Supports git@github.com:owner/repo.git and https://github.com/owner/repo(.git)
    cleaned = url.replace(".git", "")
    if cleaned.startswith("git@github.com:"):
        tail = cleaned.split("git@github.com:", 1)[1]
    elif "github.com/" in cleaned:
        tail = cleaned.split("github.com/", 1)[1]
    else:
        raise ValueError("remote.origin.url is not a GitHub repository URL")

    if "/" not in tail:
        raise ValueError("unable to parse OWNER/REPO from remote URL")
    owner, repo = tail.split("/", 1)
    return f"{owner}/{repo}"


def current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    return result.stdout.strip()


def current_commit_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    return result.stdout.strip()


def download_artifact_json(artifact: dict[str, Any]) -> dict[str, Any]:
    token = gh_resolve_token()
    url = artifact.get("archive_download_url")
    if not url:
        raise RuntimeError("artifact missing archive_download_url")

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

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.endswith(".json"):
                payload = zf.read(name).decode("utf-8")
                return json.loads(payload)

    raise RuntimeError("artifact zip did not contain a .json payload")


def find_fresh_artifacts(repo: str, branch: str) -> tuple[dict[str, dict[str, Any]], int | None]:
    owner, repo_name = repo.split("/", 1)
    payload = gh_get_github_api(f"/repos/{owner}/{repo_name}/actions/runs?branch={branch}&per_page=20")
    runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
    cutoff = now_utc() - timedelta(hours=24)

    for run in runs:
        run_id = run.get("id")
        if run_id is None:
            continue
        artifacts_payload = gh_get_github_api(f"/repos/{owner}/{repo_name}/actions/runs/{run_id}/artifacts?per_page=100")
        artifacts = artifacts_payload.get("artifacts", []) if isinstance(artifacts_payload, dict) else []
        by_name = {a.get("name"): a for a in artifacts if isinstance(a, dict)}

        selected: dict[str, dict[str, Any]] = {}
        fresh_count = 0
        for key, name in ARTIFACT_BY_TOOL.items():
            artifact = by_name.get(name)
            if not artifact:
                continue
            created_at = parse_iso_z(artifact.get("created_at"))
            if created_at and created_at >= cutoff:
                selected[key] = artifact
                fresh_count += 1

        if fresh_count:
            return selected, int(run_id)

    return {}, None


def run_digest_local(command: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except Exception as exc:
        return None, str(exc)

    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "digest failed").strip()

    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError:
        return None, "digest returned non-JSON output"


def tool_findings_from_review(doc: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    out = {"coderabbit": [], "copilot": []}
    if not doc:
        return out
    for tool in doc.get("tools", []):
        name = tool.get("name")
        if name in out:
            out[name] = tool.get("findings", []) or []
    return out


def tool_findings_from_ci(doc: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not doc:
        return []
    for tool in doc.get("tools", []):
        if tool.get("name") == "github-actions-ci":
            return tool.get("findings", []) or []
    return []


def tool_findings_from_named_tool(doc: dict[str, Any] | None, tool_name: str) -> list[dict[str, Any]]:
    if not doc:
        return []
    for tool in doc.get("tools", []):
        if tool.get("name") == tool_name:
            return tool.get("findings", []) or []
    return []


def load_existing_first_seen() -> dict[str, str]:
    if not OUT_JSON.exists():
        return {}
    try:
        existing = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}

    mapping: dict[str, str] = {}
    for tool in existing.get("tools", []):
        for finding in tool.get("findings", []):
            fid = finding.get("id")
            fs = finding.get("first_seen")
            if fid and fs:
                mapping[str(fid)] = str(fs)
    return mapping


def apply_first_seen(findings: list[dict[str, Any]], prior: dict[str, str]) -> None:
    today = today_ymd()
    for finding in findings:
        fid = str(finding.get("id"))
        finding["first_seen"] = prior.get(fid, today)
        finding["last_seen"] = today


def severity_rank(tool_name: str, severity: str) -> int:
    n = (severity or "").lower()
    if tool_name in {"coderabbit", "copilot"}:
        order = ["critical", "high", "medium", "low", "open_comment", "outdated_comment", "info"]
    else:
        order = ["failure", "error", "advisory", "warning", "info"]
    return order.index(n) if n in order else len(order)


def render_md(document: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# BUG-GATE-HIT-LIST")
    lines.append("")
    lines.append("Signal-only advisory list. Canonical source of truth is BUG-GATE-HIT-LIST.json. Refresh is manual.")
    lines.append("")
    lines.append(f"Last refreshed: {document['last_refreshed']}")
    lines.append(f"Refresh source: {document['refresh_source']}")
    lines.append("")

    for tool in document["tools"]:
        name = tool["name"]
        lines.append(f"## {name}")
        lines.append("")
        lines.append("| Severity | Rule | File | Line | Symbol | Message | First Seen | Link |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")

        findings = tool.get("findings", [])
        findings = sorted(
            findings,
            key=lambda f: (
                severity_rank(name, f.get("tool_severity", "")),
                str(f.get("file") or ""),
                f.get("line") if isinstance(f.get("line"), int) else 10**9,
            ),
        )

        if not findings:
            lines.append("| n/a | n/a | n/a | n/a | n/a | no findings | n/a | n/a |")
            lines.append("")
            continue

        for f in findings:
            link = f.get("source_url_if_available") or ""
            lines.append(
                "| {sev} | {rule} | {file} | {line} | {sym} | {msg} | {fs} | {link} |".format(
                    sev=f.get("tool_severity") or "",
                    rule=f.get("rule") or "",
                    file=f.get("file") or "",
                    line=f.get("line") if f.get("line") is not None else "",
                    sym=f.get("symbol_if_extractable") or "",
                    msg=(f.get("message") or "").replace("|", "\\|"),
                    fs=f.get("first_seen") or "",
                    link=link,
                )
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh BUG-GATE-HIT-LIST from digest artifacts or local digests.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prefer-artifacts", action="store_true", help="Prefer fresh CI digest artifacts (default mode).")
    mode.add_argument("--local-only", action="store_true", help="Skip artifact fetch and run local digests only.")
    args = parser.parse_args()

    use_local_only = bool(args.local_only)
    if not use_local_only and not args.prefer_artifacts:
        # default mode
        args.prefer_artifacts = True

    try:
        repo = parse_repo_from_remote()
        branch = current_branch()
        commit_sha = current_commit_sha()
    except Exception as exc:
        print(f"error: unable to resolve local git context: {exc}", file=sys.stderr)
        return 2

    review_doc: dict[str, Any] | None = None
    ci_doc: dict[str, Any] | None = None
    sonar_doc: dict[str, Any] | None = None
    codeql_doc: dict[str, Any] | None = None
    pip_audit_doc: dict[str, Any] | None = None
    mypy_doc: dict[str, Any] | None = None
    artifact_run_id: int | None = None
    local_fallback_used = False
    used_artifact_review = False
    used_artifact_ci = False
    used_artifact_sonar = False
    used_artifact_codeql = False
    used_artifact_pip_audit = False
    used_artifact_mypy = False

    if not use_local_only:
        try:
            artifacts, artifact_run_id = find_fresh_artifacts(repo, branch)
            if "review" in artifacts:
                review_doc = download_artifact_json(artifacts["review"])
                used_artifact_review = True
            if "ci" in artifacts:
                ci_doc = download_artifact_json(artifacts["ci"])
                used_artifact_ci = True
            if "sonar" in artifacts:
                sonar_doc = download_artifact_json(artifacts["sonar"])
                used_artifact_sonar = True
            if "codeql" in artifacts:
                codeql_doc = download_artifact_json(artifacts["codeql"])
                used_artifact_codeql = True
            if "pip_audit" in artifacts:
                pip_audit_doc = download_artifact_json(artifacts["pip_audit"])
                used_artifact_pip_audit = True
            if "mypy" in artifacts:
                mypy_doc = download_artifact_json(artifacts["mypy"])
                used_artifact_mypy = True
        except Exception as exc:
            print(f"warn: artifact lookup failed, falling back to local digests: {exc}", file=sys.stderr)
            local_fallback_used = True

    if use_local_only or review_doc is None:
        local_fallback_used = True
        review_cmd = [
            sys.executable,
            str(HELPERS_DIR / "review_bot_digest.py"),
            "--repo",
            repo,
            "--json",
        ]
        review_doc, review_err = run_digest_local(review_cmd)
        if review_doc is None:
            print(f"warn: review digest local run failed: {review_err}", file=sys.stderr)
            review_doc = {"status": "no_data", "tools": [{"name": "coderabbit", "findings": []}, {"name": "copilot", "findings": []}]}

    if use_local_only or ci_doc is None:
        local_fallback_used = True
        ci_cmd = [
            sys.executable,
            str(HELPERS_DIR / "ci_summary_digest.py"),
            "--repo",
            repo,
            "--branch",
            branch,
            "--json",
        ]
        ci_doc, ci_err = run_digest_local(ci_cmd)
        if ci_doc is None:
            print(f"warn: ci digest local run failed: {ci_err}", file=sys.stderr)
            ci_doc = {"status": "no_data", "tools": [{"name": "github-actions-ci", "findings": []}]}

    if use_local_only or sonar_doc is None:
        local_fallback_used = True
        sonar_cmd = [
            sys.executable,
            str(HELPERS_DIR / "sonar_digest.py"),
            "--json",
        ]
        sonar_doc, sonar_err = run_digest_local(sonar_cmd)
        if sonar_doc is None:
            print(f"warn: sonar digest local run failed: {sonar_err}", file=sys.stderr)
            sonar_doc = {"status": "no_data", "tools": [{"name": "sonarcloud", "findings": []}]}

    if use_local_only or codeql_doc is None:
        local_fallback_used = True
        codeql_cmd = [
            sys.executable,
            str(HELPERS_DIR / "codeql_digest.py"),
            "--repo",
            repo,
            "--json",
        ]
        codeql_doc, codeql_err = run_digest_local(codeql_cmd)
        if codeql_doc is None:
            print(f"warn: codeql digest local run failed: {codeql_err}", file=sys.stderr)
            codeql_doc = {"status": "no_data", "tools": [{"name": "codeql", "findings": []}]}

    if use_local_only or pip_audit_doc is None:
        local_fallback_used = True
        pip_audit_cmd = [
            sys.executable,
            str(HELPERS_DIR / "pip_audit_digest.py"),
            "--json",
        ]
        pip_audit_doc, pip_audit_err = run_digest_local(pip_audit_cmd)
        if pip_audit_doc is None:
            print(f"warn: pip-audit digest local run failed: {pip_audit_err}", file=sys.stderr)
            pip_audit_doc = {"status": "no_data", "tools": [{"name": "pip-audit", "findings": []}]}

    if use_local_only or mypy_doc is None:
        local_fallback_used = True
        mypy_cmd = [
            sys.executable,
            str(HELPERS_DIR / "mypy_digest.py"),
            "--json",
        ]
        mypy_doc, mypy_err = run_digest_local(mypy_cmd)
        if mypy_doc is None:
            print(f"warn: mypy digest local run failed: {mypy_err}", file=sys.stderr)
            mypy_doc = {"status": "no_data", "tools": [{"name": "mypy", "findings": []}]}

    review_findings = tool_findings_from_review(review_doc)
    ci_findings = tool_findings_from_ci(ci_doc)
    sonar_findings = tool_findings_from_named_tool(sonar_doc, "sonarcloud")
    codeql_findings = tool_findings_from_named_tool(codeql_doc, "codeql")
    pip_audit_findings = tool_findings_from_named_tool(pip_audit_doc, "pip-audit")
    mypy_findings = tool_findings_from_named_tool(mypy_doc, "mypy")

    prior_first_seen = load_existing_first_seen()
    apply_first_seen(review_findings["coderabbit"], prior_first_seen)
    apply_first_seen(review_findings["copilot"], prior_first_seen)
    apply_first_seen(ci_findings, prior_first_seen)
    apply_first_seen(sonar_findings, prior_first_seen)
    apply_first_seen(codeql_findings, prior_first_seen)
    apply_first_seen(pip_audit_findings, prior_first_seen)
    apply_first_seen(mypy_findings, prior_first_seen)

    if all([
        used_artifact_review,
        used_artifact_ci,
        used_artifact_sonar,
        used_artifact_codeql,
        used_artifact_pip_audit,
        used_artifact_mypy,
    ]) and not local_fallback_used:
        refresh_source = "ci-artifacts"
    elif local_fallback_used and any([
        used_artifact_review,
        used_artifact_ci,
        used_artifact_sonar,
        used_artifact_codeql,
        used_artifact_pip_audit,
        used_artifact_mypy,
    ]):
        refresh_source = "mixed"
    else:
        refresh_source = "local-run"

    document = {
        "schema_version": "1.0.0",
        "last_refreshed": now_iso(),
        "refresh_source": refresh_source,
        "refresh_context": {
            "repo": repo,
            "branch": branch,
            "commit_sha": commit_sha,
            "artifact_run_id": artifact_run_id,
            "local_fallback_used": bool(local_fallback_used),
        },
        "tools": [
            {
                "name": "coderabbit",
                "tool_version_if_known": None,
                "findings": review_findings["coderabbit"],
            },
            {
                "name": "copilot",
                "tool_version_if_known": None,
                "findings": review_findings["copilot"],
            },
            {
                "name": "github-actions-ci",
                "tool_version_if_known": None,
                "findings": ci_findings,
            },
            {
                "name": "sonarcloud",
                "tool_version_if_known": None,
                "findings": sonar_findings,
            },
            {
                "name": "codeql",
                "tool_version_if_known": None,
                "findings": codeql_findings,
            },
            {
                "name": "pip-audit",
                "tool_version_if_known": None,
                "findings": pip_audit_findings,
            },
            {
                "name": "mypy",
                "tool_version_if_known": None,
                "findings": mypy_findings,
            },
        ],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(document, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_md(document), encoding="utf-8")

    print(f"refresh_source: {refresh_source}")
    print(f"coderabbit findings: {len(review_findings['coderabbit'])}")
    print(f"copilot findings: {len(review_findings['copilot'])}")
    print(f"github-actions-ci findings: {len(ci_findings)}")
    print(f"sonarcloud findings: {len(sonar_findings)}")
    print(f"codeql findings: {len(codeql_findings)}")
    print(f"pip-audit findings: {len(pip_audit_findings)}")
    print(f"mypy findings: {len(mypy_findings)}")
    print(f"wrote: {OUT_JSON}")
    print(f"wrote: {OUT_MD}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
