from __future__ import annotations

import pytest


def test_analyze_campaign_counts_successes_filters_invalid_rows_and_keeps_thermal_events(
    tmp_path,
) -> None:
    """Analysis drives scoring, so pin the row filters and denominator semantics."""
    from src.analyze import analyze_campaign
    from src.db import get_connection, init_db

    db_path = tmp_path / "lab.sqlite"
    init_db(db_path)

    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?, ?, ?, ?)",
            ("camp", "camp", "complete", "2026-05-06T00:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO configs (
                id, campaign_id, variable_name, variable_value, config_values_json, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("cfg", "camp", "ngl", "30", "{}", "complete"),
        )

        cycle_ids: dict[str, int] = {}
        for cycle_number, status in ((1, "complete"), (2, "invalid"), (3, "complete")):
            cur = conn.execute(
                """
                INSERT INTO cycles (config_id, campaign_id, cycle_number, status)
                VALUES (?, ?, ?, ?)
                """,
                ("cfg", "camp", cycle_number, status),
            )
            cycle_ids[status if cycle_number != 3 else "request_invalid"] = int(
                cur.lastrowid
            )

        conn.executemany(
            """
            INSERT INTO requests (
                cycle_id, campaign_id, config_id, cycle_number, request_index,
                is_cold, request_type, outcome, ttft_ms, prompt_per_second,
                predicted_per_second, cycle_status
            ) VALUES (?, 'camp', 'cfg', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                # Complete-cycle successes across request types all count in success_rate.
                (cycle_ids["complete"], 1, 1, 1, "speed_short", "success", 50.0, 900.0, 90.0, "complete"),
                (cycle_ids["complete"], 1, 2, 0, "speed_short", "success", 10.0, 1000.0, 100.0, "complete"),
                (cycle_ids["complete"], 1, 3, 0, "speed_medium", "success", 20.0, 800.0, 80.0, "complete"),
                (cycle_ids["complete"], 1, 4, 0, "quality_code", "success", 30.0, 700.0, 70.0, "complete"),
                (cycle_ids["complete"], 1, 5, 0, "speed_short", "timeout", None, None, None, "complete"),
                # These rows must not affect stats or request-count denominators.
                (cycle_ids["invalid"], 2, 2, 0, "speed_short", "success", 1.0, 1.0, 999.0, "complete"),
                (cycle_ids["request_invalid"], 3, 2, 0, "speed_short", "success", 2.0, 2.0, 888.0, "invalid"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO telemetry (
                campaign_id, config_id, cycle_id, timestamp,
                cpu_temp_c, power_limit_throttling
            ) VALUES ('camp', 'cfg', ?, ?, ?, ?)
            """,
            [
                (cycle_ids["complete"], "2026-05-06T00:00:01Z", 70.0, 1),
                # Invalid cycles are retained for thermal evidence.
                (cycle_ids["invalid"], "2026-05-06T00:00:02Z", 101.0, 0),
                (cycle_ids["request_invalid"], "2026-05-06T00:00:03Z", 70.0, 0),
            ],
        )

    stats = analyze_campaign("camp", db_path)["cfg"]

    assert stats["success_rate"] == pytest.approx(4 / 5)
    assert stats["total_attempted"] == 5
    assert stats["valid_warm_request_count"] == 1
    assert stats["valid_cold_request_count"] == 1
    assert stats["warm_tg_median"] == pytest.approx(100.0)
    assert stats["warm_ttft_median_ms"] == pytest.approx(10.0)
    assert stats["cold_ttft_median_ms"] == pytest.approx(50.0)
    assert stats["pp_median"] == pytest.approx(1000.0)
    assert stats["speed_medium_warm_tg_median"] == pytest.approx(80.0)
    assert stats["speed_medium_degradation_pct"] == pytest.approx(20.0)
    assert stats["thermal_events"] == 2
    assert stats["cycle_success_rate"] == pytest.approx(2 / 3)
