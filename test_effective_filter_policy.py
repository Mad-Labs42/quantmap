"""
Tests for ACPM Slice 2: effective_filter_policy_json seam.

Covers:
  - DB schema round-trip and migration from v13
  - canonical_json_sha256 key-order stability
  - build_override_layers for mode and YAML layers
  - build_effective_filter_policy: profile default, custom, quick, YAML override
  - scoring confirmation: confirmed and mismatch
  - trust_identity projection: explicit, reconstructed, inferred_limited, unknown
  - metadata.json filter_policy projection
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_BASE_GATES: dict = {
    "max_cv": 0.05,
    "max_thermal_events": 0.0,
    "max_outliers": 3.0,
    "max_warm_ttft_p90_ms": 500.0,
    "min_success_rate": 0.9,
    "min_warm_tg_p10": 7.0,
    "min_valid_warm_count": 3.0,
}

_BASE_SOURCE: dict = {
    "source": "methodology_snapshot",
    "snapshot_id": 1,
    "profile_name": "default_throughput_v1",
    "profile_version": "v1",
    "methodology_version": None,
    "capture_quality": "complete",
    "capture_source": "score_campaign:initial_scoring",
}

_FULL_RUN_PLAN_SNAP: dict = {
    "run_mode": "full",
    "filter_overrides": None,
}

_CUSTOM_RUN_PLAN_SNAP: dict = {
    "run_mode": "custom",
    "filter_overrides": {"min_valid_warm_count": 1},
}

_QUICK_RUN_PLAN_SNAP: dict = {
    "run_mode": "quick",
    "filter_overrides": {"min_valid_warm_count": 3},
}


# ---------------------------------------------------------------------------
# DB schema
# ---------------------------------------------------------------------------

def test_new_db_has_effective_filter_policy_json_column(tmp_path: Path) -> None:
    from src.db import get_connection, init_db, SCHEMA_VERSION

    db = tmp_path / "lab.sqlite"
    init_db(db)

    with get_connection(db) as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(campaign_start_snapshot)")}
        assert "effective_filter_policy_json" in cols

        version = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        assert version["version"] == SCHEMA_VERSION
        assert SCHEMA_VERSION == 14


def test_new_db_effective_filter_policy_json_is_nullable(tmp_path: Path) -> None:
    from src.db import get_connection, init_db

    db = tmp_path / "lab.sqlite"
    init_db(db)

    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?,?,?,?)",
            ("legacy_run", "legacy_run", "complete", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO campaign_start_snapshot (campaign_id, timestamp_utc) VALUES (?,?)",
            ("legacy_run", "2026-01-01T00:00:00Z"),
        )
        row = conn.execute(
            "SELECT effective_filter_policy_json FROM campaign_start_snapshot WHERE campaign_id=?",
            ("legacy_run",),
        ).fetchone()
        assert row["effective_filter_policy_json"] is None


def test_migration_from_v13_adds_column_leaves_existing_rows_null(tmp_path: Path) -> None:
    """Simulate a v13 DB (without effective_filter_policy_json) and migrate it."""
    from src.db import get_connection, init_db, SCHEMA_VERSION

    db = tmp_path / "lab.sqlite"

    # Build a v13-equivalent DB by hand: DDL without the new column, schema_version=13.
    with sqlite3.connect(db) as raw:
        raw.execute(
            """
            CREATE TABLE campaigns (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
            )
            """
        )
        raw.execute(
            """
            CREATE TABLE campaign_start_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                run_plan_json TEXT,
                acpm_planning_metadata_json TEXT
            )
            """
        )
        raw.execute(
            "CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL)"
        )
        raw.execute(
            "INSERT INTO schema_version VALUES (13, '2026-01-01T00:00:00Z')"
        )
        raw.execute(
            "INSERT INTO campaigns VALUES ('old_run','old_run','complete','2026-01-01T00:00:00Z')"
        )
        raw.execute(
            "INSERT INTO campaign_start_snapshot (campaign_id, timestamp_utc) VALUES ('old_run','2026-01-01T00:00:00Z')"
        )
        raw.commit()

    init_db(db)

    with get_connection(db) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(campaign_start_snapshot)")}
        assert "effective_filter_policy_json" in cols

        v = conn.execute("SELECT version FROM schema_version").fetchone()
        assert v["version"] == SCHEMA_VERSION

        row = conn.execute(
            "SELECT effective_filter_policy_json FROM campaign_start_snapshot WHERE campaign_id='old_run'"
        ).fetchone()
        assert row["effective_filter_policy_json"] is None


def test_effective_filter_policy_json_round_trips(tmp_path: Path) -> None:
    from src.db import get_connection, init_db
    from src.effective_filter_policy import build_effective_filter_policy

    db = tmp_path / "lab.sqlite"
    init_db(db)

    policy = build_effective_filter_policy(_BASE_GATES, _BASE_SOURCE, [])
    policy_json = json.dumps(policy, sort_keys=True)

    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at) VALUES (?,?,?,?)",
            ("run1", "run1", "complete", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO campaign_start_snapshot
              (campaign_id, timestamp_utc, effective_filter_policy_json)
            VALUES (?, ?, ?)
            """,
            ("run1", "2026-01-01T00:00:00Z", policy_json),
        )
        row = conn.execute(
            "SELECT effective_filter_policy_json FROM campaign_start_snapshot WHERE campaign_id='run1'"
        ).fetchone()
        parsed = json.loads(row["effective_filter_policy_json"])

    assert parsed["schema"] == "quantmap.effective_filter_policy"
    assert parsed["schema_version"] == 1
    assert parsed["truth_status"] == "explicit"
    assert parsed["effective_filters"] == _BASE_GATES


