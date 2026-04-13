"""
QuantMap code identity capture.

This module captures the identity of the QuantMap code that started a run.
It deliberately does not describe backend binaries; llama-server identity
lives in campaign_start_snapshot backend fields.
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.version import __methodology_version__, __version__


_REPO_ROOT = Path(__file__).parent.parent


def _run_git(args: list[str]) -> tuple[str | None, str | None]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip() or f"git exited {proc.returncode}"
    return proc.stdout.strip(), None


def _source_tree_hash() -> tuple[str | None, str | None]:
    """Hash the core QuantMap source files as a git-free fallback identity."""
    candidates: list[Path] = [
        _REPO_ROOT / "quantmap.py",
        _REPO_ROOT / "pyproject.toml",
    ]
    src_dir = _REPO_ROOT / "src"
    if src_dir.exists():
        candidates.extend(sorted(src_dir.rglob("*.py")))

    h = hashlib.sha256()
    count = 0
    try:
        for path in sorted({p for p in candidates if p.is_file()}):
            rel = path.relative_to(_REPO_ROOT).as_posix()
            data = path.read_bytes()
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            h.update(data)
            h.update(b"\0")
            count += 1
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)

    if count == 0:
        return None, "no source files found"
    return h.hexdigest(), None


def capture_quantmap_identity() -> dict[str, Any]:
    """Return a JSON-serializable run-start QuantMap identity payload."""
    errors: list[str] = []

    commit, err = _run_git(["rev-parse", "HEAD"])
    if err:
        errors.append(f"git_commit: {err}")

    status, err = _run_git(["status", "--porcelain"])
    if err:
        errors.append(f"git_dirty: {err}")
        dirty: bool | None = None
    else:
        dirty = bool(status)

    describe, err = _run_git(["describe", "--always", "--dirty", "--tags"])
    if err:
        errors.append(f"git_describe: {err}")

    tree_hash, err = _source_tree_hash()
    if err:
        errors.append(f"source_tree_sha256: {err}")

    if commit:
        source = "git"
    elif tree_hash:
        source = "source_tree_hash"
    else:
        source = "unknown"

    return {
        "quantmap_version": __version__,
        "methodology_version_label": __methodology_version__,
        "git_commit": commit,
        "git_dirty": dirty,
        "git_describe": describe,
        "source_tree_sha256": tree_hash,
        "identity_source": source,
        "capture_time_utc": datetime.now(timezone.utc).isoformat(),
        "capture_errors": errors,
    }
