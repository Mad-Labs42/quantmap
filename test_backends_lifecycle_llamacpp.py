from __future__ import annotations

import ast
from contextlib import contextmanager
import inspect
from pathlib import Path
import sqlite3
import threading
from types import TracebackType

import pytest

import src.backends.lifecycle as lifecycle_module

from src.backends.contracts import BackendFailureReason, BackendKind, BackendLaunchRequest, BackendSession
from src.backend_execution_policy import (
    BackendExecutionAssessment,
    BackendExecutionPolicyError,
    DECISION_DISALLOWED,
    REASON_WSL_WINDOWS_BACKEND_INTEROP,
)
from src.settings_env import SettingsEnvError


def _request() -> BackendLaunchRequest:
    return BackendLaunchRequest(
        backend_kind=BackendKind.LLAMACPP,
        campaign_id="NGL_sweep",
        config_id="cfg_01",
        cycle_number=1,
        extra_args=("--threads", "16"),
    )


def test_llamacpp_lifecycle_maps_server_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.backends import llamacpp

    @contextmanager
    def _fake_server_context(_request: BackendLaunchRequest):
        yield {
            "host": "127.0.0.1",
            "port": 8011,
            "base_url": "http://127.0.0.1:8011",
            "pid": 9999,
            "log_file": Path("logs/server_cfg_cycle.log"),
            "resolved_cmd_argv": ["llama-server", "--port", "8011"],
            "resolved_cmd_str": "llama-server --port 8011",
            "no_warmup": True,
            "attempt_count": 2,
            "startup_duration_s": 12.3,
            "launch_time_utc": "2026-01-01T00:00:00+00:00",
            "ready_time_utc": "2026-01-01T00:00:12+00:00",
            "env_paths": {"server_bin": "D:/llama-server.exe"},
        }

    monkeypatch.setattr(llamacpp, "_start_server_context", _fake_server_context)

    with lifecycle_module.start_backend_session(_request()) as session:
        assert session.backend_kind is BackendKind.LLAMACPP
        assert session.base_url == "http://127.0.0.1:8011"
        assert session.pid == 9999
        assert session.no_warmup is True
        assert session.attempt_count == 2
        assert session.resolved_cmd_argv == ("llama-server", "--port", "8011")
        with pytest.raises(TypeError):
            session.env_paths["x"] = "y"  # type: ignore[index]


def test_classify_backend_startup_failure_gpu_oom() -> None:
    from src.backends import llamacpp

    class FakeServerOOMError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("llama-server OOM")
            self.exit_code = 137
            self.log_path = Path("logs/server_oom.log")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(llamacpp, "_server_oom_error_type", lambda: FakeServerOOMError)
    failure = lifecycle_module.classify_backend_startup_failure(
        FakeServerOOMError()
    )
    monkeypatch.undo()

    assert failure.reason is BackendFailureReason.GPU_OOM
    assert failure.exit_code == 137
    assert failure.log_path == Path("logs/server_oom.log")


def test_classify_backend_startup_failure_identity_beats_message() -> None:
    from src.backends import llamacpp

    class FakeServerOOMError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("unknown option '--timeout'")
            self.exit_code = 137
            self.log_path = Path("logs/server_oom.log")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(llamacpp, "_server_oom_error_type", lambda: FakeServerOOMError)
    failure = lifecycle_module.classify_backend_startup_failure(FakeServerOOMError())
    monkeypatch.undo()

    assert failure.reason is BackendFailureReason.GPU_OOM