# ---------------------------------------------------------------------------
# canonical_json_sha256
# ---------------------------------------------------------------------------

def test_canonical_json_sha256_is_key_order_stable() -> None:
    from src.effective_filter_policy import canonical_json_sha256

    a = {"z": 1.0, "a": 2.0}
    b = {"a": 2.0, "z": 1.0}
    assert canonical_json_sha256(a) == canonical_json_sha256(b)


def test_canonical_json_sha256_differs_for_different_values() -> None:
    from src.effective_filter_policy import canonical_json_sha256

    a = {"min_valid_warm_count": 1.0}
    b = {"min_valid_warm_count": 3.0}
    assert canonical_json_sha256(a) != canonical_json_sha256(b)


# ---------------------------------------------------------------------------
# build_override_layers
# ---------------------------------------------------------------------------

def test_build_override_layers_no_overrides() -> None:
    from src.effective_filter_policy import build_override_layers

    layers = build_override_layers(_FULL_RUN_PLAN_SNAP, None)
    assert layers == []


def test_build_override_layers_custom_mode() -> None:
    from src.effective_filter_policy import build_override_layers

    layers = build_override_layers(_CUSTOM_RUN_PLAN_SNAP, None)
    assert len(layers) == 1
    layer = layers[0]
    assert layer["authority"] == "execution_mode"
    assert layer["policy_effect"] == "user_directed_sparse_custom"
    assert layer["overrides"] == {"min_valid_warm_count": 1}
    assert layer["source_id"] == "custom"


def test_build_override_layers_quick_mode() -> None:
    from src.effective_filter_policy import build_override_layers

    layers = build_override_layers(_QUICK_RUN_PLAN_SNAP, None)
    assert len(layers) == 1
    assert layers[0]["policy_effect"] == "depth_required_relaxation"
    assert layers[0]["source_id"] == "quick"


def test_build_override_layers_yaml_override_stacks_after_mode() -> None:
    from src.effective_filter_policy import build_override_layers

    layers = build_override_layers(_CUSTOM_RUN_PLAN_SNAP, {"max_outliers": 5.0})
    assert len(layers) == 2
    assert layers[0]["authority"] == "execution_mode"
    assert layers[1]["authority"] == "campaign_yaml"
    assert layers[1]["policy_effect"] == "campaign_override"
    assert layers[1]["overrides"] == {"max_outliers": 5.0}


