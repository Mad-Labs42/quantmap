"""
QuantMap — config.py

Shared infrastructure constants for QuantMap.

This module owns constants that are meaningful regardless of which inference
backend is in use.  Backend-specific constants (binary paths, model paths,
runtime flags) live with their respective backend modules, not here.

    config.py owns:        infrastructure — lab root, directory layout, network
    server.py owns:        llama.cpp backend paths and launch helpers
    backends/llamacpp.py:  future home of server.py backend constants

Dependency rule:
    config.py imports NOTHING from the QuantMap source tree.
    All other src/ modules MAY import from config.py.
    No src/ module should import infrastructure constants from another src/ module.

All paths are resolved from environment variables (loaded from .env via
python-dotenv by the entry-point scripts) with sensible defaults so the
module works in a plain Python environment without a .env file.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Repository layout
# ---------------------------------------------------------------------------
# config.py lives at src/config.py — parent is src/, parent.parent is repo root.
_REPO_ROOT: Path = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Lab root — all runtime output (results, logs, db, state).  Gitignored.
# ---------------------------------------------------------------------------
LAB_ROOT: Path = Path(os.getenv("QUANTMAP_LAB_ROOT", r"D:/Workspaces/QuantMap"))

# ---------------------------------------------------------------------------
# Source-tree directories — live with the repo, not with runtime output.
# ---------------------------------------------------------------------------
CONFIGS_DIR: Path = Path(
    os.getenv("QUANTMAP_CONFIGS_DIR", str(_REPO_ROOT / "configs"))
)
REQUESTS_DIR: Path = Path(
    os.getenv("QUANTMAP_REQUESTS_DIR", str(_REPO_ROOT / "requests"))
)

# ---------------------------------------------------------------------------
# Network — infrastructure constants, backend-agnostic
# ---------------------------------------------------------------------------
# Loopback only — lab measurements never go over the network.
DEFAULT_HOST: str = "127.0.0.1"

# Port used in copy-paste reproduction commands (stored in configs.resolved_command).
# Lab runs use OS-assigned dynamic ports per cycle; production commands always
# reference this fixed port so the stored command is copy-paste runnable.
PRODUCTION_PORT: int = 8000
