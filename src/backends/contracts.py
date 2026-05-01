from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from pathlib import Path
from typing import Any


class BackendKind(str, Enum):
    LLAMACPP = "llamacpp"


class BackendFailureReason(str, Enum):
    GPU_OOM = "gpu_oom"
    STARTUP_TIMEOUT = "startup_timeout"
    BACKEND_PROCESS_EXIT_BEFORE_READY = "backend_process_exit_before_ready"
    HEALTHCHECK_UNREADY = "healthcheck_unready"
    COMPLETION_UNREADY = "completion_unready"
    BACKEND_FLAG_INVALID_OR_UNSUPPORTED = "backend_flag_invalid_or_unsupported"
    BACKEND_POLICY_BLOCKED = "backend_policy_blocked"
    UNKNOWN_BACKEND_STARTUP_FAILURE = "unknown_backend_startup_failure"


def _validate_identity(campaign_id: str, config_id: str) -> None:
    if not campaign_id:
        raise ValueError("campaign_id is required")
    if not config_id:
        raise ValueError("config_id is required")


def _validate_cycle_number(cycle_number: int) -> None:
    if cycle_number < 1:
        raise ValueError("cycle_number must be >= 1")


def _validate_timeouts(bind_timeout_s: int, ready_timeout_s: int) -> None:
    if bind_timeout_s <= 0 or ready_timeout_s <= 0:
        raise ValueError("timeout values must be positive")


def _normalize_extra_args(extra_args: object) -> tuple[str, ...]:
    if isinstance(extra_args, str):
        raise TypeError("extra_args must be an iterable of argument strings, not str")
    if not isinstance(extra_args, Iterable):
        raise TypeError("extra_args must be an iterable of argument strings")
    normalized_extra_args = tuple(extra_args)
    if any(not isinstance(arg, str) for arg in normalized_extra_args):
        raise TypeError("extra_args entries must be strings")
    return normalized_extra_args


def _validate_host(host: str | None) -> None:
    if host is not None:
        if not isinstance(host, str):
            raise TypeError("host must be a string when provided")
        if not host.strip():
            raise ValueError("host must not be blank when provided")


def _validate_port(port: int | None) -> None:
    if port is not None:
        if isinstance(port, bool) or not isinstance(port, int):
            raise TypeError("port must be an int between 1 and 65535 when provided")
        if port < 1 or port > 65535:
            raise ValueError("port must be between 1 and 65535 when provided")


@dataclass(frozen=True)
class BackendLaunchRequest:
    backend_kind: BackendKind
    campaign_id: str
    config_id: str
    cycle_number: int
    extra_args: tuple[str, ...] = field(default_factory=tuple)
    bind_timeout_s: int = 300
    ready_timeout_s: int = 120
    logs_dir: Path | None = None
    host: str | None = None
    port: int | None = None

    def __post_init__(self) -> None:
        _validate_identity(self.campaign_id, self.config_id)
        _validate_cycle_number(self.cycle_number)
        _validate_timeouts(self.bind_timeout_s, self.ready_timeout_s)
        normalized_extra_args = _normalize_extra_args(self.extra_args)
        _validate_host(self.host)
        _validate_port(self.port)
        object.__setattr__(self, "extra_args", normalized_extra_args)


@dataclass(frozen=True)
class BackendSession:
    backend_kind: BackendKind
    host: str
    port: int
    base_url: str
    pid: int
    log_file: Path
    resolved_cmd_argv: tuple[str, ...]
    resolved_cmd_str: str
    no_warmup: bool
    attempt_count: int
    startup_duration_s: float
    launch_time_utc: str
    ready_time_utc: str
    env_paths: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "resolved_cmd_argv", tuple(self.resolved_cmd_argv))
        object.__setattr__(
            self,
            "env_paths",
            MappingProxyType(dict(self.env_paths)),
        )


@dataclass(frozen=True)
class BackendFailure:
    backend_kind: BackendKind
    reason: BackendFailureReason
    message: str
    detail: Mapping[str, Any] = field(default_factory=dict)
    exit_code: int | None = None
    log_path: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))
