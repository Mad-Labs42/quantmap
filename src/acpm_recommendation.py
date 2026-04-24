from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RECOMMENDATION_SCHEMA_ID = "quantmap.acpm.recommendation_record"
RECOMMENDATION_SCHEMA_VERSION = 1

STATUS_STRONG_PROVISIONAL_LEADER = "strong_provisional_leader"
STATUS_BEST_VALIDATED_CONFIG = "best_validated_config"
STATUS_NEEDS_DEEPER_VALIDATION = "needs_deeper_validation"
STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence_to_recommend"

_VALID_STATUSES = {
    STATUS_STRONG_PROVISIONAL_LEADER,
    STATUS_BEST_VALIDATED_CONFIG,
    STATUS_NEEDS_DEEPER_VALIDATION,
    STATUS_INSUFFICIENT_EVIDENCE,
}


@dataclass(slots=True)
class ACPMRecommendationRecord:
    status: str
    leading_config_id: str | None
    recommended_config_id: str | None
    caveat_codes: list[str] = field(default_factory=list)
    handoff_ready: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    schema_id: str = RECOMMENDATION_SCHEMA_ID
    schema_version: int = RECOMMENDATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"Unsupported ACPM recommendation status: {self.status}")
        if self.handoff_ready:
            if self.status != STATUS_BEST_VALIDATED_CONFIG:
                raise ValueError("handoff_ready requires best_validated_config status")
            if self.recommended_config_id is None:
                raise ValueError("handoff_ready requires recommended_config_id")

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "status": self.status,
            "leading_config_id": self.leading_config_id,
            "recommended_config_id": self.recommended_config_id,
            "caveat_codes": list(self.caveat_codes),
            "handoff_ready": self.handoff_ready,
            "evidence": dict(self.evidence),
        }


def _scoring_profile_name(scores: dict[str, Any]) -> str | None:
    scoring_profile = scores.get("scoring_profile")
    return getattr(scoring_profile, "name", None)


def _coverage_class(acpm_planning_metadata: dict[str, Any] | None) -> str | None:
    if not acpm_planning_metadata:
        return None
    coverage_policy = acpm_planning_metadata.get("coverage_policy") or {}
    value = coverage_policy.get("ngl_coverage_class")
    return value if isinstance(value, str) else None


def _selected_ngl_values(acpm_planning_metadata: dict[str, Any] | None) -> list[int]:
    if not acpm_planning_metadata:
        return []
    coverage_policy = acpm_planning_metadata.get("coverage_policy") or {}
    values = coverage_policy.get("selected_ngl_values")
    if not isinstance(values, list):
        return []
    return [int(v) for v in values]


def _derive_caveat_codes(
    *,
    winner: str | None,
    run_mode: str,
    coverage_class: str | None,
) -> list[str]:
    caveats: list[str] = []
    if winner is None:
        caveats.append("no_valid_winner")
        return caveats
    if coverage_class != "full":
        caveats.append("partial_scope")
        if coverage_class == "scaffolded_1x":
            caveats.append("scaffolded_ngl_coverage")
    if run_mode == "standard":
        caveats.append("reduced_repetition")
    elif run_mode == "quick":
        caveats.append("single_cycle_only")
    elif run_mode == "custom":
        caveats.append("reduced_repetition")
    return caveats


def _derive_status(*, winner: str | None, run_mode: str, coverage_class: str | None) -> str:
    if winner is None:
        return STATUS_INSUFFICIENT_EVIDENCE
    if coverage_class != "full":
        return STATUS_NEEDS_DEEPER_VALIDATION
    if run_mode == "full":
        return STATUS_BEST_VALIDATED_CONFIG
    if run_mode in {"standard", "quick"}:
        return STATUS_STRONG_PROVISIONAL_LEADER
    return STATUS_NEEDS_DEEPER_VALIDATION


def evaluate_acpm_recommendation(
    *,
    campaign_id: str,
    run_mode: str,
    scope_authority: str,
    scores: dict[str, Any],
    acpm_planning_metadata: dict[str, Any] | None,
) -> ACPMRecommendationRecord:
    winner = scores.get("winner")
    winner_id = winner if isinstance(winner, str) else None
    coverage_class = _coverage_class(acpm_planning_metadata)
    status = _derive_status(
        winner=winner_id,
        run_mode=run_mode,
        coverage_class=coverage_class,
    )
    recommended_config_id = winner_id if status in {
        STATUS_BEST_VALIDATED_CONFIG,
        STATUS_STRONG_PROVISIONAL_LEADER,
    } else None
    handoff_ready = status == STATUS_BEST_VALIDATED_CONFIG and recommended_config_id is not None
    caveat_codes = _derive_caveat_codes(
        winner=winner_id,
        run_mode=run_mode,
        coverage_class=coverage_class,
    )
    evidence = {
        "campaign_id": campaign_id,
        "run_mode": run_mode,
        "scope_authority": scope_authority,
        "coverage_class": coverage_class,
        "selected_ngl_values": _selected_ngl_values(acpm_planning_metadata),
        "scoring_profile_name": _scoring_profile_name(scores),
        "methodology_snapshot_id": scores.get("methodology_snapshot_id"),
    }
    return ACPMRecommendationRecord(
        status=status,
        leading_config_id=winner_id,
        recommended_config_id=recommended_config_id,
        caveat_codes=caveat_codes,
        handoff_ready=handoff_ready,
        evidence=evidence,
    )
