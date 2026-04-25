from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _recommendation_record(
    *,
    status: str = "needs_deeper_validation",
    leading_config_id: str | None = "NGL_sweep_90",
    recommended_config_id: str | None = None,
    handoff_ready: bool | None = False,
    caveat_codes: list[str] | None = None,
    coverage_class: str = "scaffolded_1x",
) -> dict:
    return {
        "schema_id": "quantmap.acpm.recommendation_record",
        "schema_version": 1,
        "status": status,
        "leading_config_id": leading_config_id,
        "recommended_config_id": recommended_config_id,
        "handoff_ready": handoff_ready,
        "caveat_codes": caveat_codes or ["partial_scope", "scaffolded_ngl_coverage"],
        "evidence": {
            "coverage_class": coverage_class,
            "scope_authority": "planner",
            "selected_ngl_values": [10, 30, 50, 70, 90, 999],
            "scoring_profile_name": "acpm_balanced_v1",
            "methodology_snapshot_id": 17,
        },
    }


def test_trust_identity_projects_recommendation_record(tmp_path: Path):
    from src.db import get_connection, init_db, write_recommendation_record
    from src.trust_identity import load_run_identity, recommendation_projection

    db_path = tmp_path / "lab.sqlite"
    init_db(db_path)

    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?, ?, ?, ?)",
            ("NGL_sweep", "NGL_sweep", "complete", "2026-04-23T00:00:00Z"),
        )
        write_recommendation_record(conn, "NGL_sweep", _recommendation_record())
        conn.commit()

    identity = load_run_identity("NGL_sweep", db_path)
    projection = recommendation_projection(identity)

    assert projection["available"] is True
    assert projection["status"] == "needs_deeper_validation"
    assert projection["leading_config_id"] == "NGL_sweep_90"
    assert projection["recommended_config_id"] is None
    assert projection["coverage_class"] == "scaffolded_1x"
    assert projection["source"] == "campaigns.recommendation_record_json"


def test_export_recommendation_projection_preserves_authority_fields():
    from src.export import _build_recommendation_projection

    identity = SimpleNamespace(
        recommendation=_recommendation_record(
            status="strong_provisional_leader",
            leading_config_id="NGL_sweep_999",
            recommended_config_id="NGL_sweep_999",
            handoff_ready=False,
            caveat_codes=["reduced_repetition"],
            coverage_class="full",
        ),
        sources={"recommendation": "campaigns.recommendation_record_json"},
    )

    projection = _build_recommendation_projection(identity)

    assert projection["status"] == "strong_provisional_leader"
    assert projection["leading_config_id"] == "NGL_sweep_999"
    assert projection["recommended_config_id"] == "NGL_sweep_999"
    assert projection["handoff_ready"] is False
    assert projection["coverage_class"] == "full"
    assert projection["caveat_codes"] == ["reduced_repetition"]


def test_campaign_summary_recommendation_lines_keep_leader_and_recommendation_separate():
    from src.report import render_recommendation_projection

    lines = render_recommendation_projection(
        {
            "available": True,
            "status": "needs_deeper_validation",
            "leading_config_id": "NGL_sweep_90",
            "recommended_config_id": None,
            "handoff_ready": False,
            "caveat_codes": ["partial_scope", "scaffolded_ngl_coverage"],
            "coverage_class": "scaffolded_1x",
            "scope_authority": "planner",
            "selected_ngl_values": [10, 30, 50, 70, 90, 999],
            "source": "campaigns.recommendation_record_json",
        }
    )

    joined = "\n".join(lines)
    assert "Leading config" in joined
    assert "Recommended config" in joined
    assert "NGL_sweep_90" in joined
    assert "No ACPM recommendation issued" in joined
    assert "scaffolded_1x" in joined


def test_run_reports_recommendation_section_handles_missing_record_without_fabrication():
    from src.report_campaign import _section_recommendation

    lines = _section_recommendation({"available": False, "source": "not_recorded"})
    joined = "\n".join(lines)

    assert "Recommendation Authority" in joined
    assert "not_recorded" in joined.lower()
    assert "best_validated_config" not in joined


def test_compare_result_and_markdown_include_recommendation_projection(tmp_path: Path):
    from src.compare import generate_compare_result
    from src.db import get_connection, init_db, write_recommendation_record
    from src.report_compare import render_compare_markdown

    db_path = tmp_path / "lab.sqlite"
    init_db(db_path)

    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?, ?, ?, ?)",
            ("A", "Campaign A", "complete", "2026-04-23T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?, ?, ?, ?)",
            ("B", "Campaign B", "complete", "2026-04-23T01:00:00Z"),
        )
        conn.execute(
            "INSERT INTO scores (campaign_id, config_id, warm_tg_median, warm_ttft_median_ms, warm_tg_cv, passed_filters, is_score_winner) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("A", "cfg_90", 10.0, 220.0, 0.02, 1, 1),
        )
        conn.execute(
            "INSERT INTO scores (campaign_id, config_id, warm_tg_median, warm_ttft_median_ms, warm_tg_cv, passed_filters, is_score_winner) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("B", "cfg_999", 12.0, 210.0, 0.02, 1, 1),
        )
        write_recommendation_record(
            conn,
            "A",
            _recommendation_record(
                status="needs_deeper_validation",
                leading_config_id="cfg_90",
                recommended_config_id=None,
                handoff_ready=False,
            ),
        )
        write_recommendation_record(
            conn,
            "B",
            _recommendation_record(
                status="best_validated_config",
                leading_config_id="cfg_999",
                recommended_config_id="cfg_999",
                handoff_ready=True,
                caveat_codes=[],
                coverage_class="full",
            ),
        )
        conn.commit()

    result = generate_compare_result("A", "B", db_path)
    rendered = render_compare_markdown(result)

    assert result.to_dict()["recommendation_a"]["status"] == "needs_deeper_validation"
    assert result.to_dict()["recommendation_b"]["status"] == "best_validated_config"
    assert "Recommendation Authority" in rendered
    assert "needs_deeper_validation" in rendered
    assert "best_validated_config" in rendered


def test_explain_briefing_reads_recommendation_authority_without_replacing_winner(tmp_path: Path):
    from src.db import get_connection, init_db, write_recommendation_record
    from src.explain import get_campaign_briefing

    db_path = tmp_path / "lab.sqlite"
    init_db(db_path)

    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?, ?, ?, ?)",
            ("NGL_sweep", "NGL_sweep", "complete", "2026-04-23T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO scores (campaign_id, config_id, warm_tg_median, warm_ttft_median_ms, warm_tg_cv, passed_filters, is_score_winner) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("NGL_sweep", "cfg_90", 11.0, 215.0, 0.02, 1, 1),
        )
        write_recommendation_record(conn, "NGL_sweep", _recommendation_record())
        conn.commit()

    briefing = get_campaign_briefing("NGL_sweep", db_path, evidence_mode=True)

    assert "cfg_90" in briefing.headline
    assert any("ACPM recommendation status: needs_deeper_validation" in line for line in briefing.evidence_lines)
    assert any("Recommended config: none issued" in line for line in briefing.evidence_lines)
