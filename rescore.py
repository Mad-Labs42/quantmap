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
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv  # type: ignore[import]

load_dotenv()

from src import ui

console = ui.get_console()

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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rescore(
    campaign_id: str,
    baseline: dict,
    force_new_anchors: bool = False,
    current_input: bool = False,
) -> bool:
    """Re-run analysis + scoring + report for one campaign. Returns True on success."""
    from src.analyze import analyze_campaign
    from src.score import score_campaign, ELIMINATION_FILTERS
    from src.report import generate_report
    from src.report_campaign import generate_campaign_report
    from src.db import init_db, get_connection
    from src.trust_identity import (
        MethodologySnapshotError,
        load_baseline_for_historical_use,
        load_methodology_for_historical_scoring,
        load_run_identity,
    )
    from src.governance import CurrentMethodologyLoadError

    logger.info("=" * 60)
    logger.info("Re-scoring campaign: %s", campaign_id)
    if force_new_anchors:
        if not current_input:
            logger.error(
                "--force-new-anchors requires --current-input. Snapshot-locked "
                "rescore cannot re-anchor to current files."
            )
            return False
        logger.warning("METHODOLOGY MIGRATION: Re-anchoring to current Registry/Baseline references")

    if not DB_PATH.exists():
        logger.error("Database not found: %s", DB_PATH)
        return False

    # Run schema migrations before any reads or writes.  rescore.py may be run
    # against a DB created by an older QuantMap version that predates schema
    # versioning; init_db() handles the forward migration safely.
    init_db(DB_PATH)
    baseline, baseline_source = load_baseline_for_historical_use(
        campaign_id,
        DB_PATH,
        fallback_baseline=baseline,
        allow_current_input=current_input,
    )
    if baseline_source != "snapshot" and not current_input:
        logger.error(
            "No snapshot baseline is available for %s. Refusing snapshot-locked "
            "rescore. Re-run with --current-input to use the currently loaded "
            "baseline explicitly.",
            campaign_id,
        )
        return False
    if baseline_source == "current_input_explicit":
        logger.warning(
            "CURRENT-INPUT RESCORE: using the currently loaded baseline/profile "
            "rather than a complete historical snapshot for %s.",
            campaign_id,
        )
    if not current_input:
        try:
            load_methodology_for_historical_scoring(campaign_id, DB_PATH)
        except MethodologySnapshotError as exc:
            logger.error("%s", exc)
            return False
    trust_identity = load_run_identity(campaign_id, DB_PATH)
    
    # Load campaign-level run_mode from DB to reconstruct mode overrides
    conn = get_connection(DB_PATH)
    try:
        camp_row = conn.execute("SELECT run_mode FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    finally:
        conn.close()
        
    run_mode = camp_row["run_mode"] if camp_row else "full"

    mode_filter_overrides = {}
    if run_mode == "custom":
        # custom: single user-suppliced values, absolute floor of 1 warm sample.
        mode_filter_overrides = {"min_valid_warm_count": 1}
    elif run_mode in ("quick", "standard"):
        # quick and standard both run full value coverage; quick uses 1 cycle
        # per config (runner.py line 1525-1528 → 3-sample floor for statistical
        # functions).  Must match runner.py exactly so rescore produces the same
        # winner as the original run.
        mode_filter_overrides = {"min_valid_warm_count": 3}

    filter_overrides = dict(mode_filter_overrides)

    # Load campaign-level elimination_overrides from the YAML if present.
    # This ensures rescore produces the same result as a live run would:
    # if the campaign YAML overrides a filter threshold, that override is
    # respected here too rather than falling back to global defaults. (L6 fix)
    campaign_data = None
    raw_campaign_yaml = trust_identity.start_snapshot.get("campaign_yaml_content")
    if raw_campaign_yaml and not current_input:
        try:
            campaign_data = yaml.safe_load(raw_campaign_yaml) or {}
        except Exception as exc:
            logger.warning("Could not parse campaign snapshot YAML: %s", exc)

    campaign_yaml_path = CONFIGS_DIR / "campaigns" / f"{campaign_id}.yaml"
    if campaign_data is None and campaign_yaml_path.exists():
        try:
            with open(campaign_yaml_path, encoding="utf-8") as f:
                campaign_data = yaml.safe_load(f)
        except Exception as exc:
            logger.warning(
                "Could not load campaign YAML for filter overrides (%s): %s — using global defaults",
                campaign_yaml_path, exc,
            )
    else:
        logger.debug(
            "Campaign YAML not found at %s — using global filter defaults", campaign_yaml_path
        )

    yaml_filter_overrides = (campaign_data or {}).get("elimination_overrides") or {}
    if yaml_filter_overrides or filter_overrides:
        filter_overrides = {**filter_overrides, **yaml_filter_overrides}
        logger.info(
            "Effective filter overrides for %s mode: %s",
            run_mode, filter_overrides,
        )

    try:
        with get_connection(DB_PATH) as conn:
            now = _utc_now()
            conn.execute(
                """
                UPDATE campaigns
                SET analysis_status='running',
                    analysis_started_at=?,
                    analysis_failure_reason=NULL,
                    report_status='pending',
                    status_model_version=1
                WHERE id=?
                """,
                (now, campaign_id),
            )
            conn.commit()

        # Avoid double-analysis — score_campaign runs analyze internally
        result = score_campaign(
            campaign_id, 
            DB_PATH, 
            baseline=baseline, 
            filter_overrides=filter_overrides,
            force_new_anchors=force_new_anchors,
            current_input=current_input,
            current_input_reason="current_input_rescore" if current_input else "snapshot_locked",
        )
        # The score_campaign return dict changed in Phase 3.3/4
        # stats, passing, unrankable, eliminated, scores_df
        stats      = result["stats"]
        passing    = result["passing"]
        unrankable = result["unrankable"]
        eliminated = result["eliminated"]
        scores_df  = result["scores_df"]
        winner     = result["winner"]
        
        if not stats:
            logger.error("No stats returned — campaign may not be in database: %s", campaign_id)
            return False

        with get_connection(DB_PATH) as conn:
            now = _utc_now()
            conn.execute(
                """
                UPDATE campaigns
                SET analysis_status='complete',
                    analysis_completed_at=?,
                    report_status='running',
                    report_started_at=?,
                    report_failure_reason=NULL,
                    status_model_version=1
                WHERE id=?
                """,
                (now, now, campaign_id),
            )
            conn.commit()

        report_path = generate_report(campaign_id, DB_PATH, baseline, result, stats)
        logger.info("Report written: %s", report_path)

        # Regenerate run-reports.md so it always reflects the current DB state.
        # Without this, run-reports.md retains conclusions (winner, eliminated, Pareto)
        # from the prior scoring pass while campaign-summary.md and the scores table
        # are already updated — the two files would then contradict each other.
        v2_ok = True
        try:
            v2_path = generate_campaign_report(
                campaign_id, DB_PATH, baseline,
                scores_result=result, stats=stats,
            )
            logger.info("run-reports.md written: %s", v2_path)
        except Exception as _v2_exc:
            v2_ok = False
            logger.warning(
                "run-reports.md regeneration failed (non-fatal): %s",
                _v2_exc,
            )

        # Generate metadata.json (4th formal artifact).
        try:
            from src.export import generate_metadata_json  # noqa: PLC0415
            meta_path = generate_metadata_json(
                campaign_id,
                DB_PATH,
                scores_result=result,
                stats=stats,
            )
            logger.info("metadata.json written: %s", meta_path)
        except Exception as _meta_exc:
            logger.warning("metadata.json generation failed (non-fatal): %s", _meta_exc)

        with get_connection(DB_PATH) as conn:
            from src.trust_identity import summarize_report_artifact_status  # noqa: PLC0415

            report_status = (
                summarize_report_artifact_status(campaign_id, DB_PATH)
                if v2_ok
                else "partial"
            )
            conn.execute(
                """
                UPDATE campaigns
                SET report_status=?,
                    report_completed_at=?,
                    status_model_version=1
                WHERE id=?
                """,
                (report_status, _utc_now(), campaign_id),
            )
            conn.commit()

        # Print summary to console
        winner = result.get("winner")
        passing = result.get("passing", {})
        eliminated = result.get("eliminated", {})
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
        expected_trust_block = isinstance(
            exc, (MethodologySnapshotError, CurrentMethodologyLoadError)
        )
        if expected_trust_block:
            logger.error("Rescore blocked for %s: %s", campaign_id, exc)
        else:
            logger.error("Rescore failed for %s: %s", campaign_id, exc, exc_info=True)
        with get_connection(DB_PATH) as conn:
            conn.execute(
                """
                UPDATE campaigns
                SET analysis_status=CASE
                        WHEN analysis_status='complete' THEN analysis_status
                        ELSE 'failed'
                    END,
                    analysis_failed_at=CASE
                        WHEN analysis_status='complete' THEN analysis_failed_at
                        ELSE ?
                    END,
                    analysis_failure_reason=CASE
                        WHEN analysis_status='complete' THEN analysis_failure_reason
                        ELSE ?
                    END,
                    report_status=CASE
                        WHEN analysis_status='complete' THEN 'failed'
                        ELSE 'skipped'
                    END,
                    report_failed_at=CASE
                        WHEN analysis_status='complete' THEN ?
                        ELSE report_failed_at
                    END,
                    report_failure_reason=CASE
                        WHEN analysis_status='complete' THEN ?
                        ELSE report_failure_reason
                    END,
                    status_model_version=1
                WHERE id=?
                """,
                (_utc_now(), str(exc), _utc_now(), str(exc), campaign_id),
            )
            conn.commit()
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
    parser.add_argument(
        "--force-new-anchors",
        action="store_true",
        help="Force re-anchoring to current Registry/Baseline references (Methodology Migration)",
    )
    parser.add_argument(
        "--current-input",
        action="store_true",
        help="Explicitly use current baseline/campaign/profile inputs when a complete snapshot is unavailable",
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
        console.print(f"[{idx}/{total}] Re-scoring: {cid}")
        logger.info("Re-scoring %d/%d: %s", idx, total, cid)
        results[cid] = rescore(
            cid,
            baseline,
            force_new_anchors=args.force_new_anchors,
            current_input=args.current_input,
        )

    # Summary
    passed = [c for c, ok in results.items() if ok]
    failed = [c for c, ok in results.items() if not ok]

    console.print()
    console.print(f"{ui.SYM_DIVIDER}" * 60)
    console.print(f"Re-score complete: {len(passed)} succeeded, {len(failed)} failed")
    if failed:
        console.print(f"Failed: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
