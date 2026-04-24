"""Tests for the `quantmap acpm` namespace (CLI UX Bundle 3)."""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

from rich.console import Console

import src.ui as ui


REPO_ROOT = Path(__file__).resolve().parent


def _run_cli(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "quantmap.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def test_acpm_help_includes_plan_validate_info():
    output = _run_cli("acpm", "--help")
    assert "plan" in output
    assert "validate" in output
    assert "info" in output


def test_acpm_info_lists_all_three_profiles():
    output = _run_cli("acpm", "info")
    assert "Balanced" in output
    assert "T/S" in output
    assert "TTFT" in output


def test_acpm_info_profile_shows_lens_description():
    output = _run_cli("acpm", "info", "--profile", "Balanced")
    assert "Balanced" in output
    assert "lens" in output.lower()


def test_acpm_info_unknown_profile_exits_1():
    result = subprocess.run(
        [sys.executable, "quantmap.py", "acpm", "info", "--profile", "BadProfile"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode != 0
    assert "BadProfile" in result.stdout or "Unknown" in result.stdout


def test_acpm_plan_unknown_campaign_exits_1():
    result = subprocess.run(
        [sys.executable, "quantmap.py", "acpm", "plan",
         "--campaign", "does_not_exist_999", "--profile", "Balanced"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode != 0
    assert "does_not_exist_999" in result.stdout or "not found" in result.stdout.lower()


def test_acpm_plan_unknown_profile_exits_1():
    result = subprocess.run(
        [sys.executable, "quantmap.py", "acpm", "plan",
         "--campaign", "B_low_sample", "--profile", "BadProfile"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode != 0


def test_acpm_plan_valid_inputs_shows_preview():
    output = _run_cli("acpm", "plan", "--campaign", "NGL_sweep", "--profile", "Balanced")
    assert "NGL_sweep" in output
    assert "Balanced" in output
    assert "1x" in output


def test_acpm_validate_valid_inputs_exits_0():
    result = subprocess.run(
        [sys.executable, "quantmap.py", "acpm", "validate",
         "--campaign", "NGL_sweep", "--profile", "Balanced"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0


def test_acpm_validate_unknown_campaign_exits_1():
    result = subprocess.run(
        [sys.executable, "quantmap.py", "acpm", "validate",
         "--campaign", "does_not_exist_999", "--profile", "Balanced"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode != 0


def test_acpm_validate_unknown_profile_exits_1():
    result = subprocess.run(
        [sys.executable, "quantmap.py", "acpm", "validate",
         "--campaign", "B_low_sample", "--profile", "BadProfile"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode != 0


def test_render_acpm_plan_preview_output():
    from src.acpm_planning import (
        ACPMPlanningMetadata,
        ACPMPlannerOutput,
        ACPMSelectedScope,
    )

    metadata = ACPMPlanningMetadata(
        planner_id="acpm-v1",
        planner_version="0.1",
        planner_policy_id="acpm_slice4",
        profile_name="Balanced",
        repeat_tier="1x",
        scope_authority="planner",
        source_campaign_ref="configs/campaigns/TestCampaign.yaml",
        selected_scope_digest="TestCampaign:Balanced:1x:10,30,50",
        narrowing_steps=[],
        coverage_policy={"ngl_coverage_class": "scaffolded_1x", "selected_ngl_values": [10, 30, 50]},
    )
    plan = ACPMPlannerOutput(
        selected_scope=ACPMSelectedScope(
            variable="n_gpu_layers",
            selected_values=[10, 30, 50],
            selected_config_ids=["TestCampaign_10", "TestCampaign_30", "TestCampaign_50"],
        ),
        run_mode="quick",
        profile_name="Balanced",
        repeat_tier="1x",
        planning_metadata=metadata,
    )
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True, width=140)
    ui.render_acpm_plan_preview(plan, target_console=console)
    output = buf.getvalue()
    assert "Balanced" in output
    assert "1x" in output
    assert "n_gpu_layers" in output


def test_render_acpm_validate_result_all_pass():
    from src.acpm_planning import ACPMApplicabilityResult

    result = ACPMApplicabilityResult(
        applicable=True,
        reason=None,
        campaign_id="TestCampaign",
        variable="n_gpu_layers",
        all_values=[10, 30, 50, 70, 90, 999],
    )
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True, width=140)
    ui.render_acpm_validate_result(
        "TestCampaign", "Balanced", "1x", result,
        profile_info={"display_label": "Balanced", "lens_description": "Mixed."},
        tier_ok=True, profile_ok=True, campaign_exists=True,
        target_console=console,
    )
    output = buf.getvalue()
    assert "ACPM Validate" in output
    assert "Balanced" in output
    assert "All ACPM" in output


def test_render_acpm_validate_result_fails():
    from src.acpm_planning import ACPMApplicabilityResult

    result = ACPMApplicabilityResult(
        applicable=False,
        reason="unsupported_variable",
        campaign_id="BadCampaign",
        variable="threads",
        all_values=[],
    )
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True, width=140)
    ui.render_acpm_validate_result(
        "BadCampaign", "Balanced", "1x", result,
        profile_info={"display_label": "Balanced", "lens_description": "Mixed."},
        tier_ok=True, profile_ok=True, campaign_exists=False,
        target_console=console,
    )
    output = buf.getvalue()
    assert "ACPM Validate" in output
    assert "failed" in output.lower()