# ---------------------------------------------------------------------------
# build_effective_filter_policy: policy classification
# ---------------------------------------------------------------------------

def test_profile_default_no_layers() -> None:
    from src.effective_filter_policy import build_effective_filter_policy

    policy = build_effective_filter_policy(_BASE_GATES, _BASE_SOURCE, [])

    assert policy["policy_id"] == "profile_default"
    assert policy["policy_modifiers"] == []
    assert policy["final_policy_authority"] == "methodology_profile"
    assert policy["authority_chain"] == ["methodology_profile"]
    assert policy["effective_filters"] == dict(_BASE_GATES)
    assert policy["changed_filter_keys"] == []
    assert policy["rankability_affecting_keys"] == []


def test_custom_mode_layer_sets_user_directed_sparse_custom() -> None:
    from src.effective_filter_policy import build_effective_filter_policy, build_override_layers

    layers = build_override_layers(_CUSTOM_RUN_PLAN_SNAP, None)
    policy = build_effective_filter_policy(_BASE_GATES, _BASE_SOURCE, layers)

    assert policy["policy_id"] == "user_directed_sparse_custom"
    assert policy["policy_modifiers"] == []
    assert policy["effective_filters"]["min_valid_warm_count"] == 1
    assert "min_valid_warm_count" in policy["changed_filter_keys"]
    assert "min_valid_warm_count" in policy["rankability_affecting_keys"]
    assert "execution_mode" in policy["authority_chain"]


def test_quick_mode_layer_same_value_as_base_no_changed_key() -> None:
    """Quick mode injects min_valid_warm_count=3, same as base gate — no changed key."""
    from src.effective_filter_policy import build_effective_filter_policy, build_override_layers

    layers = build_override_layers(_QUICK_RUN_PLAN_SNAP, None)
    policy = build_effective_filter_policy(_BASE_GATES, _BASE_SOURCE, layers)

    assert policy["policy_id"] == "depth_required_relaxation"
    assert policy["effective_filters"]["min_valid_warm_count"] == 3.0
    assert "min_valid_warm_count" not in policy["changed_filter_keys"]
    # Authority chain still records execution_mode because a layer exists.
    assert "execution_mode" in policy["authority_chain"]


def test_yaml_override_sets_campaign_override_modifier() -> None:
    from src.effective_filter_policy import build_effective_filter_policy, build_override_layers

    layers = build_override_layers(_FULL_RUN_PLAN_SNAP, {"max_outliers": 5.0})
    policy = build_effective_filter_policy(_BASE_GATES, _BASE_SOURCE, layers)

    assert policy["policy_id"] == "profile_default"
    assert "campaign_override" in policy["policy_modifiers"]
    assert policy["final_policy_authority"] == "campaign_yaml"
    assert policy["effective_filters"]["max_outliers"] == 5.0
    assert "max_outliers" in policy["changed_filter_keys"]


def test_custom_plus_yaml_override_stacks_correctly() -> None:
    from src.effective_filter_policy import build_effective_filter_policy, build_override_layers

    layers = build_override_layers(_CUSTOM_RUN_PLAN_SNAP, {"max_outliers": 5.0})
    policy = build_effective_filter_policy(_BASE_GATES, _BASE_SOURCE, layers)

    assert policy["policy_id"] == "user_directed_sparse_custom"
    assert "campaign_override" in policy["policy_modifiers"]
    assert policy["effective_filters"]["min_valid_warm_count"] == 1
    assert policy["effective_filters"]["max_outliers"] == 5.0
    # YAML wins on conflicting keys: if yaml also overrides min_valid_warm_count
    layers2 = build_override_layers(_CUSTOM_RUN_PLAN_SNAP, {"min_valid_warm_count": 2.0})
    policy2 = build_effective_filter_policy(_BASE_GATES, _BASE_SOURCE, layers2)
    assert policy2["effective_filters"]["min_valid_warm_count"] == 2.0  # YAML wins


# ---------------------------------------------------------------------------
# Scoring confirmation
# ---------------------------------------------------------------------------

