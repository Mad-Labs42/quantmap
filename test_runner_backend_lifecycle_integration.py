from __future__ import annotations

from contextlib import contextmanager
import json
import os
import sqlite3
import sys
import threading
import types
from pathlib import Path
from typing import Any

from rich.console import Console

REPO_ROOT = Path(__file__).resolve().parent
os.environ.setdefault("QUANTMAP_LAB_ROOT", str(REPO_ROOT))

import src.runner as runner  # noqa: E402
from src.backends import (  # noqa: E402
    BackendFailure,
    BackendFailureReason,
    BackendKind,
    BackendLaunchRequest,
    BackendSession,
    BackendStartupError,
)
from src.measure import RequestOutcome, RequestResult  # noqa: E402


class _Collector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: list[object] = []
        self.started: tuple[str, str, int, int] | None = None
        self.stop_count = 0

    def start(
        self,
        campaign_id: str,
        config_id: str,
        *,
        server_pid: int,
        cycle_id: int,
    ) -> None:
        self.started = (campaign_id, config_id, server_pid, cycle_id)

    def stop(self) -> tuple[list[object], list[object]]:
        self.stop_count += 1
        return [], []


def _cycle_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE cycles (
            id INTEGER PRIMARY KEY,
            status TEXT,
            server_pid INTEGER,
            server_log_path TEXT,
            started_at TEXT,
            completed_at TEXT,
            invalid_reason TEXT,
            no_warmup INTEGER,
            attempt_count INTEGER,
            startup_duration_s REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE requests (
            cycle_id INTEGER,
            cycle_status TEXT
        )
        """
    )
    conn.execute("INSERT INTO cycles (id, status) VALUES (101, 'pending')")
    conn.execute("INSERT INTO requests (cycle_id, cycle_status) VALUES (101, 'complete')")
    conn.commit()
    return conn


def _result() -> RequestResult:
    return RequestResult(
        campaign_id="camp",
        config_id="cfg",
        cycle_number=1,
        request_index=1,
        is_cold=True,
        request_type="speed_medium",
        outcome=RequestOutcome.SUCCESS,
        http_status=200,
        ttft_ms=12.5,
        total_wall_ms=120.0,
        prompt_n=4,
        prompt_ms=2.0,
        prompt_per_second=2000.0,
        predicted_n=8,
        predicted_ms=80.0,
        predicted_per_second=100.0,
        cache_n=4,
        total_tokens=12,
        timestamp_start="2026-05-02T10:00:00+00:00",
    )


def test_run_cycle_uses_backend_session_for_cycle_and_request_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.backends as backends

    conn = _cycle_connection()
    collector = _Collector()
    captured_request: BackendLaunchRequest | None = None
    written_rows: list[dict[str, Any]] = []

    @contextmanager
    def _session(request: BackendLaunchRequest):
        nonlocal captured_request
        captured_request = request
        yield BackendSession(
            backend_kind=BackendKind.LLAMACPP,
            host="127.0.0.1",
            port=4545,
            base_url="http://127.0.0.1:4545",
            pid=4321,
            log_file=tmp_path / "server.log",
            resolved_cmd_argv=("llama-server", "--port", "4545"),
            resolved_cmd_str="llama-server --port 4545",
            no_warmup=True,
            attempt_count=3,
            startup_duration_s=4.25,
            launch_time_utc="2026-05-02T10:00:00+00:00",
            ready_time_utc="2026-05-02T10:00:04+00:00",
            env_paths={"server_bin": "/opt/llama-server"},
        )

    monkeypatch.setattr(backends, "start_backend_session", _session)
    monkeypatch.setattr(runner, "load_request_payload", lambda _path: {"prompt": "hello"})
    monkeypatch.setattr(runner, "measure_request_sync", lambda **_kwargs: _result())
    monkeypatch.setattr(runner, "write_request", lambda _conn, _cycle_id, row: written_rows.append(row))

    thermal_event, results = runner._run_cycle(
        conn,
        {
            "config_id": "cfg",
            "server_args": ["--threads", "8"],
        },
        cycle_number=1,
        cycle_id=101,
        campaign_id="camp",
        lab_config={
            "cycles_per_config": 1,
            "requests_per_cycle": 1,
            "server_ready_timeout_s": 9,
            "server_bind_timeout_s": 7,
        },
        request_files={"speed_medium": tmp_path / "speed_medium.json"},
        collector=collector,  # type: ignore[arg-type]
        console=Console(file=open(os.devnull, "w", encoding="utf-8")),
        logs_dir=tmp_path / "logs",
        raw_telemetry_jsonl_path=tmp_path / "raw-telemetry.jsonl",
    )

    assert thermal_event is False
    assert len(results) == 1
    assert collector.started == ("camp", "cfg", 4321, 101)
    assert collector.stop_count == 1

    assert captured_request == BackendLaunchRequest(
        backend_kind=BackendKind.LLAMACPP,
        campaign_id="camp",
        config_id="cfg",
        cycle_number=1,
        extra_args=("--threads", "8"),
        ready_timeout_s=9,
        bind_timeout_s=7,
        logs_dir=tmp_path / "logs",
    )

    cycle = conn.execute("SELECT * FROM cycles WHERE id=101").fetchone()
    assert dict(cycle) | {"started_at": None, "completed_at": None} == {
        "id": 101,
        "status": "complete",
        "server_pid": 4321,
        "server_log_path": str(tmp_path / "server.log"),
        "started_at": None,
        "completed_at": None,
        "invalid_reason": None,
        "no_warmup": 1,
        "attempt_count": 3,
        "startup_duration_s": 4.25,
    }
    assert written_rows[0]["server_pid"] == 4321
    assert written_rows[0]["resolved_command"] == "llama-server --port 4545"
    assert written_rows[0]["resolved_cmd_argv"] == ("llama-server", "--port", "4545")

    raw_record = json.loads((tmp_path / "raw-telemetry.jsonl").read_text(encoding="utf-8"))
    assert raw_record["_stream"] == "requests"
    assert raw_record["server_pid"] == 4321
    assert raw_record["resolved_cmd_argv"] == ["llama-server", "--port", "4545"]


def test_run_cycle_marks_non_oom_backend_startup_failure_invalid(monkeypatch) -> None:
    import src.backends as backends

    conn = _cycle_connection()
    collector = _Collector()

    class _FakeServerOOMError(RuntimeError):
        pass

    def _fail_startup(_request: BackendLaunchRequest):
        failure = BackendFailure(
            backend_kind=BackendKind.LLAMACPP,
            reason=BackendFailureReason.BACKEND_FLAG_INVALID_OR_UNSUPPORTED,
            message="error: unknown option '--read-timeout'",
        )
        raise BackendStartupError(failure)

    monkeypatch.setitem(
        sys.modules,
        "src.server",
        types.SimpleNamespace(ServerOOMError=_FakeServerOOMError),
    )
    monkeypatch.setattr(backends, "start_backend_session", _fail_startup)
    monkeypatch.setattr(
        runner,
        "measure_request_sync",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("requests must not run")),
    )

    thermal_event, results = runner._run_cycle(
        conn,
        {
            "config_id": "cfg",
            "server_args": ["--bad-flag"],
        },
        cycle_number=1,
        cycle_id=101,
        campaign_id="camp",
        lab_config={"cycles_per_config": 1, "requests_per_cycle": 1},
        request_files={"speed_medium": Path("speed_medium.json")},
        collector=collector,  # type: ignore[arg-type]
        console=Console(file=open(os.devnull, "w", encoding="utf-8")),
    )

    assert thermal_event is False
    assert results == []
    assert collector.started is None
    assert collector.stop_count == 1

    cycle = conn.execute("SELECT status, invalid_reason FROM cycles WHERE id=101").fetchone()
    assert dict(cycle) == {
        "status": "invalid",
        "invalid_reason": "startup_failure: backend_flag_invalid_or_unsupported",
    }
    request = conn.execute("SELECT cycle_status FROM requests WHERE cycle_id=101").fetchone()
    assert dict(request) == {"cycle_status": "invalid"}
