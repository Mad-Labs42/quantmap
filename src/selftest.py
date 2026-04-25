"""
QuantMap — selftest.py

Deterministic trust suite for toolchain integrity.
Verifies governance, registry, scoring math, and reporting path.
"""

import os
import tempfile
import sqlite3
from pathlib import Path

from src import ui
from src.diagnostics import Status, CheckResult, DiagnosticReport

def test_registry() -> CheckResult:
    """Verify registry loading and basic definitions."""
    try:
        from src.governance import BUILTIN_REGISTRY
        if len(BUILTIN_REGISTRY) < 10:
            return CheckResult("Registry Intake", Status.FAIL, "Registry loaded but feels sparse")
        return CheckResult("Registry Intake", Status.PASS, f"Verified {len(BUILTIN_REGISTRY)} metric definitions")
    except Exception as e:
        return CheckResult("Registry Intake", Status.FAIL, f"Registry Load Error: {e}")

def test_scoring_core() -> CheckResult:
    """Verify scoring logic using hardcoded fixture data produces deterministic output."""
    try:
        from src import score
        from src.governance import get_default_profile, get_builtin_registry

        # Minimal fixture: one config with deterministic warm TG and TTFT values.
        # All required scoring metrics are present so the config is rankable.
        # Designed for I/O-free, RNG-free determinism.
        # NOTE: valid_warm_request_count must be >= ELIMINATION_FILTERS["min_valid_warm_count"]
        # (default 10) or the fixture config is eliminated before compute_scores is reached.
        fixture_stats: dict = {
            "fixture_cfg_A": {
                "warm_tg_median":          10.0,
                "warm_tg_p10":              9.0,
                "warm_ttft_median_ms":    150.0,
                "warm_ttft_p90_ms":       200.0,
                "cold_ttft_median_ms":   3000.0,
                "pp_median":              500.0,
                "warm_tg_cv":             0.02,
                "thermal_events":            0,
                "outlier_count":             0,
                "success_rate":            1.0,
                "valid_warm_request_count": 10,
                "requests_total":           11,
            }
        }
        profile  = get_default_profile()
        registry = get_builtin_registry()
        passing, _elim = score.apply_elimination_filters(fixture_stats)
        rankable, _ifail, unrankable = score._split_by_rankability(passing, registry)
        scores_df, _, _, _ = score.compute_scores(
            rankable, unrankable, fixture_stats, profile, registry, {}
        )
        if scores_df.empty or "is_score_winner" not in scores_df.columns:
            return CheckResult(
                "Scoring Engine",
                Status.FAIL,
                "Scoring returned empty DataFrame — scoring pipeline may be broken",
            )
        winner_rows = scores_df[scores_df["is_score_winner"] == True]  # noqa: E712
        winner = winner_rows.index[0] if not winner_rows.empty else None
        if winner != "fixture_cfg_A":
            return CheckResult(
                "Scoring Engine",
                Status.FAIL,
                f"Scoring regression: expected winner 'fixture_cfg_A', got '{winner}'",
            )
        return CheckResult("Scoring Engine", Status.PASS, "Deterministic fixture score verified")
    except Exception as e:
        return CheckResult("Scoring Engine", Status.FAIL, f"Scoring Logic Error: {e}")


def test_persistence_smoke() -> CheckResult:
    """Verify DB write/read path on a temporary database."""
    tmp_db = None
    try:
        fd, tmp_db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        tmp_db = Path(tmp_db_path)
        
        conn = sqlite3.connect(tmp_db)
        conn.execute("CREATE TABLE test (key TEXT, val TEXT)")
        conn.execute("INSERT INTO test VALUES ('selftest', 'ok')")
        row = conn.execute("SELECT val FROM test").fetchone()
        conn.close()
        
        if row and row[0] == 'ok':
            return CheckResult("Persistence (DB)", Status.PASS, "SQLite IO verified")
        return CheckResult("Persistence (DB)", Status.FAIL, "DB Write/Read mismatch")
    except Exception as e:
        return CheckResult("Persistence (DB)", Status.FAIL, f"DB Error: {e}")
    finally:
        if tmp_db and tmp_db.exists():
            tmp_db.unlink()

def run_selftest(live: bool = False):
    """Execute the trust suite."""
    ui.print_banner("QuantMap Self-Test — Tool Integrity Suite")
    
    report = DiagnosticReport("Tool Integrity Report")
    
    # 1. Governance
    report.add(test_registry())
    
    # 2. Persistence
    report.add(test_persistence_smoke())
    
    # 3. Analytics
    report.add(test_scoring_core())
    
    # 4. Live Check (Optional)
    if live:
        report.add(CheckResult("Live Server", Status.INFO, "Skipping live check - logic pending backend refactor"))
    else:
        report.add(CheckResult("Live Path", Status.SKIP, "Live checks disabled (use --live)"))

    report.print_summary(
        ready_label="TOOLING READY",
        warnings_label="TOOLING READY WITH WARNINGS",
        blocked_label="TOOLING BLOCKED",
    )
    ui.print_next_actions([
        "quantmap doctor",
        "quantmap run --campaign <ID> --validate",
    ])
    
    return report.readiness != Status.FAIL

if __name__ == "__main__":
    run_selftest()
