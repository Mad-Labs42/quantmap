"""Unit tests for ui.render_post_run_review_from_read_model().

Tests the final-review renderer in isolation — no server, no DB, no campaign execution.
All scenarios are built from FinalReviewReadModel; outcome truth comes from the model,
not from binary report_ok inference.
"""

from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

import src.ui as ui
from src.artifact_paths import (
    ARTIFACT_CAMPAIGN_SUMMARY,
    ARTIFACT_METADATA,
    ARTIFACT_RAW_TELEMETRY,
    ARTIFACT_RUN_REPORTS,
    FILENAME_CAMPAIGN_SUMMARY,
    FILENAME_METADATA,
    FILENAME_RAW_TELEMETRY,
    FILENAME_RUN_REPORTS,
)
from src.campaign_outcome.contracts import (
    CampaignOutcomeKind,
    FinalReviewMetricsSnapshot,
    FinalReviewReadModel,
)

# Backwards-compat alias (same type)
PostRunReviewMetrics = FinalReviewMetricsSnapshot


# ---------------------------------------------------------------------------
# Read-model builder helpers — reduce per-test boilerplate without hiding truth
# ---------------------------------------------------------------------------


def _success_rm(
    *,
    failure_cause: str | None = None,
    failure_remediation: str | None = None,
    metrics: PostRunReviewMetrics | None = None,
    report_generation_ok: bool | None = True,
) -> FinalReviewReadModel:
    """Minimal SUCCESS read model."""
    return FinalReviewReadModel(
        headline_status="Success",
        outcome_kind=CampaignOutcomeKind.SUCCESS,
        show_next_actions=True,
        success_style_diagnostics=True,
        failure_cause=failure_cause,
        failure_remediation=failure_remediation,
        report_generation_ok=report_generation_ok,
        metrics=metrics,
        artifact_block_mode="full",
    )


def _failed_rm(
    *,
    failure_cause: str | None = None,
    failure_remediation: str | None = None,
    metrics: PostRunReviewMetrics | None = None,
    report_generation_ok: bool | None = False,
) -> FinalReviewReadModel:
    """Minimal FAILED read model."""
    return FinalReviewReadModel(
        headline_status="Failed — campaign did not complete successfully",
        outcome_kind=CampaignOutcomeKind.FAILED,
        show_next_actions=False,
        success_style_diagnostics=False,
        failure_cause=failure_cause,
        failure_remediation=failure_remediation,
        report_generation_ok=report_generation_ok,
        metrics=metrics,
        artifact_block_mode="diagnostics_only",
    )


def _render(
    read_model: FinalReviewReadModel,
    *,
    campaign_id: str = "X_test",
    artifacts: list[dict] | None = None,
    diagnostics_path: str | None = None,
    yolo_mode: bool = False,
) -> str:
    """Render a FinalReviewReadModel through the canonical entrypoint, return output."""
    buf = io.StringIO()
    con = Console(file=buf, force_terminal=False, no_color=True, width=200)
    ui.render_post_run_review_from_read_model(
        campaign_id=campaign_id,
        read_model=read_model,
        artifacts=artifacts,
        diagnostics_path=diagnostics_path,
        yolo_mode=yolo_mode,
        target_console=con,
    )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Diagnostics block
# ---------------------------------------------------------------------------


def test_diagnostics_path_appears_when_provided():
    out = _render(
        _success_rm(),
        campaign_id="X_test",
        diagnostics_path="/lab/artifacts/logs/model/X_test",
    )
    assert "Internal diagnostic files were retained for debugging." in out
    assert "By default, they are not included in the user-facing artifact list." in out
    assert "/lab/artifacts/logs/model/X_test" in out


def test_diagnostics_block_omitted_when_path_is_none():
    out = _render(_success_rm(), campaign_id="X_test", diagnostics_path=None)
    assert "Internal diagnostic files were retained for debugging." not in out
    assert "By default, they are not included" not in out


# ---------------------------------------------------------------------------
# YOLO mode
# ---------------------------------------------------------------------------


def test_no_yolo_text_on_normal_run():
    out = _render(_success_rm(), campaign_id="X_test", yolo_mode=False)
    assert "YOLO Mode Active" not in out
    assert "Validation requirements were relaxed" not in out


def test_yolo_text_appears_when_explicitly_set():
    out = _render(_success_rm(), campaign_id="X_test", yolo_mode=True)
    assert "YOLO Mode Active" in out
    assert (
        "Validation requirements were relaxed because the user chose to continue after a trust warning."
        in out
    )


