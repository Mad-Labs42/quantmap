"""Runner-level hardening tests for campaign outcome finalization (Slice 1)."""

from __future__ import annotations

import dataclasses
import io
import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

import src.runner as runner
import src.ui as ui
from src.campaign_outcome import CampaignEvidenceSummary
from src.campaign_outcome.contracts import (
    CampaignOutcome,
    CampaignOutcomeInputs,
    CampaignOutcomeKind,
    FailureDomain,
    FinalReviewReadModel,
    MeasurementPhaseVerdict,
)
from src.artifact_paths import ARTIFACT_CAMPAIGN_SUMMARY, FILENAME_CAMPAIGN_SUMMARY
from src.campaign_outcome.evaluate import evaluate_campaign_outcome


def _raise_keyboard_interrupt(*_args: object, **_kwargs: object) -> bool:
    raise KeyboardInterrupt()


def _setup_valid_winner_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub evidence + scoring to a single valid-with-winner config.

    Encodes one domain event: ``run_campaign`` sees one completed config with
    one successful warm request and one passing winner. Tests still call
    ``runner.run_campaign(...)`` and assert the outcome at the call site.
    """
    monkeypatch.setattr(
        runner,
        "_fetch_campaign_evidence_summary",
        lambda *_a, **_k: CampaignEvidenceSummary(
            configs_total=1,
            configs_completed=1,
            configs_oom=0,
            configs_skipped_oom=0,
            configs_degraded=0,
            cycles_attempted=1,
            cycles_complete=1,
            cycles_invalid=0,
            has_any_success_request=True,
        ),
    )
    monkeypatch.setattr(
        "src.score.score_campaign",
        lambda *_a, **_k: {
            "winner": "test_10",
            "effective_filters": {},
            "stats": {"test_10": {}},
            "passing": {"test_10": {"warm_tg_median": 100.0}},
            "eliminated": {},
            "unrankable": {},
        },
    )


def _setup_secondary_report_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Layer secondary-report failure on top of valid-with-winner evidence.

    Primary report (``src.report.generate_report``) succeeds; secondary
    run-reports (``src.report_campaign.generate_campaign_report``) raises.
    """
    _setup_valid_winner_evidence(monkeypatch)
    monkeypatch.setattr(
        "src.report.generate_report",
        lambda *_a, **_k: tmp_path / FILENAME_CAMPAIGN_SUMMARY,
    )

    def _v2_fail(*_a: object, **_k: object) -> Path:
        raise RuntimeError("secondary report failed")

    monkeypatch.setattr("src.report_campaign.generate_campaign_report", _v2_fail)


def _capture_read_models(
    monkeypatch: pytest.MonkeyPatch, console: Console
) -> list[FinalReviewReadModel]:
    """Install a render-capture wrapper; return the list to assert on at the call site.

    The real renderer still runs (against the test console), so console-output
    assertions like "Report generation: OK" continue to work alongside
    read-model assertions.
    """
    captured: list[FinalReviewReadModel] = []
    _real_render = ui.render_post_run_review_from_read_model

    def _capture_render(**kwargs: Any) -> Any:
        kwargs.pop("target_console", None)
        rm: FinalReviewReadModel = kwargs["read_model"]
        captured.append(rm)
        return _real_render(**kwargs, target_console=console)

    monkeypatch.setattr(
        runner.ui,
        "render_post_run_review_from_read_model",
        _capture_render,
    )
    return captured


