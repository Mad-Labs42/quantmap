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
    config.py imports only the stdlib-only settings_env helper from the
    QuantMap source tree.
    All other src/ modules MAY import from config.py.
    No src/ module should import infrastructure constants from another src/ module.

All paths are resolved from environment variables. Copy .env.example to .env
and configure it before running any QuantMap commands. QUANTMAP_LAB_ROOT is
required; the module raises EnvironmentError at import time if it is unset.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.settings_env import optional_env_path, require_env_path

# ---------------------------------------------------------------------------
# Repository layout
# ---------------------------------------------------------------------------
# config.py lives at src/config.py — parent is src/, parent.parent is repo root.
_REPO_ROOT: Path = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Lab root — all runtime output (results, logs, db, state).  Gitignored.
# ---------------------------------------------------------------------------
LAB_ROOT: Path = require_env_path(
    "QUANTMAP_LAB_ROOT",
    purpose="QuantMap lab root",
    recommendation=(
        "Copy .env.example to .env and set QUANTMAP_LAB_ROOT to your lab "
        "directory (e.g. D:/Workspaces/QuantMap)."
    ),
)

# ---------------------------------------------------------------------------
# Source-tree directories — live with the repo, not with runtime output.
# ---------------------------------------------------------------------------
CONFIGS_DIR: Path = optional_env_path("QUANTMAP_CONFIGS_DIR", _REPO_ROOT / "configs")
REQUESTS_DIR: Path = optional_env_path("QUANTMAP_REQUESTS_DIR", _REPO_ROOT / "requests")

# ---------------------------------------------------------------------------
# Network — infrastructure constants, backend-agnostic
# ---------------------------------------------------------------------------
# Loopback only — lab measurements never go over the network.
DEFAULT_HOST: str = os.getenv("QUANTMAP_SERVER_HOST", "127.0.0.1")

# Port used in copy-paste reproduction commands (stored in configs.resolved_command).
# Lab runs use OS-assigned dynamic ports per cycle; production commands always
# reference this fixed port so the stored command is copy-paste runnable.
PRODUCTION_PORT: int = 8000
