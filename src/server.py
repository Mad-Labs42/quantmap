"""
QuantMap — server.py
Server lifecycle manager for llama-server (Build B, MKL runtime).

Forked from: alexziskind1/llama-throughput-lab/tests/llama_server_test_utils.py
             (MIT License — original copyright alexziskind1)

QuantMap additions over the original:
  1. MKL environment loading  — Build B requires Intel oneAPI MKL DLLs at
     runtime. _load_mkl_env() injects the required PATH entries before any
     subprocess is launched. Without this the binary crashes immediately with
     a missing DLL error.
  2. Log capture              — Server stdout/stderr is written to a
     timestamped log file per config per cycle. The file handle is explicitly
     closed in the finally block after the process exits to avoid handle leaks
     and buffering issues on Windows.
  3. --no-warmup retry        — llama-server runs a warmup generation on
     startup that can hang indefinitely on large MoE models. If the server
     does not reach completion-ready within ready_timeout_s, it is killed and
     restarted with --no-warmup appended. Both attempts are logged under the
     same config/cycle stem with _attempt1 / _attempt2 suffixes.
  4. Dynamic port selection   — Uses socket.bind(port=0) to let the OS assign
     a free port. Best-effort: there is a narrow race window between port
     assignment and subprocess bind, which is acceptable for lab isolation.
     The final production command always uses --port 8000 (Mimiry); dynamic
     ports are a lab-only mechanism.

All file-system paths resolve through environment variables loaded from .env
(via python-dotenv) with pathlib.Path throughout. No hardcoded paths.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

from dotenv import load_dotenv  # type: ignore[import]

load_dotenv()

from src.config import DEFAULT_HOST, LAB_ROOT, PRODUCTION_PORT  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# llama.cpp backend constants
# ---------------------------------------------------------------------------
# These constants are llama.cpp-specific and belong here (not in config.py).
# config.py owns infrastructure constants that are backend-agnostic.
# Future migration path: move this block to backends/llamacpp.py.

# llama-server binary — Build B FROZEN at commit afa6bfe4f
# (GGML_CUDA_FORCE_MMQ=ON baked in at compile time; do not upgrade during campaigns)
_server_bin_raw = os.getenv("QUANTMAP_SERVER_BIN")
if _server_bin_raw is None:
    raise EnvironmentError(
        "QUANTMAP_SERVER_BIN is not set. "
        "Copy .env.example to .env and set QUANTMAP_SERVER_BIN to the llama-server binary path "
        "(e.g. D:/.store/tools/llama.cpp/build-B/bin/llama-server.exe)."
    )
SERVER_BIN: Path = Path(_server_bin_raw)

# First model shard — llama.cpp resolves the remaining shards automatically
_model_path_raw = os.getenv("QUANTMAP_MODEL_PATH")
if _model_path_raw is None:
    raise EnvironmentError(
        "QUANTMAP_MODEL_PATH is not set. "
        "Copy .env.example to .env and set QUANTMAP_MODEL_PATH to the first GGUF shard "
        "(e.g. D:/.store/models/MiniMax-M2.5/UD-Q3_K_XL/MiniMax-M2.5-UD-Q3_K_XL-00001-of-00004.gguf)."
    )
MODEL_PATH: Path = Path(_model_path_raw)

# Server log directory — runtime output, lives under LAB_ROOT (gitignored)
LOGS_DIR: Path = LAB_ROOT / "logs"

# Intel oneAPI paths -- required for Build B MKL DLL resolution
MKL_ROOT = Path(
    os.getenv(
        "QUANTMAP_MKL_ROOT",
        r"C:/Program Files (x86)/Intel/oneAPI/mkl/latest",
    )
)
COMPILER_ROOT = Path(
    os.getenv(
        "QUANTMAP_COMPILER_ROOT",
        r"C:/Program Files (x86)/Intel/oneAPI/compiler/latest",
    )
)
CUDA_PATH = Path(
    os.getenv(
        "QUANTMAP_CUDA_PATH",
        r"C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.6",
    )
)

# Server ready timeouts (seconds)
SERVER_BIND_TIMEOUT_S: int = int(os.getenv("QUANTMAP_SERVER_BIND_TIMEOUT", "300"))
SERVER_READY_TIMEOUT_S: int = int(os.getenv("QUANTMAP_SERVER_READY_TIMEOUT", "120"))

# Ensure lab root and logs dir exist at import time so downstream modules
# can assume LAB_ROOT is present without each module owning that responsibility.
LAB_ROOT.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 1. MKL Environment Loading
# ---------------------------------------------------------------------------


def _load_mkl_env() -> dict[str, str]:
    """
    Build the environment dict required to run Build B.

    Build B links against Intel oneAPI MKL. The DLLs are not on the default
    Windows PATH, so they must be injected before the subprocess is launched.
    Prepends CUDA, MKL, and compiler bin dirs to PATH so they take priority
    over any stale system copies.

    Logs the resolved paths explicitly so environment drift is diagnosable
    without reading the full process environment.

    Returns a copy of os.environ with the required additions.
    Logs a warning (does not abort) if any injected path does not exist on
    disk, so failures are informative rather than silent.
    """
    env = os.environ.copy()

    mkl_bin = str(MKL_ROOT / "bin")
    compiler_bin = str(COMPILER_ROOT / "bin")
    cuda_bin = str(CUDA_PATH / "bin")

    existing_path = env.get("PATH", "")
    injected = ";".join([cuda_bin, mkl_bin, compiler_bin])
    env["PATH"] = f"{injected};{existing_path}"
    env["CUDA_PATH"] = str(CUDA_PATH)
    env["CMAKE_PREFIX_PATH"] = str(MKL_ROOT)

    # Log resolved paths explicitly for environment drift diagnosis
    logger.info("MKL env -- server_bin:    %s", SERVER_BIN)
    logger.info("MKL env -- model_path:    %s", MODEL_PATH)
    logger.info("MKL env -- cuda_bin:      %s", cuda_bin)
    logger.info("MKL env -- mkl_bin:       %s", mkl_bin)
    logger.info("MKL env -- compiler_bin:  %s", compiler_bin)

    missing = [
        f"{label}: {path}"
        for label, path in [
            ("MKL bin", mkl_bin),
            ("Compiler bin", compiler_bin),
            ("CUDA bin", cuda_bin),
        ]
        if not Path(path).exists()
    ]
    if missing:
        logger.warning(
            "MKL env: the following paths do not exist on disk -- "
            "Build B may crash with missing DLL errors:\n  %s",
            "\n  ".join(missing),
        )

    return env


# ---------------------------------------------------------------------------
# 2. Log file path helper
# ---------------------------------------------------------------------------


def get_runtime_env_summary() -> dict[str, object]:
    """
    Return the environment snapshot relevant to inference reproducibility.

    Two categories are captured:

    INJECTED — env vars that _load_mkl_env() sets unconditionally before
        the subprocess launches.  Required for Build B MKL DLL resolution.
        These are always present regardless of the host environment.

    AMBIENT — env vars already set in os.environ that silently alter GPU
        device selection or inference behavior.  QuantMap does not set these;
        they come from the user's shell or system configuration.  Their
        *absence* (null) is explicitly recorded because absence and presence
        are both meaningful states:

          CUDA_VISIBLE_DEVICES:
            null  = not set; all GPUs visible, CUDA selects device 0 by
                    its own ordering (typically fastest-first)
            "0"   = explicitly restricted to GPU 0
            "1"   = explicitly restricted to GPU 1 (different hardware!)
            ""    = empty string — NO GPUs visible, forces CPU-only mode

          CUDA_DEVICE_ORDER:
            null             = not set; CUDA default (FASTEST_FIRST on most
                               drivers — ranks by compute throughput)
            "BY_BUS_ID"      = stable PCIe slot order; GPU 0 is always the
                               card in the lowest-numbered slot regardless
                               of speed
            "FASTEST_FIRST"  = explicit default; highest-throughput GPU = 0

        Storing null explicitly — rather than omitting the key — makes it
        possible to distinguish "not captured" from "confirmed not set" when
        reading the stored JSON.

    Stored in configs.runtime_env_json at config registration time (before
    the first cycle starts), so the snapshot reflects the environment that
    will be active when the subprocess is launched.

    Returns:
        {
            "injected": {
                "CUDA_PATH":         "<path>",
                "CMAKE_PREFIX_PATH": "<path>",
                "PATH_prepend":      ["<cuda_bin>", "<mkl_bin>", "<compiler_bin>"],
            },
            "ambient": {
                "CUDA_VISIBLE_DEVICES": "<value>" | null,
                "CUDA_DEVICE_ORDER":    "<value>" | null,
            },
        }
    """
    # _AMBIENT_VARS: env vars that affect GPU device selection or inference
    # behavior but are NOT set by QuantMap.  Extend this list as new
    # silent-impact vars are identified — each entry is captured at config
    # registration time and stored verbatim (including None for absent).
    _AMBIENT_VARS = (
        "CUDA_VISIBLE_DEVICES",   # most common source of silent GPU mismatch
        "CUDA_DEVICE_ORDER",      # controls device-index → physical-card mapping
    )

    return {
        "injected": {
            "CUDA_PATH": str(CUDA_PATH),
            "CMAKE_PREFIX_PATH": str(MKL_ROOT),
            "PATH_prepend": [
                str(CUDA_PATH / "bin"),
                str(MKL_ROOT / "bin"),
                str(COMPILER_ROOT / "bin"),
            ],
        },
        "ambient": {
            var: os.environ.get(var)  # None if absent — explicitly represented
            for var in _AMBIENT_VARS
        },
    }


def get_production_command(extra_args: list[str]) -> str:
    """
    Build the canonical copy-paste production command string for a config.

    Uses the fixed PRODUCTION_PORT (not the dynamic lab port) so the stored
    resolved_command is immediately runnable without editing.

    Callers (runner.py) pass the config-specific extra_args from
    _config_to_server_args().  SERVER_BIN, MODEL_PATH, DEFAULT_HOST, and
    PRODUCTION_PORT are all resolved here — the caller has no need to know
    the binary path or model path directly.

    Future backend migration: when backends/llamacpp.py exists, this function
    moves there and runner.py imports from the backend module instead.

    Args:
        extra_args: config-specific llama-server flags, e.g.
                    ["--threads", "16", "--threads-batch", "16", ...]

    Returns:
        Space-joined command string suitable for storing in configs.resolved_command.
    """
    parts = [
        str(SERVER_BIN),
        "--host", DEFAULT_HOST,
        "--port", str(PRODUCTION_PORT),
        "--model", str(MODEL_PATH),
    ] + extra_args
    return " ".join(parts)


def _log_path(campaign_id: str, config_id: str, cycle: int, attempt: int) -> Path:
    """
    Return the log file path for a given campaign / config / cycle / attempt.

    Both warmup attempts for the same cycle share the same config/cycle stem
    and are differentiated by _attempt1 / _attempt2. This keeps downstream
    log correlation clean: all logs for a given config/cycle are co-located
    and sortable.

    Creates parent directories if they do not exist.
    """
    log_dir = LOGS_DIR / campaign_id
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return log_dir / f"server_{config_id}_cycle{cycle:02d}_attempt{attempt}_{ts}.log"


# ---------------------------------------------------------------------------
# Port selection (dynamic -- lab runs only)
# ---------------------------------------------------------------------------


def _pick_port() -> int:
    """
    Ask the OS for a free port by binding to port 0.

    Best-effort: there is a narrow race window between the OS returning the
    port number and the subprocess binding to it. Acceptable for lab isolation;
    the two-stage readiness check provides an implicit failure path if the
    port is claimed in between.

    Lab runs only. The final production command always uses --port 8000.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((DEFAULT_HOST, 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Readiness checks
# ---------------------------------------------------------------------------


def _wait_for_server(host: str, port: int, timeout_s: int) -> None:
    """
    Poll until any readiness endpoint responds or timeout expires.

    Checks /health first, then /v1/models. Returns as soon as either responds
    with a qualifying status code. This confirms the HTTP layer is active but
    NOT that the model is loaded. Use _wait_for_completion_ready() as the
    authoritative model readiness gate.
    """
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    health_url = f"http://{host}:{port}/health"
    models_url = f"http://{host}:{port}/v1/models"

    while time.monotonic() < deadline:
        for url in (health_url, models_url):
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    if resp.status == 200:
                        resp.read()
                        return
            except urllib.error.HTTPError as exc:
                if exc.code in {200, 404}:
                    return
                last_error = exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        time.sleep(0.5)

    raise RuntimeError(
        f"Server did not become ready at {host}:{port} "
        f"within {timeout_s}s. Last error: {last_error}"
    )


def _wait_for_completion_ready(host: str, port: int, timeout_s: int) -> None:
    """
    Send a minimal completion request to confirm the model is fully loaded.

    /health returning 200 only means the HTTP layer is up. This function
    sends a real (minimal) completion request and waits for a successful
    response, confirming the model weights are loaded and inference is
    possible. This is the authoritative readiness gate.

    Raises RuntimeError on timeout.
    """
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    url = f"http://{host}:{port}/completion"
    payload = {"prompt": "ping", "n_predict": 1, "temperature": 0.0, "stream": False}
    body = json.dumps(payload).encode("utf-8")

    while time.monotonic() < deadline:
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    resp.read()
                    return
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                time.sleep(0.5)
                continue
            data = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP error {exc.code}: {data}") from exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.5)

    raise RuntimeError(f"Model did not become ready within {timeout_s}s: {last_error}")


# ---------------------------------------------------------------------------
# 3. Core server launch (log handle ownership is explicit)
# ---------------------------------------------------------------------------


def _launch_server(
    cmd: list[str],
    env: dict[str, str],
    log_file: Path,
) -> tuple[subprocess.Popen, IO[str]]:
    """
    Launch llama-server as a subprocess, routing stdout/stderr to log_file.

    Returns (process, log_handle). The caller MUST close log_handle after
    the process exits. Opened with buffering=1 (line-buffered) so diagnostic
    lines appear in the log file promptly rather than being held in a buffer.

    Ownership contract: start_server() closes the handle in its finally block.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    # line-buffered so server diagnostics appear promptly in the log
    log_handle: IO[str] = open(log_file, "w", encoding="utf-8", buffering=1)  # noqa: WPS515

    logger.debug("Server log: %s", log_file)
    logger.debug("Command argv: %s", cmd)

    process = subprocess.Popen(
        cmd,
        stdout=log_handle,
        stderr=log_handle,
        env=env,
        text=True,
    )
    return process, log_handle


# ---------------------------------------------------------------------------
# 4. Public context manager
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def start_server(
    extra_args: list[str],
    campaign_id: str,
    config_id: str,
    cycle: int,
    host: str = DEFAULT_HOST,
    port: int | None = None,
    bind_timeout_s: int = SERVER_BIND_TIMEOUT_S,
    ready_timeout_s: int = SERVER_READY_TIMEOUT_S,
):
    """
    Context manager that starts llama-server and yields connection info.

    On entry:
      - Loads MKL environment and logs resolved paths
      - Picks a free port (dynamic -- lab runs only)
      - Launches server subprocess with line-buffered log capture
      - Waits for HTTP readiness (_wait_for_server)
      - Waits for model readiness (_wait_for_completion_ready)
      - If warmup hangs past ready_timeout_s: kills and retries with
        --no-warmup on a new port. Both attempts logged as _attempt1 /
        _attempt2 under the same config/cycle stem.

    On exit (normal or exception):
      - Closes the log file handle explicitly (before process wait, to flush
        all buffered output to disk before releasing the file lock on Windows)
      - Terminates the server (SIGTERM, then forced termination if needed)

    Yields a dict:
      {
        "host":               str,
        "port":               int,
        "base_url":           str,        "http://{host}:{port}"
        "pid":                int,
        "log_file":           Path,
        "resolved_cmd_argv":  list[str],  canonical -- structured command list
        "resolved_cmd_str":   str,        human-readable only, not shell-safe
        "no_warmup":          bool,       True if --no-warmup retry was used
        "attempt_count":      int,        total attempts made (1 = clean start, 2 = no-warmup retry used)
        "launch_time_utc":    str,        ISO8601 UTC timestamp of subprocess launch
        "ready_time_utc":     str,        ISO8601 UTC timestamp of completion-ready
        "startup_duration_s": float,      seconds from launch to completion-ready
        "env_paths": {
            "server_bin":     str,
            "model_path":     str,
            "cuda_bin":       str,
            "mkl_bin":        str,
            "compiler_bin":   str,
        },
      }

    NOTE: runner.py should record no_warmup=True as part of cycle metadata,
    not just as a log event. A config that consistently requires --no-warmup
    is operationally significant and must be visible in analysis.

    Raises:
      FileNotFoundError  -- server binary or model shard not found
      RuntimeError       -- server failed to become ready after retry
    """
    # -- Pre-flight checks ---------------------------------------------------
    if not SERVER_BIN.is_file():
        raise FileNotFoundError(
            f"llama-server binary not found: {SERVER_BIN}\n"
            "Check QUANTMAP_SERVER_BIN in .env"
        )
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(
            f"Model shard not found: {MODEL_PATH}\nCheck QUANTMAP_MODEL_PATH in .env"
        )

    if port is None:
        port = _pick_port()

    env = _load_mkl_env()

    env_paths = {
        "server_bin": str(SERVER_BIN),
        "model_path": str(MODEL_PATH),
        "cuda_bin": str(CUDA_PATH / "bin"),
        "mkl_bin": str(MKL_ROOT / "bin"),
        "compiler_bin": str(COMPILER_ROOT / "bin"),
    }

    base_cmd: list[str] = [
        str(SERVER_BIN),
        "--host",
        host,
        "--port",
        str(port),
        "--model",
        str(MODEL_PATH),
    ] + extra_args

    # -- Attempt 1 (with warmup) --------------------------------------------
    attempt = 1
    no_warmup = False
    log_file = _log_path(campaign_id, config_id, cycle, attempt)
    launch_ts = datetime.now(timezone.utc)
    process, log_handle = _launch_server(base_cmd, env, log_file)
    active_cmd = base_cmd

    try:
        _wait_for_server(host, port, timeout_s=bind_timeout_s)

        try:
            _wait_for_completion_ready(host, port, timeout_s=ready_timeout_s)

        except RuntimeError:
            # -- Warmup hung: attempt 2 with --no-warmup --------------------
            logger.warning(
                "Server did not reach completion-ready within %ds "
                "(warmup likely hung). Forcing termination and retrying "
                "with --no-warmup.",
                ready_timeout_s,
            )
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Server (attempt 1, pid=%d) did not terminate cleanly -- "
                    "forcing process termination.",
                    process.pid,
                )
                process.kill()
                process.wait(timeout=5)

            # Close handle from attempt 1 before opening attempt 2
            log_handle.close()

            # New port to avoid TIME_WAIT on the same port
            port = _pick_port()
            attempt = 2
            no_warmup = True

            no_warmup_cmd: list[str] = (
                [
                    str(SERVER_BIN),
                    "--host",
                    host,
                    "--port",
                    str(port),
                    "--model",
                    str(MODEL_PATH),
                ]
                + extra_args
                + ["--no-warmup"]
            )

            log_file = _log_path(campaign_id, config_id, cycle, attempt)
            launch_ts = datetime.now(timezone.utc)
            process, log_handle = _launch_server(no_warmup_cmd, env, log_file)
            active_cmd = no_warmup_cmd

            _wait_for_server(host, port, timeout_s=bind_timeout_s)
            _wait_for_completion_ready(host, port, timeout_s=ready_timeout_s)

        ready_ts = datetime.now(timezone.utc)
        startup_duration = (ready_ts - launch_ts).total_seconds()

        logger.info(
            "Server ready -- pid=%d port=%d attempt_count=%d no_warmup=%s startup=%.1fs",
            process.pid,
            port,
            attempt,
            no_warmup,
            startup_duration,
        )

        yield {
            "host": host,
            "port": port,
            "base_url": f"http://{host}:{port}",
            "pid": process.pid,
            "log_file": log_file,
            "resolved_cmd_argv": list(active_cmd),  # copied — prevents aliasing
            "resolved_cmd_str": " ".join(active_cmd),  # human-readable only
            "no_warmup": no_warmup,
            "attempt_count": attempt,
            "launch_time_utc": launch_ts.isoformat(),
            "ready_time_utc": ready_ts.isoformat(),
            "startup_duration_s": startup_duration,
            "env_paths": env_paths,
        }

    finally:
        # -- Close log handle, then terminate process -----------------------
        # In the normal path: handle is closed here before process.wait(),
        # ensuring buffered output is flushed and the file lock released on
        # Windows before we exit.
        # In the warmup-retry path: attempt 1's handle was already closed
        # before attempt 2 launched; this closes attempt 2's handle.
        try:
            log_handle.close()
        except Exception:  # noqa: BLE001
            pass

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Server (pid=%d) did not terminate cleanly -- "
                    "forcing process termination.",
                    process.pid,
                )
                process.kill()
                process.wait(timeout=5)

        logger.debug("Server process exited (pid=%d)", process.pid)


# ---------------------------------------------------------------------------
# Token extraction helpers (carried from llama-throughput-lab, unchanged)
# ---------------------------------------------------------------------------


def extract_token_count(response: dict[str, Any]) -> int:
    """Extract predicted token count from a llama.cpp completion response."""
    timings: dict[str, Any] = response.get("timings") or {}
    for key in ("predicted_n", "tokens_predicted", "completion_tokens"):
        if key in timings:
            return int(timings[key])
        if key in response:
            return int(response[key])
    usage: dict[str, Any] = response.get("usage") or {}
    if "completion_tokens" in usage:
        return int(usage["completion_tokens"])
    return 0


def extract_tokens_per_second(response: dict[str, Any]) -> float:
    """Extract tokens-per-second from a llama.cpp completion response."""
    timings: dict[str, Any] = response.get("timings") or {}
    for key in ("predicted_per_second", "tokens_per_second"):
        if key in timings:
            return float(timings[key])
    predicted_n = timings.get("predicted_n")
    predicted_ms = timings.get("predicted_ms")
    if predicted_n and predicted_ms:
        return float(predicted_n) / (float(predicted_ms) / 1000.0)
    return 0.0


def extract_timings(response: dict[str, Any]) -> dict[str, Any]:
    """
    Extract the full timings block from a llama.cpp completion response.
    Returns a flat dict with all available timing fields, or empty dict.
    Used by measure.py to capture prompt_n, prompt_ms, predicted_n,
    predicted_ms, predicted_per_second, and cache_n in one call.
    """
    return response.get("timings") or {}
