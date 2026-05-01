"""Slice 1 tests: pure campaign outcome evaluation and projection."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.campaign_outcome import evaluate_campaign_outcome, project_final_review
from src.campaign_outcome.contracts import (
    AbortReason,
    CampaignEvidenceSummary,
    CampaignOutcomeInputs,
    CampaignOutcomeKind,
    FailureDomain,
    MeasurementPhaseVerdict,
    PostRunVerdict,
)


def _base_evidence(**kwargs) -> CampaignEvidenceSummary:
    defaults = dict(
        configs_total=2,
        configs_completed=2,
        configs_oom=0,
        configs_skipped_oom=0,
        configs_degraded=0,
        cycles_attempted=4,
        cycles_complete=4,
        cycles_invalid=0,
        has_any_success_request=True,
        campaign_db_status="complete",
    )
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
    out = evaluate_campaign_outcome(inp)
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
    out = evaluate_campaign_outcome(inp)
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
    out = evaluate_campaign_outcome(inp)
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
    out = evaluate_campaign_outcome(inp)
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
    out = evaluate_campaign_outcome(inp)
    assert out.outcome_kind == CampaignOutcomeKind.ABORTED
    assert out.abort == AbortReason.USER_INTERRUPT


def test_backend_startup_distinct_from_measurement_body():
    ev_startup = _base_evidence(
        has_any_success_request=False,
        cycles_attempted=2,
        cycles_invalid=2,
        cycles_complete=0,
    )
    inp_b = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        campaign_db_status="running",
        last_backend_failure_reason="startup_timeout",
        scoring_completed=False,
        evidence=ev_startup,
    )
    out_b = evaluate_campaign_outcome(inp_b)
    assert out_b.failure_domain == FailureDomain.BACKEND_STARTUP

    ev_body = _base_evidence(
        has_any_success_request=False,
        cycles_attempted=2,
        cycles_invalid=2,
        cycles_complete=0,
    )
    inp_body = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        campaign_db_status="running",
        scoring_completed=False,
        evidence=ev_body,
    )
    out_body = evaluate_campaign_outcome(inp_body)
    assert out_body.failure_domain == FailureDomain.MEASUREMENT_BODY


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
    out = evaluate_campaign_outcome(inp)
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
    out = evaluate_campaign_outcome(inp)
    assert out.outcome_kind in (
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
    out = evaluate_campaign_outcome(inp)
    assert out.measurement == MeasurementPhaseVerdict.PARTIAL
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert not out.allows_success_style_review


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
    out = evaluate_campaign_outcome(inp)
    assert out.measurement == MeasurementPhaseVerdict.SUCCEEDED
    assert out.post_run == PostRunVerdict.REPORT_PARTIAL
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert out.failure_domain == FailureDomain.ARTIFACT_PROJECTION


@pytest.mark.parametrize(
    ("report_status", "expected_post_run"),
    (
        ("failed", PostRunVerdict.REPORT_FAILED),
        ("skipped", PostRunVerdict.ANALYSIS_SKIPPED),
    ),
)
def test_explicit_report_status_blocks_success_when_report_ok_is_stale(
    report_status: str,
    expected_post_run: PostRunVerdict,
):
    inp = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=True,
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        report_status=report_status,
        evidence=_base_evidence(),
    )
    out = evaluate_campaign_outcome(inp)
    assert out.measurement == MeasurementPhaseVerdict.SUCCEEDED
    assert out.post_run == expected_post_run
    assert out.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert out.failure_domain == FailureDomain.POST_RUN_PIPELINE
    assert not out.allows_success_style_review
    assert not out.allows_recommendation_authority


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
    good = evaluate_campaign_outcome(inp)
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
    assert not evaluate_campaign_outcome(no_winner).allows_recommendation_authority

    bad_report = CampaignOutcomeInputs(
        campaign_id="c",
        effective_campaign_id="c",
        report_ok=False,
        scoring_completed=True,
        passing_count=1,
        winner_config_id="w",
        evidence=_base_evidence(),
    )
    br = evaluate_campaign_outcome(bad_report)
    assert br.measurement == MeasurementPhaseVerdict.SUCCEEDED
    assert not br.allows_recommendation_authority


def test_frozen_dataclasses_immutable():
    ev = _base_evidence()
    with pytest.raises(FrozenInstanceError):
        ev.configs_total = 3  # type: ignore[misc]


def test_campaign_outcome_package_root_api_surface() -> None:
    import src.campaign_outcome as co

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
