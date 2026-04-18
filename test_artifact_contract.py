"""
test_artifact_contract.py
Phase 6 validation: 4-artifact canonical contract.

Checks:
  1. ARTIFACT_TYPES_DEPRECATED does not overlap with canonical types.
  2. write_raw_jsonl writes _stream into the primary record (not only merged_path).
  3. TelemetryCollector.__init__ no longer requires telemetry_jsonl_path.
  4. TelemetryCollector writes only to raw_telemetry_jsonl_path (merged path).
  5. measurement_paths / report_paths do not add raw.jsonl or telemetry.jsonl
     to the 'approved' dict subset (backward compat aliases are still there,
     but the canonical set is exactly 1 measurement file).
  6. Trust identity completeness requires the canonical measurement artifact.
  7. A complete campaign invoked without resume does not mutate telemetry.
"""
from __future__ import annotations

import io
import json
import sqlite3
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level imports
# ---------------------------------------------------------------------------
from src.artifact_paths import (
    ARTIFACT_CAMPAIGN_SUMMARY,
    ARTIFACT_METADATA,
    ARTIFACT_RAW_TELEMETRY,
    ARTIFACT_RUN_REPORTS,
    ARTIFACT_TYPES_DEPRECATED,
    measurement_paths,
    report_paths,
)
from src.db import write_raw_jsonl


# =============================================================================
# Test 1 — canonical / deprecated separation
# =============================================================================

def test_canonical_not_in_deprecated():
    """Canonical type constants must not appear in ARTIFACT_TYPES_DEPRECATED."""
    canonical = {
        ARTIFACT_CAMPAIGN_SUMMARY,
        ARTIFACT_RUN_REPORTS,
        ARTIFACT_RAW_TELEMETRY,
        ARTIFACT_METADATA,
    }
    overlap = canonical & ARTIFACT_TYPES_DEPRECATED
    assert not overlap, (
        f"Canonical artifact types found in ARTIFACT_TYPES_DEPRECATED: {overlap}. "
        "These canonical types must NEVER be deprecated."
    )


# =============================================================================
# Test 2 — write_raw_jsonl injects _stream into primary record
# =============================================================================

def test_write_raw_jsonl_injects_stream_into_primary(tmp_path):
    """_stream must appear in the primary JSONL file, not only the merged path."""
    primary = tmp_path / "raw-telemetry.jsonl"
    record = {"campaign_id": "test", "value": 42}

    write_raw_jsonl(primary, record, stream="requests")

    lines = primary.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["_stream"] == "requests", (
        "write_raw_jsonl must inject _stream into the primary file record."
    )
    assert parsed["value"] == 42


def test_write_raw_jsonl_no_double_write_when_paths_equal(tmp_path):
    """No duplicate writes when jsonl_path and merged_path are the same file."""
    path = tmp_path / "raw-telemetry.jsonl"
    record = {"x": 1}

    write_raw_jsonl(path, record, stream="telemetry", merged_path=path)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1, (
        "Record must appear exactly once when jsonl_path == merged_path."
    )


def test_write_raw_jsonl_double_write_different_paths(tmp_path):
    """Record is written to both files when paths differ (transition compat)."""
    primary = tmp_path / "a.jsonl"
    secondary = tmp_path / "b.jsonl"
    record = {"y": 2}

    write_raw_jsonl(primary, record, stream="requests", merged_path=secondary)

    primary_lines = primary.read_text(encoding="utf-8").strip().splitlines()
    secondary_lines = secondary.read_text(encoding="utf-8").strip().splitlines()
    assert len(primary_lines) == 1
    assert len(secondary_lines) == 1
    p = json.loads(primary_lines[0])
    s = json.loads(secondary_lines[0])
    assert p["_stream"] == "requests"
    assert s["_stream"] == "requests"


# =============================================================================
# Test 3 — TelemetryCollector constructor no longer requires telemetry_jsonl_path
# =============================================================================

def test_telemetry_collector_constructor_no_legacy_param(tmp_path):
    """TelemetryCollector must accept db_path + raw_telemetry_jsonl_path only."""
    from src.telemetry import TelemetryCollector

    db_path = tmp_path / "lab.sqlite"
    merged = tmp_path / "raw-telemetry.jsonl"

    # Must not raise — no telemetry_jsonl_path required
    collector = TelemetryCollector(db_path=db_path, raw_telemetry_jsonl_path=merged)
    assert collector._merged_jsonl_path == merged
    assert not hasattr(collector, "_jsonl_path"), (
        "TelemetryCollector must not have a _jsonl_path attribute (legacy writer removed)."
    )


