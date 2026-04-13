"""
QuantMap settings/environment path helpers.

This module is intentionally narrow and stdlib-only. It normalizes environment
path semantics so required runtime paths never silently become Path('.').
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


class SettingsEnvError(EnvironmentError):
    """Raised when a required settings/env path is unavailable."""


@dataclass(frozen=True)
class EnvPath:
    name: str
    raw: str | None
    path: Path | None
    status: str
    message: str
    recommendation: str

    @property
    def available(self) -> bool:
        return self.path is not None and self.status == "available"


@dataclass(frozen=True)
class LabPaths:
    lab_root: Path
    db_dir: Path
    logs_dir: Path
    results_dir: Path
    state_dir: Path

    @property
    def db_path(self) -> Path:
        return self.db_dir / "lab.sqlite"


def read_env_path(
    name: str,
    *,
    purpose: str = "path",
    recommendation: str | None = None,
) -> EnvPath:
    """Read a path env var, treating missing/empty/whitespace as unavailable."""
    raw = os.getenv(name)
    rec = recommendation or f"Set {name} in .env or pass an explicit path where supported."
    if raw is None:
        return EnvPath(
            name=name,
            raw=None,
            path=None,
            status="missing",
            message=f"{name} is not set",
            recommendation=rec,
        )
    cleaned = raw.strip()
    if cleaned == "":
        return EnvPath(
            name=name,
            raw=raw,
            path=None,
            status="empty",
            message=f"{name} is empty",
            recommendation=rec,
        )
    if Path(cleaned) == Path("."):
        return EnvPath(
            name=name,
            raw=raw,
            path=None,
            status="invalid",
            message=f"{name} points to the current directory",
            recommendation=rec,
        )
    return EnvPath(
        name=name,
        raw=raw,
        path=Path(cleaned),
        status="available",
        message=f"{name} is available for {purpose}",
        recommendation="",
    )


def require_env_path(
    name: str,
    *,
    purpose: str,
    recommendation: str | None = None,
) -> Path:
    """Return an env path or raise a clear error for missing/empty values."""
    value = read_env_path(name, purpose=purpose, recommendation=recommendation)
    if value.path is None:
        raise SettingsEnvError(f"{value.message}. {value.recommendation}")
    return value.path


def optional_env_path(name: str, default: Path | str) -> Path:
    """Return a non-empty env path, otherwise the provided default."""
    value = read_env_path(name)
    return value.path if value.path is not None else Path(default)


def derive_lab_paths(lab_root: Path) -> LabPaths:
    """Derive standard lab subpaths from a validated lab root."""
    return LabPaths(
        lab_root=lab_root,
        db_dir=lab_root / "db",
        logs_dir=lab_root / "logs",
        results_dir=lab_root / "results",
        state_dir=lab_root / "state",
    )