def test_yolo_default_is_false():
    """Calling without yolo_mode must not produce YOLO text."""
    out = _render(_success_rm(), campaign_id="X_test")
    assert "YOLO Mode Active" not in out


# ---------------------------------------------------------------------------
# Next actions block
# ---------------------------------------------------------------------------


def test_next_actions_shown_on_success():
    out = _render(_success_rm(), campaign_id="TestCamp_01")
    assert "Next actions" in out
    assert "quantmap explain TestCamp_01 --evidence" in out
    assert "quantmap artifacts TestCamp_01" in out
    assert "quantmap list" in out


def test_next_actions_hidden_on_failure():
    out = _render(_failed_rm(), campaign_id="TestCamp_01")
    assert "Next actions" not in out


# ---------------------------------------------------------------------------
# Artifact block
# ---------------------------------------------------------------------------


def test_artifact_block_shown_when_provided():
    artifacts = [
        {
            "artifact_type": ARTIFACT_CAMPAIGN_SUMMARY,
            "filename": FILENAME_CAMPAIGN_SUMMARY,
            "path": Path("/lab/artifacts/reports/model/TestCamp_01")
            / FILENAME_CAMPAIGN_SUMMARY,
            "exists": True,
            "db_status": "complete",
            "sha256": None,
        },
    ]
    out = _render(_success_rm(), campaign_id="TestCamp_01", artifacts=artifacts)
    assert "Campaign Summary" in out
    assert "TestCamp_01" in out


def test_artifact_block_omitted_when_not_provided():
    out = _render(_success_rm(), campaign_id="TestCamp_01", artifacts=None)
    assert "Artifacts —" not in out


def test_artifact_block_shows_missing_status():
    artifacts = [
        {
            "artifact_type": "run_reports_md",
            "filename": "run-reports.md",
            "path": Path("/lab/artifacts/reports/model/TestCamp_01/run-reports.md"),
            "exists": False,
            "db_status": None,
            "sha256": None,
        },
    ]
    out = _render(_success_rm(), campaign_id="TestCamp_01", artifacts=artifacts)
    assert "not found" in out


def test_artifact_block_shows_raw_type_as_dim_secondary():
    """Known artifact types include both friendly label and dimmed raw type."""
    artifacts = [
        {
            "artifact_type": "metadata_json",
            "filename": "metadata.json",
            "path": Path("/lab/metadata.json"),
            "exists": True,
            "db_status": "complete",
            "sha256": None,
        },
    ]
    out = _render(_success_rm(), campaign_id="TestCamp_01", artifacts=artifacts)
    assert "Metadata" in out
    assert "metadata_json" in out


def test_artifact_block_unknown_type_falls_back_to_raw():
    artifacts = [
        {
            "artifact_type": "some_future_type",
            "filename": "futurist.md",
            "path": Path("/lab/futurist.md"),
            "exists": True,
            "db_status": "complete",
            "sha256": None,
        },
    ]
    out = _render(_success_rm(), campaign_id="TestCamp_01", artifacts=artifacts)
    assert "some_future_type" in out


def test_artifact_block_human_labels_all_types():
    """Each known artifact_type renders its human-friendly label."""
    artifacts = [
        {
            "artifact_type": ARTIFACT_CAMPAIGN_SUMMARY,
            "filename": FILENAME_CAMPAIGN_SUMMARY,
            "path": Path("/lab") / FILENAME_CAMPAIGN_SUMMARY,
            "exists": True,
            "db_status": "complete",
            "sha256": None,
        },
        {
            "artifact_type": ARTIFACT_RUN_REPORTS,
            "filename": FILENAME_RUN_REPORTS,
            "path": Path("/lab") / FILENAME_RUN_REPORTS,
            "exists": True,
            "db_status": "complete",
            "sha256": None,
        },
        {
            "artifact_type": ARTIFACT_METADATA,
            "filename": FILENAME_METADATA,
            "path": Path("/lab") / FILENAME_METADATA,
            "exists": True,
            "db_status": "complete",
            "sha256": None,
        },
        {
            "artifact_type": ARTIFACT_RAW_TELEMETRY,
            "filename": FILENAME_RAW_TELEMETRY,
            "path": Path("/lab") / FILENAME_RAW_TELEMETRY,
            "exists": True,
            "db_status": "complete",
            "sha256": None,
        },
    ]
    out = _render(_success_rm(), campaign_id="TestCamp_01", artifacts=artifacts)
    assert "Campaign Summary" in out
    assert "Run Reports" in out
    assert "Metadata" in out
    assert "Raw Telemetry" in out


