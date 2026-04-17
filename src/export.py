"""
QuantMap — export.py

Portable forensic case file generator (.qmap).
Bundles campaign data, methodology, and telemetry into a single SQLite file.
"""

from __future__ import annotations

import sqlite3
import json
from datetime import datetime
from pathlib import Path

from src import ui

def run_export(
    campaign_id: str,
    source_db: Path,
    output_path: Path,
    lite: bool = False,
    strip_env: bool = False,
    redaction_root: Path | None = None,
) -> bool:
    """Export a campaign to a standalone .qmap SQLite file."""
    console = ui.get_console()
    ui.print_banner(f"QuantMap Export: {campaign_id}")
    
    # Ensure source exists
    if not source_db.exists():
        console.print(f"[red]Error: Source database not found at {source_db}[/red]")
        return False

    if strip_env and (redaction_root is None or redaction_root == Path(".")):
        console.print(
            "[red]Error: --strip-env requires a valid redaction root, but "
            "QUANTMAP_LAB_ROOT is missing, empty, or invalid.[/red]"
        )
        console.print(
            "[dim]Set QUANTMAP_LAB_ROOT or export without --strip-env. "
            "QuantMap will not create a bundle that appears redacted when "
            "redaction is incomplete.[/dim]"
        )
        return False

    # 1. Setup target directory and file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.unlink()
        except Exception as e:
            console.print(f"[red]Error: Could not overwrite existing file: {e}[/red]")
            return False

    try:
        dest_conn = sqlite3.connect(output_path)
        src_conn = sqlite3.connect(source_db)
        src_conn.row_factory = sqlite3.Row
    except Exception as e:
        console.print(f"[red]Error: Database connection failed: {e}[/red]")
        return False

    try:
        # 2. Migrate Data with Schema Introspection
        tables = [
            "campaigns",
            "campaign_start_snapshot",
            "methodology_snapshots",
            "configs",
            "scores",
            "cycles",
            "requests",
            "artifacts",
            "schema_version",
        ]
        if not lite:
            tables.append("telemetry")
            tables.append("background_snapshots")
        
        # We also need a metadata table
        dest_conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, val TEXT)")

        for table in tables:
            console.print(f"  [dim]Migrating {table}...[/dim]")
            _migrate_with_introspection(src_conn, dest_conn, table, campaign_id)

        # 3. Optional Stripping
        redaction_status = "not_requested"
        if strip_env:
            console.print(f"  [dim]Redacting environment metadata...[/dim]")
            redaction_status = _redact_env(dest_conn, redaction_root)

        # 4. Write Manifest
        _write_manifest(
            dest_conn,
            campaign_id,
            source_db,
            lite=lite,
            stripped=strip_env,
            redaction_status=redaction_status,
            redaction_root=redaction_root,
        )
        
        dest_conn.close()
        src_conn.close()
        
        # 5. Final Summary
        size_mb = output_path.stat().st_size / (1024 * 1024)
        console.print(f"\n[bold green]{ui.SYM_OK} EXPORT COMPLETE[/bold green]")
        console.print(f"  [bold]Bundle Path:[/bold]     {output_path}")
        console.print(f"  [bold]Bundle Size:[/bold]     {size_mb:.2f} MB")
        console.print(f"  [bold]Fidelity:[/bold]        {'Lite (Stats-only)' if lite else 'Full Forensic'}")
        privacy_label = (
            f"Stripped/Redacted ({redaction_status})"
            if strip_env
            else "Original (Internal)"
        )
        console.print(f"  [bold]Privacy:[/bold]         {privacy_label}")
        
        console.print("\n[yellow]Note: The .qmap format is an isolated offline database dump. Physical "
                      "artifact files (JSONL, MD) remain on the original disk.[/yellow]")
                      
        return True

    except Exception as e:
        if dest_conn: dest_conn.close()
        console.print(f"[bold red]Export Failed:[/bold red] {e}")
        return False

