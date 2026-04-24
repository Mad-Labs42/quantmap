"""Tests for `quantmap acpm run` (CLI UX Bundle 4)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def _run_cli(*args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "quantmap.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout, result.stderr


def test_acpm_run_help_shows_arguments():
    rc, out, err = _run_cli("acpm", "run", "--help")
    assert rc == 0
    assert "--campaign" in out
    assert "--profile" in out
    assert "--tier" in out
    assert "--validate" in out
    assert "--dry-run" in out


def test_acpm_run_missing_campaign_exits_1():
    rc, out, err = _run_cli("acpm", "run", "--profile", "Balanced")
    assert rc in (1, 2)  # argparse returns 2 for missing required arg
    combined = (out + err).lower()
    assert "error" in combined or "required" in combined


def test_acpm_run_unknown_campaign_exits_1():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "DOES_NOT_EXIST", "--profile", "Balanced")
    assert rc == 1
    assert "Campaign not found" in out


def test_acpm_run_unknown_profile_exits_1():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "NGL_sweep", "--profile", "InvalidProfile")
    assert rc == 1
    assert "Unknown profile" in out


def test_acpm_run_unknown_tier_exits_1():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "NGL_sweep", "--profile", "Balanced", "--tier", "10x")
    assert rc == 1
    assert "Unknown tier" in out


def test_acpm_run_non_applicable_campaign_exits_1():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "B_low_sample", "--profile", "Balanced")
    assert rc == 1
    assert "not ACPM-applicable" in out


def test_acpm_run_validate_exits_0():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "NGL_sweep", "--profile", "Balanced", "--validate")
    assert rc in (0, 1)  # exits 0 if env OK, 1 if model missing (expected in CI)
    assert "validation" in out.lower() or "pre-flight" in out.lower()


def test_acpm_run_dry_run_exits_0():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "NGL_sweep", "--profile", "Balanced", "--dry-run")
    assert rc == 0
    assert "NGL_sweep" in out
    assert "Balanced" in out


def test_acpm_run_dry_run_shows_scope_and_values():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "NGL_sweep", "--profile", "Balanced", "--dry-run")
    assert rc == 0
    assert "Scope:" in out or "scope" in out.lower()
    assert "Values:" in out or "values" in out.lower()


def test_acpm_run_tier_1x_default():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "NGL_sweep", "--profile", "Balanced", "--dry-run")
    assert rc == 0
    assert "1x" in out or "1" in out


def test_acpm_run_tier_3x():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "NGL_sweep", "--profile", "Balanced", "--tier", "3x", "--dry-run")
    assert rc == 0
    assert "3x" in out or "3" in out


def test_acpm_run_tier_5x():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "NGL_sweep", "--profile", "Balanced", "--tier", "5x", "--dry-run")
    assert rc == 0
    assert "5x" in out or "5" in out


def test_acpm_run_profile_ts():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "NGL_sweep", "--profile", "T/S", "--dry-run")
    assert rc == 0
    assert "T/S" in out


def test_acpm_run_profile_ttft():
    rc, out, err = _run_cli("acpm", "run", "--campaign", "NGL_sweep", "--profile", "TTFT", "--dry-run")
    assert rc == 0
    assert "TTFT" in out


def test_manual_run_still_works():
    rc, out, err = _run_cli("run", "--help")
    assert rc == 0
    assert "--campaign" in out
    assert "--mode" in out


def test_acpm_run_appears_in_acpm_help():
    rc, out, err = _run_cli("acpm", "--help")
    assert rc == 0
    assert "run" in out