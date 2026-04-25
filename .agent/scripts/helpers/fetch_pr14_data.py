"""Fetch PR #14 inline comments and CodeQL alerts for analysis."""
import json
import subprocess
import sys


def run_gh(args):
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout, result.stderr, result.returncode


def main():
    # Inline review comments
    stdout, stderr, rc = run_gh([
        "api", "repos/Mad-Labs42/quantmap/pulls/14/comments",
        "--paginate",
    ])
    if rc != 0:
        print(f"Error fetching comments: {stderr}", file=sys.stderr)
        return

    comments = json.loads(stdout)
    print(f"=== INLINE COMMENTS ({len(comments)}) ===")
    for c in comments:
        path = c.get("path", "?")
        line = c.get("line", c.get("original_line", "?"))
        body = c.get("body", "")
        print(f"\n--- {path}:{line} ---")
        print(body[:800])

    # CodeQL alerts
    print("\n\n=== CODEQL ALERTS ===")
    stdout2, stderr2, rc2 = run_gh([
        "api", "repos/Mad-Labs42/quantmap/code-scanning/alerts",
        "--field", "ref=refs/pull/14/head",
        "--paginate",
    ])
    if rc2 != 0:
        print(f"Error fetching CodeQL alerts: {stderr2}")
        # Try without field
        stdout2, stderr2, rc2 = run_gh([
            "api", "repos/Mad-Labs42/quantmap/code-scanning/alerts",
        ])
        if rc2 != 0:
            print(f"Still failing: {stderr2}")
            return

    alerts = json.loads(stdout2)
    print(f"Total alerts: {len(alerts)}")
    for a in alerts:
        rule = a.get("rule", {})
        loc = a.get("most_recent_instance", {}).get("location", {})
        print(f"\n[{a.get('state')}] {rule.get('id')} - {rule.get('description')}")
        print(f"  Severity: {rule.get('severity')} / {a.get('rule', {}).get('security_severity_level', 'N/A')}")
        print(f"  File: {loc.get('path')}:{loc.get('start_line')}")
        print(f"  Message: {a.get('most_recent_instance', {}).get('message', {}).get('text', '')[:300]}")


if __name__ == "__main__":
    main()
