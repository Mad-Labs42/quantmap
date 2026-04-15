"""QuantMap — run_plan.py

Resolved execution plan for a single QuantMap run.

RunPlan is the single source of truth for validate / dry-run / execution /
analysis / scoring / reporting.  Every significant decision about what gets
run, under what identity, in what mode, and with what schedule is captured
here once so downstream code never has to re-derive it.

Mode semantics:
  "full"     — complete campaign, all values, full intended schedule.
               Highest-confidence, recommendation-grade.
  "standard" — complete campaign, all values, reduced repetition (3 cycles).
               Development-grade: "we tested everything, not as deeply as Full."
               Triggered via --mode standard.
  "quick"    — complete campaign, all values, 1 cycle.
               Fastest complete-pass mode — broad but shallow.
               Useful for plumbing checks, bug-finding, first look.
               Lowest-confidence full-coverage mode.
               Triggered via --mode quick.
  "custom"   — user-directed exact scope.  User chose the values/shape;
               QuantMap preserves that intent without automatically narrowing.
               Honest about what was and was not tested.

This module has no imports from other QuantMap modules so both runner.py
and report.py can import it freely without circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------

# Cycle counts per mode.  Applied by runner.py when the corresponding mode flag
# is active and no --cycles CLI override is present.  Live here (not runner.py)
# so report.py can reference them without a circular import if ever needed.
STANDARD_CYCLES_PER_CONFIG: int = 3
QUICK_CYCLES_PER_CONFIG: int = 1


def resolve_run_mode(values_override: list | None, mode_flag: str | None = None) -> str:
    """Resolve the effective run mode for this execution.

      --mode quick                               →  "quick"
      --mode standard                            →  "standard"
      Any user-directed value subset (--values)  →  "custom"
      Full campaign (no narrowing overrides)      →  "full"

    Note: --mode and --values are mutually exclusive (enforced by CLI).
    """
    if mode_flag == "quick":
        return "quick"
    if mode_flag == "standard":
        return "standard"
    if values_override is not None:
        return "custom"
    return "full"


# Human-readable mode labels used in reports and console output.
MODE_LABELS: dict[str, str] = {
    "full":     "Full",
    "standard": "Standard",
    "quick":    "Quick",
    "custom":   "Custom",
}

# One-line mode descriptions for report headers.
MODE_DESCRIPTIONS: dict[str, str] = {
    "full":     "complete sweep — all campaign values — highest-confidence",
    "standard": "complete sweep — full value list — reduced repetition — development-grade",
    "quick":    "complete sweep — full value list — 1 cycle — fastest complete-pass mode",
    "custom":   "user-directed — exact scope — targeted run",
}


# ---------------------------------------------------------------------------
# RunPlan
# ---------------------------------------------------------------------------

@dataclass
class RunPlan:
    """Resolved execution plan for a single QuantMap run.

    Attributes:
    ----------
    parent_campaign_id : str
        The YAML campaign ID (e.g. "NGL_sweep").  Identifies the source
        campaign definition regardless of the effective run scope.

    effective_campaign_id : str
        The scoped DB/path identity for this run.  Equals parent_campaign_id
        for Full runs; is namespaced (e.g. "NGL_sweep__v30") for Custom runs
        so all DB rows, progress state, and report outputs are fully isolated.

    run_mode : str
        "custom" | "full" | "standard" | "quick"

    variable : str
        The campaign variable being swept.

    all_campaign_values : list
        Complete value list from the campaign YAML — the full search space.

    selected_values : list
        Values that will actually be tested in this run.  Equals
        all_campaign_values for Full, Standard, and Quick runs; is a subset for Custom.

    selected_configs : list[dict]
        The filtered list of config dicts to execute.

    cycles_per_config : int
        Effective number of cycles per config after all overrides resolve.

    requests_per_cycle : int
        Effective number of requests per cycle after all overrides resolve.

    baseline_path : Path
        Path to the baseline YAML in effect.

    effective_lab_root : Path
        Root directory for all outputs (DB, logs, results, state).

    db_path : Path
        Full path to lab.sqlite.

    state_file : Path
        Full path to progress.json.

    results_dir : Path
        Directory for results of this specific run
        (= effective_lab_root / "results" / effective_campaign_id).

    values_override : list | None
        Original --values argument as parsed, if provided.  Stored for audit.

    cycles_override : int | None
        Original --cycles CLI value, if provided.  Stored for audit.

    requests_per_cycle_override : int | None
        Original --requests-per-cycle CLI value, if provided.  Stored for audit.

    filter_overrides : dict | None
        Scoring filter threshold overrides applied for this run's mode.
        None means all ELIMINATION_FILTERS defaults are used.
        Custom mode injects {"min_valid_warm_count": 1} to avoid
        gate-keeping intentionally sparse targeted runs.
        Standard and Full use defaults unchanged.

    mode_flag : str | None
        Original --mode CLI value as passed by the user ("standard", "quick"),
        or None if mode was resolved implicitly (Full default or Custom via --values).
        Stored verbatim for audit trail.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    parent_campaign_id: str
    effective_campaign_id: str
    run_mode: str

    # ── Campaign scope ────────────────────────────────────────────────────────
    variable: str
    all_campaign_values: list
    selected_values: list
    selected_configs: list

    # ── Execution schedule ────────────────────────────────────────────────────
    cycles_per_config: int
    requests_per_cycle: int

    # ── Infrastructure paths (required — no defaults) ─────────────────────────
    baseline_path: Path
    effective_lab_root: Path
    db_path: Path
    state_file: Path
    results_dir: Path

    # ── Optional fields — defaults declared below this line ──────────────────
    # (Python dataclass rule: fields with defaults must follow fields without)

    # Scoring filter overrides for this run's mode.
    # None = use all ELIMINATION_FILTERS defaults unchanged.
    # Custom mode injects {"min_valid_warm_count": 1} to prevent gate-keeping
    # intentionally sparse targeted runs as "insufficient data".
    # Standard and Full use defaults unchanged.
    filter_overrides: dict | None = None

    # mode_flag stores the original --mode CLI value, if provided.
    # Stored for audit trail; None means mode was resolved implicitly (Full or Custom).
    mode_flag: str | None = None

    # Original user-provided CLI overrides — stored verbatim for audit trail.
    values_override: list | None = None
    cycles_override: int | None = None
    requests_per_cycle_override: int | None = None

    # ── Derived convenience properties ────────────────────────────────────────

    def to_snapshot_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of the effective run intent."""
        return {
            "parent_campaign_id": self.parent_campaign_id,
            "effective_campaign_id": self.effective_campaign_id,
            "run_mode": self.run_mode,
            "variable": self.variable,
            "all_campaign_values": self.all_campaign_values,
            "selected_values": self.selected_values,
            "selected_config_ids": [
                cfg.get("config_id") for cfg in self.selected_configs
            ],
            "cycles_per_config": self.cycles_per_config,
            "requests_per_cycle": self.requests_per_cycle,
            "baseline_path": str(self.baseline_path),
            "effective_lab_root": str(self.effective_lab_root),
            "db_path": str(self.db_path),
            "state_file": str(self.state_file),
            "results_dir": str(self.results_dir),
            "filter_overrides": self.filter_overrides,
            "mode_flag": self.mode_flag,
            "values_override": self.values_override,
            "cycles_override": self.cycles_override,
            "requests_per_cycle_override": self.requests_per_cycle_override,
        }

    @property
    def is_custom(self) -> bool:
        """True when the run mode is Custom."""
        return self.run_mode == "custom"

    @property
    def is_full(self) -> bool:
        """True when the run mode is Full."""
        return self.run_mode == "full"

    @property
    def is_standard(self) -> bool:
        """True when the run mode is Standard."""
        return self.run_mode == "standard"

    @property
    def is_quick(self) -> bool:
        """True when the run mode is Quick."""
        return self.run_mode == "quick"

    @property
    def mode_label(self) -> str:
        """Human-readable mode name (e.g. 'Custom')."""
        return MODE_LABELS.get(self.run_mode, self.run_mode.title())

    @property
    def mode_description(self) -> str:
        """One-line description of the mode for report headers."""
        return MODE_DESCRIPTIONS.get(self.run_mode, "")

    @property
    def untested_values(self) -> list:
        """Values from the full campaign that are NOT being tested in this run.
        Empty for Full, Standard, and Quick runs (all cover the full campaign value list).
        """
        selected_set = {str(v) for v in self.selected_values}
        return [v for v in self.all_campaign_values if str(v) not in selected_set]

    @property
    def coverage_fraction(self) -> float:
        """Fraction of campaign values covered by this run (0.0–1.0).
        1.0 for Full, Standard, and Quick runs; <1.0 for Custom runs.
        """
        if not self.all_campaign_values:
            return 1.0
        return len(self.selected_values) / len(self.all_campaign_values)

    @property
    def warm_samples_per_config(self) -> int:
        """Total warm request slots per config across all cycles.

        This counts all warm requests (i.e. requests_per_cycle − 1 cold per cycle),
        including the speed_medium warm request injected as the final slot of the
        final cycle.  This is therefore one higher than the warm speed_short count
        that analyze.py uses for valid_warm_request_count and TG statistics.

        Concrete values (requests_per_cycle=6):
          Full     (5 cycles): 5 × 5 = 25  [24 warm speed_short + 1 speed_medium]
          Standard (3 cycles): 3 × 5 = 15  [14 warm speed_short + 1 speed_medium]
          Quick    (1 cycle):  1 × 5 =  5  [ 4 warm speed_short + 1 speed_medium]
        """
        return self.cycles_per_config * (self.requests_per_cycle - 1)