def _minimal_run_campaign_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Console:
    import sys
    import types

    fake_server = types.SimpleNamespace(
        SERVER_BIN="fake-server", MODEL_PATH="fake-model"
    )
    monkeypatch.setitem(sys.modules, "src.server", fake_server)

    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=False, no_color=True, width=200)
    monkeypatch.setattr(runner, "console", test_console)

    monkeypatch.setattr(runner, "_derive_lab_root", lambda _campaign: tmp_path)
    monkeypatch.setattr(runner, "infer_model_identity", lambda *_a, **_k: "test_model")
    for runner_attr in ("_setup_logging", "_run_preflight_checks"):
        monkeypatch.setattr(runner, runner_attr, lambda *_a, **_k: None)
    monkeypatch.setattr(
        "src.telemetry_policy.enforce_current_run_readiness",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        runner,
        "artifact_dir",
        lambda *_a, **_k: tmp_path / "artifacts" / "logs" / "test_model" / "test_camp",
    )
    monkeypatch.setattr(runner, "_run_config", lambda *_a, **_k: True)
    monkeypatch.setattr(runner, "_hash_file", lambda *_a, **_k: "abc")
    module_stub_values = {
        "src.report_campaign.generate_campaign_report": tmp_path / "run-reports.md",
        "src.export.generate_metadata_json": tmp_path / "metadata.json",
        "src.trust_identity.summarize_report_artifact_status": "complete",
    }
    for target, value in module_stub_values.items():
        monkeypatch.setattr(target, lambda *_a, _v=value, **_k: _v)
    monkeypatch.setattr("src.db.write_jsonl_marker", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.telemetry.shutdown", lambda: None)

    campaign_value = {"id": "test_camp", "variable": "n_gpu_layers", "values": [10]}
    baseline_value = {
        "requests": {"a": "a.json"},
        "lab": {"cycles_per_config": 1, "requests_per_cycle": 1},
    }
    monkeypatch.setattr(runner, "load_campaign", lambda _campaign_id: campaign_value)
    monkeypatch.setattr(runner, "load_baseline", lambda _path: baseline_value)
    monkeypatch.setattr(
        runner, "validate_campaign_purity", lambda *args: "n_gpu_layers"
    )
    monkeypatch.setattr(
        runner,
        "build_config_list",
        lambda *_args: [
            {
                "config_id": "test_10",
                "variable_name": "n_gpu_layers",
                "variable_value": 10,
                "full_config": {},
            }
        ],
    )
    (tmp_path / "a.json").touch()
    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)

    db_path = tmp_path / "db" / "lab.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    from src.db import init_db

    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, created_at) VALUES ('test_camp', 'test_camp', '2026-04-25T12:00:00Z')"
        )

    _fake_artifacts = [
        {
            "artifact_type": ARTIFACT_CAMPAIGN_SUMMARY,
            "filename": FILENAME_CAMPAIGN_SUMMARY,
            "path": tmp_path
            / "artifacts"
            / "reports"
            / "test_model"
            / "test_camp"
            / FILENAME_CAMPAIGN_SUMMARY,
            "exists": True,
            "db_status": "complete",
            "sha256": None,
        },
    ]
    monkeypatch.setattr(runner, "get_campaign_artifact_paths", lambda *_a, **_k: _fake_artifacts)

    return test_console


def test_exit_code_helper_maps_success_style_only() -> None:
    good = evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            scoring_completed=True,
            passing_count=1,
            winner_config_id="w",
            report_status="complete",
            evidence=CampaignEvidenceSummary(
                configs_total=1,
                configs_completed=1,
                has_any_success_request=True,
                cycles_attempted=1,
                cycles_complete=1,
            ),
        )
    )
    assert runner._exit_code_for_campaign_outcome(good) == 0

    bad = evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            scoring_completed=True,
            passing_count=0,
            winner_config_id=None,
            evidence=CampaignEvidenceSummary(
                configs_total=1,
                configs_completed=1,
                has_any_success_request=True,
                cycles_attempted=1,
                cycles_complete=1,
            ),
        )
    )
    assert runner._exit_code_for_campaign_outcome(bad) == 1


def test_exit_code_helper_keeps_partial_measurement_nonzero() -> None:
    partial_measurement = evaluate_campaign_outcome(
        CampaignOutcomeInputs(
            campaign_id="c",
            effective_campaign_id="c",
            report_ok=True,
            report_status="complete",
            scoring_completed=True,
            passing_count=1,
            winner_config_id="w",
            evidence=CampaignEvidenceSummary(
                configs_total=1,
                configs_completed=1,
                has_any_success_request=True,
                cycles_attempted=2,
                cycles_complete=1,
                cycles_invalid=1,
                configs_oom=0,
                configs_skipped_oom=0,
            ),
        )
    )
    assert partial_measurement.measurement == MeasurementPhaseVerdict.PARTIAL
    assert partial_measurement.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert not partial_measurement.allows_success_style_review
    assert runner._exit_code_for_campaign_outcome(partial_measurement) == 1


