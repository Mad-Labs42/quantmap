"""Runner-level hardening tests for campaign outcome finalization (Slice 1)."""

from __future__ import annotations

import io
import logging
import sqlite3
from pathlib import Path

import pytest
from rich.console import Console

import src.runner as runner
import src.ui as ui
from src.campaign_outcome import CampaignEvidenceSummary
from src.campaign_outcome.contracts import (
    CampaignOutcomeInputs,
    CampaignOutcomeKind,
    FailureDomain,
    MeasurementPhaseVerdict,
)
from src.artifact_paths import ARTIFACT_CAMPAIGN_SUMMARY, FILENAME_CAMPAIGN_SUMMARY
from src.campaign_outcome.evaluate import evaluate_campaign_outcome


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

    monkeypatch.setattr(runner, "_derive_lab_root", lambda _: tmp_path)
    monkeypatch.setattr(
        runner, "infer_model_identity", lambda *args, **kwargs: "test_model"
    )
    monkeypatch.setattr(runner, "_setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_run_preflight_checks", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "src.telemetry_policy.enforce_current_run_readiness",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        runner,
        "artifact_dir",
        lambda *args, **kwargs: (
            tmp_path / "artifacts" / "logs" / "test_model" / "test_camp"
        ),
    )
    monkeypatch.setattr(runner, "_run_config", lambda *args, **kwargs: True)
    monkeypatch.setattr(runner, "_hash_file", lambda *args, **kwargs: "abc")
    monkeypatch.setattr(
        "src.report_campaign.generate_campaign_report",
        lambda *args, **kwargs: tmp_path / "run-reports.md",
    )
    monkeypatch.setattr(
        "src.export.generate_metadata_json",
        lambda *args, **kwargs: tmp_path / "metadata.json",
    )
    monkeypatch.setattr(
        "src.trust_identity.summarize_report_artifact_status",
        lambda *args, **kwargs: "complete",
    )
    monkeypatch.setattr("src.db.write_jsonl_marker", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.telemetry.shutdown", lambda: None)

    campaign = {"id": "test_camp", "variable": "n_gpu_layers", "values": [10]}
    baseline = {
        "requests": {"a": "a.json"},
        "lab": {"cycles_per_config": 1, "requests_per_cycle": 1},
    }
    monkeypatch.setattr(runner, "load_campaign", lambda _: campaign)
    monkeypatch.setattr(runner, "load_baseline", lambda _: baseline)
    monkeypatch.setattr(
        runner, "validate_campaign_purity", lambda *args: "n_gpu_layers"
    )
    monkeypatch.setattr(
        runner,
        "build_config_list",
        lambda *args: [
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
    monkeypatch.setattr(
        runner, "get_campaign_artifact_paths", lambda *args, **kwargs: _fake_artifacts
    )

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


def test_runner_primary_report_failure_preserves_measurement_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Primary report failure is post-run truth; measurement verdict stays succeeded when evidence supports it."""
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

    def _boom(*_a, **_k):
        raise RuntimeError("primary report generation failed")

    monkeypatch.setattr("src.report.generate_report", _boom)

    outcomes: list = []
    _real_eval = runner.evaluate_campaign_outcome

    def _wrap_eval(inp):
        o = _real_eval(inp)
        outcomes.append(o)
        return o

    monkeypatch.setattr(runner, "evaluate_campaign_outcome", _wrap_eval)

    captured_models: list = []
    _real_render = ui.render_post_run_review_from_read_model

    def _capture_render(**kwargs):
        kwargs.pop("target_console", None)
        captured_models.append(kwargs["read_model"])
        _real_render(**kwargs, target_console=con)

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

    def _wrap_eval(inp: CampaignOutcomeInputs):
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
        lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()),
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
        lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()),
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
        lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()),
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
