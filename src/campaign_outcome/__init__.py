"""Campaign outcome seam (Slice 1): contracts, pure evaluator, and projection.

Public exports are the stable integration surface for ``runner`` / CLI: build
``CampaignOutcomeInputs`` from lab evidence, call ``evaluate_campaign_outcome``,
then ``project_final_review`` before rendering. Outcome truth is not derived here.
"""

from __future__ import annotations

from src.campaign_outcome.contracts import (
    CampaignEvidenceSummary,
    CampaignOutcome,
    CampaignOutcomeInputs,
    FinalReviewMetricsSnapshot,
    FinalReviewReadModel,
)
from src.campaign_outcome.evaluate import evaluate_campaign_outcome
from src.campaign_outcome.projection import project_final_review

__all__ = [
    "CampaignEvidenceSummary",
    "CampaignOutcome",
    "CampaignOutcomeInputs",
    "FinalReviewMetricsSnapshot",
    "FinalReviewReadModel",
    "evaluate_campaign_outcome",
    "project_final_review",
]