def test_classify_backend_startup_failure_backend_policy_by_identity() -> None:
    from src.backends import llamacpp

    assessment = BackendExecutionAssessment(
        execution_support_tier="degraded",
        execution_platform="wsl2",
        backend_target_kind="windows_native_executable",
        backend_path="D:/Tools/llama-server.exe",
        decision=DECISION_DISALLOWED,
        reason_code=REASON_WSL_WINDOWS_BACKEND_INTEROP,
        diagnostic="Backend execution policy blocked this backend target.",
        remediation="Run backend inside the same OS boundary.",
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(llamacpp, "_backend_execution_policy_error_type", lambda: BackendExecutionPolicyError)
    failure = lifecycle_module.classify_backend_startup_failure(BackendExecutionPolicyError(assessment))
    monkeypatch.undo()

    assert failure.reason is BackendFailureReason.BACKEND_POLICY_BLOCKED
    assert failure.detail["classification_source"] == "backend_execution_policy_exception"


@pytest.mark.parametrize(
    ("message", "expected_reason"),
    [
        (
            "Server did not become ready at 127.0.0.1:8000 within 30s",
            BackendFailureReason.HEALTHCHECK_UNREADY,
        ),
        (
            "Model did not become ready within 120s",
            BackendFailureReason.COMPLETION_UNREADY,
        ),
        (
            "Server process exited (code=3) before model was ready",
            BackendFailureReason.BACKEND_PROCESS_EXIT_BEFORE_READY,
        ),
        (
            "error: unrecognized argument '--fake-flag'",
            BackendFailureReason.BACKEND_FLAG_INVALID_OR_UNSUPPORTED,
        ),
        (
            "error: unknown option '--timeout'",
            BackendFailureReason.BACKEND_FLAG_INVALID_OR_UNSUPPORTED,
        ),
        (
            "error: unrecognized argument '--read-timeout'",
            BackendFailureReason.BACKEND_FLAG_INVALID_OR_UNSUPPORTED,
        ),
        (
            "Backend execution policy blocked this backend target",
            BackendFailureReason.BACKEND_POLICY_BLOCKED,
        ),
        (
            "server startup timeout after 300s",
            BackendFailureReason.STARTUP_TIMEOUT,
        ),
        (
            "error: unrecognized argument '--threads' after startup timed out waiting",
            BackendFailureReason.BACKEND_FLAG_INVALID_OR_UNSUPPORTED,
        ),
        (
            "error: unknown option '--read-timeout' but timeout was exceeded",
            BackendFailureReason.BACKEND_FLAG_INVALID_OR_UNSUPPORTED,
        ),
        (
            "something failed mysteriously with no recognizable backend signal",
            BackendFailureReason.UNKNOWN_BACKEND_STARTUP_FAILURE,
        ),
    ],
)
def test_classify_backend_startup_failure_known_mappings(
    message: str,
    expected_reason: BackendFailureReason,
) -> None:
    failure = lifecycle_module.classify_backend_startup_failure(RuntimeError(message))
    assert failure.reason is expected_reason


def test_classify_backend_startup_failure_falls_back_unknown() -> None:
    failure = lifecycle_module.classify_backend_startup_failure(RuntimeError("some unexpected startup error"))
    assert failure.reason is BackendFailureReason.UNKNOWN_BACKEND_STARTUP_FAILURE


class _BodyValueError(ValueError):
    """Sentinel body exception (distinct from generic ValueError)."""


class _LabConfigMisconfigurationError(Exception):
    """Fake non-config entry error used to verify unknown startup classification."""


def test_start_backend_session_wraps_entry_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.backends import llamacpp

    class _BoomOnEnter:
        def __enter__(self) -> object:
            raise RuntimeError("Server did not become ready at 127.0.0.1:8000 within 30s")

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _tb: TracebackType | None,
        ) -> bool:
            return False

    def _boom_on_enter(_request: BackendLaunchRequest) -> _BoomOnEnter:
        return _BoomOnEnter()

    monkeypatch.setattr(llamacpp, "start_llamacpp_session", _boom_on_enter)

    ctx = lifecycle_module.start_backend_session(_request())
    with pytest.raises(lifecycle_module.BackendStartupError) as exc_info:
        ctx.__enter__()
    assert exc_info.value.failure.reason is BackendFailureReason.HEALTHCHECK_UNREADY


def test_start_backend_session_does_not_wrap_body_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.backends import llamacpp

    @contextmanager
    def _session(_request: BackendLaunchRequest):
        yield object()

    monkeypatch.setattr(llamacpp, "start_llamacpp_session", _session)

    with pytest.raises(_BodyValueError, match="body explosion"):
        with lifecycle_module.start_backend_session(_request()):
            raise _BodyValueError("body explosion")


