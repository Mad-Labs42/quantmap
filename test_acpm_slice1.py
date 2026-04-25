from __future__ import annotations

import json
from pathlib import Path

import pytest


def _sample_run_plan_kwargs(tmp_path: Path) -> dict:
    return {
        "parent_campaign_id": "NGL_sweep",
        "effective_campaign_id": "NGL_sweep__v30",
        "run_mode": "custom",
        "variable": "ngl",
        "all_campaign_values": [10, 30, 50],
        "selected_values": [30],
        "selected_configs": [{"config_id": "NGL_30"}],
        "cycles_per_config": 1,
        "requests_per_cycle": 6,
        "baseline_path": tmp_path / "baseline.yaml",
        "effective_lab_root": tmp_path,
        "db_path": tmp_path / "lab.sqlite",
        "state_file": tmp_path / "progress.json",
        "results_dir": tmp_path / "results" / "NGL_sweep__v30",
    }


def test_run_plan_records_scope_authority_and_reads_legacy_missing_as_unknown(tmp_path):
    from src.run_plan import RunPlan, resolve_scope_authority, scope_authority_from_snapshot

    plan = RunPlan(**_sample_run_plan_kwargs(tmp_path), scope_authority="user")

    snapshot = plan.to_snapshot_dict()
    assert snapshot["scope_authority"] == "user"
    assert scope_authority_from_snapshot(snapshot) == "user"
    assert scope_authority_from_snapshot({"run_mode": "custom"}) == "unknown"

    assert resolve_scope_authority(values_override=[30]) == "user"
    assert resolve_scope_authority(values_override=None) == "campaign_yaml"
    assert resolve_scope_authority(values_override=None, explicit_scope_authority="planner") == "planner"
    with pytest.raises(ValueError, match="scope_authority"):
        resolve_scope_authority(values_override=None, explicit_scope_authority="acpm")


def test_acpm_planner_contract_compiles_only_structural_execution_inputs():
    from src.acpm_planning import (
        ACPMPlanningMetadata,
        ACPMPlannerOutput,
        ACPMSelectedScope,
    )

    metadata = ACPMPlanningMetadata(
        planner_id="acpm-v1",
        planner_version="0.1",
        planner_policy_id="structural-prep-only",
        profile_name="Balanced",
        repeat_tier="1x",
        scope_authority="planner",
        source_campaign_ref="configs/campaigns/NGL_sweep.yaml",
        selected_scope_digest="sha256:test",
        narrowing_steps=[{"step": "scope_materialized", "reason": "test"}],
        coverage_policy={"coverage_class": "planner_selected"},
    )
    output = ACPMPlannerOutput(
        selected_scope=ACPMSelectedScope(
            variable="ngl",
            selected_values=[10, 30],
            selected_config_ids=["NGL_10", "NGL_30"],
        ),
        run_mode="quick",
        profile_name="Balanced",
        repeat_tier="1x",
        planning_metadata=metadata,
    )

    execution_inputs = output.to_execution_inputs()
    assert execution_inputs == {
        "run_mode": "quick",
        "scope_authority": "planner",
        "selected_values": [10, 30],
        "selected_config_ids": ["NGL_10", "NGL_30"],
        "scoring_profile_name": "acpm_balanced_v1",
    }
    assert output.to_planning_metadata_snapshot()["schema_id"] == "quantmap.acpm.planning_metadata"


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "run_plan_json",
        "effective_filter_policy_json",
        "scores",
        "recommendation_status",
        "recommended_config_id",
    ],
)
def test_acpm_planning_metadata_rejects_shadow_truth_fields(forbidden_key):
    from src.acpm_planning import ACPMPlanningMetadata

    with pytest.raises(ValueError, match=forbidden_key):
        ACPMPlanningMetadata(
            planner_id="acpm-v1",
            planner_version="0.1",
            planner_policy_id="structural-prep-only",
            profile_name="Balanced",
            repeat_tier="1x",
            scope_authority="planner",
            source_campaign_ref="configs/campaigns/NGL_sweep.yaml",
            selected_scope_digest="sha256:test",
            narrowing_steps=[],
            coverage_policy={forbidden_key: "not allowed"},
        )


