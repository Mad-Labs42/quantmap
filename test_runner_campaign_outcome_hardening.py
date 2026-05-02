"""Runner-level hardening tests for campaign outcome finalization (Slice 1)."""

from __future__ import annotations

import io
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
from src.db import init_db, write_request


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
    db_path = tmp_path / "lab.sqlite"
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, created_at) VALUES (?, ?, ?)",
            ("camp", "camp", "2026-05-02T00:00:00Z"),
        )
        conn.executemany(
            """
            INSERT INTO configs
                (id, campaign_id, variable_name, variable_value, config_values_json, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("cfg_complete", "camp", "n_gpu_layers", "10", "{}", "complete"),
                ("cfg_degraded", "camp", "n_gpu_layers", "20", "{}", "degraded"),
                ("cfg_oom", "camp", "n_gpu_layers", "30", "{}", "oom"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO cycles (config_id, campaign_id, cycle_number, status)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("cfg_complete", "camp", 1, "complete"),
                ("cfg_degraded", "camp", 1, "invalid"),
            ],
        )
        complete_cycle_id, invalid_cycle_id = [
            row[0] for row in conn.execute("SELECT id FROM cycles ORDER BY id")
        ]

        base_request = {
            "campaign_id": "camp",
            "config_id": "cfg_complete",
            "cycle_number": 1,
            "request_index": 1,
            "is_cold": 0,
            "request_type": "speed_short",
            "http_status": 200,
            "ttft_ms": 1.0,
            "total_wall_ms": 2.0,
            "prompt_n": 1,
            "prompt_ms": 1.0,
            "prompt_per_second": 1.0,
            "predicted_n": 1,
            "predicted_ms": 1.0,
            "predicted_per_second": 1.0,
            "cache_n": 0,
            "total_tokens": 2,
            "server_pid": 123,
            "resolved_command": "server",
            "timestamp_start": "2026-05-02T00:00:01Z",
            "error_detail": "",
        }
        write_request(
            conn,
            complete_cycle_id,
            {**base_request, "outcome": "timeout", "cycle_status": "complete"},
        )
        write_request(
            conn,
            invalid_cycle_id,
            {
                **base_request,
                "config_id": "cfg_degraded",
                "outcome": "success",
                "cycle_status": "invalid",
            },
        )
        conn.commit()

        no_complete_success = runner._fetch_campaign_evidence_summary(conn, "camp")
        assert no_complete_success.configs_total == 3
        assert no_complete_success.configs_completed == 1
        assert no_complete_success.configs_oom == 1
        assert no_complete_success.configs_degraded == 1
        assert no_complete_success.cycles_attempted == 2
        assert no_complete_success.cycles_complete == 1
        assert no_complete_success.cycles_invalid == 1
        assert not no_complete_success.has_any_success_request

        write_request(
            conn,
            complete_cycle_id,
            {**base_request, "outcome": "success", "cycle_status": "complete"},
        )
        conn.commit()

        with_complete_success = runner._fetch_campaign_evidence_summary(conn, "camp")
        assert with_complete_success.has_any_success_request


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
        lambda *args, **kwargs: tmp_path / "campaign-summary.md",
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
