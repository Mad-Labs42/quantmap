"""Slice 1 tests: pure campaign outcome evaluation and projection."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.campaign_outcome.contracts import (
    AbortReason,
    CampaignEvidenceSummary,
    CampaignOutcomeInputs,
    CampaignOutcomeKind,
    FailureDomain,
    FinalReviewReadModel,
    MeasurementPhaseVerdict,
    PostRunVerdict,
)
import src.campaign_outcome.evaluate as outcome_evaluate
from src.campaign_outcome.projection import project_final_review


def _base_evidence(**kwargs) -> CampaignEvidenceSummary:
    defaults = {
        "configs_total": 2,
        "configs_completed": 2,
        "configs_oom": 0,
        "configs_skipped_oom": 0,
        "configs_degraded": 0,
        "cycles_attempted": 4,
        "cycles_complete": 4,
        "cycles_invalid": 0,
        "has_any_success_request": True,
        "campaign_db_status": "complete",
    }
    defaults.update(kwargs)
    return CampaignEvidenceSummary(**defaults)


def test_report_ok_true_does_not_mask_invalid_campaign():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        scoring_completed=True,
        passing_count=0,
        winner_config_id=None,
        evidence=_base_evidence(
            has_any_success_request=False, cycles_attempted=0, configs_completed=0
        ),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.outcome_kind != CampaignOutcomeKind.SUCCESS
    assert not out.allows_success_style_review


def test_report_failure_does_not_erase_measurement_truth():
    ev = _base_evidence()
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=False,
        scoring_completed=True,
        passing_count=1,
        winner_config_id="cfg_a",
        evidence=ev,
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.measurement == MeasurementPhaseVerdict.SUCCEEDED
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert out.failure_domain == FailureDomain.POST_RUN_PIPELINE


def test_no_valid_config_blocks_success_style_review():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        scoring_completed=True,
        passing_count=0,
        winner_config_id=None,
        evidence=_base_evidence(),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.outcome_kind == CampaignOutcomeKind.INSUFFICIENT_EVIDENCE
    assert not out.allows_success_style_review
    assert not out.allows_recommendation_authority


def test_final_review_read_model_not_raw_report_ok():
    ev = _base_evidence()
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=False,
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        evidence=ev,
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    rm = project_final_review(out)
    assert rm.headline_status != "Success"
    assert rm.report_generation_ok is False


def test_abort_maps_to_aborted():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        user_interrupted=True,
        evidence=_base_evidence(),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.outcome_kind == CampaignOutcomeKind.ABORTED
    assert out.abort == AbortReason.USER_INTERRUPT
    assert out.report_ok is None


@pytest.mark.parametrize(
    ("flag_name", "abort_reason"),
    [
        ("telemetry_aborted_before_db", AbortReason.TELEMETRY_STARTUP),
        ("backend_policy_blocked", AbortReason.BACKEND_EXECUTION_POLICY),
    ],
)
def test_pre_measurement_startup_blocks_are_abort_outcomes(
    flag_name: str, abort_reason: AbortReason
) -> None:
    """Telemetry readiness ABORT and backend policy block are pre-measurement aborts."""
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        evidence=_base_evidence(has_any_success_request=True),
        **{flag_name: True},
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.outcome_kind == CampaignOutcomeKind.ABORTED
    assert out.measurement == MeasurementPhaseVerdict.NOT_STARTED
    assert out.abort == abort_reason
    assert out.report_ok is None
    assert out.failure_domain == FailureDomain.CONTRACT_CONFIG_ENV
    assert not out.allows_success_style_review
    assert not out.allows_recommendation_authority


def test_fatal_measurement_exception_is_failed_measurement_outcome() -> None:
    """Fatal exception during measurement fails measurement; not success-style review."""
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        fatal_exception_during_measurement=True,
        fatal_exception_message="server vanished",
        report_ok=True,
        evidence=_base_evidence(has_any_success_request=True),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.outcome_kind == CampaignOutcomeKind.FAILED
    assert out.measurement == MeasurementPhaseVerdict.FAILED
    assert out.post_run == PostRunVerdict.NOT_REACHED
    assert out.failure_domain == FailureDomain.UNKNOWN
    assert out.failure_detail == "server vanished"
    assert not out.allows_success_style_review


def test_backend_startup_distinct_from_measurement_body():
    """Startup vs body domain while DB reflects a finished lifecycle (complete)."""
    ev_startup = _base_evidence(
        has_any_success_request=False,
        cycles_attempted=2,
        cycles_invalid=2,
        cycles_complete=0,
    )
    inp_b = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        campaign_db_status="complete",
        last_backend_failure_reason="startup_timeout",
        scoring_completed=False,
        evidence=ev_startup,
    )
    out_b = outcome_evaluate.evaluate_campaign_outcome(inp_b)
    assert out_b.measurement == MeasurementPhaseVerdict.FAILED
    assert out_b.failure_domain == FailureDomain.BACKEND_STARTUP
    assert out_b.outcome_kind == CampaignOutcomeKind.FAILED

    ev_body = _base_evidence(
        has_any_success_request=False,
        cycles_attempted=2,
        cycles_invalid=2,
        cycles_complete=0,
    )
    inp_body = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        campaign_db_status="complete",
        scoring_completed=False,
        evidence=ev_body,
    )
    out_body = outcome_evaluate.evaluate_campaign_outcome(inp_body)
    assert out_body.measurement == MeasurementPhaseVerdict.FAILED
    assert out_body.outcome_kind == CampaignOutcomeKind.FAILED
    assert out_body.failure_domain == FailureDomain.MEASUREMENT_BODY


def test_lifecycle_complete_no_success_measurement_body_without_startup_signal():
    """Ordinary no-success body failure stays MEASUREMENT_BODY when lifecycle complete."""
    ev = _base_evidence(
        campaign_db_status="complete",
        has_any_success_request=False,
        cycles_attempted=2,
        cycles_invalid=2,
        cycles_complete=0,
    )
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        campaign_db_status="complete",
        last_backend_failure_reason=None,
        scoring_completed=False,
        evidence=ev,
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.measurement == MeasurementPhaseVerdict.FAILED
    assert out.outcome_kind == CampaignOutcomeKind.FAILED
    assert out.failure_domain == FailureDomain.MEASUREMENT_BODY


def test_complete_lifecycle_startup_failure_is_failed_not_insufficient_evidence():
    """Lifecycle complete + startup signal retains BACKEND_STARTUP and FAILED outcome kind."""
    ev = _base_evidence(
        campaign_db_status="complete",
        has_any_success_request=False,
        cycles_attempted=2,
        cycles_complete=2,
        cycles_invalid=0,
    )
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        campaign_db_status="complete",
        last_backend_failure_reason="cuda_init_failed",
        scoring_completed=False,
        evidence=ev,
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.measurement == MeasurementPhaseVerdict.FAILED
    assert out.outcome_kind == CampaignOutcomeKind.FAILED
    assert out.failure_domain == FailureDomain.BACKEND_STARTUP


def test_no_measurement_evidence_stays_insufficient_even_when_db_lifecycle_complete():
    """NOT_STARTED / NO_EVIDENCE synthesis applies even when DB lifecycle looks complete."""
    ev = CampaignEvidenceSummary(
        configs_total=0,
        configs_completed=0,
        cycles_attempted=0,
        cycles_complete=0,
        cycles_invalid=0,
        has_any_success_request=False,
        campaign_db_status="complete",
    )
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        campaign_db_status="complete",
        scoring_completed=False,
        evidence=ev,
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.measurement == MeasurementPhaseVerdict.NOT_STARTED
    assert out.outcome_kind == CampaignOutcomeKind.INSUFFICIENT_EVIDENCE
    assert out.failure_detail == "No measurement evidence to score."


def test_happy_path_success_style():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        scoring_completed=True,
        passing_count=1,
        winner_config_id="best",
        report_status="complete",
        evidence=_base_evidence(),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.outcome_kind == CampaignOutcomeKind.SUCCESS
    assert out.allows_success_style_review
    assert out.allows_recommendation_authority
    rm = project_final_review(out)
    assert rm.show_next_actions


def test_lifecycle_complete_does_not_imply_outcome_success():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        campaign_db_status="complete",
        report_ok=True,
        scoring_completed=True,
        passing_count=1,
        winner_config_id="x",
        evidence=_base_evidence(has_any_success_request=False, configs_completed=2),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.outcome_kind in (
        CampaignOutcomeKind.FAILED,
        CampaignOutcomeKind.INSUFFICIENT_EVIDENCE,
        CampaignOutcomeKind.DEGRADED,
    )
    assert not out.allows_success_style_review


def test_partial_evidence_partial_outcome():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        evidence=_base_evidence(cycles_invalid=1),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.measurement == MeasurementPhaseVerdict.PARTIAL
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert not out.allows_success_style_review
    assert not out.allows_recommendation_authority


def test_boundary_invalid_cycles_do_not_downgrade_measurement_when_oom_signals_present():
    """OOM + skipped-OOM capacity must meet invalid-cycle count (aggregate Slice 1 rule)."""
    out = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            scoring_completed=True,
            passing_count=1,
            winner_config_id="w",
            report_status="complete",
            evidence=_base_evidence(
                cycles_invalid=2,
                configs_oom=1,
                configs_skipped_oom=1,
            ),
        )
    )
    assert out.measurement == MeasurementPhaseVerdict.SUCCEEDED
    assert out.outcome_kind == CampaignOutcomeKind.SUCCESS
    assert out.allows_recommendation_authority


def test_invalid_cycles_remain_partial_when_oom_capacity_below_invalid_count():
    """Insufficient OOM/skipped-OOM capacity cannot explain all invalid cycles → PARTIAL."""
    out = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            scoring_completed=True,
            passing_count=1,
            winner_config_id="w",
            report_status="complete",
            evidence=_base_evidence(
                cycles_invalid=3,
                configs_oom=1,
                configs_skipped_oom=0,
            ),
        )
    )
    assert out.measurement == MeasurementPhaseVerdict.PARTIAL
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert not out.allows_recommendation_authority


def test_invalid_cycles_remain_partial_when_no_boundary_oom_aggregate_evidence():
    """Without OOM/skipped-OOM signals, invalid cycles stay unexplained → PARTIAL."""
    out = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            scoring_completed=True,
            passing_count=1,
            winner_config_id="w",
            evidence=_base_evidence(cycles_invalid=2),
        )
    )
    assert out.measurement == MeasurementPhaseVerdict.PARTIAL
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL


def test_invalid_cycles_remain_partial_when_only_configs_degraded_no_oom_skipped():
    """configs_degraded alone does not explain boundary invalid cycles (Slice 1 aggregates)."""
    out = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            scoring_completed=True,
            passing_count=1,
            winner_config_id="w",
            evidence=_base_evidence(cycles_invalid=2, configs_degraded=1),
        )
    )
    assert out.measurement == MeasurementPhaseVerdict.PARTIAL
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL


def test_report_ok_true_with_report_status_failed_not_success_style():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        report_status="failed",
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        evidence=_base_evidence(),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.post_run == PostRunVerdict.REPORT_FAILED
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert not out.allows_success_style_review
    assert out.measurement == MeasurementPhaseVerdict.SUCCEEDED


def test_report_ok_true_with_report_status_skipped_not_success_style():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        report_status="skipped",
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        evidence=_base_evidence(),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.post_run == PostRunVerdict.REPORT_SKIPPED
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert not out.allows_success_style_review
    assert out.measurement == MeasurementPhaseVerdict.SUCCEEDED


def test_report_status_partial_keeps_partial_kind_but_allows_success_style_review():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        report_status="partial",
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        evidence=_base_evidence(),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.post_run == PostRunVerdict.REPORT_PARTIAL
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert out.allows_success_style_review
    assert out.allows_recommendation_authority


def test_report_status_partial_without_winner_stays_non_success_style() -> None:
    out = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            report_status="partial",
            scoring_completed=True,
            passing_count=1,
            winner_config_id=None,
            evidence=_base_evidence(),
        )
    )
    assert out.outcome_kind in (
        CampaignOutcomeKind.INSUFFICIENT_EVIDENCE,
        CampaignOutcomeKind.DEGRADED,
    )
    assert not out.allows_success_style_review
    assert not out.allows_recommendation_authority


def test_report_status_complete_overrides_stale_report_ok_false():
    """Explicit ``report_status=complete`` wins over a stale ``report_ok=False`` bit."""
    out = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=False,
            report_status=" COMPLETE ",
            scoring_completed=True,
            passing_count=1,
            winner_config_id="w",
            evidence=_base_evidence(),
        )
    )
    assert out.post_run == PostRunVerdict.REPORT_SUCCEEDED
    assert out.outcome_kind == CampaignOutcomeKind.SUCCESS
    assert out.allows_recommendation_authority


def test_synthesized_abort_reason_propagates_to_campaign_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthesis may attach ``abort``; main path must not discard it (future-proofing)."""

    def _fake_synth(*args: object, **kwargs: object) -> outcome_evaluate._OutcomeSynth:
        return outcome_evaluate._OutcomeSynth(
            CampaignOutcomeKind.ABORTED,
            FailureDomain.CONTRACT_CONFIG_ENV,
            "synthetic abort detail",
            AbortReason.UNKNOWN,
        )

    monkeypatch.setattr(outcome_evaluate, "_synthesize_outcome", _fake_synth)
    out = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            scoring_completed=True,
            report_ok=True,
            report_status="complete",
            passing_count=1,
            winner_config_id="w",
            evidence=_base_evidence(),
        )
    )
    assert out.outcome_kind == CampaignOutcomeKind.ABORTED
    assert out.abort == AbortReason.UNKNOWN
    assert out.failure_detail == "synthetic abort detail"
    assert not out.allows_success_style_review
    assert not out.allows_recommendation_authority