def test_fetch_campaign_evidence_summary_counts_only_complete_success_requests(
    tmp_path: Path,
) -> None:
    """DB aggregation: OOM/skip/degraded/incomplete cycles; success only if complete cycle."""
    from src.db import init_db

    db_path = tmp_path / "lab.sqlite"
    init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, created_at) VALUES ('camp', 'camp', '2026-04-25T12:00:00Z')"
        )
        conn.executemany(
            """
            INSERT INTO configs
                (id, campaign_id, variable_name, variable_value, config_values_json, status)
            VALUES (?, 'camp', 'n_gpu_layers', ?, '{}', ?)
            """,
            [
                ("complete_cfg", "10", "complete"),
                ("oom_cfg", "20", "oom"),
                ("skipped_cfg", "30", "skipped_oom"),
                ("degraded_cfg", "40", "degraded"),
            ],
        )
        cur = conn.execute(
            """
            INSERT INTO cycles (config_id, campaign_id, cycle_number, status)
            VALUES ('complete_cfg', 'camp', 1, 'complete')
            """
        )
        complete_cycle_id = cur.lastrowid
        cur = conn.execute(
            """
            INSERT INTO cycles (config_id, campaign_id, cycle_number, status)
            VALUES ('degraded_cfg', 'camp', 1, 'invalid')
            """
        )
        invalid_cycle_id = cur.lastrowid
        conn.executemany(
            """
            INSERT INTO requests
                (cycle_id, campaign_id, config_id, cycle_number, request_index,
                 is_cold, request_type, outcome, cycle_status)
            VALUES (?, 'camp', ?, 1, ?, 0, 'speed_short', ?, ?)
            """,
            [
                (complete_cycle_id, "complete_cfg", 1, "success", "complete"),
                (invalid_cycle_id, "degraded_cfg", 1, "success", "invalid"),
                (complete_cycle_id, "complete_cfg", 2, "timeout", "complete"),
            ],
        )
        conn.commit()

        summary = runner._fetch_campaign_evidence_summary(conn, "camp")

    assert summary == CampaignEvidenceSummary(
        configs_total=4,
        configs_completed=1,
        configs_oom=1,
        configs_skipped_oom=1,
        configs_degraded=1,
        cycles_attempted=2,
        cycles_complete=1,
        cycles_invalid=1,
        has_any_success_request=True,
    )


def test_runner_exit_nonzero_when_report_ok_but_no_measurement_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Complete lifecycle + primary report OK cannot yield success-style review without measurement success."""
    con = _minimal_run_campaign_env(tmp_path, monkeypatch)

    monkeypatch.setattr(
        runner,
        "_fetch_campaign_evidence_summary",
        lambda *_a, **_k: CampaignEvidenceSummary(
            configs_total=1,
            configs_completed=1,
            configs_oom=0,
            configs_skipped_oom=0,
            configs_degraded=0,
            cycles_attempted=1,
            cycles_complete=1,
            cycles_invalid=0,
            has_any_success_request=False,
        ),
    )
    monkeypatch.setattr(
        "src.score.score_campaign",
        lambda *_a, **_k: {
            "winner": None,
            "effective_filters": {},
            "stats": {},
            "passing": {},
            "eliminated": {},
            "unrankable": {},
        },
    )
    monkeypatch.setattr(
        "src.report.generate_report",
        lambda *args, **kwargs: tmp_path / FILENAME_CAMPAIGN_SUMMARY,
    )

    captured_models: list = []
    _real = ui.render_post_run_review_from_read_model

    def _capture_render(**kwargs):
        kwargs.pop("target_console", None)
        captured_models.append(kwargs["read_model"])
        _real(**kwargs, target_console=con)

    monkeypatch.setattr(
        runner.ui,
        "render_post_run_review_from_read_model",
        _capture_render,
    )

    with pytest.raises(SystemExit) as exc:
        runner.run_campaign(
            campaign_id="test_camp",
            dry_run=False,
            yolo_mode=False,
            baseline_path=tmp_path / "baseline.yaml",
        )
    assert exc.value.code == 1
    assert captured_models
    rm = captured_models[-1]
    assert rm.outcome_kind != CampaignOutcomeKind.SUCCESS
    assert not rm.show_next_actions
    assert rm.report_generation_ok is True


def test_runner_secondary_report_failure_keeps_partial_warning_but_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Secondary run-reports failure remains PARTIAL warning but keeps core success exit."""
    con = _minimal_run_campaign_env(tmp_path, monkeypatch)
    _setup_secondary_report_failure(monkeypatch, tmp_path)
    captured_models = _capture_read_models(monkeypatch, con)

    runner.run_campaign(
        campaign_id="test_camp",
        dry_run=False,
        yolo_mode=False,
        baseline_path=tmp_path / "baseline.yaml",
    )
    assert captured_models
    rm = captured_models[-1]
    assert rm.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert rm.show_next_actions
    assert rm.report_generation_ok is True
    assert rm.failure_cause and "Report bundle partially generated" in rm.failure_cause
    buf = con.file
    if hasattr(buf, "getvalue"):
        out = buf.getvalue()
        assert "Report generation: FAILED" not in out
        assert "Report bundle partially generated" in out


