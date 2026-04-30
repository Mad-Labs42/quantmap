from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Iterator

from src.backends import llamacpp
from src.backends.contracts import BackendFailure, BackendKind, BackendLaunchRequest, BackendSession


class BackendStartupError(RuntimeError):
    """Backend failed while entering startup/session context."""

    def __init__(self, failure: BackendFailure) -> None:
        self.failure = failure
        super().__init__(failure.message)


def classify_backend_startup_failure(
    exc: BaseException,
    *,
    backend_kind: BackendKind = BackendKind.LLAMACPP,
    log_path: Path | None = None,
) -> BackendFailure:
    if backend_kind is BackendKind.LLAMACPP:
        return llamacpp.classify_llamacpp_startup_failure(exc, log_path=log_path)
    raise ValueError(f"Unsupported backend kind: {backend_kind}")


@contextmanager
def start_backend_session(request: BackendLaunchRequest) -> Iterator[BackendSession]:
    if request.backend_kind is not BackendKind.LLAMACPP:
        raise ValueError(f"Unsupported backend kind: {request.backend_kind}")

    from src.settings_env import SettingsEnvError  # noqa: PLC0415

    with ExitStack() as stack:
        try:
            session = stack.enter_context(llamacpp.start_llamacpp_session(request))
        except SettingsEnvError:
            raise
        except Exception as exc:
            failure = classify_backend_startup_failure(
                exc,
                backend_kind=request.backend_kind,
                log_path=None,
            )
            raise BackendStartupError(failure) from exc

        yield session