def test_start_backend_session_cleanup_error_not_classified_as_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.backends import llamacpp

    class CleanupError(RuntimeError):
        pass

    class _SessionWithCleanupFailure:
        def __enter__(self) -> object:
            return object()

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _tb: TracebackType | None,
        ) -> bool:
            raise CleanupError("cleanup failure")

    def _session(_request: BackendLaunchRequest) -> _SessionWithCleanupFailure:
        return _SessionWithCleanupFailure()

    monkeypatch.setattr(llamacpp, "start_llamacpp_session", _session)

    with pytest.raises(CleanupError, match="cleanup failure"):
        with lifecycle_module.start_backend_session(_request()):
            _ = "body executes; cleanup error should still propagate"


def test_start_backend_session_passthrough_settings_env_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.backends import llamacpp

    class _SettingsEnvFail:
        def __enter__(self) -> object:
            raise SettingsEnvError("QUANTMAP_LAB_ROOT is not set")

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _tb: TracebackType | None,
        ) -> bool:
            return False

    def _settings_env_fail(_request: BackendLaunchRequest) -> _SettingsEnvFail:
        return _SettingsEnvFail()

    monkeypatch.setattr(llamacpp, "start_llamacpp_session", _settings_env_fail)

    ctx = lifecycle_module.start_backend_session(_request())
    with pytest.raises(SettingsEnvError) as exc_info:
        ctx.__enter__()
    assert type(exc_info.value) is SettingsEnvError


def test_start_backend_session_unknown_entry_error_becomes_unknown_startup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown entry exceptions are startup failures with unknown reason."""
    from src.backends import llamacpp

    class _ConfigFail:
        def __enter__(self) -> object:
            raise _LabConfigMisconfigurationError("invalid lab root layout")

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _tb: TracebackType | None,
        ) -> bool:
            return False

    def _fail(_request: BackendLaunchRequest) -> _ConfigFail:
        return _ConfigFail()

    monkeypatch.setattr(llamacpp, "start_llamacpp_session", _fail)

    ctx = lifecycle_module.start_backend_session(_request())
    with pytest.raises(lifecycle_module.BackendStartupError) as exc_info:
        ctx.__enter__()
    assert exc_info.value.failure.reason is BackendFailureReason.UNKNOWN_BACKEND_STARTUP_FAILURE
    assert "invalid lab root layout" in exc_info.value.failure.message


def test_start_backend_session_inner_exit_suppresses_body_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If inner CM returns True from __exit__, suppression must propagate per CM protocol."""
    from src.backends import llamacpp

    class _SuppressBody:
        def __enter__(self) -> object:
            return object()

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _tb: TracebackType | None,
        ) -> bool:
            return exc_type is _BodyValueError

    def _session(_request: BackendLaunchRequest) -> _SuppressBody:
        return _SuppressBody()

    monkeypatch.setattr(llamacpp, "start_llamacpp_session", _session)

    with lifecycle_module.start_backend_session(_request()):
        raise _BodyValueError("suppressed by inner exit")


def test_start_backend_session_inner_exit_does_not_suppress_body_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.backends import llamacpp

    class _NoSuppress:
        def __enter__(self) -> object:
            return object()

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _tb: TracebackType | None,
        ) -> bool:
            return False

    def _session(_request: BackendLaunchRequest) -> _NoSuppress:
        return _NoSuppress()

    monkeypatch.setattr(llamacpp, "start_llamacpp_session", _session)

    with pytest.raises(_BodyValueError, match="not suppressed"):
        with lifecycle_module.start_backend_session(_request()):
            raise _BodyValueError("not suppressed")


