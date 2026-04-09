"""
QuantMap — run_context.py

Lifecycle integration layer: orchestrates the characterization pipeline and
binds all environment data to a single, structured run context object.

This module is the bridge between the characterization subsystem and real
QuantMap runs. It calls each stage in order, merges their warnings, and
returns a single JSON-serializable dict that is ready to be attached to a run.

Public API:
    create_run_context(
        model_path=None,
        sample_duration_s=5.0,
        sample_interval_s=1.0,
    ) -> dict

    compute_run_context_confidence(
        baseline, sample_window, summary, assessment, capabilities, warnings
    ) -> dict

Dependency rule:
    Imports only from src.characterization and stdlib.
    Does not import from config.py or any other src/ module.
    Does not introduce CLI, reporting, or side effects.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from characterization import (
    assess_environment_quality,
    characterize_environment,
    get_characterization_capabilities,
    sample_environment_window,
    summarize_environment_samples,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Probe domain groupings
# ---------------------------------------------------------------------------
# These must stay in sync with get_characterization_capabilities() in
# characterization.py. They define which probes belong to which measurement
# domain for domain-level coverage analysis.

_PROBE_DOMAIN_CPU: frozenset[str] = frozenset({
    "cpu_brand", "cpu_architecture", "cpu_core_count", "cpu_percent", "cpu_freq",
})
_PROBE_DOMAIN_MEMORY: frozenset[str] = frozenset({
    "ram_stats", "swap_stats",
})
_PROBE_DOMAIN_GPU: frozenset[str] = frozenset({
    "pynvml_available", "gpu_name", "gpu_vram",
    "gpu_utilization", "gpu_mem_utilization",
    "gpu_temperature", "gpu_power", "gpu_graphics_clock", "gpu_mem_clock",
})
_PROBE_DOMAIN_DISK: frozenset[str] = frozenset({
    "disk_io_counters",
})

# Probe states that mean "this probe is expected on this machine."
# These contribute to both the coverage numerator (if supported) and
# the denominator (whether supported, unavailable, or failed).
#
# "unsupported_on_platform" and "not_implemented" are intentionally excluded:
# they represent probes that are not applicable to this machine or not yet
# implemented — their absence is not a coverage gap.
_IN_SCOPE_STATES: frozenset[str] = frozenset({
    "supported", "expected_unavailable", "probe_failed",
})


# ---------------------------------------------------------------------------
# Domain coverage helper
# ---------------------------------------------------------------------------

def _domain_coverage(probe_names: frozenset[str], caps: dict[str, Any]) -> dict[str, Any]:
    """
    Analyse coverage of a probe domain on this machine.

    Returns a dict with:
        status      — "complete" | "partial" | "absent" | "not_applicable"
        supported   — probe names that are working
        unavailable — probe names that are "unavailable_at_runtime"
        failed      — probe names that are "probe_failed"

    "not_applicable": all probes in this domain are unsupported_on_platform or
    not_implemented (i.e. not relevant for this machine type).

    "absent": all in-scope probes are either unavailable_at_runtime or
    probe_failed — none are working.

    "partial": at least one probe is working, but not all in-scope probes are.

    "complete": all in-scope probes are working.
    """
    in_scope:    list[str] = []
    supported:   list[str] = []
    unavailable: list[str] = []
    failed:      list[str] = []

    for probe in probe_names:
        state = caps.get(probe)
        if state in _IN_SCOPE_STATES:
            in_scope.append(probe)
            if state == "supported":
                supported.append(probe)
            elif state == "expected_unavailable":
                unavailable.append(probe)
            elif state == "probe_failed":
                failed.append(probe)
        # "unsupported_on_platform", "inapplicable", and "not_implemented" → not in in_scope

    n_in_scope  = len(in_scope)
    n_supported = len(supported)

    if n_in_scope == 0:
        status = "not_applicable"
    elif n_supported == n_in_scope:
        status = "complete"
    elif n_supported > 0:
        status = "partial"
    else:
        status = "absent"

    return {
        "status":      status,
        "supported":   supported,
        "unavailable": unavailable,
        "failed":      failed,
    }


# ---------------------------------------------------------------------------
# Public: compute_run_context_confidence
# ---------------------------------------------------------------------------

def compute_run_context_confidence(
    baseline:     dict[str, Any],
    sample_window: dict[str, Any],
    summary:      dict[str, Any],
    assessment:   dict[str, Any],
    capabilities: dict[str, Any],
    warnings:     list[str],
) -> dict[str, Any]:
    """
    Analyse how complete and trustworthy the RunContext observation is.

    This is a structured judgment — not a pass/fail gate — intended to let
    downstream consumers know how much weight to place on the environment
    quality assessment.

    Capability states are treated differently:
        "supported"                → probe worked; counts toward coverage
        "expected_unavailable"     → probe expected but software dependency failed;
                                     counts as a coverage penalty
        "probe_failed"             → probe should have worked, did not;
                                     counts as a coverage penalty and a failure
        "unsupported_on_platform"  → probe not applicable on this machine OS;
                                     excluded from coverage calculation entirely
        "inapplicable"             → probe not physically/logically applicable;
                                     recorded as missing, but excluded from coverage penalty
        "not_implemented"          → reserved; excluded from calculation

    This distinction matters: a machine with no NVIDIA GPU will have all GPU
    probes as "unavailable_at_runtime". That does not indicate failure — it
    indicates a hardware boundary. Confidence is not penalised for probes
    that are genuinely inapplicable.

    Args:
        baseline:     From characterize_environment().
        sample_window: From sample_environment_window().
        summary:      From summarize_environment_samples().
        assessment:   From assess_environment_quality().
        capabilities: From get_characterization_capabilities().
        warnings:     Top-level merged warnings from create_run_context().

    Returns:
        {
          "observation_completeness": str,  # "high" | "medium" | "low"
          "assessment_confidence":    str,  # "high" | "medium" | "low"
          "capability_coverage":      float,  # 0.0–1.0 (in-scope probes only)
          "available_probe_count":    int,
          "total_probe_count":        int,   # in-scope probes only
          "missing_capabilities":     list[str],  # unavailable_at_runtime
          "failed_probes":            list[str],  # probe_failed
          "confidence_reasons":       list[str],
        }

    Never raises.
    """
    caps = capabilities or {}

    # ------------------------------------------------------------------
    # 1. Probe state inventory
    # ------------------------------------------------------------------
    available_probes: list[str] = []
    unavailable_probes: list[str] = []
    inapplicable_probes: list[str] = []
    failed_probes:    list[str] = []
    in_scope_probes:  list[str] = []

    for probe, state in caps.items():
        if state in _IN_SCOPE_STATES:
            in_scope_probes.append(probe)
            if state == "supported":
                available_probes.append(probe)
            elif state == "expected_unavailable":
                unavailable_probes.append(probe)
            elif state == "probe_failed":
                failed_probes.append(probe)
        elif state == "inapplicable":
            inapplicable_probes.append(probe)

    available_probe_count = len(available_probes)
    total_probe_count     = len(in_scope_probes)
    n_failed              = len(failed_probes)
    
    capability_coverage   = (
        available_probe_count / total_probe_count
        if total_probe_count > 0 else 0.0
    )

    # ------------------------------------------------------------------
    # 2. Domain-level coverage
    # ------------------------------------------------------------------
    cpu_dom    = _domain_coverage(_PROBE_DOMAIN_CPU,    caps)
    memory_dom = _domain_coverage(_PROBE_DOMAIN_MEMORY, caps)
    gpu_dom    = _domain_coverage(_PROBE_DOMAIN_GPU,    caps)
    disk_dom   = _domain_coverage(_PROBE_DOMAIN_DISK,   caps)

    # ------------------------------------------------------------------
    # 3. Sample and summary signal inventory
    # ------------------------------------------------------------------
    samples      = sample_window.get("samples") or []
    sample_count = len(samples)

    stats = summary.get("stats")      or {}
    vol   = summary.get("volatility") or {}

    # CPU backbone: the two signals assessment most depends on for CPU quality
    cpu_backbone_present = (
        stats.get("max_cpu_percent") is not None
        and stats.get("avg_cpu_percent") is not None
    )
    # Memory backbone: minimum available RAM across window
    mem_backbone_present = stats.get("min_available_ram") is not None
    # CPU volatility: needed for cpu_volatile and cpu_freq_throttled reasons
    cpu_vol_present = vol.get("cpu_std_dev") is not None

    n_backbone_signals = sum([cpu_backbone_present, mem_backbone_present, cpu_vol_present])

    # Process data: check whether any sample contained process observations
    process_data_present = any(
        bool(s.get("process_details"))
        for s in samples
    )
    if not process_data_present:
        # Fallback: baseline background_load (from characterize_environment)
        bl_load = (baseline.get("background_load") or {})
        process_data_present = bool(
            bl_load.get("top_cpu_processes") or bl_load.get("top_mem_processes")
        )

    n_warnings = len(warnings)

    # ------------------------------------------------------------------
    # 4. Confidence reason strings
    # ------------------------------------------------------------------
    # Short machine-readable strings. Positive signals come before negative
    # so readers can quickly scan for the dominant factors.
    reasons: list[str] = []

    # CPU domain
    if cpu_dom["status"] == "complete":
        reasons.append("cpu_metrics_complete")
    elif cpu_dom["status"] == "partial":
        reasons.append("cpu_metrics_incomplete")
    elif cpu_dom["status"] == "absent":
        reasons.append("cpu_metrics_absent")
    # "not_applicable" for CPU is theoretically impossible — no reason added

    # Memory domain
    if memory_dom["status"] == "complete":
        reasons.append("memory_metrics_complete")
    elif memory_dom["status"] == "partial":
        reasons.append("memory_metrics_partial")
    # GPU domain — distinguish "unavailable" (no GPU/NVML) from "failed" (broken probes)
    if gpu_dom["status"] == "complete":
        reasons.append("gpu_metrics_complete")
    elif gpu_dom["status"] == "partial":
        if gpu_dom["failed"]:
            reasons.append("gpu_telemetry_incomplete")   # some probes actively failed
        # partial due only to unavailability → not a negative signal
    elif gpu_dom["status"] == "absent":
        if gpu_dom["unavailable"] and not gpu_dom["failed"]:
            # All GPU probes unavailable (expected telemetry missing)
            reasons.append("gpu_telemetry_unavailable")
        elif gpu_dom["failed"]:
            # All GPU probes that were expected failed outright.
            reasons.append("gpu_telemetry_failed")
    # "not_applicable" (all inapplicable or unsupported) → no reason added

    # Thermal — distinguish platform limitation from runtime failure
    cpu_temp_state = caps.get("cpu_temperature")
    if cpu_temp_state in ("expected_unavailable", "probe_failed"):
        # "expected_unavailable" on Linux/macOS means sensors not configured properly;
        # "probe_failed" means the probe threw an unexpected error.
        # "unsupported_on_platform" (Windows) is expected — no reason added.
        reasons.append("thermal_observation_unavailable")

    # Sampling adequacy
    if sample_count >= 3:
        reasons.append("sampling_window_populated")
    elif 1 <= sample_count < 3:
        reasons.append("sampling_window_sparse")
    else:
        reasons.append("no_samples_collected")

    # Process observability
    if process_data_present:
        reasons.append("process_data_present")
    else:
        reasons.append("process_data_absent")

    # Probe failures
    if n_failed >= 3:
        reasons.append("major_probe_failures")
    elif n_failed >= 1:
        reasons.append("probe_failures_present")

    # Assessment signal depth — flag if assessment had almost nothing to work with
    if n_backbone_signals == 0:
        reasons.append("assessment_built_from_limited_signals")

    # Warning surface
    if n_warnings <= 2:
        reasons.append("minimal_warnings")
    elif n_warnings >= 6:
        reasons.append("elevated_warning_count")

    # ------------------------------------------------------------------
    # 5. observation_completeness
    # ------------------------------------------------------------------
    # Measures how completely the environment was observed.
    #
    # "high":   Core domains (CPU, memory, disk) fully covered; adequate
    #           sampling; GPU either covered or absent due to unavailability
    #           (not failure); no more than one probe failure.
    #
    # "medium": Core domains at least partially covered; at least one sample
    #           collected; probe failures do not dominate.
    #
    # "low":    Core domain coverage is absent or severely degraded, or no
    #           samples were collected at all.
    #
    # GPU absence due to "inapplicable" is not penalised here:
    # machines without NVIDIA GPU monitoring still provide full CPU/memory/
    # disk visibility.

    core_complete = (
        cpu_dom["status"] == "complete"
        and memory_dom["status"] == "complete"
        and disk_dom["status"] == "complete"
    )
    core_present = (
        cpu_dom["status"] in ("complete", "partial")
        and memory_dom["status"] in ("complete", "partial")
    )

    # GPU is acceptable when: complete, not_applicable, or absent solely due to
    # unavailability (no NVML/GPU) — not due to probe failures.
    gpu_acceptable = (
        gpu_dom["status"] in ("complete", "not_applicable")
        or (gpu_dom["status"] in ("absent", "partial") and not gpu_dom["failed"])
    )

    if core_complete and gpu_acceptable and sample_count >= 3 and n_failed <= 1:
        observation_completeness = "high"
    elif core_present and sample_count >= 1 and n_failed <= 4:
        observation_completeness = "medium"
    else:
        observation_completeness = "low"

    # ------------------------------------------------------------------
    # 6. assessment_confidence
    # ------------------------------------------------------------------
    # Measures how trustworthy the environment_quality judgment is.
    #
    # "high":   CPU backbone metrics and memory metrics are both present;
    #           adequate sample count; low warning surface; observation
    #           completeness is not "low".
    #
    # "medium": At least one backbone signal (CPU or memory) present; at least
    #           one sample collected; observation completeness is not "low".
    #
    # "low":    Minimal signals — assessment may have been based on very little
    #           data or no samples at all.
    #
    # Note: GPU signal absence does not automatically lower assessment_confidence
    # when CPU and memory signals are present. A CPU/memory-focused benchmark
    # can still have a high-confidence environment assessment without GPU
    # telemetry.

    if (
        cpu_backbone_present
        and mem_backbone_present
        and sample_count >= 3
        and n_warnings <= 4
        and observation_completeness != "low"
    ):
        assessment_confidence = "high"
    elif (
        (cpu_backbone_present or mem_backbone_present)
        and sample_count >= 1
        and observation_completeness != "low"
    ):
        assessment_confidence = "medium"
    else:
        assessment_confidence = "low"

    return {
        "observation_completeness": observation_completeness,
        "assessment_confidence":    assessment_confidence,
        "capability_coverage":      round(capability_coverage, 3),
        "available_probe_count":    available_probe_count,
        "total_probe_count":        total_probe_count,
        "missing_capabilities":     unavailable_probes,   # expected_unavailable
        "inapplicable_capabilities": inapplicable_probes,  # inapplicable
        "failed_probes":            failed_probes,         # probe_failed
        "confidence_reasons":       reasons,
    }


# ---------------------------------------------------------------------------
# Public: create_run_context
# ---------------------------------------------------------------------------

def create_run_context(
    model_path: str | None = None,
    sample_duration_s: float = 5.0,
    sample_interval_s: float = 1.0,
) -> dict[str, Any]:
    """
    Capture a complete environment snapshot and return it as a run context.

    Runs each characterization stage in sequence:
        1. Baseline snapshot     (characterize_environment)
        2. Sample window         (sample_environment_window)
        3. Summary               (summarize_environment_samples)
        4. Quality assessment    (assess_environment_quality)
        5. Capability report     (get_characterization_capabilities)
        6. Confidence analysis   (compute_run_context_confidence)

    Warnings from every stage are collected and merged into a single top-level
    list, prefixed with the stage name so the source is always traceable.

    Args:
        model_path:        Path to the model file. Forwarded to
                           characterize_environment() for model size probing.
                           If None, QUANTMAP_MODEL_PATH is used as fallback.
        sample_duration_s: How long to run the environment sampling window.
        sample_interval_s: Target spacing between samples within the window.

    Returns:
        A JSON-serializable dict::

            {
              "timestamp":    str (ISO 8601 UTC, start of this function),

              "baseline":     dict from characterize_environment(),
              "sample_window": dict from sample_environment_window(),
              "summary":      dict from summarize_environment_samples(),
              "assessment":   dict from assess_environment_quality(),
              "capabilities": dict from get_characterization_capabilities(),
              "confidence":   dict from compute_run_context_confidence(),

              "meta": {
                "sample_duration_s": float,
                "sample_interval_s": float,
              },

              "warnings": [str, ...]   # merged from all stages
            }

    Never raises. Stage failures are recorded in warnings and the affected
    key is set to an empty dict so callers can always .get() safely.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    warnings: list[str] = []

    # ------------------------------------------------------------------
    # Stage 1: Baseline snapshot
    # ------------------------------------------------------------------
    baseline: dict[str, Any] = {}
    try:
        baseline = characterize_environment(model_path=model_path)
        for w in baseline.get("warnings") or []:
            warnings.append(f"baseline: {w}")
    except Exception as exc:
        warnings.append(f"baseline: stage failed — {exc}")
        logger.exception("create_run_context: characterize_environment failed")

    # ------------------------------------------------------------------
    # Stage 2: Sample window
    # ------------------------------------------------------------------
    sample_window: dict[str, Any] = {}
    try:
        sample_window = sample_environment_window(
            duration_s=sample_duration_s,
            interval_s=sample_interval_s,
        )
        for w in sample_window.get("warnings") or []:
            warnings.append(f"sample_window: {w}")
    except Exception as exc:
        warnings.append(f"sample_window: stage failed — {exc}")
        logger.exception("create_run_context: sample_environment_window failed")

    # ------------------------------------------------------------------
    # Stage 3: Summary
    # ------------------------------------------------------------------
    summary: dict[str, Any] = {}
    try:
        summary = summarize_environment_samples(
            sample_window.get("samples") or []
        )
        for w in summary.get("warnings") or []:
            warnings.append(f"summary: {w}")
    except Exception as exc:
        warnings.append(f"summary: stage failed — {exc}")
        logger.exception("create_run_context: summarize_environment_samples failed")

    # ------------------------------------------------------------------
    # Stage 4: Quality assessment
    # ------------------------------------------------------------------
    assessment: dict[str, Any] = {}
    try:
        assessment = assess_environment_quality(
            baseline=baseline,
            sample_window=sample_window,
            summary=summary,
        )
        for w in assessment.get("warnings") or []:
            warnings.append(f"assessment: {w}")
    except Exception as exc:
        warnings.append(f"assessment: stage failed — {exc}")
        logger.exception("create_run_context: assess_environment_quality failed")

    # ------------------------------------------------------------------
    # Stage 5: Capabilities
    # ------------------------------------------------------------------
    capabilities: dict[str, Any] = {}
    try:
        capabilities = get_characterization_capabilities()
    except Exception as exc:
        warnings.append(f"capabilities: stage failed — {exc}")
        logger.exception("create_run_context: get_characterization_capabilities failed")

    # ------------------------------------------------------------------
    # Stage 6: Confidence analysis
    # ------------------------------------------------------------------
    confidence: dict[str, Any] = {}
    try:
        confidence = compute_run_context_confidence(
            baseline=baseline,
            sample_window=sample_window,
            summary=summary,
            assessment=assessment,
            capabilities=capabilities,
            warnings=warnings,
        )
    except Exception as exc:
        warnings.append(f"confidence: stage failed — {exc}")
        logger.exception("create_run_context: compute_run_context_confidence failed")

    return {
        "timestamp":     timestamp,
        "baseline":      baseline,
        "sample_window": sample_window,
        "summary":       summary,
        "assessment":    assessment,
        "capabilities":  capabilities,
        "confidence":    confidence,
        "meta": {
            "sample_duration_s": sample_duration_s,
            "sample_interval_s": sample_interval_s,
        },
        "warnings": warnings,
    }
