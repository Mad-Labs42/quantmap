"""
test_governance.py
Verification of Phase 3.1 Registry/Profile architecture.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent))


from src.governance import (
    BUILTIN_REGISTRY, 
    DEFAULT_PROFILE, 
    validate_profile_against_registry, 
    ProfileValidationError, 
    ExperimentProfile, 
    ExperimentFamily, 
    RankingMode, 
    CompositeBasis, 
    ConfidencePolicy, 
    OutlierPolicy, 
    FenceMethod
)

def test_registry_integrity():
    print("Testing Registry Integrity...")
    reg = BUILTIN_REGISTRY
    assert len(reg) >= 10, f"Expected at least 10 metrics, got {len(reg)}"
    
    # Check canonical metric
    tg = reg.get("warm_tg_median")
    assert tg.human_label == "Warm Token Generation (Median)"
    assert tg.gate_capable is True
    
    # Check required vs optional logic
    primary = reg.get_required_score_metrics()
    assert "warm_tg_median" in primary
    assert "warm_tg_p10" in primary
    
    secondary = reg.get_optional_score_metrics()
    assert "warm_ttft_median_ms" in secondary
    print("  [PASS] Registry looks solid.")

def test_profile_validation():
    print("\nTesting Profile Validation...")
    prof = DEFAULT_PROFILE
    reg = BUILTIN_REGISTRY
    
    # Valid profile
    validate_profile_against_registry(prof, reg)
    print("  [PASS] Default profile validated.")
    


    # Invalid profile — metric mismatch
    bad_prof_data = {
        "name": "bad_profile",
        "version": "0.0.1",
        "experiment_family": ExperimentFamily.throughput,
        "description": "test",
        "active_metrics": ["non_existent_metric"],
        "primary_metrics": [],
        "secondary_metrics": [],
        "weights": {"non_existent_metric": 1.0},
        "ranking_mode": RankingMode.composite,
        "composite_basis": CompositeBasis.raw_score,
        "confidence_policy": ConfidencePolicy.none,
        "min_sample_gate": 3,
        "outlier_policy": OutlierPolicy.flag_symmetric,
        "outlier_fence_method": FenceMethod.iqr_1_5,
        "gate_overrides": {},
        "report_emphasis": [],
        "diagnostic_metrics": []
    }
    bad_prof = ExperimentProfile(**bad_prof_data)
    
    try:
        validate_profile_against_registry(bad_prof, reg)
        assert False, "Should have failed validation for non-existent metric"
    except ProfileValidationError as e:
        print(f"  [PASS] Successfully caught invalid metric: {str(e)[:60]}...")

    # Invalid profile — weights sum
    try:
        ExperimentProfile(
            name="weight_fail",
            version="0.0.1",
            experiment_family=ExperimentFamily.throughput,
            description="test",
            active_metrics=["warm_tg_median"],
            primary_metrics=[],
            secondary_metrics=[],
            weights={"warm_tg_median": 0.5},
            ranking_mode=RankingMode.composite,
            composite_basis=CompositeBasis.raw_score,
            confidence_policy=ConfidencePolicy.none,
            min_sample_gate=3,
            outlier_policy=OutlierPolicy.flag_symmetric,
            outlier_fence_method=FenceMethod.iqr_1_5,
            gate_overrides={},
            report_emphasis=[],
            diagnostic_metrics=[]
        )
        assert False, "Should have failed weight sum validation"
    except ValueError as e:
        print(f"  [PASS] Successfully caught unbalanced weights: {str(e)[:60]}...")

if __name__ == "__main__":
    try:
        test_registry_integrity()
        test_profile_validation()
        print("\nALL GOVERNANCE VERIFICATIONS PASSED")
    except Exception as e:
        print(f"\nVERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
