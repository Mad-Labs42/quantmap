"""Tests for YOLO mode terminal review output and internal diagnostics notice."""

from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

from src.runner import run_campaign
import src.runner as runner


def _run_mocked_campaign(tmp_path: Path, monkeypatch, yolo_mode: bool) -> str:
    import sys
    import types

    fake_server = types.SimpleNamespace(
        SERVER_BIN="fake-server",
        MODEL_PATH="fake-model"
    )
    monkeypatch.setitem(sys.modules, "src.server", fake_server)

    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=False, no_color=True, width=200)

    monkeypatch.setattr(runner, "console", test_console)
    monkeypatch.setattr(runner, "_derive_lab_root", lambda _: tmp_path)
    monkeypatch.setattr(runner, "infer_model_identity", lambda *args, **kwargs: "test_model")
    
    # Mock all the heavy lifting
    monkeypatch.setattr(runner, "_setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_run_preflight_checks", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.telemetry_policy.enforce_current_run_readiness", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "artifact_dir", lambda *args, **kwargs: tmp_path / "artifacts" / "logs" / "test_model" / "test_camp")
    monkeypatch.setattr(runner, "_run_config", lambda *args, **kwargs: True)
    monkeypatch.setattr(runner, "_hash_file", lambda *args, **kwargs: "abc")
    monkeypatch.setattr("src.score.score_campaign", lambda *args, **kwargs: {"winner": None, "effective_filters": {}, "stats": {}})
    monkeypatch.setattr("src.report.generate_report", lambda *args, **kwargs: tmp_path / "campaign-summary.md")
    monkeypatch.setattr("src.report_campaign.generate_campaign_report", lambda *args, **kwargs: tmp_path / "run-reports.md")
    monkeypatch.setattr("src.export.generate_metadata_json", lambda *args, **kwargs: tmp_path / "metadata.json")
    monkeypatch.setattr("src.trust_identity.summarize_report_artifact_status", lambda *args, **kwargs: "complete")
    monkeypatch.setattr("src.db.write_jsonl_marker", lambda *args, **kwargs: None)
    monkeypatch.setattr("src.telemetry.shutdown", lambda: None)
    
    # Needs a valid campaign and baseline
    campaign = {"id": "test_camp", "variable": "n_gpu_layers", "values": [10]}
    baseline = {"requests": {"a": "a.json"}, "lab": {"cycles_per_config": 1, "requests_per_cycle": 1}}
    
    monkeypatch.setattr(runner, "load_campaign", lambda _: campaign)
    monkeypatch.setattr(runner, "load_baseline", lambda _: baseline)
    monkeypatch.setattr(runner, "validate_campaign_purity", lambda *args: "n_gpu_layers")
    monkeypatch.setattr(runner, "build_config_list", lambda *args: [{"config_id": "test_10", "variable_name": "n_gpu_layers", "variable_value": 10, "full_config": {}}])
    
    # We need a dummy request file
    (tmp_path / "a.json").touch()
    monkeypatch.setattr(runner, "_REPO_ROOT", tmp_path)
    
    import sqlite3
    db_path = tmp_path / "db" / "lab.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    from src.db import init_db
    init_db(db_path)
    
    # Create required DB tables so updates don't crash
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO campaigns (id, name, created_at) VALUES ('test_camp', 'test_camp', '2026-04-25T12:00:00Z')")

    run_campaign(
        campaign_id="test_camp",
        dry_run=False,
        yolo_mode=yolo_mode,
        baseline_path=tmp_path / "baseline.yaml",
    )
    
    return buf.getvalue()


def test_normal_run_does_not_contain_yolo_wording(tmp_path: Path, monkeypatch):
    output = _run_mocked_campaign(tmp_path, monkeypatch, yolo_mode=False)
    
    assert "YOLO Mode Active" not in output
    assert "Validation requirements were relaxed" not in output
    
    assert "Internal diagnostic files were retained for debugging." in output
    assert "By default, they are not included in the user-facing artifact list." in output
    assert "logs\\test_model\\test_camp" in output.replace("/", "\\")


def test_yolo_run_contains_yolo_wording(tmp_path: Path, monkeypatch):
    output = _run_mocked_campaign(tmp_path, monkeypatch, yolo_mode=True)
    
    assert "YOLO Mode Active" in output
    assert "Validation requirements were relaxed because the user chose to continue after a trust warning." in output
    
    assert "Internal diagnostic files were retained for debugging." in output
    assert "By default, they are not included in the user-facing artifact list." in output
    assert "logs\\test_model\\test_camp" in output.replace("/", "\\")
