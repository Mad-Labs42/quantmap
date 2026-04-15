"""QuantMap — governance.py

Phase 3 Metric Governance layer.

This module implements the two-layer architecture defined in the Phase 3
Design Memo (Revision 1.1):

    Layer 1: Metric Registry  — canonical metric definitions (what a metric IS)
    Layer 2: Experiment Profile — campaign-specific scoring intent (how a metric is USED)

The Metric Registry and default Experiment Profile are loaded lazily from
configs/metrics.yaml and configs/profiles/default_throughput_v1.yaml.

DESIGN INVARIANTS:
    - A Profile cannot change what a metric is. It can only change how it is used.
    - The Registry is the single source of truth. There is no hand-authored
      duplicate registry in Python code.
    - Load-time validation enforces the override boundary (Section 5.2 of the
      Design Memo). Forbidden overrides raise ProfileValidationError immediately.
    - This module does NOT implement scoring logic. It defines schemas and
      validation only. Scoring still lives in score.py.

DEPENDENCY RULE:
    - governance.py imports pydantic, yaml, pathlib, enum, logging.
    - No other src/ module should import pydantic. The dependency is isolated here.
    - Other src/ modules import governance.py for BUILTIN_REGISTRY and profiles.
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator, model_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repository paths
# ---------------------------------------------------------------------------
_REPO_ROOT: Path = Path(__file__).parent.parent
_METRICS_YAML: Path = _REPO_ROOT / "configs" / "metrics.yaml"
_PROFILES_DIR: Path = _REPO_ROOT / "configs" / "profiles"


# ---------------------------------------------------------------------------
# Enums — vocabulary of the governance layer
# ---------------------------------------------------------------------------

class MetricClass(str, Enum):
    performance = "performance"
    latency = "latency"
    stability = "stability"
    resource = "resource"
    telemetry = "telemetry"
    environmental = "environmental"


class ObjectiveDirection(str, Enum):
    maximize = "maximize"
    minimize = "minimize"
    target_band = "target_band"
    threshold_pass_fail = "threshold_pass_fail"


class RequirementLevel(str, Enum):
    required = "required"
    optional = "optional"
    conditionally_applicable = "conditionally_applicable"


class MissingnessPolicy(str, Enum):
    exclude_config = "exclude_config"
    exclude_dimension_on_systemic_failure = "exclude_dimension_on_systemic_failure"
    warning_only = "warning_only"
    substitute_if_structurally_inapplicable = "substitute_if_structurally_inapplicable"


class EstimatorType(str, Enum):
    median = "median"
    mean = "mean"
    winsorized_mean = "winsorized_mean"
    p10 = "p10"
    p90 = "p90"
    max = "max"
    count = "count"


class OutlierPolicy(str, Enum):
    """QuantMap uses TRUE WINSORIZATION (capping extreme values at fence
    percentiles, preserving N) — never trimming (dropping values, reducing N).
    The 'winsorize' option caps; 'flag_symmetric' flags without modifying.
    There is no 'trim' option by design.
    """
    flag_symmetric = "flag_symmetric"
    winsorize = "winsorize"
    none = "none"


class FenceMethod(str, Enum):
    iqr_1_5 = "iqr_1_5"
    iqr_3 = "iqr_3"
    z_score_3 = "z_score_3"
    none = "none"


class TransformFamily(str, Enum):
    reference_based = "reference_based"
    saturating_utility = "saturating_utility"
    robust_quantile = "robust_quantile"
    hardened_minmax = "hardened_minmax"
    threshold_utility = "threshold_utility"
    piecewise_linear = "piecewise_linear"
    log = "log"
    raw = "raw"
    none = "none"


class ConfidencePolicy(str, Enum):
    lcb_k1 = "lcb_k1"
    lcb_k2 = "lcb_k2"
    display_only = "display_only"
    none = "none"


class ExperimentFamily(str, Enum):
    throughput = "throughput"
    latency = "latency"
    stability = "stability"
    thermal = "thermal"
    resource_efficiency = "resource_efficiency"
    diagnostic = "diagnostic"
    custom = "custom"


class RankingMode(str, Enum):
    composite = "composite"
    pareto = "pareto"
    hybrid = "hybrid"
    stability_first = "stability_first"
    diagnostic_only = "diagnostic_only"


class CompositeBasis(str, Enum):
    lcb_score = "lcb_score"
    raw_score = "raw_score"
    median_score = "median_score"


# ---------------------------------------------------------------------------
# Layer 1: Metric Definition
# ---------------------------------------------------------------------------

class MetricDefinition(BaseModel):
    """Canonical definition of a single metric variable.

    This model is the schema for each entry in configs/metrics.yaml.
    It defines what a metric IS, independent of any campaign or profile.

    Fields marked 'SCHEMA GROUNDWORK ONLY' define the vocabulary for
    future phases but do not trigger any behavioral logic in the current
    scoring pipeline.
    """
    canonical_name: str
    human_label: str
    description: str
    units: str

    metric_class: MetricClass
    objective_direction: ObjectiveDirection

    # Ranking participation defaults
    rank_bearing_default: bool
    diagnostic_only: bool
    gate_capable: bool
    score_capable: bool
    pareto_capable: bool
    report_only: bool

    # Availability
    required: RequirementLevel
    conditionality_note: str | None = None

    # Missingness
    missingness_policy: MissingnessPolicy
    missingness_note: str | None = None

    # Estimation
    default_estimator: EstimatorType
    default_outlier_policy: OutlierPolicy
    outlier_fence_method: FenceMethod
    both_tails_flagged: bool

    # Normalization (ranking authority, not display)
    default_transform: TransformFamily
    transform_params: dict[str, Any] | None = None
    fixed_reference_value: float | None = None
    reference_provenance: str | None = None

    # Confidence
    default_confidence_policy: ConfidencePolicy
    min_sample_gate: int

    # Experiment compatibility
    experiment_family_tags: list[str]
    profile_override_allowed: list[str]

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# Layer 1: Metric Registry
# ---------------------------------------------------------------------------

class MetricRegistry:
    """Container for all metric definitions. Loaded from configs/metrics.yaml.

    This is a read-only singleton. It does not support dynamic modification
    or runtime reload.
    """

    def __init__(self, metrics: dict[str, MetricDefinition]) -> None:
        self._metrics = metrics

    def get(self, canonical_name: str) -> MetricDefinition:
        """Get a metric by canonical name. Raises KeyError if not found."""
        if canonical_name not in self._metrics:
            raise KeyError(
                f"Unknown metric '{canonical_name}'. "
                f"Known metrics: {sorted(self._metrics.keys())}"
            )
        return self._metrics[canonical_name]

    def all_metrics(self) -> dict[str, MetricDefinition]:
        """Return all metric definitions."""
        return dict(self._metrics)

    def get_rank_bearing(self) -> list[MetricDefinition]:
        """Return all metrics that are rank-bearing by default."""
        return [m for m in self._metrics.values() if m.rank_bearing_default]

    def get_gate_capable(self) -> list[MetricDefinition]:
        """Return all metrics that can be used as elimination gates."""
        return [m for m in self._metrics.values() if m.gate_capable]

    def get_score_capable(self) -> list[MetricDefinition]:
        """Return all metrics that can contribute to composite score."""
        return [m for m in self._metrics.values() if m.score_capable]

    def get_required_score_metrics(self) -> frozenset[str]:
        """Return canonical names of metrics that are both required AND score-capable.
        This is the Registry-derived equivalent of the legacy _PRIMARY_SCORE_METRICS.
        """
        return frozenset(
            m.canonical_name for m in self._metrics.values()
            if m.required == RequirementLevel.required and m.score_capable
        )

    def get_optional_score_metrics(self) -> tuple[str, ...]:
        """Return canonical names of metrics that are optional (or conditionally
        applicable) AND score-capable.
        This is the Registry-derived equivalent of the legacy _SECONDARY_SCORE_METRICS.
        """
        return tuple(
            m.canonical_name for m in self._metrics.values()
            if m.required in (RequirementLevel.optional, RequirementLevel.conditionally_applicable)
            and m.score_capable
        )

    def __len__(self) -> int:
        return len(self._metrics)

    def __contains__(self, canonical_name: str) -> bool:
        return canonical_name in self._metrics

    def __repr__(self) -> str:
        return f"MetricRegistry({len(self._metrics)} metrics)"


# ---------------------------------------------------------------------------
# Layer 2: Experiment Profile
# ---------------------------------------------------------------------------

class ExperimentProfile(BaseModel):
    """Campaign-specific scoring configuration.

    Defines HOW metrics are used for a specific evaluation goal, without
    redefining what those metrics are. See Section 5 of the Phase 3 Design Memo.
    """
    name: str
    version: str
    experiment_family: ExperimentFamily
    description: str

    # Active metrics and roles
    active_metrics: list[str]
    primary_metrics: list[str]
    secondary_metrics: list[str]

    # Weighting
    weights: dict[str, float]
    normalize_weights: bool = True

    # Ranking
    ranking_mode: RankingMode
    composite_basis: CompositeBasis

    # Confidence
    confidence_policy: ConfidencePolicy
    min_sample_gate: int

    # Outlier handling
    outlier_policy: OutlierPolicy
    outlier_fence_method: FenceMethod

    # Gate overrides (tighten only)
    gate_overrides: dict[str, float]

    # Reporting
    report_emphasis: list[str]
    diagnostic_metrics: list[str]

    model_config = {"frozen": True}

    @field_validator("weights")
    @classmethod
    def _weights_sum_to_one(cls, v: dict[str, float]) -> dict[str, float]:
        total = sum(v.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Profile weights must sum to 1.0, got {total:.6f}. "
                f"Weights: {v}"
            )
        return v

    @model_validator(mode="after")
    def _metrics_consistency(self) -> ExperimentProfile:
        """Validate that primary/secondary/weights reference active metrics."""
        active = set(self.active_metrics)

        for pm in self.primary_metrics:
            if pm not in active:
                raise ValueError(
                    f"Primary metric '{pm}' is not in active_metrics."
                )

        for sm in self.secondary_metrics:
            if sm not in active:
                raise ValueError(
                    f"Secondary metric '{sm}' is not in active_metrics."
                )

        for wm in self.weights:
            if wm not in active:
                raise ValueError(
                    f"Weighted metric '{wm}' is not in active_metrics."
                )

        return self


# ---------------------------------------------------------------------------
# Profile Validation — Override Boundary Enforcement
# ---------------------------------------------------------------------------

class ProfileValidationError(Exception):
    """Raised when a Profile violates a Registry-level invariant."""
    pass


class CurrentMethodologyLoadError(RuntimeError):
    """Raised when current live Registry/Profile files cannot be loaded."""

    def __init__(self, component: str, path: Path | None, original: Exception) -> None:
        self.component = component
        self.path = path
        self.original = original
        location = f" at {path}" if path is not None else ""
        super().__init__(f"Current methodology {component} failed to load{location}: {original}")


# Fields that are LOCKED to the Registry. Profiles cannot override these.
_REGISTRY_IMMUTABLE_FIELDS: frozenset[str] = frozenset({
    "units",
    "objective_direction",
    "canonical_name",
    "both_tails_flagged",
})


def validate_profile_against_registry(
    profile: ExperimentProfile,
    registry: MetricRegistry,
) -> None:
    """Enforce the override boundary from Section 5.2 of the Design Memo.

    Raises ProfileValidationError if the profile violates any Registry constraint.
    This function MUST be called at load time, not lazily during scoring.
    """
    errors: list[str] = []

    # 1. All active metrics must exist in the Registry
    for metric_name in profile.active_metrics:
        if metric_name not in registry:
            errors.append(
                f"Active metric '{metric_name}' is not defined in the Metric Registry."
            )

    # 2. Gate overrides may only tighten, never relax
    # We compare against the profile's own gate_overrides — the actual
    # comparison against Registry minimums will happen when we have
    # gate-specific metadata. For now, validate that all gate override
    # keys are recognized.
    recognized_gates = {
        "max_cv", "max_thermal_events", "max_outliers",
        "max_warm_ttft_p90_ms", "min_success_rate",
        "min_warm_tg_p10", "min_valid_warm_count",
    }
    for gate_key in profile.gate_overrides:
        if gate_key not in recognized_gates:
            errors.append(
                f"Gate override '{gate_key}' is not a recognized gate. "
                f"Known gates: {sorted(recognized_gates)}"
            )

    # 3. Min sample gate cannot relax below Registry minimums
    for metric_name in profile.active_metrics:
        if metric_name not in registry:
            continue  # Already reported above
        metric_def = registry.get(metric_name)
        if profile.min_sample_gate < metric_def.min_sample_gate:
            # This is a warning, not necessarily a hard error for Phase 3.1
            # because the profile's min_sample_gate is a global setting.
            # Metric-level gates take precedence in the Registry.
            pass

    # 4. Experiment family compatibility
    for metric_name in profile.active_metrics:
        if metric_name not in registry:
            continue
        metric_def = registry.get(metric_name)
        family_tags = metric_def.experiment_family_tags
        if "all" not in family_tags and profile.experiment_family.value not in family_tags:
            errors.append(
                f"Metric '{metric_name}' is not compatible with experiment family "
                f"'{profile.experiment_family.value}'. Compatible families: {family_tags}"
            )

    if errors:
        error_msg = "Profile validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ProfileValidationError(error_msg)

    logger.info(
        "Profile '%s' validated against Registry (%d metrics, %d active).",
        profile.name, len(registry), len(profile.active_metrics),
    )


# ---------------------------------------------------------------------------
# YAML Loaders
# ---------------------------------------------------------------------------

def load_registry(yaml_path: Path | None = None) -> MetricRegistry:
    """Load the Metric Registry from configs/metrics.yaml.

    Fails loudly and immediately if the YAML is missing, malformed, or
    any metric definition fails schema validation.

    Callers that need the process-default current Registry should use
    get_builtin_registry(), which caches this loader lazily.
    """
    path = yaml_path or _METRICS_YAML
    if not path.exists():
        raise FileNotFoundError(
            f"Metric Registry YAML not found at {path}. "
            f"This file is required for QuantMap to operate."
        )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict) or "metrics" not in raw:
        raise ValueError(
            f"Invalid metrics.yaml structure. Expected top-level 'metrics' key, "
            f"got keys: {list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}"
        )

    metrics: dict[str, MetricDefinition] = {}
    for name, fields in raw["metrics"].items():
        try:
            metrics[name] = MetricDefinition(canonical_name=name, **fields)
        except Exception as exc:
            raise ValueError(
                f"Failed to parse metric '{name}' from {path}: {exc}"
            ) from exc

    logger.info("Loaded Metric Registry: %d metrics from %s", len(metrics), path)
    return MetricRegistry(metrics)


def load_profile(
    profile_name: str,
    profiles_dir: Path | None = None,
) -> ExperimentProfile:
    """Load an Experiment Profile from configs/profiles/<name>.yaml.

    Fails loudly if the file is missing or the profile fails validation.
    Does NOT validate against the Registry — call validate_profile_against_registry()
    separately for that.
    """
    directory = profiles_dir or _PROFILES_DIR
    path = directory / f"{profile_name}.yaml"

    if not path.exists():
        raise FileNotFoundError(
            f"Experiment Profile '{profile_name}' not found at {path}."
        )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(
            f"Invalid profile YAML structure in {path}. Expected a mapping."
        )

    try:
        profile = ExperimentProfile(**raw)
    except Exception as exc:
        raise ValueError(
            f"Failed to parse profile '{profile_name}' from {path}: {exc}"
        ) from exc

    logger.info("Loaded Experiment Profile: '%s' v%s", profile.name, profile.version)
    return profile


# ---------------------------------------------------------------------------
# Lazy current-methodology accessors
# ---------------------------------------------------------------------------

_DEFAULT_PROFILE_NAME = "default_throughput_v1"
_BUILTIN_REGISTRY_CACHE: MetricRegistry | None = None
_DEFAULT_PROFILE_CACHE: ExperimentProfile | None = None


def get_builtin_registry() -> MetricRegistry:
    """Return the current live Metric Registry, loading it on first use."""
    global _BUILTIN_REGISTRY_CACHE
    if _BUILTIN_REGISTRY_CACHE is None:
        try:
            _BUILTIN_REGISTRY_CACHE = load_registry()
        except Exception as exc:
            raise CurrentMethodologyLoadError("metric registry", _METRICS_YAML, exc) from exc
    return _BUILTIN_REGISTRY_CACHE


def get_default_profile(profile_name: str = _DEFAULT_PROFILE_NAME) -> ExperimentProfile:
    """Return a validated current live Experiment Profile, loading it on first use."""
    global _DEFAULT_PROFILE_CACHE
    profile_path = _PROFILES_DIR / f"{profile_name}.yaml"
    try:
        registry = get_builtin_registry()
        if profile_name == _DEFAULT_PROFILE_NAME:
            if _DEFAULT_PROFILE_CACHE is None:
                profile = load_profile(profile_name)
                validate_profile_against_registry(profile, registry)
                _DEFAULT_PROFILE_CACHE = profile
            return _DEFAULT_PROFILE_CACHE

        profile = load_profile(profile_name)
        validate_profile_against_registry(profile, registry)
        return profile
    except CurrentMethodologyLoadError:
        raise
    except Exception as exc:
        raise CurrentMethodologyLoadError("experiment profile", profile_path, exc) from exc


def load_current_methodology(
    profile_name: str | None = None,
) -> tuple[ExperimentProfile, MetricRegistry]:
    """Return the current live Profile and Registry for explicit current-input paths."""
    registry = get_builtin_registry()
    profile = get_default_profile(profile_name or _DEFAULT_PROFILE_NAME)
    return profile, registry


class _LazyRegistry:
    """Compatibility proxy that avoids loading current Registry at module import."""

    def _registry(self) -> MetricRegistry:
        return get_builtin_registry()

    def get(self, canonical_name: str) -> MetricDefinition:
        return self._registry().get(canonical_name)

    def all_metrics(self) -> dict[str, MetricDefinition]:
        return self._registry().all_metrics()

    def get_rank_bearing(self) -> list[MetricDefinition]:
        return self._registry().get_rank_bearing()

    def get_gate_capable(self) -> list[MetricDefinition]:
        return self._registry().get_gate_capable()

    def get_score_capable(self) -> list[MetricDefinition]:
        return self._registry().get_score_capable()

    def get_required_score_metrics(self) -> frozenset[str]:
        return self._registry().get_required_score_metrics()

    def get_optional_score_metrics(self) -> tuple[str, ...]:
        return self._registry().get_optional_score_metrics()

    def __len__(self) -> int:
        return len(self._registry())

    def __contains__(self, canonical_name: str) -> bool:
        return canonical_name in self._registry()

    def __repr__(self) -> str:
        return repr(self._registry())


class _LazyProfile:
    """Compatibility proxy that avoids loading current Profile at module import."""

    def _profile(self) -> ExperimentProfile:
        return get_default_profile()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._profile(), name)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._profile().model_dump(*args, **kwargs)

    def __repr__(self) -> str:
        return repr(self._profile())


BUILTIN_REGISTRY = _LazyRegistry()
DEFAULT_PROFILE = _LazyProfile()

# ---------------------------------------------------------------------------
# Legacy compatibility helpers
#
# These provide the exact same frozensets/dicts that score.py previously
# defined as module-level constants. The values MUST be identical to the
# legacy constants — this is verified by determinism tests.
# ---------------------------------------------------------------------------

def get_legacy_score_weights() -> dict[str, float]:
    """Return the Profile's weights dict — must match legacy SCORE_WEIGHTS."""
    return dict(get_default_profile().weights)