def test_runner_secondary_report_failure_normalizes_stale_report_ok_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Structured report_status=partial wins if legacy report_ok was stale false."""
    con = _minimal_run_campaign_env(tmp_path, monkeypatch)
    _setup_secondary_report_failure(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "src.trust_identity.summarize_report_artifact_status",
        lambda *_a, **_k: "partial",
    )

    def _force_stale_report_ok(inp: CampaignOutcomeInputs) -> CampaignOutcome:
        new_inp: CampaignOutcomeInputs = dataclasses.replace(inp, report_ok=False)
        return evaluate_campaign_outcome(new_inp)

    monkeypatch.setattr(
        runner,
        "evaluate_campaign_outcome",
        _force_stale_report_ok,
    )

    captured_models = _capture_read_models(monkeypatch, con)

    runner.run_campaign(
        campaign_id="test_camp",
        dry_run=False,
        yolo_mode=False,
        baseline_path=tmp_path / "baseline.yaml",
    )
    assert captured_models
    rm = captured_models[-1]
    assert rm.outcome_kind == CampaignOutcomeKind.PARTIAL
    assert rm.show_next_actions
    assert rm.report_generation_ok is True
    buf = con.file
    if hasattr(buf, "getvalue"):
        out = buf.getvalue()
        assert "Report generation: OK" in out
        assert "Report generation: FAILED" not in out


def test_runner_primary_report_failure_preserves_measurement_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Primary report failure is post-run truth; measurement verdict stays succeeded when evidence supports it."""
    con = _minimal_run_campaign_env(tmp_path, monkeypatch)
    _setup_valid_winner_evidence(monkeypatch)

    def _boom(*_a: object, **_k: object) -> Path:
        raise RuntimeError("primary report generation failed")

    monkeypatch.setattr("src.report.generate_report", _boom)

    outcomes: list[CampaignOutcome] = []
    _real_eval = runner.evaluate_campaign_outcome

    def _wrap_eval(inp: CampaignOutcomeInputs) -> CampaignOutcome:
        o = _real_eval(inp)
        outcomes.append(o)
        return o

    monkeypatch.setattr(runner, "evaluate_campaign_outcome", _wrap_eval)

    captured_models = _capture_read_models(monkeypatch, con)

    with pytest.raises(SystemExit) as exc:
        runner.run_campaign(
            campaign_id="test_camp",
            dry_run=False,
            yolo_mode=False,
            baseline_path=tmp_path / "baseline.yaml",
        )
    assert exc.value.code == 1
    assert outcomes
    final_out = outcomes[-1]
    assert final_out.measurement == MeasurementPhaseVerdict.SUCCEEDED
    assert final_out.failure_domain == FailureDomain.POST_RUN_PIPELINE
    assert captured_models
    rm = captured_models[-1]
    assert not rm.show_next_actions
    assert rm.report_generation_ok is False
    assert rm.failure_cause and "Primary report generation failed" in rm.failure_cause
    assert "Post-campaign analysis failed" not in (rm.failure_cause or "")
    assert rm.failure_remediation and "Review logs" in rm.failure_remediation