def test_telemetry_collector_write_sample_uses_merged_path(tmp_path):
    """_write_sample must write to raw_telemetry_jsonl_path (merged), not a separate file."""
    from src.telemetry import TelemetryCollector, TelemetrySample
    from dataclasses import asdict
    from datetime import datetime, timezone

    db_path = tmp_path / "lab.sqlite"
    merged = tmp_path / "raw-telemetry.jsonl"

    collector = TelemetryCollector(db_path=db_path, raw_telemetry_jsonl_path=merged)

    # Build a minimal sample
    sample = TelemetrySample(
        campaign_id="test",
        config_id="cfg_01",
        cycle_id=1,
        timestamp=datetime.now(timezone.utc).isoformat(),
        cpu_temp_c=None,
        power_limit_throttling=None,
        gpu_vram_used_mb=None,
        gpu_temp_c=None,
        cpu_power_w=None,
        ram_used_gb=None,
        cpu_pcore_freq_ghz=None,
        cpu_ecore_freq_ghz=None,
        gpu_util_pct=None,
        gpu_power_w=None,
        gpu_graphics_clock_mhz=None,
        gpu_mem_clock_mhz=None,
        gpu_pstate=None,
        gpu_throttle_reasons=None,
        liquid_temp_c=None,
        disk_read_mbps=None,
        disk_write_mbps=None,
        page_faults_sec=None,
        net_sent_mbps=None,
        net_recv_mbps=None,
        cpu_freq_mhz=None,
        cpu_util_pct=None,
        cpu_util_per_core_json=None,
        ram_available_gb=None,
        ram_committed_gb=None,
        pagefile_used_gb=None,
        context_switches_sec=None,
        interrupts_sec=None,
        server_cpu_pct=None,
        server_rss_mb=None,
        server_private_bytes_mb=None,
        server_vms_mb=None,
        server_thread_count=None,
        server_handle_count=None,
        server_pid=None,
        cpu_core_voltage_v=None,
        cpu_ia_cores_power_w=None,
        gpu_hotspot_temp_c=None,
        gpu_mem_temp_c=None,
        gpu_fan_rpm=None,
        cpu_fan_rpm=None,
    )

    # _write_sample only writes JSONL (DB insert will fail without schema — that's ok here)
    collector._write_sample(sample)

    # The merged path must have content
    assert merged.exists(), "raw-telemetry.jsonl must be written by _write_sample."
    lines = merged.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed.get("_stream") == "telemetry", (
        "_write_sample must annotate the record with _stream='telemetry'."
    )

    # No separate telemetry.jsonl should exist
    legacy_tele = tmp_path / "telemetry.jsonl"
    assert not legacy_tele.exists(), (
        "TelemetryCollector must NOT write a separate telemetry.jsonl (Phase 6 cleanup)."
    )


# =============================================================================
# Test 4 — measurement_paths canonical set is exactly 1 file
# =============================================================================

def test_measurement_paths_canonical_count(tmp_path):
    """The approved measurement-family output is exactly raw-telemetry.jsonl."""
    paths = measurement_paths(tmp_path, "test-model", "C01_test", create=False)

    canonical_keys = {"raw_telemetry_jsonl"}
    assert canonical_keys <= set(paths.keys()), "raw_telemetry_jsonl must be present."

    # Raw.jsonl and telemetry.jsonl retained as aliases for read-compat, but their
    # values must point to deprecated filenames (sanity check).
    assert paths["raw_jsonl"].name == "raw.jsonl"
    assert paths["telemetry_jsonl"].name == "telemetry.jsonl"
    assert paths["raw_telemetry_jsonl"].name == "raw-telemetry.jsonl"


# =============================================================================
# Test 5 — report_paths canonical set has no unexpected new files
# =============================================================================

def test_report_paths_canonical_set(tmp_path):
    """report_paths must expose exactly the 4-artifact fields plus deprecated aliases."""
    paths = report_paths(tmp_path, "test-model", "C01_test", create=False)

    required = {"campaign_summary_md", "run_reports_md", "metadata_json", "dir"}
    deprecated_aliases = {"report_md", "report_v2_md", "scores_csv"}
    allowed = required | deprecated_aliases

    unexpected = set(paths.keys()) - allowed
    assert not unexpected, (
        f"Unexpected keys in report_paths: {unexpected}. "
        "Do not add new artifact families here — use a dedicated function."
    )

    # Verify canonical filenames
    assert paths["campaign_summary_md"].name == "campaign-summary.md"
    assert paths["run_reports_md"].name == "run-reports.md"
    assert paths["metadata_json"].name == "metadata.json"


# =============================================================================
# Test 6 — Trust Identity artifact completeness requires raw_telemetry_jsonl
# =============================================================================

