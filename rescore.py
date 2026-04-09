"""
QuantMap — rescore.py

Re-runs the analysis + scoring + report pipeline for a completed campaign
using data already in lab.sqlite. Does NOT re-run any experiments.

Use this after changing elimination thresholds or scoring weights in score.py
to replay the pipeline on existing data without re-collecting measurements.

Usage:
    python rescore.py C01_threads_batch
    python rescore.py C01_threads_batch C02_n_parallel   # multiple campaigns
    python rescore.py --all                               # every completed campaign
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv  # type: ignore[import]

load_dotenv()

from src.config import CONFIGS_DIR, LAB_ROOT  # noqa: E402

# Paths derived from shared constants (src.config is the single source of truth)
DB_PATH       = LAB_ROOT / "db" / "lab.sqlite"
BASELINE_YAML = CONFIGS_DIR / "baseline.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("rescore")


def rescore(campaign_id: str, baseline: dict) -> bool:
    """Re-run analysis + scoring + report for one campaign. Returns True on success."""
    from src.analyze import analyze_campaign
    from src.score import score_campaign, ELIMINATION_FILTERS
    from src.report import generate_report
    from src.db import init_db, get_connection

    logger.info("=" * 60)
    logger.info("Re-scoring campaign: %s", campaign_id)
    logger.info("Active thresholds: %s", ELIMINATION_FILTERS)

    if not DB_PATH.exists():
        logger.error("Database not found: %s", DB_PATH)
        return False

    # Run schema migrations before any reads or writes.  rescore.py may be run
    # against a DB created by an older QuantMap version that predates schema
    # versioning; init_db() handles the forward migration safely.
    init_db(DB_PATH)
    
    # Load campaign-level run_mode from DB to reconstruct mode overrides
    conn = get_connection(DB_PATH)
    try:
        camp_row = conn.execute("SELECT run_mode FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    finally:
        conn.close()
        
    run_mode = camp_row["run_mode"] if camp_row else "full"

    mode_filter_overrides = {}
    if run_mode in ("custom", "quick"):
        mode_filter_overrides = {"min_valid_warm_count": 1}
    elif run_mode == "standard":
        mode_filter_overrides = {"min_valid_warm_count": 3}

    filter_overrides = dict(mode_filter_overrides)

    # Load campaign-level elimination_overrides from the YAML if present.
    # This ensures rescore produces the same result as a live run would:
    # if the campaign YAML overrides a filter threshold, that override is
    # respected here too rather than falling back to global defaults. (L6 fix)
    campaign_yaml_path = CONFIGS_DIR / "campaigns" / f"{campaign_id}.yaml"
    if campaign_yaml_path.exists():
        try:
            with open(campaign_yaml_path, encoding="utf-8") as f:
                campaign_data = yaml.safe_load(f)
            yaml_filter_overrides = campaign_data.get("elimination_overrides") or {}
            
            if yaml_filter_overrides or filter_overrides:
                filter_overrides = {**filter_overrides, **yaml_filter_overrides}
                logger.info(
                    "Effective filter overrides for %s mode: %s",
                    run_mode, filter_overrides,
                )
        except Exception as exc:
            logger.warning(
                "Could not load campaign YAML for filter overrides (%s): %s — using global defaults",
                campaign_yaml_path, exc,
            )
    else:
        logger.debug(
            "Campaign YAML not found at %s — using global filter defaults", campaign_yaml_path
        )

    try:
        # Avoid double-analysis — score_campaign runs analyze internally
        scores = score_campaign(campaign_id, DB_PATH, baseline, filter_overrides=filter_overrides or None)
        stats = scores.get("stats", {})
        
        if not stats:
            logger.error("No stats returned — campaign may not be in database: %s", campaign_id)
            return False

        report_path = generate_report(campaign_id, DB_PATH, baseline, scores, stats)

        logger.info("Report written: %s", report_path)

        # Print summary to console
        winner = scores.get("winner")
        passing = scores.get("passing", {})
        eliminated = scores.get("eliminated", {})
        logger.info(
            "Result: %d passing, %d eliminated. Winner: %s",
            len(passing), len(eliminated), winner or "none",
        )
        if winner and winner in passing:
            w = passing[winner]
            logger.info(
                "  Winner: tg_median=%.2f t/s  ttft_median=%.0fms  cv=%.3f",
                w.get("warm_tg_median") or 0,
                w.get("warm_ttft_median_ms") or 0,
                w.get("warm_tg_cv") or 0,
            )
        for cid, reason in sorted(eliminated.items()):
            logger.info("  Eliminated %s: %s", cid, reason)

        return True

    except Exception as exc:
        logger.error("Rescore failed for %s: %s", campaign_id, exc, exc_info=True)
        return False


def get_completed_campaigns() -> list[str]:
    """
    Return campaign IDs that have at least one complete config in the DB.

    NOTE (LOW-12 — pre-release): This returns campaigns where ANY config has
    status='complete', which includes partially-run campaigns (e.g. 3 of 5
    configs done before a crash).  A fully-complete campaign should require
    campaigns.status='complete'.  The current behaviour is intentionally
    permissive — rescoring a partial campaign to check intermediate results
    is a valid use case during development.

    Before release, add a --partial flag to make the distinction explicit:
        default (no flag):  campaigns.status = 'complete'  (fully done)
        --partial:          any config status = 'complete'  (current behaviour)
    """
    from src.db import get_connection
    with get_connection(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT DISTINCT campaign_id FROM configs WHERE status='complete'"
        ).fetchall()
    return [r[0] for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-run analysis+scoring+report on already-collected campaign data."
    )
    parser.add_argument(
        "campaigns",
        nargs="*",
        metavar="CAMPAIGN_ID",
        help="Campaign ID(s) to re-score (e.g. C01_threads_batch)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-score all campaigns with completed data in the database",
    )
    args = parser.parse_args()

    if not args.all and not args.campaigns:
        parser.print_help()
        sys.exit(1)

    if not BASELINE_YAML.exists():
        logger.error("baseline.yaml not found: %s", BASELINE_YAML)
        sys.exit(1)

    with open(BASELINE_YAML, encoding="utf-8") as f:
        baseline = yaml.safe_load(f)

    if args.all:
        campaign_ids = get_completed_campaigns()
        if not campaign_ids:
            logger.error("No completed campaigns found in database.")
            sys.exit(1)
        logger.info("Re-scoring all completed campaigns: %s", campaign_ids)
    else:
        campaign_ids = args.campaigns

    total = len(campaign_ids)
    results = {}
    for idx, cid in enumerate(campaign_ids, start=1):
        # U5: show per-campaign progress so --all on 10+ campaigns is legible
        print(f"[{idx}/{total}] Re-scoring: {cid}")
        logger.info("Re-scoring %d/%d: %s", idx, total, cid)
        results[cid] = rescore(cid, baseline)

    # Summary
    passed = [c for c, ok in results.items() if ok]
    failed = [c for c, ok in results.items() if not ok]

    print()
    print("=" * 60)
    print(f"Re-score complete: {len(passed)} succeeded, {len(failed)} failed")
    if failed:
        print(f"Failed: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