def test_distinct_failure_detail_analysis_branches():
    base_ev = _base_evidence()
    failed = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            scoring_completed=False,
            analysis_status="failed",
            evidence=base_ev,
        )
    )
    skipped = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            scoring_completed=False,
            analysis_status="skipped",
            evidence=base_ev,
        )
    )
    not_reached = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            scoring_completed=False,
            analysis_status="running",
            evidence=base_ev,
        )
    )
    assert failed.failure_detail == "Post-campaign analysis failed."
    assert skipped.failure_detail == "Post-campaign analysis was skipped."
    assert (
        not_reached.failure_detail
        == "Post-campaign analysis and scoring did not complete."
    )


def test_distinct_failure_detail_report_branches():
    base_ev = _base_evidence()
    common = {
        "campaign_id": "c",
        "effective_campaign_id": "c",
        "scoring_completed": True,
        "passing_count": 1,
        "winner_config_id": "w",
        "evidence": base_ev,
    }
    failed = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(**common, report_ok=False, report_status="failed")
    )
    skipped = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(**common, report_ok=False, report_status="skipped")
    )
    partial = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(**common, report_ok=True, report_status="partial")
    )
    assert (
        failed.failure_detail
        == "Primary report generation failed; measurement data remains valid."
    )
    assert (
        skipped.failure_detail
        == "Primary report generation was skipped; measurement data remains valid."
    )
    assert (
        partial.failure_detail
        == "Report bundle partially generated (secondary artifacts)."
    )


