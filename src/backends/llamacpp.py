from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, NotRequired, TypedDict

from src.backends.contracts import (
    BackendFailure,
    BackendFailureReason,
    BackendKind,
    BackendLaunchRequest,
    BackendSession,
)


class _StartServerKwargs(TypedDict):
    extra_args: list[str]
    campaign_id: str
    config_id: str
    cycle: int
    port: int | None
    bind_timeout_s: int
    ready_timeout_s: int
    logs_dir: Path | None
    host: NotRequired[str]


def _server_oom_error_type() -> type[BaseException] | None:
    try:
        from src.server import ServerOOMError  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    return ServerOOMError


def _backend_execution_policy_error_type() -> type[BaseException] | None:
    try:
        from src.backend_execution_policy import BackendExecutionPolicyError  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    return BackendExecutionPolicyError


def _start_server_callable():
    from src.server import start_server  # noqa: PLC0415

    return start_server


def _start_server_context(request: BackendLaunchRequest):
    start_server = _start_server_callable()
    kwargs: _StartServerKwargs = {
        "extra_args": list(request.extra_args),
        "campaign_id": request.campaign_id,
        "config_id": request.config_id,
        "cycle": request.cycle_number,
        "port": request.port,
        "bind_timeout_s": request.bind_timeout_s,
        "ready_timeout_s": request.ready_timeout_s,
        "logs_dir": request.logs_dir,
    }
    if request.host is not None:
        kwargs["host"] = request.host
    return start_server(**kwargs)


def _classify_exception_type(
    exc: BaseException,
    *,
    message: str,
    detail: dict[str, str],
    log_path: Path | None,
) -> BackendFailure | None:
    server_oom_error_type = _server_oom_error_type()
    if server_oom_error_type is not None and isinstance(exc, server_oom_error_type):
        detail["classification_source"] = "server_oom_exception"
        exit_code = getattr(exc, "exit_code", None)
        resolved_log_path = getattr(exc, "log_path", None) or log_path
        return BackendFailure(
            backend_kind=BackendKind.LLAMACPP,
            reason=BackendFailureReason.GPU_OOM,
            message=message,
            detail=detail,
            exit_code=exit_code if isinstance(exit_code, int) else None,
            log_path=Path(resolved_log_path) if resolved_log_path else None,
        )

    backend_execution_policy_error_type = _backend_execution_policy_error_type()
    if (
        backend_execution_policy_error_type is not None
        and isinstance(exc, backend_execution_policy_error_type)
    ):
        detail["classification_source"] = "backend_execution_policy_exception"
        return BackendFailure(
            backend_kind=BackendKind.LLAMACPP,
            reason=BackendFailureReason.BACKEND_POLICY_BLOCKED,
            message=message,
            detail=detail,
            log_path=log_path,
        )
    return None


def _classify_message(message: str) -> BackendFailureReason:
    lowered = message.lower()
    if "backend execution policy" in lowered or lowered.startswith("backend policy blocked"):
        return BackendFailureReason.BACKEND_POLICY_BLOCKED
    if "unrecognized argument" in lowered or "unknown option" in lowered:
        return BackendFailureReason.BACKEND_FLAG_INVALID_OR_UNSUPPORTED
    if "did not become ready at" in lowered and "within" in lowered:
        return BackendFailureReason.HEALTHCHECK_UNREADY
    if "model did not become ready within" in lowered:
        return BackendFailureReason.COMPLETION_UNREADY
    if "process exited" in lowered and "before" in lowered:
        return BackendFailureReason.BACKEND_PROCESS_EXIT_BEFORE_READY
    if "timed out" in lowered or "timeout" in lowered:
        return BackendFailureReason.STARTUP_TIMEOUT
    return BackendFailureReason.UNKNOWN_BACKEND_STARTUP_FAILURE


def classify_llamacpp_startup_failure(
    exc: BaseException,
    *,
    log_path: Path | None = None,
) -> BackendFailure:
    message = str(exc)
    detail: dict[str, str] = {"exception_type": type(exc).__name__}
    identity_classification = _classify_exception_type(
        exc,
        message=message,
        detail=detail,
        log_path=log_path,
    )
    if identity_classification is not None:
        return identity_classification

    reason = _classify_message(message)

    detail["classification_source"] = "message_fallback"
    return BackendFailure(
        backend_kind=BackendKind.LLAMACPP,
        reason=reason,
        message=message,
        detail=detail,
        log_path=log_path,
    )


@contextmanager
def start_llamacpp_session(request: BackendLaunchRequest) -> Iterator[BackendSession]:
    if request.backend_kind is not BackendKind.LLAMACPP:
        raise ValueError(f"Unsupported backend kind for llama.cpp adapter: {request.backend_kind}")

    with _start_server_context(request) as session:
        yield BackendSession(
            backend_kind=BackendKind.LLAMACPP,
            host=str(session["host"]),
            port=int(session["port"]),
            base_url=str(session["base_url"]),
            pid=int(session["pid"]),
            log_file=Path(str(session["log_file"])),
            resolved_cmd_argv=tuple(session["resolved_cmd_argv"]),
            resolved_cmd_str=str(session["resolved_cmd_str"]),
            no_warmup=bool(session["no_warmup"]),
            attempt_count=int(session["attempt_count"]),
            startup_duration_s=float(session["startup_duration_s"]),
            launch_time_utc=str(session["launch_time_utc"]),
            ready_time_utc=str(session["ready_time_utc"]),
            env_paths=session.get("env_paths") or {},
        )
