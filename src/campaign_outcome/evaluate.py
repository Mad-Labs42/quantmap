"""Pure campaign outcome evaluation."""

from __future__ import annotations

import dataclasses

from src.campaign_outcome.contracts import (
    AbortReason,
    CampaignLifecyclePhase,
    CampaignOutcome,
    CampaignOutcomeInputs,
    CampaignOutcomeKind,
    FailureDomain,
    MeasurementPhaseVerdict,
    PostRunVerdict,
)


def evaluate_campaign_outcome(inputs: CampaignOutcomeInputs) -> CampaignOutcome:
    """Derive structured outcome from runner-provided inputs only (no I/O)."""
    phase = CampaignLifecyclePhase.FINALIZATION
    ev = inputs.evidence

    if inputs.user_interrupted:
        return _finalize(
            inputs,
            outcome_kind=CampaignOutcomeKind.ABORTED,
            measurement=MeasurementPhaseVerdict.IN_PROGRESS,
            post_run=PostRunVerdict.NOT_REACHED,
            failure_domain=None,
            failure_detail="Interrupted by user.",
            abort=AbortReason.USER_INTERRUPT,
            report_ok=inputs.report_ok,
        )

    if inputs.telemetry_aborted_before_db:
        return _finalize(
            inputs,
            outcome_kind=CampaignOutcomeKind.ABORTED,
            measurement=MeasurementPhaseVerdict.NOT_STARTED,
            post_run=PostRunVerdict.NOT_REACHED,
            failure_domain=FailureDomain.CONTRACT_CONFIG_ENV,
            failure_detail="Telemetry prerequisites not met before measurement.",
            abort=AbortReason.TELEMETRY_STARTUP,
            report_ok=inputs.report_ok,
        )

    if inputs.backend_policy_blocked:
        return _finalize(
            inputs,
            outcome_kind=CampaignOutcomeKind.ABORTED,
            measurement=MeasurementPhaseVerdict.NOT_STARTED,
            post_run=PostRunVerdict.ANALYSIS_SKIPPED,
            failure_domain=FailureDomain.CONTRACT_CONFIG_ENV,
            failure_detail="Backend execution policy blocked measurement startup.",
            abort=AbortReason.BACKEND_EXECUTION_POLICY,
            report_ok=inputs.report_ok,
        )

    if inputs.fatal_exception_during_measurement:
        return _finalize(
            inputs,
            outcome_kind=CampaignOutcomeKind.FAILED,
            measurement=MeasurementPhaseVerdict.FAILED,
            post_run=PostRunVerdict.NOT_REACHED,
            failure_domain=FailureDomain.UNKNOWN,
            failure_detail=inputs.fatal_exception_message
            or "Fatal error during measurement.",
            abort=None,
            report_ok=inputs.report_ok,
        )

    measurement, measurement_failure_domain = _measurement_domain(inputs)
    post_run = _post_run_verdict(inputs)

    outcome_kind, failure_domain, failure_detail = _synthesize_outcome(
        inputs, measurement, measurement_failure_domain, post_run
    )

    allows_success = outcome_kind == CampaignOutcomeKind.SUCCESS

    # Handoff-grade authority (Slice 1): not synonymous with "measurement rows
    # exist" — requires rankable winner, completed scoring, and primary report OK.
    # ``report_ok`` in this conjunction gates user-facing review authority only;
    # it does not mean measurement evidence became scientifically invalid when false.
    allows_rec = (
        measurement
        in (MeasurementPhaseVerdict.SUCCEEDED, MeasurementPhaseVerdict.PARTIAL)
        and ev.has_any_success_request
        and inputs.scoring_completed
        and inputs.passing_count > 0
        and inputs.winner_config_id is not None
        and inputs.report_ok is True
        and not inputs.user_interrupted
        and not inputs.telemetry_aborted_before_db
        and not inputs.backend_policy_blocked
    )

    evidence_out = dataclasses.replace(
        ev,
        campaign_db_status=inputs.campaign_db_status,
        analysis_status=inputs.analysis_status,
        report_status=inputs.report_status,
    )

    return CampaignOutcome(
        outcome_kind=outcome_kind,
        lifecycle_phase_at_decision=phase,
        measurement=measurement,
        post_run=post_run,
        failure_domain=failure_domain,
        failure_detail=failure_detail,
        abort=None,
        allows_success_style_review=allows_success,
        allows_recommendation_authority=allows_rec,
        report_ok=inputs.report_ok,
        run_reports_ok=inputs.run_reports_ok,
        metadata_ok=inputs.metadata_ok,
        evidence_summary=evidence_out,
    )


def _finalize(
    inputs: CampaignOutcomeInputs,
    *,
    outcome_kind: CampaignOutcomeKind,
    measurement: MeasurementPhaseVerdict,
    post_run: PostRunVerdict,
    failure_domain: FailureDomain | None,
    failure_detail: str | None,
    abort: AbortReason | None,
    report_ok: bool | None,
) -> CampaignOutcome:
    evidence_out = dataclasses.replace(
        inputs.evidence,
        campaign_db_status=inputs.campaign_db_status,
        analysis_status=inputs.analysis_status,
        report_status=inputs.report_status,
    )
    return CampaignOutcome(
        outcome_kind=outcome_kind,
        lifecycle_phase_at_decision=CampaignLifecyclePhase.FINALIZATION,
        measurement=measurement,
        post_run=post_run,
        failure_domain=failure_domain,
        failure_detail=failure_detail,
        abort=abort,
        allows_success_style_review=False,
        allows_recommendation_authority=False,
        report_ok=report_ok,
        run_reports_ok=inputs.run_reports_ok,
        metadata_ok=inputs.metadata_ok,
        evidence_summary=evidence_out,
    )


