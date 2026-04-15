"""QuantMap — audit_methodology.py

Utility to verify methodological integrity between two campaigns.
Checks that both campaigns were scored using identical anchors and Registry versions.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

# Ensure src is in path
sys.path.append(str(Path(__file__).parent.parent))

from src import ui
from src.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("audit")
console = ui.get_console()

def get_methodology(campaign_id: str, db_path: Path) -> dict[str, Any] | None:
    from src.trust_identity import load_run_identity

    with get_connection(db_path) as conn:
        row = conn.execute("SELECT id FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if not row:
            logger.error("Campaign not found: %s", campaign_id)
            return None

    identity = load_run_identity(campaign_id, db_path)
    methodology = identity.methodology
    if methodology.get("source") == "unknown":
        return None
    return {
        "version": methodology.get("version"),
        "references": methodology.get("anchors", {}),
        "methodology_snapshot_id": methodology.get("id"),
        "capture_quality": methodology.get("capture_quality"),
        "capture_source": methodology.get("capture_source"),
    }

def compare_methodologies(id1: str, m1: dict, id2: str, m2: dict) -> bool:
    ui.print_banner(f"Methodology Audit: {id1} vs {id2}")

    v1 = m1.get("version", "unknown")
    v2 = m2.get("version", "unknown")

    if v1 != v2:
        console.print(f"[bold red]{ui.SYM_FAIL} Methodology version mismatch:[/bold red] {id1} (v{v1}) vs {id2} (v{v2})")
    else:
        console.print(f"[bold green]{ui.SYM_OK} Methodology version:[/bold green] v{v1}")

    refs1 = m1.get("references", {})
    refs2 = m2.get("references", {})

    all_metrics = sorted(set(refs1.keys()) | set(refs2.keys()))
    mismatches = 0

    from rich.table import Table
    table = Table(box=None if ui.USE_ASCII else None)
    table.add_column("Metric", style="cyan")
    table.add_column("Anchor 1", justify="right")
    table.add_column("Anchor 2", justify="right")
    table.add_column("Status", justify="left")

    for m in all_metrics:
        r1 = refs1.get(m, {})
        r2 = refs2.get(m, {})

        v1 = r1.get("value")
        v2 = r2.get("value")
        s1 = r1.get("source")
        s2 = r2.get("source")

        status_label = ui.SYM_OK
        status_style = "green"
        if v1 != v2:
            status_label = f"VALUE DRIFT {ui.SYM_WARN}"
            status_style = "yellow"
            mismatches += 1
        elif s1 != s2:
            status_label = "SOURCE DELTA"
            status_style = "yellow"
            mismatches += 1

        v1_str = f"{v1:.2f}" if v1 is not None else "N/A"
        v2_str = f"{v2:.2f}" if v2 is not None else "N/A"

        table.add_row(m, v1_str, v2_str, f"[{status_style}]{status_label}[/{status_style}]")

    console.print()
    console.print(table)

    if mismatches == 0:
        console.print(f"\n[bold green]{ui.SYM_OK} Methodological Integrity Verified.[/bold green] Campaigns are safe to compare.\n")
        return True
    else:
        console.print(f"\n[bold red]{ui.SYM_FAIL} {mismatches} methodological differences detected.[/bold red] Direct comparison may be invalid.\n")
        return False

def main():
    parser = argparse.ArgumentParser(description="Audit methodological integrity between two campaigns.")
    parser.add_argument("campaign1", help="First Campaign ID")
    parser.add_argument("campaign2", help="Second Campaign ID")
    parser.add_argument("--db", type=Path, help="Path to lab.sqlite (optional)")
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        from src.config import LAB_ROOT

        db_path = LAB_ROOT / "db" / "lab.sqlite"

    m1 = get_methodology(args.campaign1, db_path)
    m2 = get_methodology(args.campaign2, db_path)

    if not m1:
        console.print(f"[bold red]{ui.SYM_FAIL} Error:[/bold red] No methodology snapshot found for {args.campaign1}")
        sys.exit(1)
    if not m2:
        console.print(f"[bold red]{ui.SYM_FAIL} Error:[/bold red] No methodology snapshot found for {args.campaign2}")
        sys.exit(1)

    ok = compare_methodologies(args.campaign1, m1, args.campaign2, m2)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