def _migrate_with_introspection(src: sqlite3.Connection, dest: sqlite3.Connection, table: str, campaign_id: str):
    """Introspect schema and migrate rows for a specific campaign."""
    # 1. Get CREATE TABLE statement from source
    cursor = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
    sql_row = cursor.fetchone()
    if not sql_row:
        # Table not found (might be telemetry in an older DB)
        return
    
    # 2. Create table in destination
    dest.execute(sql_row["sql"])
    
    # 3. Fetch and insert data
    column_rows = src.execute(f"PRAGMA table_info({table})").fetchall()
    column_names = {r[1] for r in column_rows}
    if table == "campaigns":
        query = f"SELECT * FROM {table} WHERE id = ?"
        rows = src.execute(query, (campaign_id,)).fetchall()
    elif "campaign_id" in column_names:
        query = f"SELECT * FROM {table} WHERE campaign_id = ?"
        rows = src.execute(query, (campaign_id,)).fetchall()
    else:
        rows = src.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return
        
    columns = rows[0].keys()
    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    
    dest.executemany(insert_sql, [tuple(r) for r in rows])
    dest.commit()

def _write_manifest(
    conn: sqlite3.Connection,
    campaign_id: str,
    source_db: Path,
    lite: bool,
    stripped: bool,
    redaction_status: str,
    redaction_root: Path | None,
):
    """Write the case-file manifest to the metadata table."""
    from src.version import __version__, __methodology_version__
    from src.code_identity import capture_quantmap_identity
    from src.trust_identity import (
        load_artifact_summaries,
        load_run_identity,
        methodology_source_label,
    )

    run_identity = load_run_identity(campaign_id, source_db)
    exporter_identity = capture_quantmap_identity()
    methodology_label = methodology_source_label(run_identity.methodology)
    artifacts = load_artifact_summaries(campaign_id, source_db)
    artifact_statuses = {
        row.get("artifact_type"): {
            "status": row.get("status"),
            "verification_source": row.get("verification_source"),
            "has_sha256": bool(row.get("sha256")),
        }
        for row in artifacts
    }
    completeness = {
        "baseline": run_identity.sources.get("baseline"),
        "campaign": run_identity.sources.get("campaign"),
        "quantmap": run_identity.sources.get("quantmap"),
        "methodology": methodology_label,
        "telemetry_provider": run_identity.sources.get("telemetry_provider"),
        "telemetry_capture_quality": run_identity.telemetry_provider.get("capture_quality"),
        "execution_environment": run_identity.execution_environment.get("support_tier"),
        "measurement_grade": run_identity.execution_environment.get("measurement_grade"),
        "artifact_statuses": artifact_statuses,
        "is_snapshot_complete": (
            run_identity.sources.get("baseline") == "snapshot"
            and run_identity.sources.get("campaign") == "snapshot"
            and run_identity.sources.get("quantmap") == "snapshot"
            and methodology_label == "snapshot_complete"
        ),
    }
    
    manifest = {
        "bundle_kind": "campaign",
        "campaign_id": campaign_id,
        "run_quantmap_identity": json.dumps(run_identity.quantmap, default=str),
        "run_identity_sources": json.dumps(run_identity.sources, default=str),
        "run_methodology_identity": json.dumps(run_identity.methodology, default=str),
        "run_telemetry_provider_evidence": json.dumps(run_identity.telemetry_provider, default=str),
        "run_execution_environment": json.dumps(run_identity.execution_environment, default=str),
        "provenance_completeness": json.dumps(completeness, default=str),
        "exporter_quantmap_identity": json.dumps(exporter_identity, default=str),
        "exporter_software_version": __version__,
        "exporter_methodology_version": __methodology_version__,
        "is_full_forensic": not lite,
        "is_environment_stripped": stripped,
        "redaction_status": redaction_status,
        "export_timestamp": datetime.now().isoformat()
    }

    def _manifest_value(val: object) -> str:
        text = str(val)
        if stripped and redaction_root is not None:
            lab_path = str(redaction_root)
            for variant in {lab_path, lab_path.replace("\\", "/"), json.dumps(lab_path)[1:-1]}:
                text = text.replace(variant, "<REDACTED>")
        return text
    
    for k, v in manifest.items():
        conn.execute("INSERT INTO metadata (key, val) VALUES (?, ?)", (k, _manifest_value(v)))
    conn.commit()

