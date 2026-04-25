from __future__ import annotations

import pytest


_NGL_CAMPAIGN = {
    "campaign_id": "NGL_sweep",
    "variable": "n_gpu_layers",
    "values": [10, 20, 30, 40, 50, 60, 70, 80, 90, 999],
}


def test_compile_repeat_tier_1x_uses_locked_ngl_scaffold():
    from src.acpm_planning import (
        NGL_SCAFFOLD_1X,
        compile_repeat_tier,
    )

    selected_values, run_mode, coverage_policy = compile_repeat_tier(
        "1x",
        _NGL_CAMPAIGN["values"],
    )

    assert selected_values == NGL_SCAFFOLD_1X
    assert run_mode == "quick"
    assert coverage_policy["ngl_coverage_class"] == "scaffolded_1x"
    assert coverage_policy["selected_ngl_values"] == NGL_SCAFFOLD_1X


def test_compile_repeat_tier_3x_maps_to_standard():
    from src.acpm_planning import compile_repeat_tier

    selected_values, run_mode, coverage_policy = compile_repeat_tier(
        "3x",
        _NGL_CAMPAIGN["values"],
    )

    assert selected_values == _NGL_CAMPAIGN["values"]
    assert run_mode == "standard"
    assert coverage_policy["ngl_coverage_class"] == "full"


def test_compile_repeat_tier_5x_maps_to_full():
    from src.acpm_planning import compile_repeat_tier

    selected_values, run_mode, coverage_policy = compile_repeat_tier(
        "5x",
        _NGL_CAMPAIGN["values"],
    )

    assert selected_values == _NGL_CAMPAIGN["values"]
    assert run_mode == "full"
    assert coverage_policy["ngl_coverage_class"] == "full"


def test_compile_repeat_tier_rejects_unknown_repeat_tier():
    from src.acpm_planning import compile_repeat_tier

    with pytest.raises(ValueError, match="Unknown ACPM repeat tier"):
        compile_repeat_tier("9x", _NGL_CAMPAIGN["values"])


def test_applicability_accepts_valid_structural_campaign():
    from src.acpm_planning import check_campaign_applicability

    result = check_campaign_applicability(_NGL_CAMPAIGN)

    assert result.applicable is True
    assert result.reason is None
    assert result.variable == "n_gpu_layers"
    assert result.all_values == _NGL_CAMPAIGN["values"]


def test_applicability_rejects_unknown_or_unsupported_variable():
    from src.acpm_planning import check_campaign_applicability

    result = check_campaign_applicability(
        {
            "campaign_id": "threads_sweep",
            "variable": "threads",
            "values": [1, 2, 4],
        }
    )

    assert result.applicable is False
    assert result.reason == "unsupported_variable"


def test_applicability_does_not_prune_by_profile_preference():
    from src.acpm_planning import check_campaign_applicability

    result = check_campaign_applicability(_NGL_CAMPAIGN)

    assert result.applicable is True
    assert result.all_values == _NGL_CAMPAIGN["values"]


def test_planner_output_execution_inputs_include_scoring_profile_name():
    from src.acpm_planning import compile_acpm_plan

    output = compile_acpm_plan(
        campaign=_NGL_CAMPAIGN,
        profile_name="Balanced",
        repeat_tier="1x",
    )

    execution_inputs = output.to_execution_inputs()
    assert execution_inputs["scoring_profile_name"] == "acpm_balanced_v1"


def test_planner_output_execution_inputs_preserve_existing_structural_keys():
    from src.acpm_planning import compile_acpm_plan

    output = compile_acpm_plan(
        campaign=_NGL_CAMPAIGN,
        profile_name="TTFT",
        repeat_tier="3x",
    )

    execution_inputs = output.to_execution_inputs()
    assert execution_inputs["run_mode"] == "standard"
    assert execution_inputs["scope_authority"] == "planner"
    assert execution_inputs["selected_values"] == _NGL_CAMPAIGN["values"]
    assert execution_inputs["selected_config_ids"] == [
        "NGL_sweep_10",
        "NGL_sweep_20",
        "NGL_sweep_30",
        "NGL_sweep_40",
        "NGL_sweep_50",
        "NGL_sweep_60",
        "NGL_sweep_70",
        "NGL_sweep_80",
        "NGL_sweep_90",
        "NGL_sweep_999",
    ]


def test_compile_plan_1x_sets_scaffold_coverage_policy():
    from src.acpm_planning import compile_acpm_plan

    output = compile_acpm_plan(
        campaign=_NGL_CAMPAIGN,
        profile_name="T/S",
        repeat_tier="1x",
        source_campaign_ref="configs/campaigns/NGL_sweep.yaml",
    )

    snapshot = output.to_planning_metadata_snapshot()
    assert snapshot["profile_name"] == "T/S"
    assert snapshot["repeat_tier"] == "1x"
    assert snapshot["coverage_policy"]["ngl_coverage_class"] == "scaffolded_1x"
    assert snapshot["coverage_policy"]["selected_ngl_values"] == [10, 30, 50, 70, 90, 999]