def test_project_final_review_artifact_block_mode_reflects_outcome_truth() -> None:
    """Projection picks artifact prominence from outcome kind — not filesystem state."""
    happy = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            scoring_completed=True,
            passing_count=1,
            winner_config_id="w",
            report_status="complete",
            evidence=_base_evidence(),
        )
    )
    assert project_final_review(happy).artifact_block_mode == "full"

    partial = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            scoring_completed=True,
            passing_count=1,
            winner_config_id="w",
            report_status="failed",
            evidence=_base_evidence(),
        )
    )
    assert partial.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert project_final_review(partial).artifact_block_mode == "full"

    degraded = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            scoring_completed=True,
            passing_count=0,
            winner_config_id=None,
            report_status="complete",
            evidence=_base_evidence(configs_degraded=1),
        )
    )
    assert degraded.outcome_kind == CampaignOutcomeKind.DEGRADED
    assert project_final_review(degraded).artifact_block_mode == "full"

    failed = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            scoring_completed=False,
            evidence=_base_evidence(
                has_any_success_request=False,
                cycles_attempted=2,
                cycles_invalid=2,
                cycles_complete=0,
            ),
        )
    )
    assert failed.outcome_kind == CampaignOutcomeKind.FAILED
    assert project_final_review(failed).artifact_block_mode == "diagnostics_only"

    insufficient = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            scoring_completed=False,
            evidence=CampaignEvidenceSummary(
                configs_total=0,
                configs_completed=0,
                cycles_attempted=0,
                cycles_complete=0,
                cycles_invalid=0,
                has_any_success_request=False,
            ),
        )
    )
    assert insufficient.outcome_kind == CampaignOutcomeKind.INSUFFICIENT_EVIDENCE
    assert project_final_review(insufficient).artifact_block_mode == "diagnostics_only"

    aborted = outcome_evaluate.evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            user_interrupted=True,
            evidence=_base_evidence(),
        )
    )
    assert aborted.outcome_kind == CampaignOutcomeKind.ABORTED
    assert project_final_review(aborted).artifact_block_mode == "diagnostics_only"


