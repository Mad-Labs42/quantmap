"""Project CampaignOutcome into a UI-facing read model (no ui imports)."""

from __future__ import annotations

from src.campaign_outcome.contracts import (
    CampaignOutcome,
    CampaignOutcomeKind,
    FinalReviewMetricsSnapshot,
    FinalReviewReadModel,
)


_HEADLINE: dict[CampaignOutcomeKind, str] = {
    CampaignOutcomeKind.SUCCESS: "Success",
    CampaignOutcomeKind.FAILED: "Failed — campaign did not complete successfully",
    CampaignOutcomeKind.ABORTED: "Aborted — campaign did not complete successfully",
    CampaignOutcomeKind.PARTIAL: "Only partial evidence — not a full success",
    CampaignOutcomeKind.DEGRADED: "Degraded evidence — not a full success",
    CampaignOutcomeKind.INSUFFICIENT_EVIDENCE: "Insufficient evidence — not a successful outcome",
}


def project_final_review(
    outcome: CampaignOutcome,
    *,
    metrics: FinalReviewMetricsSnapshot | None = None,
    runner_failure_cause: str | None = None,
    runner_failure_remediation: str | None = None,
) -> FinalReviewReadModel:
    """Map outcome + optional runner strings into a presentation read model."""
    headline = _HEADLINE.get(outcome.outcome_kind, outcome.outcome_kind.value.title())
    show_next = outcome.allows_success_style_review
    success_diag = outcome.allows_success_style_review

    failure_cause = outcome.failure_detail or runner_failure_cause
    failure_remediation = runner_failure_remediation
    if outcome.abort is not None and failure_cause is None:
        failure_cause = f"Aborted: {outcome.abort.value}."

    return FinalReviewReadModel(
        headline_status=headline,
        outcome_kind=outcome.outcome_kind,
        show_next_actions=show_next,
        success_style_diagnostics=success_diag,
        failure_cause=failure_cause,
        failure_remediation=failure_remediation,
        report_generation_ok=outcome.report_ok,
        metrics=metrics,
        artifact_block_mode="full",
    )