def test_campaign_start_snapshot_metadata_column_is_nullable_and_round_trips(tmp_path):
    from src.db import get_connection, init_db

    db_path = tmp_path / "lab.sqlite"
    init_db(db_path)

    with get_connection(db_path) as conn:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(campaign_start_snapshot)")
        }
        assert "acpm_planning_metadata_json" in columns

        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?, ?, ?, ?)",
            ("non_acpm", "non_acpm", "running", "2026-04-23T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO campaign_start_snapshot (campaign_id, timestamp_utc) VALUES (?, ?)",
            ("non_acpm", "2026-04-23T00:00:00Z"),
        )
        row = conn.execute(
            "SELECT acpm_planning_metadata_json FROM campaign_start_snapshot WHERE campaign_id=?",
            ("non_acpm",),
        ).fetchone()
        assert row["acpm_planning_metadata_json"] is None

        metadata = {"schema_id": "quantmap.acpm.planning_metadata", "schema_version": 1}
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?, ?, ?, ?)",
            ("acpm_prepared", "acpm_prepared", "running", "2026-04-23T00:00:01Z"),
        )
        conn.execute(
            """
            INSERT INTO campaign_start_snapshot (
                campaign_id, timestamp_utc, acpm_planning_metadata_json
            ) VALUES (?, ?, ?)
            """,
            (
                "acpm_prepared",
                "2026-04-23T00:00:01Z",
                json.dumps(metadata, sort_keys=True),
            ),
        )
        row = conn.execute(
            "SELECT acpm_planning_metadata_json FROM campaign_start_snapshot WHERE campaign_id=?",
            ("acpm_prepared",),
        ).fetchone()
        assert json.loads(row["acpm_planning_metadata_json"]) == metadata


def test_collect_campaign_start_snapshot_accepts_optional_acpm_metadata(tmp_path, monkeypatch):
    from src import telemetry

    class _ExecutionEnvironment:
        support_tier = "windows_native"
        degraded_reasons: list[str] = []

        def to_json(self) -> str:
            return "{}"

    server_bin = tmp_path / "server.exe"
    model_path = tmp_path / "model.gguf"
    request_path = tmp_path / "speed_short.json"
    campaign_yaml = tmp_path / "campaign.yaml"
    baseline_yaml = tmp_path / "baseline.yaml"
    for path in (server_bin, model_path, request_path, campaign_yaml, baseline_yaml):
        path.write_text("content", encoding="utf-8")

    monkeypatch.setattr(
        telemetry,
        "classify_execution_environment",
        lambda: _ExecutionEnvironment(),
    )

    metadata = {"schema_id": "quantmap.acpm.planning_metadata", "schema_version": 1}
    snap = telemetry.collect_campaign_start_snapshot(
        campaign_id="acpm_prepared",
        server_bin=server_bin,
        model_path=model_path,
        build_commit="test",
        request_files={"speed_short": request_path},
        campaign_yaml_path=campaign_yaml,
        baseline_yaml_path=baseline_yaml,
        sampling_params={},
        cpu_affinity_policy="all_cores",
        acpm_planning_metadata=metadata,
    )
    assert json.loads(snap["acpm_planning_metadata_json"]) == metadata

    non_acpm_snap = telemetry.collect_campaign_start_snapshot(
        campaign_id="non_acpm",
        server_bin=server_bin,
        model_path=model_path,
        build_commit="test",
        request_files={"speed_short": request_path},
        campaign_yaml_path=campaign_yaml,
        baseline_yaml_path=baseline_yaml,
        sampling_params={},
        cpu_affinity_policy="all_cores",
    )
    assert "acpm_planning_metadata_json" not in non_acpm_snap