def test_render_post_run_review_from_read_model_skips_artifact_block_when_not_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UI stays presentation-only: artifact table follows read_model.artifact_block_mode."""
    import src.ui as ui_module

    artifact_calls: list[str] = []

    def _capture_artifacts(*_a: object, **_k: object) -> None:
        artifact_calls.append("render_artifact_block")

    monkeypatch.setattr(ui_module, "render_artifact_block", _capture_artifacts)

    artifacts = [{"artifact_type": "t", "filename": "f", "path": "/x", "exists": True}]
    rm_diag = FinalReviewReadModel(
        headline_status="Failed",
        outcome_kind=CampaignOutcomeKind.FAILED,
        show_next_actions=False,
        success_style_diagnostics=False,
        failure_cause="e",
        failure_remediation=None,
        report_generation_ok=False,
        artifact_block_mode="diagnostics_only",
    )
    ui_module.render_post_run_review_from_read_model(
        campaign_id="c",
        read_model=rm_diag,
        artifacts=artifacts,
        diagnostics_path=None,
    )
    assert artifact_calls == []

    rm_full = FinalReviewReadModel(
        headline_status="Success",
        outcome_kind=CampaignOutcomeKind.SUCCESS,
        show_next_actions=True,
        success_style_diagnostics=True,
        failure_cause=None,
        failure_remediation=None,
        report_generation_ok=True,
        artifact_block_mode="full",
    )
    ui_module.render_post_run_review_from_read_model(
        campaign_id="c",
        read_model=rm_full,
        artifacts=artifacts,
        diagnostics_path=None,
    )
    assert artifact_calls == ["render_artifact_block"]


def test_projection_prefers_evaluator_failure_detail_over_runner_cause():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=False,
        report_status="failed",
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        evidence=_base_evidence(),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    rm = project_final_review(
        out,
        runner_failure_cause="Runner-only misleading cause.",
        runner_failure_remediation="Runner remediation.",
    )
    assert rm.failure_cause == out.failure_detail
    assert "Runner-only misleading cause." not in (rm.failure_cause or "")


def test_artifact_report_failure_is_not_measurement_failure():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        report_status="partial",
        run_reports_ok=False,
        evidence=_base_evidence(),
    )
    out = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert out.measurement == MeasurementPhaseVerdict.SUCCEEDED
    assert out.post_run == PostRunVerdict.REPORT_PARTIAL
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert out.failure_domain == FailureDomain.ARTIFACT_PROJECTION
    assert out.allows_success_style_review
    assert out.allows_recommendation_authority


def test_recommendation_authority_requires_more_than_report_ok_alone():
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        evidence=_base_evidence(),
    )
    good = outcome_evaluate.evaluate_campaign_outcome(inp)
    assert good.allows_recommendation_authority

    no_winner = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        scoring_completed=True,
        passing_count=1,
        winner_config_id=None,
        evidence=_base_evidence(),
    )
    assert not outcome_evaluate.evaluate_campaign_outcome(
        no_winner
    ).allows_recommendation_authority

    bad_report = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=False,
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        evidence=_base_evidence(),
    )
    br = outcome_evaluate.evaluate_campaign_outcome(bad_report)
    assert br.measurement == MeasurementPhaseVerdict.SUCCEEDED
    assert not br.allows_recommendation_authority


def test_frozen_dataclasses_immutable():
    ev = _base_evidence()
    with pytest.raises(FrozenInstanceError):
        ev.configs_total = 3  # type: ignore[misc]


def test_campaign_outcome_package_root_api_surface() -> None:
    import importlib

    co = importlib.import_module("src.campaign_outcome")

    expected = (
        "CampaignEvidenceSummary",
        "CampaignOutcomeInputs",
        "FinalReviewMetricsSnapshot",
        "evaluate_campaign_outcome",
        "project_final_review",
    )
    assert tuple(co.__all__) == expected
    for name in co.__all__:
        assert hasattr(co, name), f"missing export: {name}"