def test_trust_identity_artifact_completeness(tmp_path):
    """summarize_report_artifact_status must require ARTIFACT_RAW_TELEMETRY for completion."""
    from src.trust_identity import summarize_report_artifact_status
    from src.db import init_db, get_connection
    from src.artifact_paths import (
        ARTIFACT_CAMPAIGN_SUMMARY, 
        ARTIFACT_RUN_REPORTS, 
        ARTIFACT_METADATA,
        ARTIFACT_RAW_TELEMETRY,
    )

    db_path = tmp_path / "lab.sqlite"
    init_db(db_path)
    campaign_id = "test_C01"

    _now = "2026-04-17T00:00:00Z"
    
    # helper to insert artifact
    def add_art(atype: str, status: str = "complete", campaign: str = campaign_id):
        artifact_path = tmp_path / "artifacts" / f"{atype}.artifact"
        with get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO artifacts (campaign_id, artifact_type, path, created_at, status) 
                VALUES (?, ?, ?, ?, ?)
                """,
                (campaign, atype, str(artifact_path), _now, status)
            )
            conn.commit()

    # 1. Empty setup -> missing/partial
    assert summarize_report_artifact_status(campaign_id, db_path) in ("legacy_unknown", "partial")

    # 2. Add only 3 artifacts (the old broken behavior)
    add_art(ARTIFACT_CAMPAIGN_SUMMARY)
    add_art(ARTIFACT_RUN_REPORTS)
    add_art(ARTIFACT_METADATA)

    # Missing raw_telemetry -> should be partial
    assert summarize_report_artifact_status(campaign_id, db_path) == "partial", (
        "Campaign must NOT be complete if raw_telemetry_jsonl is missing."
    )

    # 3. Add raw telemetry
    add_art(ARTIFACT_RAW_TELEMETRY)

    # Now we have all 4 canonical artifacts -> complete
    assert summarize_report_artifact_status(campaign_id, db_path) == "complete", (
        "Campaign must be 'complete' when all 4 canonical artifacts are registered."
    )

    legacy_campaign_id = "legacy_C01"
    for legacy_type in ("report_md", "report_v2_md", "scores_csv"):
        add_art(legacy_type, campaign=legacy_campaign_id)

    assert summarize_report_artifact_status(legacy_campaign_id, db_path) == "partial", (
        "Legacy fallback must not be complete when telemetry artifacts are missing."
    )

    add_art("raw_jsonl", campaign=legacy_campaign_id)
    assert summarize_report_artifact_status(legacy_campaign_id, db_path) == "partial", (
        "Legacy fallback must not be complete until both legacy telemetry artifacts exist."
    )

    add_art("telemetry_jsonl", campaign=legacy_campaign_id)
    assert summarize_report_artifact_status(legacy_campaign_id, db_path) == "complete", (
        "Legacy fallback may be complete only when report, score, and telemetry artifacts exist."
    )


def test_complete_campaign_no_resume_does_not_mutate_telemetry_stream(tmp_path, monkeypatch):
    """Early exits before execution must not append raw-telemetry markers."""
    monkeypatch.setenv("QUANTMAP_LAB_ROOT", str(tmp_path / "default-lab"))

    from src import runner
    from src.db import init_db, get_connection

    lab_root = tmp_path / "lab"
    db_path = lab_root / "db" / "lab.sqlite"
    db_path.parent.mkdir(parents=True)
    init_db(db_path)

    campaign_id = "complete_C01"
    now = "2026-04-17T00:00:00Z"
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?, ?, 'complete', ?)",
            (campaign_id, campaign_id, now),
        )
        conn.commit()

    class _Console:
        def print(self, *args, **kwargs):
            return None

    fake_server = types.ModuleType("src.server")
    fake_server.SERVER_BIN = tmp_path / "llama-server.exe"
    fake_server.MODEL_PATH = tmp_path / "model.gguf"
    fake_policy = types.ModuleType("src.telemetry_policy")
    fake_policy.enforce_current_run_readiness = lambda: None

    monkeypatch.setitem(sys.modules, "src.server", fake_server)
    monkeypatch.setitem(sys.modules, "src.telemetry_policy", fake_policy)
    monkeypatch.setattr(runner, "console", _Console())
    monkeypatch.setattr(runner, "_derive_lab_root", lambda baseline_path: lab_root)
    monkeypatch.setattr(runner, "_setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_run_preflight_checks", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner.tele, "shutdown", lambda: None)
    monkeypatch.setattr(
        runner,
        "load_baseline",
        lambda path=runner.BASELINE_YAML: {
            "model": {"name": "test-model"},
            "requests": {},
            "lab": {},
        },
    )
    monkeypatch.setattr(
        runner,
        "load_campaign",
        lambda _campaign_id: {"type": "primary_sweep", "values": [1]},
    )
    monkeypatch.setattr(runner, "validate_campaign_purity", lambda baseline, campaign: "threads")
    monkeypatch.setattr(
        runner,
        "build_config_list",
        lambda baseline, campaign: [
            {
                "config_id": "cfg1",
                "variable_name": "threads",
                "variable_value": 1,
                "server_args": [],
                "full_config": {},
            }
        ],
    )

    runner.run_campaign(
        campaign_id,
        resume=False,
        baseline_path=tmp_path / "baseline.yaml",
    )

    assert not list((lab_root / "artifacts").rglob("raw-telemetry.jsonl"))
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM artifacts WHERE campaign_id=? AND artifact_type=?",
            (campaign_id, ARTIFACT_RAW_TELEMETRY),
        ).fetchall()
    assert rows == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
