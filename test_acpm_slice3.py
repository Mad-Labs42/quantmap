"""
ACPM Slice 3 validation suite.

Covers: governed ACPM scoring profile YAMLs, registry constants, helper
functions, and ACPMPlanningMetadata profile_name validation tightening.
"""

import pytest

from src.governance import load_profile, load_registry, validate_profile_against_registry
from src.acpm_planning import (
    ACPM_PLANNING_METADATA_SCHEMA_ID,
    ACPM_PLANNING_METADATA_SCHEMA_VERSION,
    ACPMPlanningMetadata,
    V1_ACPM_PROFILE_IDS,
    _ACPM_PROFILE_REGISTRY,
    get_acpm_profile_info,
    load_acpm_scoring_profile,
)
from src.run_plan import SCOPE_AUTHORITY_PLANNER

# ---------------------------------------------------------------------------
# Module-level fixtures — loaded once per test session
# ---------------------------------------------------------------------------

_REFERENCE_PROFILE = load_profile("default_throughput_v1")
_REGISTRY = load_registry()
_ACPM_YAML_NAMES = {
    "Balanced": "acpm_balanced_v1",
    "T/S": "acpm_ts_v1",
    "TTFT": "acpm_ttft_v1",
}

# ---------------------------------------------------------------------------
# Helper: build a valid ACPMPlanningMetadata for a given profile_name
# ---------------------------------------------------------------------------

