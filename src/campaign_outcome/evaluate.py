"""Pure campaign outcome evaluation (Slice 1).

``evaluate_campaign_outcome`` is the only place that decides ``CampaignOutcome``
truth from ``CampaignOutcomeInputs``. It must not read the database or render
UI; callers supply aggregated evidence and status fields from the runner.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class _OutcomeSynth:
    """Private synthesis result: kind, diagnostic fields, and optional abort reason."""

    kind: CampaignOutcomeKind
    failure_domain: FailureDomain | None
    failure_detail: str | None
    abort: AbortReason | None = None


def evaluate_campaign_outcome(inputs: CampaignOutcomeInputs) -> CampaignOutcome:
    """Decide campaign outcome truth from normalized runner evidence.

    Uses flags and ``inputs.evidence`` only — no SQLite, filesystem, or console.
    Measurement verdicts, post-run verdicts (including explicit ``report_status``
    when scoring completed), failure domain/detail, abort reasons, and review
    authority gates are all resolved here in a fixed precedence order.
    """
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
            report_ok=None,
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
            report_ok=None,
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
            report_ok=None,
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

    synth = _synthesize_outcome(
        inputs, measurement, measurement_failure_domain, post_run
    )

    allows_success = _allows_success_style_review(
        outcome_kind=synth.kind,
        measurement=measurement,
        post_run=post_run,
        inputs=inputs,
    )

    # Success-style review is a process/UI gate: terminal SUCCESS is always
    # allowed, and the evaluator also allows a narrow core-valid
    # secondary-artifact PARTIAL carve-out.
    #
    # Recommendation authority is stricter and fail-closed. It can survive the
    # same secondary-artifact PARTIAL carve-out only when measurement/scoring/
    # winner truth remains valid and no abort flags are present.
    allows_rec = (
        allows_success
        and _measurement_supports_authority(measurement)
        and ev.has_any_success_request
        and _scoring_supports_authority(inputs, post_run, allow_secondary_partial=True)
    )

    evidence_out = dataclasses.replace(
        ev,
        campaign_db_status=inputs.campaign_db_status,
        analysis_status=inputs.analysis_status,
        report_status=inputs.report_status,
    )

    return CampaignOutcome(
        outcome_kind=synth.kind,
        lifecycle_phase_at_decision=CampaignLifecyclePhase.FINALIZATION,
        measurement=measurement,
        post_run=post_run,
        failure_domain=synth.failure_domain,
        failure_detail=synth.failure_detail,
        abort=synth.abort,
        allows_success_style_review=allows_success,
        allows_recommendation_authority=allows_rec,
        report_ok=_effective_report_generation_ok(inputs, post_run),
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
    """Build a terminal ``CampaignOutcome`` for abort/fatal paths.

    Success-style review and recommendation authority are forced off; callers
    rely on this invariant for early exits without duplicating gate logic.
    """
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
        if lbr:
            # Backend failure prevented any cycles from starting.  Route through
            # the startup-failure domain so the failure reason is surfaced rather
            # than suppressed behind generic NO_EVIDENCE/MEASUREMENT_BODY copy.
            return MeasurementPhaseVerdict.FAILED, FailureDomain.BACKEND_STARTUP
        return MeasurementPhaseVerdict.NO_EVIDENCE, FailureDomain.MEASUREMENT_BODY

    if ev.has_any_success_request:
        if ev.cycles_invalid > 0:
            # MVP trust policy: aggregate OOM counters (configs_oom,
            # configs_skipped_oom) are context — not exact per-cycle proof.
            # Until DB/runner/backend evidence can attribute each invalid
            # cycle row to its specific cause, invalid cycles always produce
            # PARTIAL measurement. Observed results, artifacts, and winning
            # config are preserved. Full success and recommendation
            # authority require per-cycle attribution (deferred work).
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
    inputs: CampaignOutcomeInputs,
    post_run: PostRunVerdict,
    *,
    allow_secondary_partial: bool = False,
) -> bool:
    allowed_post_run = {PostRunVerdict.REPORT_SUCCEEDED}
    if allow_secondary_partial:
        allowed_post_run.add(PostRunVerdict.REPORT_PARTIAL)
    return (
        inputs.scoring_completed
        and inputs.passing_count > 0
        and inputs.winner_config_id is not None
        and post_run in allowed_post_run
    )


def _allows_success_style_review(
    *,
    outcome_kind: CampaignOutcomeKind,
    measurement: MeasurementPhaseVerdict,
    post_run: PostRunVerdict,
    inputs: CampaignOutcomeInputs,
) -> bool:
    if outcome_kind == CampaignOutcomeKind.SUCCESS:
        return True
    if outcome_kind != CampaignOutcomeKind.PARTIAL:
        return False
    if measurement != MeasurementPhaseVerdict.SUCCEEDED:
        return False
    if post_run != PostRunVerdict.REPORT_PARTIAL:
        return False
    return _scoring_supports_authority(
        inputs,
        post_run,
        allow_secondary_partial=True,
    )


def _effective_report_generation_ok(
    inputs: CampaignOutcomeInputs, post_run: PostRunVerdict
) -> bool | None:
    """Normalize primary-report truth from authoritative post-run verdict.

    Structured post-run verdict owns report truth when available:
      - REPORT_SUCCEEDED / REPORT_PARTIAL -> True (primary report succeeded)
      - REPORT_FAILED -> False
      - REPORT_SKIPPED -> None (report not attempted)
    Analysis-side verdicts (NOT_REACHED, ANALYSIS_FAILED, ANALYSIS_SKIPPED) fall
    back to ``inputs.report_ok`` directly — its tri-state is preserved as-is so
    "not attempted" (``None``) cannot be mistaken for "failed" (``False``) by
    downstream projection or the UI subline.
    """
    if post_run in (PostRunVerdict.REPORT_SUCCEEDED, PostRunVerdict.REPORT_PARTIAL):
        return True
    if post_run == PostRunVerdict.REPORT_FAILED:
        return False
    if post_run == PostRunVerdict.REPORT_SKIPPED:
        return None
    return inputs.report_ok


def _post_run_verdict(inputs: CampaignOutcomeInputs) -> PostRunVerdict:
    """Resolve the post-run verdict from analysis/report lanes.

    Precedence (highest first):
      1. ``scoring_completed=False`` → analysis-side verdict (FAILED / SKIPPED / NOT_REACHED).
      2. Structured ``report_status`` (when present) is authoritative.
      3. Tri-state ``report_ok`` fallback when no ``report_status`` is given:
         - ``True``  → ``REPORT_SUCCEEDED``  (primary report succeeded)
         - ``False`` → ``REPORT_FAILED``     (primary report failed)
         - ``None``  → ``REPORT_SKIPPED``    (report not attempted / unknown;
           does not imply failure — distinct from explicit ``False``)
    """
    analysis_s = (inputs.analysis_status or "").strip().lower()
    report_s = (inputs.report_status or "").strip().lower()

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
    if report_s == "complete":
        return PostRunVerdict.REPORT_SUCCEEDED

    # Tri-state report_ok: distinguish "not attempted" (None) from "failed" (False).
    # Collapsing None into REPORT_FAILED would let pre-report/abort paths show
    # "Report generation: FAILED" in the UI, which is a trust violation.
    if inputs.report_ok is True:
        return PostRunVerdict.REPORT_SUCCEEDED
    if inputs.report_ok is False:
        return PostRunVerdict.REPORT_FAILED
    return PostRunVerdict.REPORT_SKIPPED


def _outcome_gate_no_measurement_evidence(
    measurement: MeasurementPhaseVerdict,
    measurement_failure_domain: FailureDomain | None,
) -> _OutcomeSynth | None:
    if measurement not in (
        MeasurementPhaseVerdict.NO_EVIDENCE,
        MeasurementPhaseVerdict.NOT_STARTED,
    ):
        return None
    return _OutcomeSynth(
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
    return _OutcomeSynth(CampaignOutcomeKind.FAILED, measurement_failure_domain, detail)


def _outcome_gate_scoring_not_completed(
    inputs: CampaignOutcomeInputs, post_run: PostRunVerdict
) -> _OutcomeSynth | None:
    if inputs.scoring_completed:
        return None
    if post_run == PostRunVerdict.ANALYSIS_FAILED:
        return _OutcomeSynth(
            CampaignOutcomeKind.FAILED,
            FailureDomain.POST_RUN_PIPELINE,
            "Post-campaign analysis failed.",
        )
    if post_run == PostRunVerdict.ANALYSIS_SKIPPED:
        return _OutcomeSynth(
            CampaignOutcomeKind.FAILED,
            FailureDomain.POST_RUN_PIPELINE,
            "Post-campaign analysis was skipped.",
        )
    return _OutcomeSynth(
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
        return _OutcomeSynth(
            CampaignOutcomeKind.DEGRADED,
            FailureDomain.MEASUREMENT_BODY,
            "No rankable winner; instrumentation or evidence quality is degraded.",
        )
    return _OutcomeSynth(
        CampaignOutcomeKind.INSUFFICIENT_EVIDENCE,
        FailureDomain.MEASUREMENT_BODY,
        "No passing rankable configuration produced a winner.",
    )


def _outcome_gate_post_run_report(
    post_run: PostRunVerdict,
) -> _OutcomeSynth | None:
    if post_run == PostRunVerdict.REPORT_FAILED:
        return _OutcomeSynth(
            CampaignOutcomeKind.PARTIAL,
            FailureDomain.POST_RUN_PIPELINE,
            "Primary report generation failed; measurement data remains valid.",
        )
    if post_run == PostRunVerdict.REPORT_SKIPPED:
        return _OutcomeSynth(
            CampaignOutcomeKind.PARTIAL,
            FailureDomain.POST_RUN_PIPELINE,
            "Primary report generation was skipped; measurement data remains valid.",
        )
    if post_run == PostRunVerdict.REPORT_PARTIAL:
        return _OutcomeSynth(
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
    return _OutcomeSynth(
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

    # Measurement verdict owns measurement truth; runner ``campaign_db_status`` is not
    # an independent scientific gate here (see synthesis order).
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

    return _OutcomeSynth(CampaignOutcomeKind.SUCCESS, None, None)
