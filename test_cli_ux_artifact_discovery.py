"""Tests for the `quantmap artifacts` command (CLI UX Bundle 2)."""

from __future__ import annotations

import io
import sqlite3
import subprocess
import sys
from pathlib import Path

from rich.console import Console

import src.ui as ui


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


def test_artifacts_help_includes_campaign_id_argument():
    output = _run_cli("artifacts", "--help")
    assert "campaign" in output.lower()


def test_artifacts_unknown_id_shows_campaign_id_in_output(tmp_path, monkeypatch):
    db_path = tmp_path / "lab.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE campaigns (
            id TEXT PRIMARY KEY,
            status TEXT
        )
        """
    )
    conn.execute("CREATE TABLE artifacts (campaign_id TEXT, artifact_type TEXT, path TEXT)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("QUANTMAP_LAB_ROOT", str(tmp_path))
    output = _run_cli("--plain", "artifacts", "does_not_exist_999")
    assert "does_not_exist_999" in output


def test_artifacts_command_returns_success_for_known_campaign(tmp_path, monkeypatch):
    reports_dir = tmp_path / "artifacts" / "reports" / "my-model" / "TestCampaign_01"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "campaign-summary.md").touch()

    db_path = tmp_path / "db" / "lab.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE campaigns (
            id TEXT PRIMARY KEY,
            status TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE artifacts (
            campaign_id TEXT,
            artifact_type TEXT,
            path TEXT,
            status TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO campaigns (id, status) VALUES ('TestCampaign_01', 'complete')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("QUANTMAP_LAB_ROOT", str(tmp_path))
    result = subprocess.run(
        [sys.executable, "quantmap.py", "artifacts", "TestCampaign_01"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0
    assert "TestCampaign_01" in result.stdout


def test_render_artifact_block_with_db_complete_shows_present():
    artifacts = [
        {
            "artifact_type": "campaign_summary_md",
            "filename": "campaign-summary.md",
            "path": Path("D:/lab/artifacts/reports/model/X_test/campaign-summary.md"),
            "exists": True,
            "db_status": "complete",
            "sha256": "abc123",
        },
    ]
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True, width=140)
    ui.render_artifact_block("X_test", artifacts, target_console=console)
    output = buf.getvalue()
    assert "campaign_summary_md" in output


def test_render_artifact_block_file_present_no_db_shows_present():
    artifacts = [
        {
            "artifact_type": "metadata_json",
            "filename": "metadata.json",
            "path": Path("D:/lab/artifacts/reports/model/Y_test/metadata.json"),
            "exists": True,
            "db_status": None,
            "sha256": None,
        },
    ]
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True, width=140)
    ui.render_artifact_block("Y_test", artifacts, target_console=console)
    output = buf.getvalue()
    assert "metadata_json" in output


def test_render_artifact_block_file_missing_shows_not_found():
    artifacts = [
        {
            "artifact_type": "raw_telemetry_jsonl",
            "filename": "raw-telemetry.jsonl",
            "path": Path("D:/lab/artifacts/measurements/model/Z_test/raw-telemetry.jsonl"),
            "exists": False,
            "db_status": None,
            "sha256": None,
        },
    ]
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, no_color=True, width=140)
    ui.render_artifact_block("Z_test", artifacts, target_console=console)
    output = buf.getvalue()
    assert "not found" in output