"""Frozen contracts for campaign outcome evaluation (Slice 1).

These types define evidence shapes, verdict enums, and read models for the
finalization seam. They do not perform I/O; the runner supplies facts, the
evaluator decides outcome truth, and projection/UI consume already-decided fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

ArtifactBlockMode = Literal["full", "diagnostics_only"]


class CampaignLifecyclePhase(str, Enum):
    """Lifecycle anchor recorded on the outcome snapshot (not a live runner state machine)."""

    PREFLIGHT = "preflight"
    CAMPAIGN_REGISTERED = "campaign_registered"
    MEASUREMENT = "measurement"
    POST_MEASUREMENT = "post_measurement"
    REPORTING = "reporting"
    FINALIZATION = "finalization"


class MeasurementPhaseVerdict(str, Enum):
    """Evaluator-owned verdict for the measurement phase from DB evidence + runner flags."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    NO_EVIDENCE = "no_evidence"


class PostRunVerdict(str, Enum):
    """Post-run pipeline verdict: analysis vs report branches depend on ``scoring_completed``."""

    NOT_REACHED = "not_reached"
    ANALYSIS_FAILED = "analysis_failed"
    ANALYSIS_SKIPPED = "analysis_skipped"
    REPORT_FAILED = "report_failed"
    REPORT_SKIPPED = "report_skipped"
    REPORT_PARTIAL = "report_partial"
    REPORT_SUCCEEDED = "report_succeeded"


class CampaignOutcomeKind(str, Enum):
    """Top-level campaign outcome classification decided only in ``evaluate_campaign_outcome``."""

    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"
    PARTIAL = "partial"
    DEGRADED = "degraded"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AbortReason(str, Enum):
    """Why an abort-style outcome was chosen (orthogonal to ``FailureDomain`` for some paths)."""

    USER_INTERRUPT = "user_interrupt"
    TELEMETRY_STARTUP = "telemetry_startup"
    BACKEND_EXECUTION_POLICY = "backend_execution_policy"
    FATAL_ORCHESTRATION = "fatal_orchestration"
    UNKNOWN = "unknown"


class FailureDomain(str, Enum):
    """Which subsystem owns the failure detail for diagnostics (not the outcome kind alone)."""

    CONTRACT_CONFIG_ENV = "contract_config_env"
    BACKEND_STARTUP = "backend_startup"
    MEASUREMENT_BODY = "measurement_body"
    POST_RUN_PIPELINE = "post_run_pipeline"
    ARTIFACT_PROJECTION = "artifact_projection"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CampaignEvidenceSummary:
    """Measurement facts aggregated from SQLite by the runner.

    Counts configs/cycles/requests for lab truth lanes only. The evaluator uses
    these counters together with runner flags; this struct does not declare
    campaign success or failure by itself.
    """

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
    """Normalized bundle built by the runner for ``evaluate_campaign_outcome`` only.

    Includes DB-backed ``evidence`` plus operational flags (telemetry, policy,
    fatal measurement). ``report_status`` is the structured post-run authority
    when present. ``report_ok`` is a legacy primary-report signal:
      - ``True``: primary campaign summary generation succeeded
      - ``False``: primary campaign summary generation failed
      - ``None``: report generation was not attempted or is unknown (typically
        abort/pre-report paths)
    Measurement truth is independent; callers must not infer ``outcome_kind``
    from these fields without passing through the evaluator.
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
    report_ok: bool | None = False
    run_reports_ok: bool | None = None
    metadata_ok: bool | None = None
    last_backend_failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CampaignOutcome:
    """Authoritative outcome truth from the pure evaluator (no DB reads, no UI).

    Projection maps this into ``FinalReviewReadModel``; the UI displays strings
    and flags derived here — it must not re-decide ``outcome_kind`` or verdicts.

    ``allows_success_style_review`` is a UI/process gate, not a synonym for
    terminal ``SUCCESS``. It is true for terminal ``SUCCESS`` and for the narrow
    core-valid secondary-artifact ``PARTIAL`` case.

    ``allows_recommendation_authority`` is a strict recommendation gate. It can
    survive secondary-artifact ``PARTIAL`` only when measurement/scoring/winner
    and primary-report truth remain valid. It must fail closed for primary
    report failure, incomplete measurement, no winner, abort, and interruption.
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
    """Optional winner/run metadata passed through to the post-run review layout.

    Presentation-only numbers for Rich (winner TG, counts, mode, elapsed). They
    do not override ``CampaignOutcome`` verdicts or recommendation authority.
    """

    winner_config_id: str | None = None
    winner_tg: float | None = None
    configs_total: int | None = None
    configs_valid: int | None = None
    configs_eliminated: int | None = None
    run_mode: str | None = None
    elapsed_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class FinalReviewReadModel:
    """Post-run review read model produced by ``project_final_review``.

    Every boolean and headline here is already decided upstream (evaluator +
    projection). Callers render as-is; do not reinterpret DB or raw flags to
    change success vs failure messaging.

    ``artifact_block_mode`` is decided in projection: ``full`` surfaces the
    canonical artifact list for inspectable outcomes; ``diagnostics_only`` omits
    that table while still allowing diagnostics paths and failure copy from the
    runner (no separate “hidden” mode in Slice 1).
    """

    headline_status: str
    outcome_kind: CampaignOutcomeKind
    show_next_actions: bool
    success_style_diagnostics: bool
    failure_cause: str | None
    failure_remediation: str | None
    report_generation_ok: bool | None
    metrics: FinalReviewMetricsSnapshot | None = None
    artifact_block_mode: ArtifactBlockMode = "full"
