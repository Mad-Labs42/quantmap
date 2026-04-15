"""QuantMap — ui.py

Central UI management. Handles:
- Symbol abstraction (UTF-8 vs ASCII fallback)
- Console capability detection (color, encoding, interactivity)
- Unified rich.Console management
"""

from __future__ import annotations

import os
import sys

from rich.console import Console
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Capability Detection Logic
# ---------------------------------------------------------------------------

def _is_plain_mode() -> bool:
    """Check if plain/conservative output is forced."""
    if os.getenv("QUANTMAP_PLAIN") == "1":
        return True
    # Check sys.argv directly for --plain (set by quantmap.py)
    if "--plain" in sys.argv:
        return True
    return False

def _supports_utf8() -> bool:
    """Check if stdout supports UTF-8 characters."""
    if sys.platform != "win32":
        return True
    # On Windows, check console encoding
    encoding = getattr(sys.stdout, "encoding", "") or ""
    return encoding.lower() in ("utf-8", "utf8")

# Force-calculate fallback state
PLAIN_MODE: bool = _is_plain_mode()
UTF8_SUPPORTED: bool = _supports_utf8()
USE_ASCII: bool = PLAIN_MODE or not UTF8_SUPPORTED

# ---------------------------------------------------------------------------
# Symbol Abstraction
# ---------------------------------------------------------------------------

SYM_OK: str = "✓" if not USE_ASCII else "[OK]"
SYM_WARN: str = "⚠️ " if not USE_ASCII else "[!]"
SYM_FAIL: str = "✗" if not USE_ASCII else "[FAIL]"
SYM_INFO: str = "ℹ " if not USE_ASCII else "[i]"
SYM_RETRY: str = "↺" if not USE_ASCII else "[RETRY]"
SYM_DIVIDER: str = "━" if not USE_ASCII else "-"

# ---------------------------------------------------------------------------
# Unified Console
# ---------------------------------------------------------------------------

# Global theme for consistent coloring
QUANTMAP_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
    "success": "green",
    "dim": "dim",
    "bold": "bold",
    "highlight": "magenta",
})

_GLOBAL_CONSOLE: Console | None = None

def get_console(force_new: bool = False, force_utf8_if_bootstrap: bool = False) -> Console:
    """Returns a unified, capability-aware rich.Console.
    
    Arguments:
        force_new: Always create a fresh instance.
        force_utf8_if_bootstrap: Internal use for testing bootstrap states.
    """
    global _GLOBAL_CONSOLE
    if _GLOBAL_CONSOLE is not None and not force_new:
        return _GLOBAL_CONSOLE

    # Capability detection
    # If stdout is not a TTY, rich usually detects this and disables color/emojis.
    # We respect sys.stdout.isatty() but allow overrides.

    force_terminal = None
    if PLAIN_MODE:
        # plain mode effectively turns off color and special glyphs
        force_terminal = False

    # On Windows, if we reconfigured stdout to UTF-8 in bootstrap,
    # sys.stdout.encoding might already be 'utf-8'.

    console = Console(
        theme=QUANTMAP_THEME,
        force_terminal=force_terminal,
        # fallback to plain text if not a tty and not forced
        no_color=PLAIN_MODE,
        # High-rigor: If we're bootstrapping, we might need a specific color system
        color_system="auto" if not PLAIN_MODE else None,
    )

    if not force_new:
        _GLOBAL_CONSOLE = console
    return console

def print_banner(text: str, style: str = "bold cyan"):
    """Unified banner printer."""
    console = get_console()
    console.print()
    console.print(f"[{style}]{text}[/{style}]")
    if USE_ASCII:
        console.print("-" * len(text))
    else:
        console.print("━" * len(text))
    console.print()

def format_status(label: str, passed: bool, detail: str = "") -> str:
    """Helper for health check style outputs."""
    symbol = SYM_OK if passed else SYM_FAIL
    style = "green" if passed else "red"
    msg = f"  [{style}]{symbol}[/{style}]  {label}"
    if detail:
        msg += f"  [dim]— {detail}[/dim]"
    return msg