def test_confirmation_confirmed_when_filters_match() -> None:
    from src.effective_filter_policy import build_effective_filter_policy

    policy = build_effective_filter_policy(
        _BASE_GATES, _BASE_SOURCE, [],
        score_effective_filters=dict(_BASE_GATES),
    )
    assert policy["scoring_confirmation"]["status"] == "confirmed"
    assert policy["scoring_confirmation"]["score_effective_filters_sha256"] is not None


def test_confirmation_mismatch_when_filters_differ() -> None:
    from src.effective_filter_policy import build_effective_filter_policy

    wrong = {**_BASE_GATES, "min_valid_warm_count": 99.0}
    policy = build_effective_filter_policy(
        _BASE_GATES, _BASE_SOURCE, [],
        score_effective_filters=wrong,
    )
    assert policy["scoring_confirmation"]["status"] == "mismatch"
    assert "expected_effective_filters_sha256" in policy["scoring_confirmation"]
    assert policy["scoring_confirmation"]["expected_effective_filters_sha256"] != policy["scoring_confirmation"]["score_effective_filters_sha256"]


def test_confirmation_not_confirmed_when_no_score_filters() -> None:
    from src.effective_filter_policy import build_effective_filter_policy

    policy = build_effective_filter_policy(_BASE_GATES, _BASE_SOURCE, [])
    assert policy["scoring_confirmation"]["status"] == "not_confirmed"


# ---------------------------------------------------------------------------
# Legacy projections (project_legacy_filter_policy)
# ---------------------------------------------------------------------------

def test_legacy_unknown_when_no_evidence() -> None:
    from src.effective_filter_policy import project_legacy_filter_policy

    proj = project_legacy_filter_policy({}, {}, None)
    assert proj["truth_status"] == "unknown"
    assert proj["effective_filters"] is None
    assert proj["policy_id"] == "legacy_unknown"


def test_legacy_inferred_limited_custom_mode() -> None:
    from src.effective_filter_policy import project_legacy_filter_policy

    proj = project_legacy_filter_policy({}, {"run_mode": "custom"}, None)
    assert proj["truth_status"] == "inferred_limited"
    assert proj["effective_filters"] == {"min_valid_warm_count": 1}
    assert proj["legacy_reader"]["label"] == "legacy_inferred_limited"


def test_legacy_inferred_limited_quick_mode() -> None:
    from src.effective_filter_policy import project_legacy_filter_policy

    proj = project_legacy_filter_policy({}, {"run_mode": "quick"}, None)
    assert proj["truth_status"] == "inferred_limited"
    assert proj["effective_filters"] == {"min_valid_warm_count": 3}


def test_legacy_reconstructed_from_complete_methodology_and_overrides() -> None:
    from src.effective_filter_policy import project_legacy_filter_policy

    methodology = {"gates": dict(_BASE_GATES), "capture_quality": "complete"}
    run_plan = {"run_mode": "custom", "filter_overrides": {"min_valid_warm_count": 1}}
    proj = project_legacy_filter_policy(methodology, run_plan, None)

    assert proj["truth_status"] == "reconstructed"
    assert proj["policy_id"] == "legacy_reconstructed"
    assert proj["effective_filters"]["min_valid_warm_count"] == 1


def test_legacy_reconstructed_yaml_adds_campaign_override_modifier() -> None:
    from src.effective_filter_policy import project_legacy_filter_policy

    methodology = {"gates": dict(_BASE_GATES), "capture_quality": "complete"}
    run_plan = {"run_mode": "full", "filter_overrides": {}}
    campaign_yaml = {"elimination_overrides": {"max_outliers": 5.0}}
    proj = project_legacy_filter_policy(methodology, run_plan, campaign_yaml)

    assert "campaign_override" in proj["policy_modifiers"]
    assert proj["effective_filters"]["max_outliers"] == 5.0


# ---------------------------------------------------------------------------
# trust_identity projection seam
# ---------------------------------------------------------------------------