def test_start_backend_session_calls_inner_exit_after_normal_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.backends import llamacpp

    exit_calls: list[tuple[type[BaseException] | None, BaseException | None, TracebackType | None]] = []

    class _TrackExit:
        def __enter__(self) -> object:
            return object()

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:
            exit_calls.append((exc_type, exc, tb))
            return False

    def _session(_request: BackendLaunchRequest) -> _TrackExit:
        return _TrackExit()

    monkeypatch.setattr(llamacpp, "start_llamacpp_session", _session)

    with lifecycle_module.start_backend_session(_request()):
        pass

    assert len(exit_calls) == 1
    assert exit_calls[0] == (None, None, None)


def test_start_backend_session_static_guard_no_broad_except_around_yield() -> None:
    module_ast = ast.parse(inspect.getsource(lifecycle_module))
    fn = next(
        node for node in module_ast.body if isinstance(node, ast.FunctionDef) and node.name == "start_backend_session"
    )

    def _contains_yield(node: ast.AST) -> bool:
        return any(isinstance(inner, ast.Yield) for inner in ast.walk(node))

    def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
        return handler.type is None or (
            isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
        )

    risky_try_blocks = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Try) and _contains_yield(node) and any(_is_broad_handler(h) for h in node.handlers)
    ]
    assert risky_try_blocks == []


def test_run_cycle_static_guard_specific_handlers_precede_generic_crash_path() -> None:
    runner_source = Path("src/runner.py").read_text(encoding="utf-8")
    module_ast = ast.parse(runner_source)
    run_cycle = next(
        node for node in module_ast.body if isinstance(node, ast.FunctionDef) and node.name == "_run_cycle"
    )
    cycle_try = next(node for node in run_cycle.body if isinstance(node, ast.Try))
    generic_handler = next(
        handler
        for handler in cycle_try.handlers
        if isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
    )

    isinstance_checks: list[str] = []
    for stmt in generic_handler.body:
        if not isinstance(stmt, ast.If):
            continue
        call = stmt.test
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "isinstance"
            and len(call.args) >= 2
            and isinstance(call.args[1], ast.Name)
        ):
            continue
        isinstance_checks.append(call.args[1].id)

    assert "SettingsEnvError" in isinstance_checks
    assert "BackendStartupError" in isinstance_checks
    assert isinstance_checks.index("SettingsEnvError") < isinstance_checks.index("BackendStartupError")


