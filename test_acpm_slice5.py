from __future__ import annotations

from pathlib import Path


def _score_result(
    *,
    winner: str | None,
    scoring_profile_name: str = "acpm_balanced_v1",
    methodology_snapshot_id: int | None = 17,
) -> dict:
    class _Profile:
        def __init__(self, name: str) -> None:
            self.name = name

    return {
        "winner": winner,
        "methodology_snapshot_id": methodology_snapshot_id,
        "scoring_profile": _Profile(scoring_profile_name),
    }


def _planning_metadata(
    *,
    coverage_class: str = "full",
    selected_values: list[int] | None = None,
) -> dict:
    return {
        "profile_name": "Balanced",
        "repeat_tier": "5x" if coverage_class == "full" else "1x",
        "scope_authority": "planner",
        "coverage_policy": {
            "ngl_coverage_class": coverage_class,
            "selected_ngl_values": selected_values or [10, 20, 30, 40, 50, 60, 70, 80, 90, 999],
            "scaffold_policy_id": None if coverage_class == "full" else "acpm_v1_ngl_scaffold_1x",
        },
    }


def test_best_validated_config_is_handoff_ready():
    from src.acpm_recommendation import evaluate_acpm_recommendation

    record = evaluate_acpm_recommendation(
        campaign_id="NGL_sweep",
        run_mode="full",
        scope_authority="planner",
        scores=_score_result(winner="NGL_sweep_999"),
        acpm_planning_metadata=_planning_metadata(coverage_class="full"),
    )

    snapshot = record.to_snapshot_dict()
    assert snapshot["status"] == "best_validated_config"
    assert snapshot["leading_config_id"] == "NGL_sweep_999"
    assert snapshot["recommended_config_id"] == "NGL_sweep_999"
    assert snapshot["handoff_ready"] is True
    assert snapshot["caveat_codes"] == []


def test_standard_run_yields_strong_provisional_leader():
    from src.acpm_recommendation import evaluate_acpm_recommendation

    record = evaluate_acpm_recommendation(
        campaign_id="NGL_sweep__standard",
        run_mode="standard",
        scope_authority="planner",
        scores=_score_result(winner="NGL_sweep_999"),
        acpm_planning_metadata=_planning_metadata(coverage_class="full"),
    )

    snapshot = record.to_snapshot_dict()
    assert snapshot["status"] == "strong_provisional_leader"
    assert snapshot["recommended_config_id"] == "NGL_sweep_999"
    assert snapshot["handoff_ready"] is False
    assert "reduced_repetition" in snapshot["caveat_codes"]


def test_scaffolded_scope_requires_deeper_validation():
    from src.acpm_recommendation import evaluate_acpm_recommendation

    record = evaluate_acpm_recommendation(
        campaign_id="NGL_sweep__quick",
        run_mode="quick",
        scope_authority="planner",
        scores=_score_result(winner="NGL_sweep_90"),
        acpm_planning_metadata=_planning_metadata(
            coverage_class="scaffolded_1x",
            selected_values=[10, 30, 50, 70, 90, 999],
        ),
    )

    snapshot = record.to_snapshot_dict()
    assert snapshot["status"] == "needs_deeper_validation"
    assert snapshot["leading_config_id"] == "NGL_sweep_90"
    assert snapshot["recommended_config_id"] is None
    assert snapshot["handoff_ready"] is False
    assert "partial_scope" in snapshot["caveat_codes"]
    assert "scaffolded_ngl_coverage" in snapshot["caveat_codes"]


def test_missing_winner_yields_insufficient_evidence():
    from src.acpm_recommendation import evaluate_acpm_recommendation

    record = evaluate_acpm_recommendation(
        campaign_id="NGL_sweep__quick",
        run_mode="quick",
        scope_authority="planner",
        scores=_score_result(winner=None),
        acpm_planning_metadata=_planning_metadata(coverage_class="full"),
    )

    snapshot = record.to_snapshot_dict()
    assert snapshot["status"] == "insufficient_evidence_to_recommend"
    assert snapshot["leading_config_id"] is None
    assert snapshot["recommended_config_id"] is None
    assert snapshot["handoff_ready"] is False
    assert snapshot["caveat_codes"] == ["no_valid_winner"]


def test_new_db_has_recommendation_record_json_column(tmp_path: Path):
    from src.db import get_connection, init_db

    db_path = tmp_path / "lab.sqlite"
    init_db(db_path)

    with get_connection(db_path) as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(campaigns)")}
        assert "recommendation_record_json" in cols


def test_migrate_v14_adds_recommendation_record_json_column(tmp_path: Path):
    from src.db import get_connection, init_db

    db_path = tmp_path / "legacy.sqlite"
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE campaigns (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                variable TEXT,
                campaign_type TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            );
            CREATE TABLE schema_version (
                version INTEGER NOT NULL,
                applied_at TEXT NOT NULL
            );
            INSERT INTO schema_version (version, applied_at) VALUES (14, '2026-04-23T00:00:00Z');
            """
        )
        conn.commit()

    init_db(db_path)

    with get_connection(db_path) as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(campaigns)")}
        assert "recommendation_record_json" in cols


def test_recommendation_record_round_trips_via_db_helper(tmp_path: Path):
    from src.acpm_recommendation import evaluate_acpm_recommendation
    from src.db import get_connection, init_db, read_recommendation_record, write_recommendation_record

    db_path = tmp_path / "lab.sqlite"
    init_db(db_path)

    record = evaluate_acpm_recommendation(
        campaign_id="NGL_sweep",
        run_mode="full",
        scope_authority="planner",
        scores=_score_result(winner="NGL_sweep_999"),
        acpm_planning_metadata=_planning_metadata(coverage_class="full"),
    )

    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?, ?, ?, ?)",
            ("NGL_sweep", "NGL_sweep", "complete", "2026-04-23T00:00:00Z"),
        )
        write_recommendation_record(conn, "NGL_sweep", record.to_snapshot_dict())
        conn.commit()

        round_trip = read_recommendation_record(conn, "NGL_sweep")

    assert round_trip is not None
    assert round_trip["status"] == "best_validated_config"
    assert round_trip["recommended_config_id"] == "NGL_sweep_999"
    assert round_trip["handoff_ready"] is True