def test_keyboard_interrupt_exits_130_not_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interrupt routes through outcome evaluation + read-model render; exits 130; no report run."""
    con = _minimal_run_campaign_env(tmp_path, monkeypatch)

    def _interrupt(*_a: object, **_k: object) -> bool:
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_run_config", _interrupt)

    outcome_calls: list[CampaignOutcomeInputs] = []

    def _wrap_eval(inp: CampaignOutcomeInputs) -> CampaignOutcome:
        outcome_calls.append(inp)
        return evaluate_campaign_outcome(inp)

    monkeypatch.setattr(runner, "evaluate_campaign_outcome", _wrap_eval)

    def _report_must_not_run(*_a: object, **_k: object) -> Path:
        raise AssertionError("generate_report must not run after KeyboardInterrupt")

    monkeypatch.setattr("src.report.generate_report", _report_must_not_run)

    captured_read_models: list = []
    _real_render = ui.render_post_run_review_from_read_model

    def _capture_render(**kwargs):
        kwargs.pop("target_console", None)
        captured_read_models.append(kwargs["read_model"])
        return _real_render(**kwargs, target_console=con)

    monkeypatch.setattr(
        runner.ui,
        "render_post_run_review_from_read_model",
        _capture_render,
    )

    with pytest.raises(SystemExit) as exc:
        runner.run_campaign(
            campaign_id="test_camp",
            dry_run=False,
            yolo_mode=False,
            baseline_path=tmp_path / "baseline.yaml",
        )
    assert exc.value.code == 130
    assert len(outcome_calls) == 1
    assert outcome_calls[0].user_interrupted is True
    assert captured_read_models
    rm = captured_read_models[-1]
    assert rm.outcome_kind == CampaignOutcomeKind.ABORTED
    assert not rm.show_next_actions
    assert rm.report_generation_ok is None
    assert rm.failure_remediation and "--resume" in rm.failure_remediation
    buf = con.file
    if hasattr(buf, "getvalue"):
        out = buf.getvalue()
        assert "--resume" in out or "resume" in out.lower()
        assert "Report generation: FAILED" not in out


def test_keyboard_interrupt_exits_130_when_finalize_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Finalize failures still exit 130 and never reach analyze/report (logged, not swallowed)."""
    _minimal_run_campaign_env(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runner,
        "_run_config",
        _raise_keyboard_interrupt,
    )

    def _boom(**kw: object) -> None:
        raise RuntimeError("finalize boom")

    monkeypatch.setattr(runner, "_finalize_interrupt_post_run_review", _boom)

    gen_calls: list[int] = []

    def _track_gen(*a: object, **k: object) -> Path:
        gen_calls.append(1)
        return tmp_path / "x.md"

    monkeypatch.setattr("src.report.generate_report", _track_gen)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as exc:
            runner.run_campaign(
                campaign_id="test_camp",
                dry_run=False,
                yolo_mode=False,
                baseline_path=tmp_path / "baseline.yaml",
            )
    assert exc.value.code == 130
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert not gen_calls
    assert "Interrupted campaign closeout failed" in caplog.text


def test_keyboard_interrupt_exits_130_when_evidence_fetch_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DB/evidence fetch during interrupt closeout is best-effort; exit 130 is mandatory."""
    _minimal_run_campaign_env(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runner,
        "_run_config",
        _raise_keyboard_interrupt,
    )

    def _locked_db(*_a: object, **_k: object):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(runner, "_fetch_campaign_evidence_summary", _locked_db)

    gen_calls: list[int] = []

    def _track_gen(*_a: object, **_k: object) -> Path:
        gen_calls.append(1)
        return tmp_path / "x.md"

    monkeypatch.setattr("src.report.generate_report", _track_gen)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as exc:
            runner.run_campaign(
                campaign_id="test_camp",
                dry_run=False,
                yolo_mode=False,
                baseline_path=tmp_path / "baseline.yaml",
            )
    assert exc.value.code == 130
    assert isinstance(exc.value.__cause__, sqlite3.OperationalError)
    assert not gen_calls
    assert "Interrupted campaign closeout failed" in caplog.text


def test_keyboard_interrupt_always_system_exit_130_when_finalize_returns_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interrupted runs cannot reach mark-complete / scoring even if finalize does not exit."""
    _minimal_run_campaign_env(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runner,
        "_run_config",
        _raise_keyboard_interrupt,
    )
    monkeypatch.setattr(
        runner,
        "_finalize_interrupt_post_run_review",
        lambda **kw: None,
    )
    with pytest.raises(SystemExit) as exc:
        runner.run_campaign(
            campaign_id="test_camp",
            dry_run=False,
            yolo_mode=False,
            baseline_path=tmp_path / "baseline.yaml",
        )
    assert exc.value.code == 130
