"""Pure campaign outcome evaluation."""

from __future__ import annotations

import dataclasses

from src.campaign_outcome.contracts import (
    AbortReason,
    CampaignEvidenceSummary,
    CampaignLifecyclePhase,
    CampaignOutcome,
    CampaignOutcomeInputs,
    CampaignOutcomeKind,
    FailureDomain,
    MeasurementPhaseVerdict,
    PostRunVerdict,
)

_OutcomeSynth = tuple[CampaignOutcomeKind, FailureDomain | None, str | None]


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

    # Handoff-grade authority (Slice 1): requires full measurement success (not
    # PARTIAL), normalized post-run success, rankable winner, and negative gates.
    allows_rec = (
        _measurement_supports_authority(measurement)
        and ev.has_any_success_request
        and _scoring_supports_authority(inputs, post_run)
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


def _measurement_supports_authority(m: MeasurementPhaseVerdict) -> bool:
    return m == MeasurementPhaseVerdict.SUCCEEDED


def _scoring_supports_authority(
    inputs: CampaignOutcomeInputs, post_run: PostRunVerdict
) -> bool:
    return (
        inputs.scoring_completed
        and inputs.passing_count > 0
        and inputs.winner_config_id is not None
        and post_run == PostRunVerdict.REPORT_SUCCEEDED
    )


def _post_run_verdict(inputs: CampaignOutcomeInputs) -> PostRunVerdict:
    analysis_s = (inputs.analysis_status or "").lower()
    report_s = (inputs.report_status or "").lower()

    if not inputs.scoring_completed:
        if analysis_s == "failed":
            return PostRunVerdict.ANALYSIS_FAILED
        if analysis_s == "skipped":
            return PostRunVerdict.ANALYSIS_SKIPPED
        return PostRunVerdict.NOT_REACHED

    # Structured post-run/report status overrides raw report_ok (Slice 1 truth lane).
    if report_s == "failed":
        return PostRunVerdict.REPORT_FAILED
    if report_s == "skipped":
        return PostRunVerdict.REPORT_SKIPPED
    if report_s == "partial":
        return PostRunVerdict.REPORT_PARTIAL

    if inputs.report_ok:
        return PostRunVerdict.REPORT_SUCCEEDED

    return PostRunVerdict.REPORT_FAILED


def _outcome_gate_lifecycle_complete_no_success(
    inputs: CampaignOutcomeInputs,
    ev: CampaignEvidenceSummary,
    measurement_failure_domain: FailureDomain | None,
) -> _OutcomeSynth | None:
    if inputs.campaign_db_status != "complete" or ev.has_any_success_request:
        return None
    # Preserve _measurement_domain's domain (e.g. BACKEND_STARTUP); do not mask
    # startup failures as generic MEASUREMENT_BODY when lifecycle is complete.
    _lifecycle_domain = measurement_failure_domain or FailureDomain.MEASUREMENT_BODY
    _msg = "Campaign lifecycle completed without successful measurement requests."
    if ev.configs_degraded > 0 and ev.configs_completed > 0:
        return CampaignOutcomeKind.DEGRADED, _lifecycle_domain, _msg
    return CampaignOutcomeKind.INSUFFICIENT_EVIDENCE, _lifecycle_domain, _msg


def _outcome_gate_no_measurement_evidence(
    measurement: MeasurementPhaseVerdict,
    measurement_failure_domain: FailureDomain | None,
) -> _OutcomeSynth | None:
    if measurement not in (
        MeasurementPhaseVerdict.NO_EVIDENCE,
        MeasurementPhaseVerdict.NOT_STARTED,
    ):
        return None
    return (
        CampaignOutcomeKind.INSUFFICIENT_EVIDENCE,
        measurement_failure_domain,
        "No measurement evidence to score.",
    )


def _outcome_gate_measurement_failed(
    inputs: CampaignOutcomeInputs,
    measurement: MeasurementPhaseVerdict,
    measurement_failure_domain: FailureDomain | None,
) -> _OutcomeSynth | None:
    if measurement != MeasurementPhaseVerdict.FAILED:
        return None
    detail = (
        f"Last backend startup failure: {inputs.last_backend_failure_reason}."
        if inputs.last_backend_failure_reason
        else "Measurement did not produce successful requests."
    )
    return CampaignOutcomeKind.FAILED, measurement_failure_domain, detail


def _outcome_gate_scoring_not_completed(
    inputs: CampaignOutcomeInputs, post_run: PostRunVerdict
) -> _OutcomeSynth | None:
    if inputs.scoring_completed:
        return None
    if post_run == PostRunVerdict.ANALYSIS_FAILED:
        return (
            CampaignOutcomeKind.FAILED,
            FailureDomain.POST_RUN_PIPELINE,
            "Post-campaign analysis failed.",
        )
    if post_run == PostRunVerdict.ANALYSIS_SKIPPED:
        return (
            CampaignOutcomeKind.FAILED,
            FailureDomain.POST_RUN_PIPELINE,
            "Post-campaign analysis was skipped.",
        )
    return (
        CampaignOutcomeKind.FAILED,
        FailureDomain.POST_RUN_PIPELINE,
        "Post-campaign analysis and scoring did not complete.",
    )


def _outcome_gate_no_rankable_winner(
    inputs: CampaignOutcomeInputs, ev: CampaignEvidenceSummary
) -> _OutcomeSynth | None:
    if inputs.passing_count > 0 and inputs.winner_config_id is not None:
        return None
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


def _outcome_gate_post_run_report(
    post_run: PostRunVerdict,
) -> _OutcomeSynth | None:
    if post_run == PostRunVerdict.REPORT_FAILED:
        return (
            CampaignOutcomeKind.PARTIAL,
            FailureDomain.POST_RUN_PIPELINE,
            "Primary report generation failed; measurement data remains valid.",
        )
    if post_run == PostRunVerdict.REPORT_SKIPPED:
        return (
            CampaignOutcomeKind.PARTIAL,
            FailureDomain.POST_RUN_PIPELINE,
            "Primary report generation was skipped; measurement data remains valid.",
        )
    if post_run == PostRunVerdict.REPORT_PARTIAL:
        return (
            CampaignOutcomeKind.PARTIAL,
            FailureDomain.ARTIFACT_PROJECTION,
            "Report bundle partially generated (secondary artifacts).",
        )
    return None


def _outcome_gate_partial_measurement(
    measurement: MeasurementPhaseVerdict,
) -> _OutcomeSynth | None:
    if measurement != MeasurementPhaseVerdict.PARTIAL:
        return None
    return (
        CampaignOutcomeKind.PARTIAL,
        FailureDomain.MEASUREMENT_BODY,
        "Partial measurement evidence (some invalid cycles).",
    )


def _synthesize_outcome(
    inputs: CampaignOutcomeInputs,
    measurement: MeasurementPhaseVerdict,
    measurement_failure_domain: FailureDomain | None,
    post_run: PostRunVerdict,
) -> _OutcomeSynth:
    ev = inputs.evidence

    r = _outcome_gate_lifecycle_complete_no_success(
        inputs, ev, measurement_failure_domain
    )
    if r is not None:
        return r
    r = _outcome_gate_no_measurement_evidence(measurement, measurement_failure_domain)
    if r is not None:
        return r
    r = _outcome_gate_measurement_failed(
        inputs, measurement, measurement_failure_domain
    )
    if r is not None:
        return r
    r = _outcome_gate_scoring_not_completed(inputs, post_run)
    if r is not None:
        return r
    r = _outcome_gate_no_rankable_winner(inputs, ev)
    if r is not None:
        return r
    r = _outcome_gate_post_run_report(post_run)
    if r is not None:
        return r
    r = _outcome_gate_partial_measurement(measurement)
    if r is not None:
        return r

    return CampaignOutcomeKind.SUCCESS, None, None
