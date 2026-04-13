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