# ---------------------------------------------------------------------------
# Renderer is side-effect-free
# ---------------------------------------------------------------------------


def test_renderer_is_idempotent():
    """Calling render_post_run_review_from_read_model twice with same args must produce same output."""
    rm = _success_rm()
    out1 = _render(rm, campaign_id="Idem_test", diagnostics_path="/lab/diag")
    out2 = _render(rm, campaign_id="Idem_test", diagnostics_path="/lab/diag")
    assert out1 == out2


# ---------------------------------------------------------------------------
# Outcome Language
# ---------------------------------------------------------------------------


def test_outcome_success():
    out = _render(_success_rm(), campaign_id="X_test")
    assert "Status:  Success" in out


def test_outcome_failure_unknown_cause():
    out = _render(_failed_rm(), campaign_id="X_test", diagnostics_path="/lab/diag")
    assert "Status:  Failed" in out
    assert "Cause: Unknown." in out
    assert "Internal diagnostics may help diagnose the issue" in out


def test_outcome_failure_known_cause():
    out = _render(
        _failed_rm(failure_cause="Disk full"),
        campaign_id="X_test",
        diagnostics_path="/lab/diag",
    )
    assert "Status:  Failed" in out
    assert "Cause: Disk full." in out
    assert "Suggested fix:" not in out
    assert "Internal diagnostics may provide more information: /lab/diag" in out


def test_outcome_failure_remediation():
    out = _render(
        _failed_rm(failure_cause="Timeout", failure_remediation="Try increasing timeout"),
        campaign_id="X_test",
    )
    assert "Cause: Timeout." in out
    assert "Suggested fix: Try increasing timeout." in out


# ---------------------------------------------------------------------------
# Singular campaign wording
# ---------------------------------------------------------------------------


def test_success_uses_singular_campaign_wording():
    """Plural 'campaigns' replaced with singular status line."""
    out = _render(_success_rm(), campaign_id="X_test")
    assert "All requested campaigns ran successfully." not in out
    assert "Status:  Success" in out


def test_failure_uses_singular_campaign_wording():
    out = _render(_failed_rm(), campaign_id="X_test")
    assert "Error: QuantMap could not execute the requested campaigns." not in out
    assert "Status:  Failed" in out


# ---------------------------------------------------------------------------
# Config summary via FinalReviewMetricsSnapshot
# ---------------------------------------------------------------------------


def test_config_summary_full_success():
    out = _render(
        _success_rm(
            metrics=PostRunReviewMetrics(
                configs_total=6,
                configs_valid=4,
                configs_eliminated=2,
                winner_config_id="FullRun_30",
                winner_tg=245.12,
                run_mode="full",
                elapsed_seconds=754.0,
            )
        ),
        campaign_id="FullRun",
    )
    assert "Configs:  6 tested" in out
    assert "4 valid" in out
    assert "2 eliminated" in out
    assert "Best observed config: FullRun_30" in out
    assert "TG 245.12 t/s" in out
    assert "Mode: Full" in out
    assert "12m 34s" in out


def test_config_summary_no_eliminated():
    out = _render(
        _success_rm(
            metrics=PostRunReviewMetrics(
                configs_total=3,
                configs_valid=3,
                configs_eliminated=0,
                winner_config_id="CleanRun_10",
                winner_tg=180.0,
            )
        ),
        campaign_id="CleanRun",
    )
    assert "3 tested" in out
    assert "3 valid" in out
    assert "0 eliminated" not in out  # zero is suppressed
    assert "Best observed config: CleanRun_10" in out


def test_config_summary_no_winner():
    """When all configs eliminated, show no-best-config message."""
    out = _render(
        _success_rm(
            metrics=PostRunReviewMetrics(
                configs_total=5,
                configs_valid=0,
                configs_eliminated=5,
            )
        ),
        campaign_id="AllElim",
    )
    assert "No valid configs produced a score." in out


def test_config_summary_winner_without_tg():
    """Winner without TG should render config ID only."""
    out = _render(
        _success_rm(
            metrics=PostRunReviewMetrics(
                configs_total=2,
                configs_valid=1,
                configs_eliminated=1,
                winner_config_id="Weird_99",
                winner_tg=None,
            )
        ),
        campaign_id="Weird",
    )
    assert "Best observed config: Weird_99" in out
    assert "t/s" not in out  # no TG means no t/s suffix


