"""
QuantMap — db.py

SQLite schema definition and initialization for lab.sqlite.
All tables are created here. This module is the single source of truth
for the database schema. runner.py, analyze.py, and report.py import
from here for table/column names.

Schema overview (MDD §11.2 + extensions):
    campaigns              — one row per campaign run
    campaign_start_snapshot — one row per campaign (system fingerprint)
    configs                — one row per config tested
    cycles                 — one row per cycle (5 per config)
    requests               — one row per request (30 per config minimum)
    telemetry              — one row per 2s sample (throughout campaign)
    background_snapshots   — one row per 10s background snapshot
    scores                 — one row per config after scoring
    artifacts              — references to generated files (reports, CSVs)
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL — Table definitions
# ---------------------------------------------------------------------------

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS campaigns (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    variable            TEXT,
    campaign_type       TEXT,  -- primary_sweep | extended_sweep | interaction | validation
    status              TEXT NOT NULL DEFAULT 'pending',
    -- pending | running | complete | failed | aborted
    created_at          TEXT NOT NULL,
    started_at          TEXT,
    completed_at        TEXT,
    failed_at           TEXT,
    failure_reason      TEXT,
    baseline_sha256     TEXT,
    campaign_sha256     TEXT,
    machine_profile_json TEXT,
    rationale           TEXT,
    notes_json          TEXT
);

CREATE TABLE IF NOT EXISTS campaign_start_snapshot (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id              TEXT NOT NULL REFERENCES campaigns(id),
    timestamp_utc            TEXT NOT NULL,
    server_binary_path       TEXT,
    server_binary_sha256     TEXT,
    model_path               TEXT,
    model_file_size_bytes    INTEGER,
    model_mtime_utc          TEXT,
    build_commit             TEXT,
    prompt_sha256_json       TEXT,   -- {"speed_short": "abc123", ...}
    sampling_params_json     TEXT,
    campaign_yaml_sha256     TEXT,
    campaign_yaml_content    TEXT,   -- full YAML text, verbatim at campaign start
    baseline_yaml_sha256     TEXT,
    os_version               TEXT,
    os_platform              TEXT,
    python_version           TEXT,
    nvidia_driver            TEXT,
    gpu_name                 TEXT,
    power_plan               TEXT,
    cpu_affinity_policy      TEXT,
    hwm_namespace            TEXT,   -- HWiNFO64
    model_disk_total_gb      REAL,
    model_disk_free_gb       REAL,
    cpu_temp_at_start_c      REAL,
    gpu_temp_at_start_c      REAL
);

CREATE TABLE IF NOT EXISTS configs (
    id                   TEXT NOT NULL,
    campaign_id          TEXT NOT NULL REFERENCES campaigns(id),
    variable_name        TEXT NOT NULL,
    variable_value       TEXT NOT NULL,    -- JSON-serialized value
    config_values_json   TEXT NOT NULL,    -- Full merged config dict (JSON)
    resolved_command     TEXT,             -- Full server launch command string (port 8000)
    runtime_env_json     TEXT,             -- JSON: env-var delta injected into subprocess
    cpu_affinity_mask    TEXT,             -- null = OS default; "0-15" = P-cores
    status               TEXT NOT NULL DEFAULT 'pending',
    -- pending | running | complete | eliminated | oom | skipped_oom
    -- oom: startup confirmed CUDA OOM; no inference ran; failure_detail has log snippet
    -- skipped_oom: not attempted; prior consecutive OOMs confirmed VRAM ceiling
    elimination_reason   TEXT,
    started_at           TEXT,
    completed_at         TEXT,
    PRIMARY KEY (id, campaign_id)
);

CREATE TABLE IF NOT EXISTS cycles (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id            TEXT NOT NULL,
    campaign_id          TEXT NOT NULL,
    cycle_number         INTEGER NOT NULL,   -- 1-indexed
    status               TEXT NOT NULL DEFAULT 'pending',
    -- pending | started | complete | invalid
    invalid_reason       TEXT,
    no_warmup            INTEGER NOT NULL DEFAULT 0,  -- bool
    attempt_count        INTEGER NOT NULL DEFAULT 1,
    startup_duration_s   REAL,
    server_pid           INTEGER,
    server_log_path      TEXT,
    started_at           TEXT,
    completed_at         TEXT,
    UNIQUE (config_id, campaign_id, cycle_number)
);

CREATE TABLE IF NOT EXISTS requests (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id              INTEGER NOT NULL REFERENCES cycles(id),
    campaign_id           TEXT NOT NULL,
    config_id             TEXT NOT NULL,
    cycle_number          INTEGER NOT NULL,
    request_index         INTEGER NOT NULL,  -- 1=cold, 2-6=warm
    is_cold               INTEGER NOT NULL,  -- bool
    request_type          TEXT NOT NULL,
    -- speed_short | speed_medium | quality_code | quality_reasoning
    outcome               TEXT NOT NULL,
    -- success|timeout|http_error|malformed_stream|truncated|server_restart|oom
    http_status           INTEGER,
    ttft_ms               REAL,
    total_wall_ms         REAL,
    prompt_n              INTEGER,
    prompt_ms             REAL,
    prompt_per_second     REAL,
    predicted_n           INTEGER,
    predicted_ms          REAL,
    predicted_per_second  REAL,
    cache_n               INTEGER,
    total_tokens          INTEGER,
    server_pid            INTEGER,
    resolved_command      TEXT,     -- copy from config for convenience
    timestamp_start       TEXT,
    cycle_status          TEXT NOT NULL DEFAULT 'complete',
    -- complete | invalid (set on cycle invalidation)
    error_detail          TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS telemetry (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id              TEXT NOT NULL,
    config_id                TEXT NOT NULL,
    timestamp                TEXT NOT NULL,
    -- ABORT tier
    cpu_temp_c               REAL,
    power_limit_throttling   INTEGER,   -- bool
    gpu_vram_used_mb         REAL,
    -- WARN tier
    gpu_temp_c               REAL,
    cpu_power_w              REAL,
    ram_used_gb              REAL,
    -- SILENT tier (hardware)
    cpu_pcore_freq_ghz       REAL,
    cpu_ecore_freq_ghz       REAL,
    gpu_util_pct             REAL,
    gpu_power_w              REAL,
    gpu_graphics_clock_mhz  REAL,
    gpu_mem_clock_mhz        REAL,
    gpu_pstate               TEXT,
    gpu_throttle_reasons     TEXT,
    liquid_temp_c            REAL,
    disk_read_mbps           REAL,
    disk_write_mbps          REAL,
    page_faults_sec          REAL,
    -- SILENT tier (extended)
    net_sent_mbps            REAL,
    net_recv_mbps            REAL,
    cpu_freq_mhz             REAL,
    cpu_util_pct             REAL,
    cpu_util_per_core_json   TEXT,
    ram_available_gb         REAL,
    ram_committed_gb         REAL,
    pagefile_used_gb         REAL,
    context_switches_sec     REAL,
    interrupts_sec           REAL,
    server_cpu_pct           REAL,
    server_rss_mb            REAL,      -- Working Set: physical RAM currently in use
    server_private_bytes_mb  REAL,      -- Private Bytes: committed incl. paged-out (Windows only)
    server_vms_mb            REAL,
    server_thread_count      INTEGER,
    server_handle_count      INTEGER,
    server_pid               INTEGER,
    -- HWiNFO extended hardware (SILENT)
    cpu_core_voltage_v       REAL,
    cpu_ia_cores_power_w     REAL,
    gpu_hotspot_temp_c       REAL,
    gpu_mem_temp_c           REAL,
    gpu_fan_rpm              REAL,
    cpu_fan_rpm              REAL
);

CREATE TABLE IF NOT EXISTS background_snapshots (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id                   TEXT NOT NULL,
    config_id                     TEXT NOT NULL,
    timestamp                     TEXT NOT NULL,
    top_cpu_procs_json            TEXT NOT NULL DEFAULT '[]',
    top_ram_procs_json            TEXT NOT NULL DEFAULT '[]',
    top_disk_procs_json           TEXT NOT NULL DEFAULT '[]',
    all_notable_procs_json        TEXT NOT NULL DEFAULT '[]',
    defender_process_running      INTEGER NOT NULL DEFAULT 0,
    windows_update_active         INTEGER NOT NULL DEFAULT 0,
    search_indexer_active         INTEGER NOT NULL DEFAULT 0,
    antivirus_scan_active         INTEGER NOT NULL DEFAULT 0,
    network_active_connections    INTEGER NOT NULL DEFAULT 0,
    network_established_connections INTEGER NOT NULL DEFAULT 0,
    power_plan                    TEXT DEFAULT '',
    high_cpu_process_count        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scores (
    id                           INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id                  TEXT NOT NULL,
    config_id                    TEXT NOT NULL,
    -- Raw statistics
    warm_tg_median               REAL,
    warm_tg_p10                  REAL,
    warm_tg_p90                  REAL,
    warm_tg_cv                   REAL,
    warm_tg_mean                 REAL,
    warm_tg_std                  REAL,
    warm_ttft_median_ms          REAL,
    warm_ttft_p90_ms             REAL,
    warm_ttft_p10_ms             REAL,
    cold_ttft_median_ms          REAL,
    cold_ttft_p90_ms             REAL,
    pp_median                    REAL,
    pp_p10                       REAL,
    pp_p90                       REAL,
    -- Thermal and reliability
    thermal_events               INTEGER,
    outlier_count                INTEGER,
    success_rate                 REAL,
    valid_warm_request_count     INTEGER,
    valid_cold_request_count     INTEGER,
    -- speed_medium degradation
    speed_medium_warm_tg_median  REAL,
    speed_medium_degradation_pct REAL,  -- positive = degradation
    speed_medium_flagged         INTEGER,  -- bool: >5% degradation
    -- Scoring
    composite_score              REAL,
    rank_overall                 INTEGER,
    -- Elimination
    passed_filters               INTEGER,  -- bool
    elimination_reason           TEXT,
    -- Report views
    pareto_dominated             INTEGER,  -- bool
    is_highest_tg                INTEGER,  -- bool
    is_score_winner              INTEGER,  -- bool
    -- Baseline comparison
    warm_tg_vs_baseline_pct      REAL,    -- % improvement vs S0-new
    warm_ttft_vs_baseline_pct    REAL,
    UNIQUE (campaign_id, config_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id   TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    -- report_md | scores_csv | raw_jsonl | telemetry_jsonl | config_yaml
    path          TEXT NOT NULL,
    sha256        TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
    -- Single-row table.  version = integer incremented with every migration.
    -- applied_at = UTC ISO8601 timestamp of the last migration run.
    -- Absence of this table means version 0 (pre-versioning, legacy DB).
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_requests_config ON requests(campaign_id, config_id);
CREATE INDEX IF NOT EXISTS idx_requests_outcome ON requests(outcome);
CREATE INDEX IF NOT EXISTS idx_telemetry_config ON telemetry(campaign_id, config_id);
CREATE INDEX IF NOT EXISTS idx_cycles_config ON cycles(config_id, campaign_id);
CREATE INDEX IF NOT EXISTS idx_scores_campaign ON scores(campaign_id);
"""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------

