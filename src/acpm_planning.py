"""
QuantMap — acpm_planning.py

Structural ACPM planner contracts.

This module intentionally defines planner/orchestrator boundaries only.  It
does not implement planner heuristics, scoring profiles, filter policy,
recommendations, report wording, or handoff generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.run_plan import SCOPE_AUTHORITY_PLANNER

ACPM_PLANNING_METADATA_SCHEMA_ID = "quantmap.acpm.planning_metadata"
ACPM_PLANNING_METADATA_SCHEMA_VERSION = 1
_ALLOWED_RUN_MODES = {"full", "standard", "quick", "custom"}
_FORBIDDEN_PLANNING_METADATA_KEYS = {
    "run_plan",
    "run_plan_json",
    "effective_filter_policy",
    "effective_filter_policy_json",
    "scores",
    "score_results",
    "recommendation",
    "recommendation_status",
    "recommended_config_id",
    "leading_config_id",
}


def _reject_shadow_truth_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if key_text in _FORBIDDEN_PLANNING_METADATA_KEYS:
                raise ValueError(
                    f"ACPM planning metadata must not contain shadow truth field {key_text!r}"
                )
            _reject_shadow_truth_fields(child)
    elif isinstance(value, list):
        for child in value:
            _reject_shadow_truth_fields(child)


@dataclass(frozen=True)
class ACPMSelectedScope:
    """Planner-selected scope summary used to compile later execution inputs."""

    variable: str
    selected_values: list[Any]
    selected_config_ids: list[str]

    def __post_init__(self) -> None:
        if not self.variable:
            raise ValueError("selected scope requires a variable")


@dataclass(frozen=True)
class ACPMPlanningMetadata:
    """Immutable adjacent planner provenance, not execution truth."""

    planner_id: str
    planner_version: str
    planner_policy_id: str
    profile_name: str
    repeat_tier: str
    scope_authority: str
    source_campaign_ref: str
    selected_scope_digest: str
    narrowing_steps: list[dict[str, Any]] = field(default_factory=list)
    coverage_policy: dict[str, Any] = field(default_factory=dict)
    schema_id: str = ACPM_PLANNING_METADATA_SCHEMA_ID
    schema_version: int = ACPM_PLANNING_METADATA_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_id != ACPM_PLANNING_METADATA_SCHEMA_ID:
            raise ValueError(f"schema_id must be {ACPM_PLANNING_METADATA_SCHEMA_ID!r}")
        if self.schema_version != ACPM_PLANNING_METADATA_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {ACPM_PLANNING_METADATA_SCHEMA_VERSION}"
            )
        if self.scope_authority != SCOPE_AUTHORITY_PLANNER:
            raise ValueError("ACPM planning metadata requires scope_authority='planner'")
        for field_name in (
            "planner_id",
            "planner_version",
            "planner_policy_id",
            "profile_name",
            "repeat_tier",
            "source_campaign_ref",
            "selected_scope_digest",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} is required")
        _reject_shadow_truth_fields(self.narrowing_steps)
        _reject_shadow_truth_fields(self.coverage_policy)

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "planner_id": self.planner_id,
            "planner_version": self.planner_version,
            "planner_policy_id": self.planner_policy_id,
            "profile_name": self.profile_name,
            "repeat_tier": self.repeat_tier,
            "scope_authority": self.scope_authority,
            "source_campaign_ref": self.source_campaign_ref,
            "selected_scope_digest": self.selected_scope_digest,
            "narrowing_steps": self.narrowing_steps,
            "coverage_policy": self.coverage_policy,
        }


@dataclass(frozen=True)
class ACPMPlannerOutput:
    """Typed planner output that can later compile into existing execution."""

    selected_scope: ACPMSelectedScope
    run_mode: str
    profile_name: str
    repeat_tier: str
    planning_metadata: ACPMPlanningMetadata
    scope_authority: str = SCOPE_AUTHORITY_PLANNER

    def __post_init__(self) -> None:
        if self.run_mode not in _ALLOWED_RUN_MODES:
            raise ValueError(
                f"run_mode must be one of {sorted(_ALLOWED_RUN_MODES)}, got {self.run_mode!r}"
            )
        if self.scope_authority != SCOPE_AUTHORITY_PLANNER:
            raise ValueError("ACPM planner output requires scope_authority='planner'")
        if self.profile_name != self.planning_metadata.profile_name:
            raise ValueError("profile_name must match planning_metadata.profile_name")
        if self.repeat_tier != self.planning_metadata.repeat_tier:
            raise ValueError("repeat_tier must match planning_metadata.repeat_tier")
        if self.scope_authority != self.planning_metadata.scope_authority:
            raise ValueError(
                "scope_authority must match planning_metadata.scope_authority"
            )

    def to_execution_inputs(self) -> dict[str, Any]:
        return {
            "run_mode": self.run_mode,
            "scope_authority": self.scope_authority,
            "selected_values": self.selected_scope.selected_values,
            "selected_config_ids": self.selected_scope.selected_config_ids,
        }

    def to_planning_metadata_snapshot(self) -> dict[str, Any]:
        return self.planning_metadata.to_snapshot_dict()
