"""Frozen contracts for campaign outcome evaluation (Slice 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

ArtifactBlockMode = Literal["full", "diagnostics_only", "hidden"]


class CampaignLifecyclePhase(str, Enum):
    PREFLIGHT = "preflight"
    CAMPAIGN_REGISTERED = "campaign_registered"
    MEASUREMENT = "measurement"
    POST_MEASUREMENT = "post_measurement"
    REPORTING = "reporting"
    FINALIZATION = "finalization"


class MeasurementPhaseVerdict(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    NO_EVIDENCE = "no_evidence"


class PostRunVerdict(str, Enum):
    NOT_REACHED = "not_reached"
    ANALYSIS_FAILED = "analysis_failed"
    ANALYSIS_SKIPPED = "analysis_skipped"
    REPORT_FAILED = "report_failed"
    REPORT_PARTIAL = "report_partial"
    REPORT_SUCCEEDED = "report_succeeded"


class CampaignOutcomeKind(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"
    PARTIAL = "partial"
    DEGRADED = "degraded"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AbortReason(str, Enum):
    USER_INTERRUPT = "user_interrupt"
    TELEMETRY_STARTUP = "telemetry_startup"
    BACKEND_EXECUTION_POLICY = "backend_execution_policy"
    FATAL_ORCHESTRATION = "fatal_orchestration"
    UNKNOWN = "unknown"


class FailureDomain(str, Enum):
    CONTRACT_CONFIG_ENV = "contract_config_env"
    BACKEND_STARTUP = "backend_startup"
    MEASUREMENT_BODY = "measurement_body"
    POST_RUN_PIPELINE = "post_run_pipeline"
    ARTIFACT_PROJECTION = "artifact_projection"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CampaignEvidenceSummary:
    """Measurement-truth summary assembled by the runner (DB), not the evaluator."""

    configs_total: int = 0
    configs_completed: int = 0
    configs_oom: int = 0
    configs_skipped_oom: int = 0
    configs_degraded: int = 0
    cycles_attempted: int = 0
    cycles_complete: int = 0
    cycles_invalid: int = 0
    has_any_success_request: bool = False
    rankable_config_count: int | None = None
    winner_present: bool = False
    campaign_db_status: str | None = None
    analysis_status: str | None = None
    report_status: str | None = None


@dataclass(frozen=True, slots=True)
class CampaignOutcomeInputs:
    """Facts supplied by the runner for ``evaluate_campaign_outcome`` only.

    ``report_ok`` means primary campaign-summary report generation
    (``generate_report``) succeeded. When false, measurement and DB evidence
    can still be valid — the evaluator must not treat this flag as erasing
    measurement truth.
    """

    campaign_id: str
    effective_campaign_id: str
    campaign_db_status: str | None = None
    analysis_status: str | None = None
    report_status: str | None = None
    failure_reason: str | None = None
    user_interrupted: bool = False
    telemetry_aborted_before_db: bool = False
    backend_policy_blocked: bool = False
    fatal_exception_during_measurement: bool = False
    fatal_exception_message: str | None = None
    evidence: CampaignEvidenceSummary = field(default_factory=CampaignEvidenceSummary)
    scoring_completed: bool = False
    passing_count: int = 0
    eliminated_count: int = 0
    unrankable_count: int = 0
    winner_config_id: str | None = None
    unrankable_reason: str | None = None
    report_ok: bool = False
    run_reports_ok: bool | None = None
    metadata_ok: bool | None = None
    last_backend_failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CampaignOutcome:
    """Structured outcome from the pure evaluator; UI renders, it does not decide.

    ``allows_recommendation_authority`` is a narrow Slice-1 **user-facing review
    gate** (measurement succeeded, scoring completed, rankable winner, primary
    report OK for handoff-style messaging). It is not a scientific invalidation
    of measurement rows; ``report_ok`` here gates that review surface only, not
    whether raw measurement data in the lab DB is trustworthy.
    """

    outcome_kind: CampaignOutcomeKind
    lifecycle_phase_at_decision: CampaignLifecyclePhase
    measurement: MeasurementPhaseVerdict
    post_run: PostRunVerdict
    failure_domain: FailureDomain | None
    failure_detail: str | None
    abort: AbortReason | None
    allows_success_style_review: bool
    allows_recommendation_authority: bool
    report_ok: bool | None
    run_reports_ok: bool | None
    metadata_ok: bool | None
    evidence_summary: CampaignEvidenceSummary


@dataclass(frozen=True, slots=True)
class FinalReviewMetricsSnapshot:
    winner_config_id: str | None = None
    winner_tg: float | None = None
    configs_total: int | None = None
    configs_valid: int | None = None
    configs_eliminated: int | None = None
    run_mode: str | None = None
    elapsed_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class FinalReviewReadModel:
    """Presentation DTO for post-run review; truth is decided in ``evaluate_campaign_outcome``."""

    headline_status: str
    outcome_kind: CampaignOutcomeKind
    show_next_actions: bool
    success_style_diagnostics: bool
    failure_cause: str | None
    failure_remediation: str | None
    report_generation_ok: bool | None
    metrics: FinalReviewMetricsSnapshot | None = None
    artifact_block_mode: ArtifactBlockMode = "full"
