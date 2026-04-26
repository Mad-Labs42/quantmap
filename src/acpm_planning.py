"""
QuantMap — acpm_planning.py

Structural ACPM planner contracts.

This module intentionally defines planner/orchestrator boundaries only.  It
owns conservative applicability, repeat-tier compilation, and planner-to-
execution compilation. It does not own scoring policy, filter policy,
recommendations, report wording, or handoff generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.run_plan import SCOPE_AUTHORITY_PLANNER

ACPM_PLANNING_METADATA_SCHEMA_ID = "quantmap.acpm.planning_metadata"
ACPM_PLANNING_METADATA_SCHEMA_VERSION = 1
_ALLOWED_RUN_MODES = {"full", "standard", "quick", "custom"}
_SUPPORTED_VARIABLES = frozenset({"n_gpu_layers"})
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

V1_ACPM_PROFILE_IDS: frozenset[str] = frozenset({"Balanced", "T/S", "TTFT"})
REPEAT_TIER_1X = "1x"
REPEAT_TIER_3X = "3x"
REPEAT_TIER_5X = "5x"
NGL_SCAFFOLD_1X = [10, 30, 50, 70, 90, 999]
NGL_COVERAGE_CLASS_SCAFFOLDED_1X = "scaffolded_1x"
NGL_COVERAGE_CLASS_FULL = "full"
NGL_SCAFFOLD_POLICY_ID = "acpm_v1_ngl_scaffold_1x"
_REPEAT_TIER_TO_RUN_MODE = {
    REPEAT_TIER_1X: "quick",
    REPEAT_TIER_3X: "standard",
    REPEAT_TIER_5X: "full",
}

_ACPM_PROFILE_REGISTRY: dict[str, dict[str, str]] = {
    "Balanced": {
        "scoring_profile_name": "acpm_balanced_v1",
        "display_label": "Balanced",
        "display_name": "Balanced",
        "lens_description": (
            "Mixed practical recommendation lens. "
            "Ranking balances throughput and latency."
        ),
    },
    "T/S": {
        "scoring_profile_name": "acpm_ts_v1",
        "display_label": "T/S (Throughput/Speed)",
        "display_name": "Throughput/Speed (T/S)",
        "lens_description": (
            "Throughput-biased lens. "
            "Prioritizes sustained token generation rate and floor."
        ),
    },
    "TTFT": {
        "scoring_profile_name": "acpm_ttft_v1",
        "display_label": "TTFT",
        "display_name": "Time-to-First-Token (TTFT)",
        "lens_description": (
            "Latency-biased lens. "
            "Prioritizes warm and cold first-token responsiveness."
        ),
    },
}


def get_acpm_profile_info(profile_id: str) -> dict[str, str]:
    """Return registry entry for an ACPM profile ID; raise ValueError if unknown."""
    if profile_id not in _ACPM_PROFILE_REGISTRY:
        raise ValueError(
            f"Unknown ACPM profile ID {profile_id!r}. "
            f"Valid IDs: {sorted(V1_ACPM_PROFILE_IDS)}"
        )
    return _ACPM_PROFILE_REGISTRY[profile_id]


def load_acpm_scoring_profile(
    profile_id: str,
    profiles_dir: Path | None = None,
) -> Any:
    """Load and validate the governance ExperimentProfile for an ACPM profile ID."""
    from src.governance import load_profile, load_registry, validate_profile_against_registry

    info = get_acpm_profile_info(profile_id)
    profile = load_profile(info["scoring_profile_name"], profiles_dir=profiles_dir)
    registry = load_registry()
    validate_profile_against_registry(profile, registry)
    return profile


def _reject_shadow_truth_fields(value: Any) -> None:
    """Recursively raise ValueError if any dict key is a forbidden shadow-truth field."""
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
class ACPMApplicabilityResult:
    """Planner-side structural applicability outcome."""

    applicable: bool
    reason: str | None
    campaign_id: str
    variable: str
    all_values: list[int]


def _validate_int_values(values: list[Any]) -> list[int]:
    """Validate campaign values as a list of positive ints; raise ValueError if invalid."""
    if len(values) < 2:
        raise ValueError("ACPM applicability requires at least two campaign values")
    normalized: list[int] = []
    for value in values:
        if not isinstance(value, int):
            raise ValueError("ACPM applicability requires integer campaign values")
        if value <= 0:
            raise ValueError("ACPM applicability requires positive campaign values")
        normalized.append(value)
    return normalized


def _config_id_for_value(campaign_id: str, value: int) -> str:
    """Derive a deterministic config ID from a campaign ID and a single integer value."""
    value_text = (
        str(value)
        .replace(".", "p")
        .replace("-", "m")
        .replace(",", "")
        .replace("=", "e")
    )[:12]
    return f"{campaign_id}_{value_text}"


def check_campaign_applicability(campaign: dict[str, Any]) -> ACPMApplicabilityResult:
    """Return a structural applicability decision for ACPM Slice 4."""

    campaign_id = str(campaign.get("campaign_id") or "")
    variable = str(campaign.get("variable") or "")
    raw_values = campaign.get("values")
    if variable not in _SUPPORTED_VARIABLES:
        return ACPMApplicabilityResult(
            applicable=False,
            reason="unsupported_variable",
            campaign_id=campaign_id,
            variable=variable,
            all_values=[],
        )
    if not isinstance(raw_values, list):
        return ACPMApplicabilityResult(
            applicable=False,
            reason="invalid_values",
            campaign_id=campaign_id,
            variable=variable,
            all_values=[],
        )
    try:
        all_values = _validate_int_values(raw_values)
    except ValueError as exc:
        return ACPMApplicabilityResult(
            applicable=False,
            reason=str(exc),
            campaign_id=campaign_id,
            variable=variable,
            all_values=[],
        )
    return ACPMApplicabilityResult(
        applicable=True,
        reason=None,
        campaign_id=campaign_id,
        variable=variable,
        all_values=all_values,
    )


def compile_repeat_tier(
    repeat_tier: str,
    all_values: list[int],
) -> tuple[list[int], str, dict[str, Any]]:
    """Compile a planner repeat tier into selected values and execution mode."""

    if repeat_tier not in _REPEAT_TIER_TO_RUN_MODE:
        raise ValueError(f"Unknown ACPM repeat tier {repeat_tier!r}")
    normalized_values = _validate_int_values(list(all_values))
    run_mode = _REPEAT_TIER_TO_RUN_MODE[repeat_tier]
    if repeat_tier == REPEAT_TIER_1X:
        selected_values = [value for value in NGL_SCAFFOLD_1X if value in normalized_values]
        if not selected_values:
            raise ValueError("ACPM 1x scaffold produced an empty selected value set")
        coverage_policy: dict[str, Any] = {
            "ngl_coverage_class": NGL_COVERAGE_CLASS_SCAFFOLDED_1X,
            "scaffold_policy_id": NGL_SCAFFOLD_POLICY_ID,
            "selected_ngl_values": selected_values,
        }
        return selected_values, run_mode, coverage_policy
    coverage_policy = {
        "ngl_coverage_class": NGL_COVERAGE_CLASS_FULL,
        "scaffold_policy_id": None,
        "selected_ngl_values": normalized_values,
    }
    return normalized_values, run_mode, coverage_policy


def compile_acpm_plan(
    campaign: dict[str, Any],
    profile_name: str,
    repeat_tier: str,
    source_campaign_ref: str | None = None,
    planner_id: str = "acpm-v1",
    planner_version: str = "0.1",
    planner_policy_id: str = "acpm_slice4",
) -> "ACPMPlannerOutput":
    """Compile a minimal Slice 4 ACPM planner output."""

    applicability = check_campaign_applicability(campaign)
    if not applicability.applicable:
        raise ValueError(
            f"Campaign {applicability.campaign_id!r} is not ACPM-applicable: "
            f"{applicability.reason}"
        )
    get_acpm_profile_info(profile_name)
    selected_values, run_mode, coverage_policy = compile_repeat_tier(
        repeat_tier,
        applicability.all_values,
    )
    campaign_id = applicability.campaign_id or "unknown_campaign"
    selected_config_ids = [
        _config_id_for_value(campaign_id, value)
        for value in selected_values
    ]
    metadata = ACPMPlanningMetadata(
        planner_id=planner_id,
        planner_version=planner_version,
        planner_policy_id=planner_policy_id,
        profile_name=profile_name,
        repeat_tier=repeat_tier,
        scope_authority=SCOPE_AUTHORITY_PLANNER,
        source_campaign_ref=source_campaign_ref or f"configs/campaigns/{campaign_id}.yaml",
        selected_scope_digest=(
            f"{campaign_id}:{profile_name}:{repeat_tier}:"
            + ",".join(str(value) for value in selected_values)
        ),
        narrowing_steps=[
            {
                "step": "applicability",
                "reason": "structural_campaign_accepted",
                "variable": applicability.variable,
            },
            {
                "step": "repeat_tier_compiled",
                "reason": repeat_tier,
                "selected_values": selected_values,
            },
        ],
        coverage_policy=coverage_policy,
    )
    return ACPMPlannerOutput(
        selected_scope=ACPMSelectedScope(
            variable=applicability.variable,
            selected_values=selected_values,
            selected_config_ids=selected_config_ids,
        ),
        run_mode=run_mode,
        profile_name=profile_name,
        repeat_tier=repeat_tier,
        planning_metadata=metadata,
    )


@dataclass(frozen=True)
class ACPMSelectedScope:
    """Planner-selected scope summary used to compile later execution inputs."""

    variable: str
    selected_values: list[Any]
    selected_config_ids: list[str]

    def __post_init__(self) -> None:
        """Validate that variable is non-empty after construction."""
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
        if self.profile_name not in V1_ACPM_PROFILE_IDS:
            raise ValueError(
                f"profile_name must be one of {sorted(V1_ACPM_PROFILE_IDS)}, "
                f"got {self.profile_name!r}"
            )
        _reject_shadow_truth_fields(self.narrowing_steps)
        _reject_shadow_truth_fields(self.coverage_policy)

    def to_snapshot_dict(self) -> dict[str, Any]:
        """Return a serialisable dict representation for DB persistence."""
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
        """Validate run_mode, scope_authority, and cross-field consistency."""
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
        """Return the compact execution-layer input dict derived from this plan."""
        return {
            "run_mode": self.run_mode,
            "scope_authority": self.scope_authority,
            "selected_values": self.selected_scope.selected_values,
            "selected_config_ids": self.selected_scope.selected_config_ids,
            "scoring_profile_name": get_acpm_profile_info(self.profile_name)[
                "scoring_profile_name"
            ],
        }

    def to_planning_metadata_snapshot(self) -> dict[str, Any]:
        """Return the planning metadata as a snapshot dict for DB persistence."""
        return self.planning_metadata.to_snapshot_dict()
