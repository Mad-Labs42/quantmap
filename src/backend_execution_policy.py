"""Backend execution policy for platform boundary safety.

This module is intentionally narrow. It does not launch backends and does not
define a backend abstraction layer; it only rejects combinations that are known
to cross an unsafe execution boundary.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.execution_environment import SUPPORT_WSL_DEGRADED, classify_execution_environment

TARGET_WINDOWS_NATIVE = "windows_native_executable"
TARGET_LINUX_NATIVE = "linux_native_executable"
TARGET_UNKNOWN = "unknown"

DECISION_ALLOWED = "allowed"
DECISION_DISALLOWED = "disallowed"

REASON_WSL_WINDOWS_BACKEND_INTEROP = "wsl_windows_backend_interop_disallowed"


class BackendExecutionPolicyError(RuntimeError):
    """Raised when backend execution is blocked by a platform policy boundary."""

    def __init__(self, assessment: "BackendExecutionAssessment") -> None:
        """Initialize the policy from a backend name and optional allowed set."""
        self.assessment = assessment
        super().__init__(assessment.diagnostic)


@dataclass(frozen=True)
class BackendExecutionAssessment:
    execution_support_tier: str
    execution_platform: str
    backend_target_kind: str
    backend_path: str
    decision: str
    reason_code: str | None
    diagnostic: str
    remediation: str

    @property
    def allowed(self) -> bool:
        """Return True if the given backend is permitted by this policy."""
        return self.decision == DECISION_ALLOWED

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation of this policy."""
        return asdict(self)


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_WSL_MOUNT_RE = re.compile(r"^/mnt/[A-Za-z]/")


def classify_backend_target(path: Path | str) -> str:
    """Classify only obvious backend target shapes.

    The policy deliberately avoids deep binary inspection so it does not
    misclassify a real Linux executable. A `.exe` suffix is enough to identify a
    Windows-native backend for this pass.
    """
    raw = str(path).strip()
    lower = raw.lower()
    if lower.endswith(".exe"):
        return TARGET_WINDOWS_NATIVE
    if _WINDOWS_DRIVE_RE.match(raw) and lower.endswith(".exe"):
        return TARGET_WINDOWS_NATIVE
    if _WSL_MOUNT_RE.match(raw) and lower.endswith(".exe"):
        return TARGET_WINDOWS_NATIVE
    if raw:
        return TARGET_LINUX_NATIVE
    return TARGET_UNKNOWN


def assess_backend_execution(
    backend_path: Path | str,
    *,
    execution_environment: dict[str, Any] | None = None,
) -> BackendExecutionAssessment:
    """Assess whether the configured backend may run in the current environment."""
    env = execution_environment or classify_execution_environment().to_dict()
    support_tier = str(env.get("support_tier") or "unknown")
    execution_platform = str(env.get("execution_platform") or "unknown")
    backend_kind = classify_backend_target(backend_path)
    backend_path_text = str(backend_path)

    if support_tier == SUPPORT_WSL_DEGRADED and backend_kind == TARGET_WINDOWS_NATIVE:
        diagnostic = (
            "Backend execution blocked by WSL boundary policy.\n\n"
            f"QuantMap is running under WSL (`{SUPPORT_WSL_DEGRADED}`), but "
            f"QUANTMAP_SERVER_BIN points to a Windows-native backend: {backend_path_text}\n\n"
            "Windows `.exe` backend execution through WSL interop is not accepted "
            "as valid in-WSL measurement execution in this pass. The run is "
            "blocked before backend startup and HTTP readiness polling.\n\n"
            "This is a backend/platform policy issue, not a failure of WSL "
            "degraded telemetry readiness. Use a Linux-native backend path inside "
            "WSL, or run the campaign from Windows when using a Windows backend."
        )
        return BackendExecutionAssessment(
            execution_support_tier=support_tier,
            execution_platform=execution_platform,
            backend_target_kind=backend_kind,
            backend_path=backend_path_text,
            decision=DECISION_DISALLOWED,
            reason_code=REASON_WSL_WINDOWS_BACKEND_INTEROP,
            diagnostic=diagnostic,
            remediation=(
                "Use a Linux-native llama-server binary inside WSL, or run the "
                "campaign from Windows with the Windows backend."
            ),
        )

    return BackendExecutionAssessment(
        execution_support_tier=support_tier,
        execution_platform=execution_platform,
        backend_target_kind=backend_kind,
        backend_path=backend_path_text,
        decision=DECISION_ALLOWED,
        reason_code=None,
        diagnostic="Backend execution policy allowed.",
        remediation="",
    )


def assert_backend_execution_allowed(
    backend_path: Path | str,
    *,
    execution_environment: dict[str, Any] | None = None,
) -> BackendExecutionAssessment:
    """Return the assessment or raise if backend execution is disallowed."""
    assessment = assess_backend_execution(
        backend_path,
        execution_environment=execution_environment,
    )
    if not assessment.allowed:
        raise BackendExecutionPolicyError(assessment)
    return assessment