def _measurement_domain(
    inputs: CampaignOutcomeInputs,
) -> tuple[MeasurementPhaseVerdict, FailureDomain | None]:
    ev = inputs.evidence
    lbr = inputs.last_backend_failure_reason

    if (
        ev.cycles_attempted == 0
        and ev.configs_completed == 0
        and not ev.has_any_success_request
    ):
        if ev.configs_total == 0:
            return MeasurementPhaseVerdict.NOT_STARTED, None
        return MeasurementPhaseVerdict.NO_EVIDENCE, FailureDomain.MEASUREMENT_BODY

    if ev.has_any_success_request:
        if ev.cycles_invalid > 0:
            return MeasurementPhaseVerdict.PARTIAL, None
        return MeasurementPhaseVerdict.SUCCEEDED, None

    if ev.cycles_attempted == 0:
        return MeasurementPhaseVerdict.NO_EVIDENCE, FailureDomain.MEASUREMENT_BODY

    if lbr:
        return MeasurementPhaseVerdict.FAILED, FailureDomain.BACKEND_STARTUP

    return MeasurementPhaseVerdict.FAILED, FailureDomain.MEASUREMENT_BODY


def _post_run_verdict(inputs: CampaignOutcomeInputs) -> PostRunVerdict:
    if not inputs.scoring_completed:
        if inputs.analysis_status == "failed":
            return PostRunVerdict.ANALYSIS_FAILED
        if inputs.analysis_status == "skipped":
            return PostRunVerdict.ANALYSIS_SKIPPED
        return PostRunVerdict.NOT_REACHED

    if inputs.report_ok:
        if inputs.report_status == "partial":
            return PostRunVerdict.REPORT_PARTIAL
        return PostRunVerdict.REPORT_SUCCEEDED

    return PostRunVerdict.REPORT_FAILED


def _synthesize_outcome(
    inputs: CampaignOutcomeInputs,
    measurement: MeasurementPhaseVerdict,
    measurement_failure_domain: FailureDomain | None,
    post_run: PostRunVerdict,
) -> tuple[CampaignOutcomeKind, FailureDomain | None, str | None]:
    ev = inputs.evidence

    if inputs.campaign_db_status == "complete" and not ev.has_any_success_request:
        if ev.configs_degraded > 0 and ev.configs_completed > 0:
            return (
                CampaignOutcomeKind.DEGRADED,
                FailureDomain.MEASUREMENT_BODY,
                "Campaign lifecycle completed without successful measurement requests.",
            )
        return (
            CampaignOutcomeKind.INSUFFICIENT_EVIDENCE,
            FailureDomain.MEASUREMENT_BODY,
            "Campaign lifecycle completed without successful measurement requests.",
        )

    if measurement in (
        MeasurementPhaseVerdict.NO_EVIDENCE,
        MeasurementPhaseVerdict.NOT_STARTED,
    ):
        return (
            CampaignOutcomeKind.INSUFFICIENT_EVIDENCE,
            measurement_failure_domain,
            "No measurement evidence to score.",
        )

    if measurement == MeasurementPhaseVerdict.FAILED:
        detail = (
            f"Last backend startup failure: {inputs.last_backend_failure_reason}."
            if inputs.last_backend_failure_reason
            else "Measurement did not produce successful requests."
        )
        return CampaignOutcomeKind.FAILED, measurement_failure_domain, detail

    if not inputs.scoring_completed:
        if post_run == PostRunVerdict.ANALYSIS_FAILED:
            return (
                CampaignOutcomeKind.FAILED,
                FailureDomain.POST_RUN_PIPELINE,
                "Analysis or scoring did not complete.",
            )
        return (
            CampaignOutcomeKind.FAILED,
            FailureDomain.POST_RUN_PIPELINE,
            "Analysis or scoring did not complete.",
        )

    if inputs.passing_count <= 0 or inputs.winner_config_id is None:
        if ev.configs_degraded > 0:
            return (
                CampaignOutcomeKind.DEGRADED,
                FailureDomain.MEASUREMENT_BODY,
                "No rankable winner; instrumentation or evidence quality is degraded.",
            )
        return (
            CampaignOutcomeKind.INSUFFICIENT_EVIDENCE,
            FailureDomain.MEASUREMENT_BODY,
            "No passing rankable configuration produced a winner.",
        )

    if not inputs.report_ok:
        return (
            CampaignOutcomeKind.PARTIAL,
            FailureDomain.POST_RUN_PIPELINE,
            "Primary report generation failed; measurement data remains valid.",
        )

    if post_run == PostRunVerdict.REPORT_PARTIAL:
        return (
            CampaignOutcomeKind.PARTIAL,
            FailureDomain.ARTIFACT_PROJECTION,
            "Report bundle partially generated (secondary artifacts).",
        )

    if measurement == MeasurementPhaseVerdict.PARTIAL:
        return (
            CampaignOutcomeKind.PARTIAL,
            FailureDomain.MEASUREMENT_BODY,
            "Partial measurement evidence (some invalid cycles).",
        )

    return CampaignOutcomeKind.SUCCESS, None, None