# Increment this whenever a new migration is added to _MIGRATIONS below.
# This is the version the current codebase expects.
SCHEMA_VERSION: int = 5


class SchemaVersionError(RuntimeError):
    """
    Raised when the database schema version is newer than the code expects.
    This means an older version of QuantMap is being run against a database
    that was created or migrated by a newer version.  Safe to catch and report,
    but the caller must not proceed — the DB may contain columns or data the
    old code does not understand.
    """


# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------
# Each entry: (target_version: int, description: str, sql_statements: list[str])
#
# Rules:
#   - Append only.  Never remove, reorder, or renumber entries.
#   - Each entry raises the schema version by exactly 1.
#   - SQL statements may be any valid SQLite DDL or DML.
#   - Migrations must be idempotent where possible (use IF NOT EXISTS / IF EXISTS).
#   - If a migration requires a data backfill, do it in the SQL statements.
#
_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "CRIT-1: replace duplicate process_rss_mb with server_private_bytes_mb. "
        "process_rss_mb was identical to server_rss_mb (both = mem.rss). "
        "server_private_bytes_mb = mem.pagefile (Windows Private Bytes — committed "
        "memory including paged-out pages, distinct from Working Set / RSS).",
        [
            "ALTER TABLE telemetry ADD COLUMN server_private_bytes_mb REAL",
        ],
    ),
    (
        2,
        "config.py + runtime_env_json: add runtime_env_json column to configs table. "
        "Stores the env-var delta (CUDA_PATH, CMAKE_PREFIX_PATH, PATH_prepend) that "
        "was injected into the llama-server subprocess — the missing half of the "
        "reproduction story alongside resolved_command.",
        [
            "ALTER TABLE configs ADD COLUMN runtime_env_json TEXT",
        ],
    ),
    (
        3,
        "QoL/L1-U6: add campaign_yaml_content to campaign_start_snapshot. "
        "The sha256 hash already proved the YAML was unchanged; this stores the "
        "verbatim YAML text so results are fully self-contained and reproducible "
        "without requiring access to the original configs/ tree. "
        "Critical for audit: if configs/campaigns/ is modified between runs, "
        "the DB row shows exactly what YAML was in effect when data was collected.",
        [
            "ALTER TABLE campaign_start_snapshot ADD COLUMN campaign_yaml_content TEXT",
        ],
    ),
    (
        4,
        "NGL sweep: add configs.failure_detail for OOM log snippets and "
        "campaign_start_snapshot.gpu_vram_total_mb for VRAM headroom reporting. "
        "failure_detail stores ≤500-char CUDA OOM log excerpt when status='oom'. "
        "gpu_vram_total_mb stores physical GPU VRAM capacity from pynvml at campaign start.",
        [
            "ALTER TABLE configs ADD COLUMN failure_detail TEXT",
            "ALTER TABLE campaign_start_snapshot ADD COLUMN gpu_vram_total_mb REAL",
        ],
    ),
    (
        5,
        "Rename windows_defender_active to defender_process_running in "
        "background_snapshots.  The old name implied Defender was actively scanning; "
        "the field only reflects process existence (MsMpEng.exe running).  The "
        "meaningful metric is antivirus_scan_active (cpu > 0.5%%).",
        [
            "ALTER TABLE background_snapshots RENAME COLUMN "
            "windows_defender_active TO defender_process_running",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def init_db(db_path: Path) -> None:
    """
    Create the database and all tables if they don't exist.
    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS throughout.
    Applies all pending schema migrations and enforces version compatibility.
    Call once at campaign start before any reads or writes.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_DDL)
        _migrate_schema(conn)
        conn.commit()
    logger.info("Database initialized at schema v%d: %s", SCHEMA_VERSION, db_path)


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """
    Read the current schema version from the database.

    Returns 0 if the schema_version table is absent (pre-versioning legacy DB)
    or empty (newly created DB where the DDL ran but no version was stamped yet).
    """
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "schema_version" not in tables:
        return 0  # legacy DB created before versioning was introduced
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    return int(row[0]) if row else 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Write (or overwrite) the single schema_version row."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)", (version, now))


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """
    Apply all pending migrations in version order.

    Forward migration (older DB → newer code):
        Runs every migration whose target_version > current DB version, in order.
        Updates schema_version to SCHEMA_VERSION when done.

    Downgrade detection (newer DB → older code):
        Raises SchemaVersionError immediately.  The caller must not proceed —
        writing to a newer-schema DB with old code risks data corruption or
        silent column omissions.

    New DB:
        Version starts at 0 (no schema_version row).  All migrations run,
        bringing the DB to SCHEMA_VERSION.

    Up-to-date DB:
        DB version == SCHEMA_VERSION.  No migrations run, no writes made.
    """
    db_version = _get_schema_version(conn)

    if db_version > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"Database schema version {db_version} is newer than this "
            f"version of QuantMap (expects v{SCHEMA_VERSION}). "
            f"Upgrade QuantMap or use the database created by the matching version."
        )

    if db_version == SCHEMA_VERSION:
        return  # already current — nothing to do

    pending = [m for m in _MIGRATIONS if m[0] > db_version]
    for target_version, description, statements in pending:
        logger.info(
            "Applying schema migration v%d: %s", target_version, description
        )
        for sql in statements:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as exc:
                # "duplicate column name" fires when the DDL already created the
                # column (new DB path) and the migration tries to ADD it again.
                # Any other OperationalError is a real problem — re-raise it.
                if "duplicate column name" in str(exc).lower():
                    logger.debug(
                        "Migration v%d SQL skipped — column already exists: %s",
                        target_version, sql,
                    )
                else:
                    raise
        logger.info("Schema migration v%d applied.", target_version)

    _set_schema_version(conn, SCHEMA_VERSION)
    logger.info(
        "Schema migrated from v%d to v%d.", db_version, SCHEMA_VERSION
    )


def get_connection(db_path: Path) -> sqlite3.Connection:
    """
    Return a new SQLite connection with recommended settings for the lab.
    Caller is responsible for closing the connection.
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def write_request(conn: sqlite3.Connection, cycle_id: int, result_dict: dict) -> None:
    """Insert a request record. result_dict must contain all requests table columns."""
    cols = [
        "cycle_id", "campaign_id", "config_id", "cycle_number", "request_index",
        "is_cold", "request_type", "outcome", "http_status", "ttft_ms",
        "total_wall_ms", "prompt_n", "prompt_ms", "prompt_per_second",
        "predicted_n", "predicted_ms", "predicted_per_second", "cache_n",
        "total_tokens", "server_pid", "resolved_command", "timestamp_start",
        "cycle_status", "error_detail",
    ]
    values = [cycle_id if k == "cycle_id" else result_dict.get(k) for k in cols]
    placeholders = ", ".join("?" for _ in cols)
    col_str = ", ".join(cols)
    conn.execute(f"INSERT INTO requests ({col_str}) VALUES ({placeholders})", values)


def write_raw_jsonl(jsonl_path: Path, record: dict) -> None:
    """Append a request record to raw.jsonl (immutable, append-only)."""
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
