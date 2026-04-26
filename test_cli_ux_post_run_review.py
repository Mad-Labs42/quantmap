"""Unit tests for ui.render_post_run_review().

Tests the renderer in isolation — no server, no DB, no real campaign execution.
"""

from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

import src.ui as ui


def _render(**kwargs) -> str:
    """Run render_post_run_review with a captured test console and return output."""
    buf = io.StringIO()
    con = Console(file=buf, force_terminal=False, no_color=True, width=200)
    ui.render_post_run_review(**kwargs, target_console=con)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Diagnostics block
# ---------------------------------------------------------------------------

def test_diagnostics_path_appears_when_provided():
    out = _render(
        campaign_id="X_test",
        report_ok=True,
        diagnostics_path="/lab/artifacts/logs/model/X_test",
    )
    assert "Internal diagnostic files were retained for debugging." in out
    assert "By default, they are not included in the user-facing artifact list." in out
    assert "/lab/artifacts/logs/model/X_test" in out


def test_diagnostics_block_omitted_when_path_is_none():
    out = _render(campaign_id="X_test", report_ok=True, diagnostics_path=None)
    assert "Internal diagnostic files were retained for debugging." not in out
    assert "By default, they are not included" not in out


# ---------------------------------------------------------------------------
# YOLO mode
# ---------------------------------------------------------------------------

def test_no_yolo_text_on_normal_run():
    out = _render(campaign_id="X_test", report_ok=True, yolo_mode=False)
    assert "YOLO Mode Active" not in out
    assert "Validation requirements were relaxed" not in out


def test_yolo_text_appears_when_explicitly_set():
    out = _render(campaign_id="X_test", report_ok=True, yolo_mode=True)
    assert "YOLO Mode Active" in out
    assert "Validation requirements were relaxed because the user chose to continue after a trust warning." in out


def test_yolo_default_is_false():
    """Calling without yolo_mode must not produce YOLO text."""
    out = _render(campaign_id="X_test", report_ok=True)
    assert "YOLO Mode Active" not in out


# ---------------------------------------------------------------------------
# Next actions block
# ---------------------------------------------------------------------------

def test_next_actions_shown_on_success():
    out = _render(campaign_id="TestCamp_01", report_ok=True)
    assert "Next actions" in out
    assert "quantmap explain TestCamp_01 --evidence" in out
    assert "quantmap artifacts TestCamp_01" in out
    assert "quantmap list" in out


def test_next_actions_hidden_on_failure():
    out = _render(campaign_id="TestCamp_01", report_ok=False)
    assert "Next actions" not in out


# ---------------------------------------------------------------------------
# Artifact block
# ---------------------------------------------------------------------------

def test_artifact_block_shown_when_provided():
    artifacts = [
        {
            "artifact_type": "campaign_summary_md",
            "filename": "campaign-summary.md",
            "path": Path("/lab/artifacts/reports/model/TestCamp_01/campaign-summary.md"),
            "exists": True,
            "db_status": "complete",
            "sha256": None,
        },
    ]
    out = _render(campaign_id="TestCamp_01", report_ok=True, artifacts=artifacts)
    assert "campaign_summary_md" in out
    assert "TestCamp_01" in out


def test_artifact_block_omitted_when_not_provided():
    out = _render(campaign_id="TestCamp_01", report_ok=True, artifacts=None)
    # render_artifact_block header includes "Artifacts —"
    assert "Artifacts —" not in out


def test_artifact_block_shows_missing_status():
    artifacts = [
        {
            "artifact_type": "run_reports_md",
            "filename": "run-reports.md",
            "path": Path("/lab/artifacts/reports/model/TestCamp_01/run-reports.md"),
            "exists": False,
            "db_status": None,
            "sha256": None,
        },
    ]
    out = _render(campaign_id="TestCamp_01", report_ok=True, artifacts=artifacts)
    assert "not found" in out


# ---------------------------------------------------------------------------
# Renderer is side-effect-free
# ---------------------------------------------------------------------------

def test_renderer_is_idempotent():
    """Calling render_post_run_review twice with same args must produce same output."""
    kwargs = {"campaign_id": "Idem_test", "report_ok": True, "diagnostics_path": "/lab/diag"}
    out1 = _render(**kwargs)
    out2 = _render(**kwargs)
    assert out1 == out2
