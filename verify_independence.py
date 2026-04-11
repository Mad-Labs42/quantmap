"""
QuantMap — verify_independence.py
Phase 3.3 Verification: Proving that scores are absolute (fixed-reference) 
rather than cohort-relative (best-in-batch).

Methodology:
1. Load a real campaign (E_ttft_calibration).
2. Score it using the standard Registry references.
3. Artificially inject a "Super Config" into the stats (with 10x throughput).
4. Re-score the augmented campaign.
5. Verify that the original config scores are IDENTICAL.
"""

import sys
from pathlib import Path
import copy
import logging
import numpy as np
import pandas as pd

# Ensure src is in path
sys.path.append(str(Path(__file__).parent))

from src import score
from src import governance
from src.config import LAB_ROOT

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

def main():
    db_path = LAB_ROOT / "db" / "lab.sqlite"
    campaign_id = "E_ttft_calibration"
    
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    print(f"\n--- Phase 3.3 Independence Check: {campaign_id} ---")
    
    # 1. Primary Scoring Pass
    print("\n1. Running primary scoring (Standard Registry Anchors)...")
    # Phase 3.3: score_campaign now requires a mandatory baseline dictionary
    dummy_baseline = {"name": "verify_independence", "reference": {}}
    res1 = score.score_campaign(campaign_id, db_path, dummy_baseline)
    df1 = res1["scores_df"]
    
    # Store a few scores for comparison
    original_scores = df1["composite_score"].to_dict()
    print(f"   Sample score for winner: {original_scores.get(res1['winner'], 'N/A'):.4f}")

    # 2. Augmented Scoring Pass (Injection of Super Config)
    print("\n2. Injecting 'Super Config' (300 t/s) into in-memory stats...")
    # NOTE: Registry anchor for warm_tg_median is 30.0 t/s.
    # If we were cohort-relative, this 300 t/s config would crush all other scores.
    
    # Deep copy stats to avoid corrupting cache (if any)
    stats2 = copy.deepcopy(res1["stats"])
    
    # Build a fake config that is 10x faster than the Registry anchor
    super_cid = "C_SUPER_CONFIG"
    super_stats = {
        "config_id": super_cid,
        "warm_tg_median": 300.0,
        "warm_tg_p10": 280.0,
        "warm_ttft_median_ms": 10.0,
        "warm_ttft_p90_ms": 15.0,
        "cold_ttft_median_ms": 1000.0,
        "pp_median": 5000.0,
        "valid_warm_request_count": 50,
        "success_rate": 1.0,
        "thermal_events": 0,
        "outlier_count": 0,
    }
    stats2[super_cid] = super_stats
    
    # We must also update 'passing' set
    passing2 = {super_cid: super_stats}
    for cid, s in res1["passing"].items():
        passing2[cid] = copy.deepcopy(s)

    # Re-run compute_scores directly with augmented data
    # We need to build the provided_references map manually to bypass score_campaign logic for this mock
    provided_refs = res1["provided_references"]
    
    print("3. Re-scoring augmented set...")
    # In Phase 3.3, compute_scores result is a tuple of (df, collapsed, high_nan, nan_invalid)
    df2, _, _, _ = score.compute_scores(
        passing2,
        {}, # unrankable
        stats2,
        res1["scoring_profile"],
        res1["registry"],
        provided_refs
    )

    # 4. Comparison
    print("\n--- RESULTS ---")
    super_score = df2.loc[super_cid, "composite_score"]
    print(f"Super Config Score: {super_score:.4f} (Normalization Anchor was {provided_refs.get('warm_tg_median')})")
    
    mismatches = 0
    for cid, score1 in original_scores.items():
        score2 = df2.loc[cid, "composite_score"]
        diff = abs(score1 - score2)
        if diff > 1e-4:
            print(f"   [FAIL] {cid}: {score1:.4f} -> {score2:.4f} (diff: {diff:.6f})")
            mismatches += 1
        else:
            # print(f"   [PASS] {cid}: {score1:.4f} == {score2:.4f}")
            pass

    if mismatches == 0:
        print("\n[SUCCESS] Independence Verified! Config scores are absolute and independent of the cohort.")
        print("This confirms the successful implementation of Phase 3.3 Fixed-Reference Governance.")
    else:
        print(f"\n[FAILURE] {mismatches} configs changed their scores when a new leader was introduced.")
        print("This indicates the system is still cohort-relative.")
        sys.exit(1)

if __name__ == "__main__":
    main()