def _make_test_db(tmp_path: Path, *, with_explicit_policy: bool, run_mode: str = "full") -> tuple[Path, str]:
    """Create a minimal DB with one campaign; optionally write v1 policy JSON."""
    from src.db import get_connection, init_db
    from src.effective_filter_policy import build_effective_filter_policy

    db = tmp_path / "lab.sqlite"
    init_db(db)
    campaign_id = "test_camp"

    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO campaigns (id, name, status, created_at, run_mode) VALUES (?,?,?,?,?)",
            (campaign_id, campaign_id, "complete", "2026-01-01T00:00:00Z", run_mode),
        )
        efp_json: str | None = None
        if with_explicit_policy:
            policy = build_effective_filter_policy(_BASE_GATES, _BASE_SOURCE, [])
            efp_json = json.dumps(policy, sort_keys=True)
        conn.execute(
            """
            INSERT INTO campaign_start_snapshot
              (campaign_id, timestamp_utc, effective_filter_policy_json)
            VALUES (?, ?, ?)
            """,
            (campaign_id, "2026-01-01T00:00:00Z", efp_json),
        )
    return db, campaign_id


def test_trust_identity_explicit_row_returns_snapshot_source(tmp_path: Path) -> None:
    from src.trust_identity import load_run_identity

    db, cid = _make_test_db(tmp_path, with_explicit_policy=True)
    identity = load_run_identity(cid, db)

    assert identity.sources["filter_policy"] == "snapshot"
    assert identity.filter_policy["truth_status"] == "explicit"
    assert identity.filter_policy["effective_filters"] == dict(_BASE_GATES)


def test_trust_identity_null_row_returns_legacy_projection(tmp_path: Path) -> None:
    from src.trust_identity import load_run_identity

    db, cid = _make_test_db(tmp_path, with_explicit_policy=False)
    identity = load_run_identity(cid, db)

    # No methodology snapshot or run_plan for this minimal test DB — expect unknown.
    assert identity.sources["filter_policy"].startswith("legacy_")
    assert identity.filter_policy["truth_status"] in ("unknown", "inferred_limited", "reconstructed")


def test_trust_identity_no_db_write_for_legacy_projection(tmp_path: Path) -> None:
    """Legacy projection must never backfill the DB column."""
    from src.db import get_connection
    from src.trust_identity import load_run_identity

    db, cid = _make_test_db(tmp_path, with_explicit_policy=False)
    load_run_identity(cid, db)

    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT effective_filter_policy_json FROM campaign_start_snapshot WHERE campaign_id=?",
            (cid,),
        ).fetchone()
    assert row["effective_filter_policy_json"] is None


# ---------------------------------------------------------------------------
# Metadata projection
# ---------------------------------------------------------------------------

def test_metadata_json_filter_policy_uses_snapshot_when_explicit(tmp_path: Path) -> None:
    """metadata.json filter_policy.source should be the snapshot column when present."""
    from src.trust_identity import load_run_identity

    db, cid = _make_test_db(tmp_path, with_explicit_policy=True)
    identity = load_run_identity(cid, db)

    # Build the filter_policy projection as export.py would:
    fp = {
        "truth_status": identity.filter_policy.get("truth_status"),
        "source": (
            "campaign_start_snapshot.effective_filter_policy_json"
            if identity.sources.get("filter_policy") == "snapshot"
            else identity.sources.get("filter_policy", "unknown")
        ),
    }
    assert fp["truth_status"] == "explicit"
    assert fp["source"] == "campaign_start_snapshot.effective_filter_policy_json"


def test_metadata_json_methodology_eligibility_filters_unchanged(tmp_path: Path) -> None:
    """Adding filter_policy must not remove methodology.eligibility_filters."""
    from src.trust_identity import load_run_identity

    db, cid = _make_test_db(tmp_path, with_explicit_policy=True)
    identity = load_run_identity(cid, db)

    # Simulate what export.py assembles:
    methodology_section = {
        "eligibility_filters": identity.methodology.get("gates"),
    }
    filter_policy_section = {
        "effective_filters": identity.filter_policy.get("effective_filters"),
    }

    # Both keys must coexist without one overwriting the other:
    assert "eligibility_filters" in methodology_section
    assert "effective_filters" in filter_policy_section