def _make_metadata(profile_name: str) -> ACPMPlanningMetadata:
    return ACPMPlanningMetadata(
        planner_id="acpm-v1",
        planner_version="0.1",
        planner_policy_id="slice3-test",
        profile_name=profile_name,
        repeat_tier="1x",
        scope_authority=SCOPE_AUTHORITY_PLANNER,
        source_campaign_ref="configs/campaigns/NGL_sweep.yaml",
        selected_scope_digest="sha256:test",
        schema_id=ACPM_PLANNING_METADATA_SCHEMA_ID,
        schema_version=ACPM_PLANNING_METADATA_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------------
# Tests 1–3: Individual profile load
# ---------------------------------------------------------------------------

def test_balanced_profile_loads():
    p = load_profile("acpm_balanced_v1")
    assert p.name == "acpm_balanced_v1"


def test_ts_profile_loads():
    p = load_profile("acpm_ts_v1")
    assert p.name == "acpm_ts_v1"


def test_ttft_profile_loads():
    p = load_profile("acpm_ttft_v1")
    assert p.name == "acpm_ttft_v1"


# ---------------------------------------------------------------------------
# Test 4: All three validate against the registry without exception
# ---------------------------------------------------------------------------

def test_all_profiles_validate_against_registry():
    for yaml_name in _ACPM_YAML_NAMES.values():
        profile = load_profile(yaml_name)
        validate_profile_against_registry(profile, _REGISTRY)  # must not raise


# ---------------------------------------------------------------------------
# Test 5: Weight sums are 1.0 within float tolerance
# ---------------------------------------------------------------------------

def test_weight_sums_are_one():
    for yaml_name in _ACPM_YAML_NAMES.values():
        profile = load_profile(yaml_name)
        total = sum(profile.weights.values())
        assert abs(total - 1.0) < 1e-6, (
            f"{yaml_name}: weights sum to {total:.8f}, expected 1.0"
        )


# ---------------------------------------------------------------------------
# Test 6: gate_overrides identical to default_throughput_v1
# ---------------------------------------------------------------------------

def test_gates_match_shared_floor():
    reference_gates = _REFERENCE_PROFILE.gate_overrides
    for yaml_name in _ACPM_YAML_NAMES.values():
        profile = load_profile(yaml_name)
        assert profile.gate_overrides == reference_gates, (
            f"{yaml_name}: gate_overrides differ from default_throughput_v1"
        )


# ---------------------------------------------------------------------------
# Test 7: warm_ttft_p90_ms weight is exactly 0.00 in all three profiles
# ---------------------------------------------------------------------------

def test_warm_ttft_p90_weight_is_zero():
    for yaml_name in _ACPM_YAML_NAMES.values():
        profile = load_profile(yaml_name)
        weight = profile.weights["warm_ttft_p90_ms"]
        assert abs(weight) < 1e-9, (
            f"{yaml_name}: warm_ttft_p90_ms weight is {weight}, expected 0.0"
        )


# ---------------------------------------------------------------------------
# Test 8: Six-metric active_metrics shape matches default_throughput_v1
# ---------------------------------------------------------------------------

def test_six_metric_shape_preserved():
    reference_metrics = set(_REFERENCE_PROFILE.active_metrics)
    for yaml_name in _ACPM_YAML_NAMES.values():
        profile = load_profile(yaml_name)
        assert set(profile.active_metrics) == reference_metrics, (
            f"{yaml_name}: active_metrics differ from default_throughput_v1"
        )


# ---------------------------------------------------------------------------
# Test 9: V1_ACPM_PROFILE_IDS constant has exactly the three expected IDs
# ---------------------------------------------------------------------------

def test_v1_profile_ids_constant():
    assert V1_ACPM_PROFILE_IDS == {"Balanced", "T/S", "TTFT"}


# ---------------------------------------------------------------------------
# Test 10: Registry dict covers exactly V1_ACPM_PROFILE_IDS
# ---------------------------------------------------------------------------

def test_registry_covers_all_v1_ids():
    assert set(_ACPM_PROFILE_REGISTRY.keys()) == V1_ACPM_PROFILE_IDS


# ---------------------------------------------------------------------------
# Test 11: get_acpm_profile_info returns expected keys for all valid IDs
# ---------------------------------------------------------------------------

def test_get_acpm_profile_info_valid():
    expected_keys = {"scoring_profile_name", "display_label", "display_name", "lens_description"}
    for profile_id in V1_ACPM_PROFILE_IDS:
        info = get_acpm_profile_info(profile_id)
        assert set(info.keys()) == expected_keys, (
            f"{profile_id}: info keys {set(info.keys())} != {expected_keys}"
        )
        # scoring_profile_name must resolve to the known YAML name
        assert info["scoring_profile_name"] == _ACPM_YAML_NAMES[profile_id]


# ---------------------------------------------------------------------------
# Test 12: get_acpm_profile_info raises ValueError for unknown ID
# ---------------------------------------------------------------------------

def test_get_acpm_profile_info_invalid():
    with pytest.raises(ValueError, match="Unknown ACPM profile ID"):
        get_acpm_profile_info("Unknown")


# ---------------------------------------------------------------------------
# Test 13: load_acpm_scoring_profile round-trip — .name matches registry entry
# ---------------------------------------------------------------------------

def test_load_acpm_scoring_profile_round_trip():
    for profile_id in V1_ACPM_PROFILE_IDS:
        profile = load_acpm_scoring_profile(profile_id)
        expected_name = get_acpm_profile_info(profile_id)["scoring_profile_name"]
        assert profile.name == expected_name, (
            f"{profile_id}: profile.name={profile.name!r}, expected {expected_name!r}"
        )


# ---------------------------------------------------------------------------
# Test 14: ACPMPlanningMetadata rejects profile_name not in V1_ACPM_PROFILE_IDS
# ---------------------------------------------------------------------------

def test_planning_metadata_rejects_unknown_profile():
    with pytest.raises(ValueError, match="profile_name must be one of"):
        _make_metadata("UnknownProfile")


# ---------------------------------------------------------------------------
# Test 15: ACPMPlanningMetadata accepts all three valid profile IDs
# ---------------------------------------------------------------------------

def test_planning_metadata_accepts_known_profiles():
    for profile_id in V1_ACPM_PROFILE_IDS:
        meta = _make_metadata(profile_id)
        assert meta.profile_name == profile_id


# ---------------------------------------------------------------------------
# Test 16: T/S display_name contains the full "Throughput/Speed" expansion
# ---------------------------------------------------------------------------

def test_ts_display_name_includes_expansion():
    info = get_acpm_profile_info("T/S")
    assert "Throughput/Speed" in info["display_name"]
