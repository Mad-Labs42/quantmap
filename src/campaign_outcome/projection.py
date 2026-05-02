"""Projection layer: map evaluator-owned ``CampaignOutcome`` into presentation data.

Does not consult the database or raw runner flags. Does not change outcome truth —
only selects headline copy, failure strings, and which optional sections apply.
"""

from __future__ import annotations

from src.campaign_outcome.contracts import (
    ArtifactBlockMode,
    CampaignOutcome,
    CampaignOutcomeKind,
    FinalReviewMetricsSnapshot,
    FinalReviewReadModel,
)


def _artifact_block_mode_for_outcome(outcome: CampaignOutcome) -> ArtifactBlockMode:
    """Choose artifact-table prominence from evaluator outcome truth only.

    A full artifact list signals that browsing lab outputs is a trustworthy review
    surface. That is misleading for failed, aborted, or insufficient-evidence
    campaigns even when files exist on disk. Partial and degraded outcomes still
    warrant the bundle so operators can inspect limited-but-real evidence.

    Slice 1 does not emit ``hidden`` from here; reserve it for future runner-fed
    context when neither bundle nor diagnostics copy should appear.
    """
    if outcome.outcome_kind in (
        CampaignOutcomeKind.SUCCESS,
        CampaignOutcomeKind.PARTIAL,
        CampaignOutcomeKind.DEGRADED,
    ):
        return "full"
    return "diagnostics_only"


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
    """Translate ``CampaignOutcome`` into ``FinalReviewReadModel`` for the UI.

    Chooses headline text, success-style sections, and ``artifact_block_mode``
    from fields already set by ``evaluate_campaign_outcome``. Optional
    runner-provided cause strings are display-only fallbacks when
    ``failure_detail`` is empty.
    """
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
        artifact_block_mode=_artifact_block_mode_for_outcome(outcome),
    )
