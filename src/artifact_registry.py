"""Artifact registration and inventory helpers.

This module centralizes artifact DB registration/upsert behavior plus the
canonical inventory/status projection used by artifact readers. Path
construction remains owned by ``src.artifact_paths``.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.db import get_connection

_SHA256_CHUNK_SIZE = 1024 * 1024
_SHA256_HEX_DIGITS = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class ArtifactInventorySpec:
    """Describe one canonical artifact entry for inventory projection."""

    artifact_type: str
    filename: str
    role: str
    candidate_path: Path | None


def _file_sha256(path: Path) -> str | None:
    """Return the SHA-256 hex digest for path, or None if unreadable."""
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(_SHA256_CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _validate_precomputed_sha256(sha256: str) -> str:
    """Validate and normalize a caller-supplied SHA-256 hex digest."""
    normalized = sha256.strip().lower()
    if len(normalized) != 64 or any(ch not in _SHA256_HEX_DIGITS for ch in normalized):
        raise ValueError(
            "precomputed_sha256 must be a non-empty 64-character hexadecimal SHA-256 digest"
        )
    return normalized


def register_artifact(
    db_path: Path,
    *,
    campaign_id: str,
    artifact_type: str,
    path: Path,
    producer: str,
    created_at: str | None = None,
    status: str | None = None,
    error_message: str | None = None,
    verification_source: str | None = None,
    precomputed_sha256: str | None = None,
) -> dict[str, Any]:
    """Replace the current DB row for one campaign artifact with a fresh record."""
    path = Path(path)
    now_utc = created_at or datetime.now(timezone.utc).isoformat()
    final_status = status or "complete"
    final_error = error_message if final_status != "complete" else None

    if precomputed_sha256 is not None and final_status != "complete":
        raise ValueError(
            f"artifact_type={artifact_type} cannot register status={final_status!r} with a SHA-256 digest"
        )

    if final_status == "complete":
        sha256 = (
            _validate_precomputed_sha256(precomputed_sha256)
            if precomputed_sha256 is not None
            else _file_sha256(path)
        )
        if sha256 is None:
            final_status = "failed"
            final_error = final_error or f"{path.name} missing or unreadable after generation"
            final_verification = verification_source or "producer_missing"
        else:
            final_verification = verification_source or "producer_hash"
    else:
        sha256 = None
        final_verification = verification_source or (
            "producer_missing" if final_status == "missing" else "producer_status"
        )

    row = {
        "campaign_id": campaign_id,
        "artifact_type": artifact_type,
        "path": str(path),
        "sha256": sha256,
        "created_at": now_utc,
        "status": final_status,
        "producer": producer,
        "error_message": final_error,
        "updated_at": now_utc,
        "verification_source": final_verification,
    }

    with get_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM artifacts WHERE campaign_id=? AND artifact_type=?",
            (campaign_id, artifact_type),
        )
        conn.execute(
            """
            INSERT INTO artifacts (
                campaign_id, artifact_type, path, sha256, created_at, status,
                producer, error_message, updated_at, verification_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["campaign_id"],
                row["artifact_type"],
                row["path"],
                row["sha256"],
                row["created_at"],
                row["status"],
                row["producer"],
                row["error_message"],
                row["updated_at"],
                row["verification_source"],
            ),
        )
        conn.commit()

    return row


def load_artifact_rows(campaign_id: str, db_path: Path) -> list[dict[str, Any]]:
    """Load artifact rows for one campaign with stable current-contract defaults."""
    try:
        with get_connection(db_path) as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT artifact_type, path, sha256, created_at, status, producer,
                           error_message, updated_at, verification_source
                    FROM artifacts
                    WHERE campaign_id=?
                    ORDER BY created_at DESC, artifact_type
                    """,
                    (campaign_id,),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
    except (OSError, sqlite3.Error):
        rows = []

    artifacts: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        data["status"] = data.get("status") or "partial"
        data["verification_source"] = data.get("verification_source") or "unknown"
        artifacts.append(data)
    return artifacts


def load_artifact_rows_by_type(
    campaign_id: str,
    db_path: Path,
) -> dict[str, dict[str, Any]]:
    """Return newest artifact row per type for one campaign."""
    by_type: dict[str, dict[str, Any]] = {}
    for row in reversed(load_artifact_rows(campaign_id, db_path)):
        artifact_type = row.get("artifact_type")
        if artifact_type:
            by_type[str(artifact_type)] = row
    return by_type


def _resolve_inventory_path(
    row: dict[str, Any] | None,
    candidate_path: Path | None,
) -> tuple[Path | None, bool]:
    """Prefer the DB-registered path and fall back to the candidate path."""
    db_path = row.get("path") if row else None
    if db_path:
        resolved = Path(str(db_path))
        return resolved, resolved.exists()
    if candidate_path is None:
        return None, False
    return candidate_path, candidate_path.exists()


def _project_inventory_status(
    row: dict[str, Any] | None,
    path: Path | None,
    *,
    missing_status: str,
) -> str:
    """Return a conservative inventory status for one artifact entry."""
    if row:
        return str(row.get("status") or "partial")
    if path is not None and path.exists():
        return "file_present"
    return missing_status


def build_artifact_inventory(
    campaign_id: str,
    db_path: Path,
    specs: list[ArtifactInventorySpec],
    *,
    missing_status: str = "not generated",
) -> list[dict[str, Any]]:
    """Project the canonical artifact inventory for one campaign."""
    rows_by_type = load_artifact_rows_by_type(campaign_id, db_path)
    inventory: list[dict[str, Any]] = []

    for spec in specs:
        row = rows_by_type.get(spec.artifact_type)
        path, exists = _resolve_inventory_path(row, spec.candidate_path)
        inventory.append(
            {
                "artifact_type": spec.artifact_type,
                "filename": spec.filename,
                "role": spec.role,
                "path": str(path) if path is not None else None,
                "exists": exists,
                "status": _project_inventory_status(
                    row,
                    path,
                    missing_status=missing_status,
                ),
                "db_status": row.get("status") if row else None,
                "sha256": row.get("sha256") if row else None,
                "verification_source": row.get("verification_source") if row else None,
                "created_at": row.get("created_at") if row else None,
                "error_message": row.get("error_message") if row else None,
                "producer": row.get("producer") if row else None,
            }
        )

    return inventory


def summarize_artifact_bundle_status(
    rows_by_type: Mapping[str, Mapping[str, Any]],
    expected_types: tuple[str, ...],
) -> str:
    """Summarize bundle completeness for the given expected artifact types."""
    if not rows_by_type:
        return "partial"

    statuses = [
        "missing"
        if artifact_type not in rows_by_type
        else str(rows_by_type[artifact_type].get("status") or "partial")
        for artifact_type in expected_types
    ]

    if statuses and all(status == "complete" for status in statuses):
        return "complete"
    if any(status in {"failed", "partial", "missing"} for status in statuses):
        return "partial"
    return "partial"