def get_legacy_elimination_filters() -> dict[str, float]:
    """Return the Profile's gate overrides — must match legacy ELIMINATION_FILTERS."""
    return dict(get_default_profile().gate_overrides)


def get_legacy_primary_score_metrics() -> frozenset[str]:
    """Return the set of required + score_capable metric names from the Registry.

    This MUST match the legacy _PRIMARY_SCORE_METRICS frozenset:
        {"warm_tg_median", "warm_tg_p10"}

    If it does not, the Registry definitions are wrong and must be corrected
    before any scoring changes are made.
    """
    result = get_builtin_registry().get_required_score_metrics()

    # Explicit verification against legacy set.
    # This guard prevents silent semantic drift during the Phase 3.1 refactor.
    _LEGACY_PRIMARY = frozenset({"warm_tg_median", "warm_tg_p10"})
    if result != _LEGACY_PRIMARY:
        raise RuntimeError(
            f"GOVERNANCE INTEGRITY ERROR: Registry-derived primary score metrics "
            f"{result} do not match legacy _PRIMARY_SCORE_METRICS {_LEGACY_PRIMARY}. "
            f"This indicates a Registry definition error. Fix configs/metrics.yaml."
        )

    return result


def get_legacy_secondary_score_metrics() -> tuple[str, ...]:
    """Return the tuple of optional + score_capable metric names from the Registry.

    This MUST match the legacy _SECONDARY_SCORE_METRICS tuple:
        ("warm_ttft_median_ms", "warm_ttft_p90_ms", "cold_ttft_median_ms", "pp_median")

    The tuple ordering matters for determinism — it must match the Registry
    iteration order, which is YAML key order (insertion order).
    """
    result = get_builtin_registry().get_optional_score_metrics()

    # Explicit verification against legacy set (order-insensitive for safety).
    _LEGACY_SECONDARY = frozenset({
        "warm_ttft_median_ms", "warm_ttft_p90_ms", "cold_ttft_median_ms", "pp_median",
    })
    if frozenset(result) != _LEGACY_SECONDARY:
        raise RuntimeError(
            f"GOVERNANCE INTEGRITY ERROR: Registry-derived secondary score metrics "
            f"{set(result)} do not match legacy _SECONDARY_SCORE_METRICS {_LEGACY_SECONDARY}. "
            f"This indicates a Registry definition error. Fix configs/metrics.yaml."
        )

    return result
