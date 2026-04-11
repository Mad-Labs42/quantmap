"""
QuantMap — export.py

Portable forensic case file generator (.qmap).
Bundles campaign data, methodology, and telemetry into a single SQLite file.
"""

from __future__ import annotations

import sqlite3
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from src import ui
from src.db import get_connection

def run_export(
    campaign_id: str,
    source_db: Path,
    output_path: Path,
    lite: bool = False,
    strip_env: bool = False
) -> bool:
    """Export a campaign to a standalone .qmap SQLite file."""
    console = ui.get_console()
    ui.print_banner(f"QuantMap Export: {campaign_id}")
    
    # Ensure source exists
    if not source_db.exists():
        console.print(f"[red]Error: Source database not found at {source_db}[/red]")
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
        tables = ["campaigns", "methodology_snapshots", "configs", "scores", "cycles", "requests"]
        if not lite:
            tables.append("telemetry")
        
        # We also need a metadata table
        dest_conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, val TEXT)")

        for table in tables:
            console.print(f"  [dim]Migrating {table}...[/dim]")
            _migrate_with_introspection(src_conn, dest_conn, table, campaign_id)

        # 3. Optional Stripping
        if strip_env:
            console.print(f"  [dim]Redacting environment metadata...[/dim]")
            _redact_env(dest_conn)

        # 4. Write Manifest
        _write_manifest(dest_conn, campaign_id, lite=lite, stripped=strip_env)
        
        dest_conn.close()
        src_conn.close()
        
        # 5. Final Summary
        size_mb = output_path.stat().st_size / (1024 * 1024)
        console.print(f"\n[bold green]{ui.SYM_OK} EXPORT COMPLETE[/bold green]")
        console.print(f"  [bold]Bundle Path:[/bold]     {output_path}")
        console.print(f"  [bold]Bundle Size:[/bold]     {size_mb:.2f} MB")
        console.print(f"  [bold]Fidelity:[/bold]        {'Lite (Stats-only)' if lite else 'Full Forensic'}")
        console.print(f"  [bold]Privacy:[/bold]         {'Stripped/Redacted' if strip_env else 'Original (Internal)'}")
        
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
    query = f"SELECT * FROM {table} WHERE campaign_id = ?" if table != "campaigns" else f"SELECT * FROM {table} WHERE id = ?"
    rows = src.execute(query, (campaign_id,)).fetchall()
    if not rows:
        return
        
    columns = rows[0].keys()
    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    
    dest.executemany(insert_sql, [tuple(r) for r in rows])
    dest.commit()

def _write_manifest(conn: sqlite3.Connection, campaign_id: str, lite: bool, stripped: bool):
    """Write the case-file manifest to the metadata table."""
    from src.version import __version__, __methodology_version__
    
    manifest = {
        "bundle_kind": "campaign",
        "campaign_id": campaign_id,
        "software_version": __version__,
        "methodology_version": __methodology_version__,
        "is_full_forensic": not lite,
        "is_environment_stripped": stripped,
        "export_timestamp": datetime.now().isoformat()
    }
    
    for k, v in manifest.items():
        conn.execute("INSERT INTO metadata (key, val) VALUES (?, ?)", (k, str(v)))
    conn.commit()

def _redact_env(conn: sqlite3.Connection):
    """Search and replace sensitive environment strings in raw_json columns."""
    from src.config import LAB_ROOT
    lab_path = str(LAB_ROOT)
    
    try:
        conn.execute("UPDATE campaigns SET metadata_json = REPLACE(metadata_json, ?, '<REDACTED>')", (lab_path,))
        conn.execute("UPDATE requests SET raw_json = REPLACE(raw_json, ?, '<REDACTED>')", (lab_path,))
        conn.commit()
    except:
        pass