def test_config_summary_fields_omitted_safely():
    """When metrics is None, no config line appears."""
    out = _render(_success_rm(metrics=None), campaign_id="NoSummary")
    assert "Configs:" not in out
    assert "Best observed config" not in out


# ---------------------------------------------------------------------------
# Run mode and elapsed time
# ---------------------------------------------------------------------------


def test_run_mode_display():
    out = _render(
        _success_rm(
            metrics=PostRunReviewMetrics(configs_total=1, configs_valid=1, run_mode="quick")
        ),
        campaign_id="M",
    )
    assert "Mode: Quick" in out


def test_run_mode_custom_label():
    out = _render(
        _success_rm(
            metrics=PostRunReviewMetrics(configs_total=1, configs_valid=1, run_mode="custom")
        ),
        campaign_id="M",
    )
    assert "Mode: Custom" in out


def test_elapsed_seconds_format():
    """_format_elapsed renders human-readable duration."""
    assert ui._format_elapsed(45) == "45s"
    assert ui._format_elapsed(90) == "1m 30s"
    assert ui._format_elapsed(3661) == "1h 1m"


def test_elapsed_appears_when_provided():
    out = _render(
        _success_rm(
            metrics=PostRunReviewMetrics(
                configs_total=1, configs_valid=1, elapsed_seconds=90
            )
        ),
        campaign_id="T",
    )
    assert "1m 30s" in out


def test_elapsed_not_shown_when_none():
    out = _render(
        _success_rm(
            metrics=PostRunReviewMetrics(
                configs_total=1, configs_valid=1, elapsed_seconds=None
            )
        ),
        campaign_id="T",
    )
    assert "Elapsed:" not in out


def test_meta_line_omitted_when_no_data():
    """Neither mode nor elapsed produces no meta line."""
    out = _render(_success_rm(metrics=None), campaign_id="T")
    assert "Mode:" not in out
    assert "Elapsed:" not in out


# ---------------------------------------------------------------------------
# Failure section orphan-blank-line guard (regression for PARTIAL carve-out)
# ---------------------------------------------------------------------------


def test_failure_section_omits_orphan_blank_line_for_partial_carveout_with_empty_cause():
    """Regression: PARTIAL + show_next_actions + empty failure_cause must not emit a dead blank section.

    The renderer is the wrong layer to assume "PARTIAL with show_next_actions
    always carries a non-empty failure_cause." Defending the contract surface
    (``failure_cause: str | None``) keeps the screen clean if a future evaluator
    path produces an empty cause for the carve-out.
    """
    rm = FinalReviewReadModel(
        headline_status="Only partial evidence — not a full success",
        outcome_kind=CampaignOutcomeKind.PARTIAL,
        show_next_actions=True,
        success_style_diagnostics=True,
        failure_cause=None,
        failure_remediation=None,
        report_generation_ok=True,
        artifact_block_mode="full",
    )
    out = _render(rm, campaign_id="T")
    # Negative checks: no failure-section copy should appear.
    assert "The following blocker was identified:" not in out
    assert "Cause: Unknown." not in out
    assert "- Cause:" not in out
    # Positive check: the headline still renders.
    assert "Only partial evidence" in out


def test_failure_section_still_renders_blocker_for_failed_outcome_with_cause():
    """Sanity: the orphan-blank-line guard does not regress the normal failure path."""
    rm = FinalReviewReadModel(
        headline_status="Failed — campaign did not complete successfully",
        outcome_kind=CampaignOutcomeKind.FAILED,
        show_next_actions=False,
        success_style_diagnostics=False,
        failure_cause="Primary report generation failed; measurement data remains valid.",
        failure_remediation="Review logs and rerun.",
        report_generation_ok=False,
        artifact_block_mode="diagnostics_only",
    )
    out = _render(rm, campaign_id="T")
    assert "The following blocker was identified:" in out
    assert "Primary report generation failed" in out
    assert "Suggested fix:" in out


def test_failure_section_still_renders_unknown_cause_when_appropriate():
    """Sanity: non-success outcomes without next-actions and without a cause still emit 'Cause: Unknown.'."""
    rm = FinalReviewReadModel(
        headline_status="Failed — campaign did not complete successfully",
        outcome_kind=CampaignOutcomeKind.FAILED,
        show_next_actions=False,
        success_style_diagnostics=False,
        failure_cause=None,
        failure_remediation=None,
        report_generation_ok=False,
        artifact_block_mode="diagnostics_only",
    )
    out = _render(rm, campaign_id="T")
    assert "Cause: Unknown." in out
