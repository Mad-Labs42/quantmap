from __future__ import annotations

from pathlib import Path

import pytest

from src.backends.contracts import (
    BackendFailure,
    BackendFailureReason,
    BackendKind,
    BackendLaunchRequest,
    BackendSession,
)


def test_launch_request_requires_identifiers() -> None:
    with pytest.raises(ValueError, match="campaign_id is required"):
        BackendLaunchRequest(
            backend_kind=BackendKind.LLAMACPP,
            campaign_id="",
            config_id="cfg",
            cycle_number=1,
        )

    with pytest.raises(ValueError, match="config_id is required"):
        BackendLaunchRequest(
            backend_kind=BackendKind.LLAMACPP,
            campaign_id="camp",
            config_id="",
            cycle_number=1,
        )


def test_launch_request_rejects_invalid_cycle_and_timeout() -> None:
    with pytest.raises(ValueError, match="cycle_number must be >= 1"):
        BackendLaunchRequest(
            backend_kind=BackendKind.LLAMACPP,
            campaign_id="camp",
            config_id="cfg",
            cycle_number=0,
        )

    with pytest.raises(ValueError, match="timeout values must be positive"):
        BackendLaunchRequest(
            backend_kind=BackendKind.LLAMACPP,
            campaign_id="camp",
            config_id="cfg",
            cycle_number=1,
            bind_timeout_s=0,
        )


def test_launch_request_stores_extra_args_as_tuple() -> None:
    args = ["--threads", "8"]
    request = BackendLaunchRequest(
        backend_kind=BackendKind.LLAMACPP,
        campaign_id="camp",
        config_id="cfg",
        cycle_number=1,
        extra_args=args,
    )
    args.append("--gpu-layers")
    assert request.extra_args == ("--threads", "8")
    assert isinstance(request.extra_args, tuple)
    with pytest.raises(AttributeError):
        request.extra_args.append("--new")  # type: ignore[attr-defined]


def test_session_and_failure_store_read_only_mappings() -> None:
    resolved_cmd = ["llama-server", "--port", "9001"]
    env_paths = {"server_bin": "D:/llama-server.exe"}
    detail = {"exception_type": "RuntimeError"}
    session = BackendSession(
        backend_kind=BackendKind.LLAMACPP,
        host="127.0.0.1",
        port=9001,
        base_url="http://127.0.0.1:9001",
        pid=321,
        log_file=Path("server.log"),
        resolved_cmd_argv=resolved_cmd,
        resolved_cmd_str="llama-server --port 9001",
        no_warmup=False,
        attempt_count=1,
        startup_duration_s=1.0,
        launch_time_utc="2026-01-01T00:00:00Z",
        ready_time_utc="2026-01-01T00:00:01Z",
        env_paths=env_paths,
    )
    failure = BackendFailure(
        backend_kind=BackendKind.LLAMACPP,
        reason=BackendFailureReason.UNKNOWN_BACKEND_STARTUP_FAILURE,
        message="boom",
        detail=detail,
    )

    env_paths["another"] = "mutated"
    detail["another"] = "mutated"
    resolved_cmd.append("--extra")

    assert tuple(session.resolved_cmd_argv) == ("llama-server", "--port", "9001")
    assert isinstance(session.resolved_cmd_argv, tuple)
    assert dict(session.env_paths) == {"server_bin": "D:/llama-server.exe"}
    assert dict(failure.detail) == {"exception_type": "RuntimeError"}

    with pytest.raises(TypeError):
        session.env_paths["x"] = "y"  # type: ignore[index]
    with pytest.raises(TypeError):
        failure.detail["x"] = "y"  # type: ignore[index]


# --- Malformed launch request (contract boundary; production must reject before adapter) ---


def _valid_launch_kwargs() -> dict:
    return {
        "backend_kind": BackendKind.LLAMACPP,
        "campaign_id": "camp",
        "config_id": "cfg",
        "cycle_number": 1,
    }


@pytest.mark.parametrize(
    "extra_args",
    [
        "--threads",
        42,
        ["--x", 1],
        ("--x", None),
    ],
)
def test_launch_request_rejects_malformed_extra_args(extra_args) -> None:
    with pytest.raises((ValueError, TypeError)):
        BackendLaunchRequest(**_valid_launch_kwargs(), extra_args=extra_args)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("host",),
    [
        ("   ",),
        ("\t",),
        ("\n",),
    ],
)
def test_launch_request_rejects_blank_host(host: str) -> None:
    with pytest.raises(ValueError, match="host"):
        BackendLaunchRequest(**_valid_launch_kwargs(), host=host)


@pytest.mark.parametrize(
    "port",
    [0, -1, 65536, True, "8080", 3.14],
)
def test_launch_request_rejects_invalid_port(port) -> None:
    with pytest.raises((ValueError, TypeError)):
        BackendLaunchRequest(**_valid_launch_kwargs(), port=port)  # type: ignore[arg-type]


def test_launch_request_plain_string_extra_args_must_not_split_to_char_tuple() -> None:
    """Guard: str must not become per-character argv (silent footgun)."""
    with pytest.raises((ValueError, TypeError)):
        BackendLaunchRequest(**_valid_launch_kwargs(), extra_args="--model x.gguf")  # type: ignore[arg-type]


def test_failure_detail_nested_dict_still_mutable_without_deep_copy() -> None:
    """Documents shallow freeze: nested values are not recursively protected."""
    inner: list[str] = ["nested"]
    failure = BackendFailure(
        backend_kind=BackendKind.LLAMACPP,
        reason=BackendFailureReason.UNKNOWN_BACKEND_STARTUP_FAILURE,
        message="boom",
        detail={"inner": inner},
    )
    inner.append("mutated")
    assert failure.detail["inner"] == ["nested", "mutated"]