def test_run_cycle_uses_real_session_log_for_mid_cycle_oom(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    server_bin = tmp_path / "llama-server"
    model_path = tmp_path / "model.gguf"
    server_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    model_path.write_text("model", encoding="utf-8")
    monkeypatch.setenv("QUANTMAP_LAB_ROOT", str(tmp_path / "lab"))
    monkeypatch.setenv("QUANTMAP_SERVER_BIN", str(server_bin))
    monkeypatch.setenv("QUANTMAP_MODEL_PATH", str(model_path))

    from src import runner
    from src.server import ServerOOMError

    server_log = tmp_path / "actual-server.log"
    server_log.write_text("CUDA error: out of memory\n", encoding="utf-8")
    request_file = tmp_path / "requests" / "speed_short.json"
    request_file.parent.mkdir()
    request_file.write_text('{"prompt": "hello"}', encoding="utf-8")

    @contextmanager
    def _fake_backend_session(_request: BackendLaunchRequest):
        yield BackendSession(
            backend_kind=BackendKind.LLAMACPP,
            host="127.0.0.1",
            port=8011,
            base_url="http://127.0.0.1:8011",
            pid=9999,
            log_file=server_log,
            resolved_cmd_argv=("llama-server", "--port", "8011"),
            resolved_cmd_str="llama-server --port 8011",
            no_warmup=False,
            attempt_count=1,
            startup_duration_s=1.0,
            launch_time_utc="2026-01-01T00:00:00+00:00",
            ready_time_utc="2026-01-01T00:00:01+00:00",
        )

    class _Collector:
        _lock = threading.Lock()
        _samples: list[object] = []

        def start(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

        def stop(self) -> tuple[list[object], list[object]]:
            return [], []

    class _Console:
        def print(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            return None

    def _boom_measure_request_sync(**_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("request failed after server OOM")

    monkeypatch.setattr("src.backends.start_backend_session", _fake_backend_session)
    monkeypatch.setattr(runner, "measure_request_sync", _boom_measure_request_sync)

    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE cycles (
            id INTEGER PRIMARY KEY,
            status TEXT,
            invalid_reason TEXT,
            server_pid INTEGER,
            server_log_path TEXT,
            started_at TEXT,
            no_warmup INTEGER,
            attempt_count INTEGER,
            startup_duration_s REAL
        )"""
    )
    conn.execute("CREATE TABLE requests (cycle_id INTEGER, cycle_status TEXT)")
    conn.execute("INSERT INTO cycles (id, status) VALUES (1, 'pending')")

    with pytest.raises(ServerOOMError) as exc_info:
        runner._run_cycle(
            conn=conn,
            config={"config_id": "cfg_01", "server_args": []},
            cycle_number=1,
            cycle_id=1,
            campaign_id="camp",
            lab_config={"requests_per_cycle": 1, "cycles_per_config": 2, "inter_request_delay_s": 0},
            request_files={"speed_short": request_file},
            collector=_Collector(),  # type: ignore[arg-type]
            console=_Console(),  # type: ignore[arg-type]
        )

    assert exc_info.value.log_path == server_log
    row = conn.execute("SELECT status, invalid_reason FROM cycles WHERE id=1").fetchone()
    assert row == ("invalid", "crash: OOM")


def test_lifecycle_test_module_imports_lifecycle_consistently() -> None:
    """Avoid mixed import styles that re-import the same module under different bindings."""
    src = Path(__file__).read_text(encoding="utf-8")
    module_ast = ast.parse(src)
    lifecycle_imports = [
        node for node in module_ast.body if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "src.backends.lifecycle"
    ]
    lifecycle_from_imports = [
        node
        for node in module_ast.body
        if isinstance(node, ast.ImportFrom) and node.module == "src.backends.lifecycle"
    ]
    assert len(lifecycle_imports) == 1
    alias = lifecycle_imports[0].names[0]
    assert alias.asname == "lifecycle_module"
    assert lifecycle_from_imports == []


def test_lifecycle_source_has_no_recursive_lifecycle_import() -> None:
    life_src = Path("src/backends/lifecycle.py").read_text(encoding="utf-8")
    assert "from src.backends.lifecycle import" not in life_src


def test_start_server_context_omits_host_when_not_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.backends import llamacpp

    captured: dict[str, object] = {}

    @contextmanager
    def _fake_start_server(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        yield {}

    monkeypatch.setattr(llamacpp, "_start_server_callable", lambda: _fake_start_server)

    with llamacpp._start_server_context(_request()):
        captured["entered"] = True

    assert "host" not in captured


def test_start_server_context_includes_host_when_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.backends import llamacpp

    captured: dict[str, object] = {}

    @contextmanager
    def _fake_start_server(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        yield {}

    monkeypatch.setattr(llamacpp, "_start_server_callable", lambda: _fake_start_server)
    request = BackendLaunchRequest(
        backend_kind=BackendKind.LLAMACPP,
        campaign_id="NGL_sweep",
        config_id="cfg_01",
        cycle_number=1,
        extra_args=("--threads", "16"),
        host="127.0.0.9",
    )

    with llamacpp._start_server_context(request):
        captured["entered"] = True

    assert captured["host"] == "127.0.0.9"


def test_start_server_context_converts_immutable_extra_args_to_legacy_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.backends import llamacpp

    captured: dict[str, object] = {}

    @contextmanager
    def _fake_start_server(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        yield {}

    monkeypatch.setattr(llamacpp, "_start_server_callable", lambda: _fake_start_server)
    request = BackendLaunchRequest(
        backend_kind=BackendKind.LLAMACPP,
        campaign_id="NGL_sweep",
        config_id="cfg_01",
        cycle_number=1,
        extra_args=("--threads", "16"),
    )

    with llamacpp._start_server_context(request):
        captured["entered"] = True

    assert isinstance(captured["extra_args"], list)
    assert captured["extra_args"] == ["--threads", "16"]
