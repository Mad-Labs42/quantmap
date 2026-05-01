"""Campaign outcome seam (Slice 1): pure evaluation + projection."""

from __future__ import annotations

from src.campaign_outcome.contracts import (
    CampaignEvidenceSummary,
    CampaignOutcomeInputs,
    FinalReviewMetricsSnapshot,
)
from src.campaign_outcome.evaluate import evaluate_campaign_outcome
from src.campaign_outcome.projection import project_final_review

__all__ = [
    "CampaignEvidenceSummary",
    "CampaignOutcomeInputs",
    "FinalReviewMetricsSnapshot",
    "evaluate_campaign_outcome",
    "project_final_review",
]