def _redact_env(conn: sqlite3.Connection, redaction_root: Path | None) -> str:
    """Search and replace sensitive lab-root strings in all text columns."""
    if redaction_root is None:
        raise ValueError("redaction root unavailable")

    lab_path = str(redaction_root)
    lab_path_variants = {
        lab_path,
        lab_path.replace("\\", "/"),
        json.dumps(lab_path)[1:-1],
    }
    replacements = 0

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for (table_name,) in tables:
        columns = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        text_columns = [
            row[1]
            for row in columns
            if "TEXT" in str(row[2] or "").upper()
        ]
        for column_name in text_columns:
            for path_variant in lab_path_variants:
                cur = conn.execute(
                    f'''
                    UPDATE "{table_name}"
                    SET "{column_name}" = REPLACE("{column_name}", ?, '<REDACTED>')
                    WHERE "{column_name}" LIKE ?
                    ''',
                    (path_variant, f"%{path_variant}%"),
                )
                replacements += cur.rowcount if cur.rowcount is not None else 0
    conn.commit()
    return f"schema_aware_applied:{replacements}"


# =============================================================================
# metadata.json generator
# =============================================================================

def generate_metadata_json(
    campaign_id: str,
    db_path: Path,
    scores_result: dict | None = None,
    stats: dict | None = None,
    lab_root: Path | None = None,
    run_plan: object | None = None,
    section_failures: list[tuple[str, str]] | None = None,
) -> Path:
    """Generate metadata.json — the structured provenance and scoring record.

    This is the fourth formal campaign artifact.  It is the machine-readable
    complement to the two human-readable reports.  It must be the authoritative
    source for:

      - Campaign identity and configuration registry
      - Methodology and scoring profile provenance
      - Ranking and scoring outputs (replaces scores.csv)
      - Environment and telemetry summary
      - Artifact inventory with status and checksums
      - Warnings and limitations surfaced during this run

    Returns the path to the written metadata.json file.

    Never raises — exceptions are caught and a partial/failed artifact is
    registered in the DB rather than crashing the caller.
    """
    import hashlib
    import logging
    from datetime import timezone

    from src.db import get_connection
    from src.artifact_paths import (
        report_paths,
        infer_model_identity,
        find_artifact_dir,
        ARTIFACT_METADATA,
        ARTIFACT_CAMPAIGN_SUMMARY,
        ARTIFACT_RUN_REPORTS,
        ARTIFACT_RAW_TELEMETRY,
        ARTIFACT_ROLES,
    )
    from src.trust_identity import (
        load_run_identity,
        load_artifact_summaries,
        methodology_source_label,
    )

    logger = logging.getLogger(__name__)

    from src.config import LAB_ROOT  # noqa: PLC0415
    effective_lab_root = lab_root if lab_root is not None else LAB_ROOT
    now_utc = datetime.now(timezone.utc).isoformat()

    # ── Resolve paths ─────────────────────────────────────────────────────────
    with get_connection(db_path) as _conn:
        camp_row = _conn.execute(
            "SELECT * FROM campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        cfg_rows = _conn.execute(
            "SELECT id, variable_value FROM configs WHERE campaign_id=?",
            (campaign_id,),
        ).fetchall()

    camp = dict(camp_row) if camp_row else {}
    snap: dict = {}
    snap_row = None
    try:
        with get_connection(db_path) as _conn:
            snap_row = _conn.execute(
                "SELECT * FROM campaign_start_snapshot WHERE campaign_id=? LIMIT 1",
                (campaign_id,),
            ).fetchone()
        if snap_row:
            import yaml  # noqa: PLC0415
            snap = dict(snap_row)
            baseline_raw = yaml.safe_load(snap.get("baseline_yaml_content") or "") or {}
    except Exception:
        pass

    model_cfg = baseline_raw.get("model", {}) if isinstance(baseline_raw.get("model", {}), dict) else {}
    model_identity = infer_model_identity(
        model_name=model_cfg.get("name"),
        model_path=model_cfg.get("path"),
    )
    report_arts = report_paths(effective_lab_root, model_identity, campaign_id, create=True)
    metadata_path = report_arts[ARTIFACT_METADATA]
    reports_dir = report_arts["dir"]

    meas_dir = find_artifact_dir(effective_lab_root, "measurements", campaign_id)
    env_dir = find_artifact_dir(effective_lab_root, "environment", campaign_id)

    # ── Analysis (re-run if not provided) ─────────────────────────────────────
    if scores_result is None:
        try:
            from src.score import score_campaign  # noqa: PLC0415
            scores_result = score_campaign(campaign_id, db_path, baseline_raw)
        except Exception as exc:
            logger.warning("metadata.json: score_campaign failed: %s", exc)
            scores_result = {}
    if stats is None:
        stats = scores_result.get("stats") or {}

    # ── Identity and provenance ────────────────────────────────────────────────
    trust_identity = load_run_identity(campaign_id, db_path)

    # ── Config registry ────────────────────────────────────────────────────────
    config_registry = []
    for r in cfg_rows:
        try:
            val = json.loads(r["variable_value"])
        except (TypeError, ValueError):
            val = r["variable_value"]
        config_registry.append({"config_id": r["id"], "variable_value": val})

    # ── Scoring and ranking outputs ────────────────────────────────────────────
    scores_df = scores_result.get("scores_df")
    eliminated = scores_result.get("eliminated") or {}
    ranked_configs = []
    eliminated_configs = []
    unrankable_reason: str | None = None

    if scores_df is not None and not scores_df.empty:
        for config_id, row in scores_df.iterrows():
            s = stats.get(config_id, {})
            ranked_configs.append({
                "config_id": config_id,
                "rank": row.get("rank_overall"),
                "composite_score": row.get("composite_score"),
                "is_winner": bool(row.get("is_score_winner", False)),
                "is_highest_tg": bool(row.get("is_highest_tg", False)),
                "pareto_dominated": bool(row.get("pareto_dominated", False)),
                "warm_tg_median": s.get("warm_tg_median"),
                "warm_ttft_median_ms": s.get("warm_ttft_median_ms"),
                "warm_tg_cv": s.get("warm_tg_cv"),
                "valid_warm_request_count": s.get("valid_warm_request_count"),
                "thermal_events": s.get("thermal_events"),
                "lcb_method": row.get("lcb_method"),
            })
    else:
        unrankable_reason = (
            scores_result.get("unrankable_reason")
            or "no ranked configs \u2014 minimum warm-sample threshold not met or all configs eliminated"
        )

    for config_id, reason in eliminated.items():
        eliminated_configs.append({"config_id": config_id, "reason": reason or "not recorded"})

    winner = next(
        (c["config_id"] for c in ranked_configs if c["is_winner"]),
        None,
    )

    # ── Artifact inventory ─────────────────────────────────────────────────────
    artifact_rows = load_artifact_summaries(campaign_id, db_path)
    artifact_inventory = []
    for row in artifact_rows:
        artifact_inventory.append({
            "artifact_type": row.get("artifact_type"),
            "role": ARTIFACT_ROLES.get(row.get("artifact_type", ""), "not classified"),
            "path": row.get("path"),
            "status": row.get("status") or "not recorded",
            "sha256": row.get("sha256"),
            "verification_source": row.get("verification_source") or "not recorded",
            "created_at": row.get("created_at"),
            "error_message": row.get("error_message"),
        })

    # Also record expected artifacts not yet in DB (generated but not registered)
    registered_types = {r["artifact_type"] for r in artifact_inventory}
    from src.artifact_paths import (  # noqa: PLC0415
        FILENAME_CAMPAIGN_SUMMARY,
        FILENAME_RUN_REPORTS,
        FILENAME_METADATA,
        FILENAME_RAW_TELEMETRY,
    )
    for art_type, filename in {
        ARTIFACT_CAMPAIGN_SUMMARY: FILENAME_CAMPAIGN_SUMMARY,
        ARTIFACT_RUN_REPORTS:      FILENAME_RUN_REPORTS,
        ARTIFACT_METADATA:         FILENAME_METADATA,
        ARTIFACT_RAW_TELEMETRY:    FILENAME_RAW_TELEMETRY,
    }.items():
        if art_type not in registered_types:
            candidate = (
                (meas_dir / filename) if art_type == ARTIFACT_RAW_TELEMETRY
                else (reports_dir / filename)
            )
            artifact_inventory.append({
                "artifact_type": art_type,
                "role": ARTIFACT_ROLES.get(art_type, ""),
                "path": str(candidate) if candidate else None,
                "status": "file_present" if (candidate and candidate.exists()) else "not generated",
                "sha256": None,
                "verification_source": "not registered \u2014 file exists but not recorded in DB",
                "created_at": None,
                "error_message": None,
            })

    # ── Warnings and section failures ──────────────────────────────────────────
    warnings_list = []
    for key, err in (section_failures or []):
        warnings_list.append({"source": key, "message": err})

    # ── Environment summary — machine-specific fields for reproducibility ─────
    machine_bl = baseline_raw.get("machine", {}) if isinstance(baseline_raw.get("machine"), dict) else {}
    exec_env = trust_identity.execution_environment or {}
    env_summary = {
        # Classification labels (from execution_environment probe)
        "support_tier":              exec_env.get("support_tier") or "not in snapshot",
        "measurement_grade":         exec_env.get("measurement_grade") or "not in snapshot",
        "telemetry_capture_quality": trust_identity.telemetry_provider.get("capture_quality") or "not in snapshot",
        # Machine identity (from baseline.yaml machine block)
        "machine_name":   machine_bl.get("name") or "not set in baseline",
        "cpu":            machine_bl.get("cpu") or "not set in baseline",
        "gpu":            machine_bl.get("gpu") or "not set in baseline",
        "ram":            machine_bl.get("ram") or "not set in baseline",
        # OS/platform (from campaign_start_snapshot DB columns)
        "os_version":     snap.get("os_version") or "not in snapshot",
        "os_platform":    snap.get("os_platform") or "not in snapshot",
        "python_version": snap.get("python_version") or "not in snapshot",
        "nvidia_driver":  snap.get("nvidia_driver") or "not in snapshot",
        "gpu_name":       snap.get("gpu_name") or "not in snapshot",
        "power_plan":     snap.get("power_plan") or "not in snapshot",
        # Starting conditions at measurement time
        "cpu_temp_at_start_c": snap.get("cpu_temp_at_start_c"),
        "gpu_temp_at_start_c": snap.get("gpu_temp_at_start_c"),
        "model_disk_free_gb":   snap.get("model_disk_free_gb"),
    }

    # ── Run context summary — DB-resident cycle counts + quality rollup ───────
    # Cycle counts come from the DB (always available).
    # Quality rollup comes from run_context JSON files if available (non-fatal).
    try:
        with get_connection(db_path) as _rc_conn:
            cycle_rows = _rc_conn.execute(
                "SELECT status, COUNT(*) as cnt FROM cycles WHERE campaign_id=? GROUP BY status",
                (campaign_id,),
            ).fetchall()
            total_cycles_db = _rc_conn.execute(
                "SELECT COUNT(*) FROM cycles WHERE campaign_id=?",
                (campaign_id,),
            ).fetchone()[0]
            invalid_count = _rc_conn.execute(
                "SELECT COUNT(*) FROM cycles WHERE campaign_id=? AND status='invalid'",
                (campaign_id,),
            ).fetchone()[0]
    except Exception:
        cycle_rows = []
        total_cycles_db = None
        invalid_count = None

    cycle_status_dist = {row["status"]: row["cnt"] for row in cycle_rows} if cycle_rows else {}

    # Attempt quality rollup from run_context JSON files (best-effort, non-fatal).
    env_agg: dict = {}
    rc_file_count = 0
    if env_dir is not None and env_dir.exists():
        try:
            from src.report_campaign import _load_run_contexts, _aggregate_environment  # noqa: PLC0415
            run_contexts = _load_run_contexts(env_dir)
            rc_file_count = len(run_contexts)
            if run_contexts:
                env_agg = _aggregate_environment(run_contexts)
        except Exception as _rc_exc:
            logger.debug("metadata.json: run_context aggregation failed (non-fatal): %s", _rc_exc)

    run_context_summary: dict = {
        "total_cycles_in_db":      total_cycles_db,
        "cycle_status_distribution": cycle_status_dist,
        "invalid_cycle_count":     invalid_count,
        "run_context_files_found": rc_file_count,
        "environment_dir":         str(env_dir) if env_dir else None,
    }
    if env_agg.get("available"):
        run_context_summary.update({
            "overall_assessment_confidence": env_agg.get("overall_confidence"),
            "clean_cycle_count":             env_agg.get("n_clean"),
            "noisy_cycle_count":             env_agg.get("n_noisy"),
            "distorted_cycle_count":         env_agg.get("n_distorted"),
            "clean_pct":                     round(env_agg.get("clean_pct", 0), 1),
            "top_interferers":               [name for name, _count in (env_agg.get("top_interferers") or [])],
            "top_anomaly_reasons":           [r for r, _count in (env_agg.get("top_reasons") or [])],
            "avg_capability_coverage":       env_agg.get("avg_capability_coverage"),
            "failed_probes":                 env_agg.get("failed_probe_names") or [],
        })
    else:
        run_context_summary["quality_rollup"] = (
            "not available — run_context files not found in environment artifact directory"
        )

    # ── Methodology provenance ─────────────────────────────────────────────────
    methodology_label = methodology_source_label(trust_identity.methodology)

    # ── Assemble document ──────────────────────────────────────────────────────
    doc: dict = {
        "_schema": "quantmap-metadata-v1",
        "_generated_at": now_utc,
        "_generator": "src.export.generate_metadata_json v1",
        "campaign": {
            "id": camp.get("id", campaign_id),
            "variable": camp.get("variable"),
            "run_mode": camp.get("run_mode"),
            "status": camp.get("status"),
            "analysis_status": camp.get("analysis_status"),
            "report_status": camp.get("report_status"),
            "started_at": camp.get("started_at"),
            "completed_at": camp.get("completed_at"),
        },
        "config_registry": config_registry,
        "methodology": {
            "profile_name": trust_identity.methodology.get("profile_name") or "not in methodology snapshot",
            "profile_version": trust_identity.methodology.get("profile_version") or "not in methodology snapshot",
            "methodology_version": trust_identity.methodology.get("version") or "not in methodology snapshot",
            "source": methodology_label,
            "weights": trust_identity.methodology.get("weights"),
            "eligibility_filters": trust_identity.methodology.get("eligibility_filters"),
            "anchors": trust_identity.methodology.get("anchors"),
        },
        "ranking": {
            "winner": winner,
            "ranked_configs": ranked_configs,
            "eliminated_configs": eliminated_configs,
            "unrankable_reason": unrankable_reason,
        },
        "environment_summary": env_summary,
        "run_context_summary":  run_context_summary,
        "baseline_identity": {
            # What exactly was tested — enough to re-run or cite the campaign
            "source": trust_identity.sources.get("baseline", "not in snapshot"),
            "capture_quality": trust_identity.sources.get("capture_quality") or "not in snapshot",
            # Model identity
            "model_name":   model_cfg.get("name") or "not set in baseline",
            "model_path":   snap.get("model_path") or model_cfg.get("path") or "not in snapshot",
            "model_size_bytes": snap.get("model_file_size_bytes"),
            "quantization": model_cfg.get("quantization") or "not set in baseline",
            # Backend/server identity
            "server_binary_path":   snap.get("server_binary_path") or "not in snapshot",
            "server_binary_sha256": snap.get("server_binary_sha256") or "not in snapshot",
            "build_commit":         snap.get("build_commit") or "not captured",
            # Sampling parameters actually used
            "sampling_params": (
                json.loads(snap["sampling_params_json"])
                if snap.get("sampling_params_json")
                else "not in snapshot"
            ),
        },
        "provenance_sources": trust_identity.sources,
        "artifacts": artifact_inventory,
        "warnings": warnings_list,
    }

    # ── Write and register ─────────────────────────────────────────────────────
    try:
        metadata_path.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
        logger.info("metadata.json written: %s", metadata_path)
    except Exception as write_exc:
        logger.error("metadata.json write failed: %s", write_exc)

    def _sha256(p: Path) -> str | None:
        try:
            h = hashlib.sha256()
            h.update(p.read_bytes())
            return h.hexdigest()
        except Exception:
            return None

    _sha = _sha256(metadata_path)
    _status = "complete" if _sha else "failed"
    _error = None if _sha else "metadata.json missing or unreadable after write"

    try:
        with get_connection(db_path) as _art_conn:
            _art_conn.execute(
                "DELETE FROM artifacts WHERE campaign_id=? AND artifact_type=?",
                (campaign_id, ARTIFACT_METADATA),
            )
            _art_conn.execute(
                "INSERT INTO artifacts (campaign_id, artifact_type, path, sha256, created_at,"
                " status, producer, error_message, updated_at, verification_source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    campaign_id,
                    ARTIFACT_METADATA,
                    str(metadata_path),
                    _sha,
                    now_utc,
                    _status,
                    "src.export.generate_metadata_json",
                    _error,
                    now_utc,
                    "producer_hash" if _sha else "producer_missing",
                ),
            )
            _art_conn.commit()
    except Exception as reg_exc:
        logger.warning("metadata.json: could not register in DB (non-fatal): %s", reg_exc)

    return metadata_path
