from __future__ import annotations

import io
import logging
import sqlite3
import subprocess
import sys
from pathlib import Path

from rich.console import Console

import src.runner as runner


REPO_ROOT = Path(__file__).resolve().parent


def _run_cli(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "quantmap.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_top_level_help_includes_workflow_and_command_family():
    output = _run_cli("--help")

    assert "Primary workflow:" in output or "Start here:" in output
    assert "quantmap doctor" in output
    assert "quantmap run --campaign <ID> --validate" in output
    assert "quantmap list" in output
    assert "Command family:" in output or "Health:" in output


def test_selftest_output_uses_tooling_scope_language():
    output = _run_cli("--plain", "self-test")

    assert "TOOLING READY" in output
    assert "Next actions" in output
    assert "quantmap doctor" in output


def test_list_output_includes_exact_ids_and_follow_up_guidance(tmp_path, monkeypatch):
    db_path = tmp_path / "lab.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE campaigns (
            id TEXT PRIMARY KEY,
            run_mode TEXT,
            status TEXT,
            analysis_status TEXT,
            report_status TEXT,
            completed_at TEXT,
            started_at TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute("CREATE TABLE configs (campaign_id TEXT)")
    conn.execute(
        """
        CREATE TABLE scores (
            campaign_id TEXT,
            config_id TEXT,
            is_score_winner INTEGER,
            warm_tg_median REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE artifacts (
            campaign_id TEXT,
            artifact_type TEXT,
            path TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE campaign_start_snapshot (
            campaign_id TEXT,
            execution_environment_json TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO campaigns (id, run_mode, status, analysis_status, report_status, created_at)
        VALUES ('B_low_sample__v512', 'custom', 'complete', 'complete', 'complete', '2026-04-17T04:10:48+00:00')
        """
    )
    conn.execute("INSERT INTO configs (campaign_id) VALUES ('B_low_sample__v512')")
    conn.execute(
        """
        INSERT INTO scores (campaign_id, config_id, is_score_winner, warm_tg_median)
        VALUES ('B_low_sample__v512', 'B_low_sample_512', 1, 9.45)
        """
    )
    conn.execute(
        """
        INSERT INTO artifacts (campaign_id, artifact_type, path)
        VALUES ('B_low_sample__v512', 'campaign_summary_md', 'D:/lab/artifacts/reports/minimax/B_low_sample__v512/campaign-summary.md')
        """
    )
    conn.execute(
        """
        INSERT INTO campaign_start_snapshot (campaign_id, execution_environment_json)
        VALUES ('B_low_sample__v512', '{"support_tier":"windows_native"}')
        """
    )
    conn.commit()
    conn.close()

    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=False, no_color=True, width=140)

    monkeypatch.setattr(runner, "DB_PATH", db_path)
    monkeypatch.setattr(runner, "init_db", lambda _path: None)
    monkeypatch.setattr(runner, "console", test_console)

    runner.list_campaigns()
    output = buf.getvalue()

    assert "B_low_sample__v512" in output
    assert "campaign-summary.md" in output
    assert "Next actions" in output
    assert "quantmap explain <campaign-id> --evidence" in output


def test_setup_logging_can_skip_console_handler(tmp_path):
    root = logging.getLogger()
    old_handlers = root.handlers[:]
    old_level = root.level
    try:
        runner._setup_logging("cli_ux_test", logs_dir=tmp_path, log_prefix="validate", console_logging=False)
        handler_names = {getattr(handler, "name", "") for handler in root.handlers}
        assert "QuantMap_File" in handler_names
        assert "QuantMap_Console" not in handler_names
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        for handler in old_handlers:
            root.addHandler(handler)
        root.setLevel(old_level)
