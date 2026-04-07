"""
QuantMap — run_plan.py

Resolved execution plan for a single QuantMap run.

RunPlan is the single source of truth for validate / dry-run / execution /
analysis / scoring / reporting.  Every significant decision about what gets
run, under what identity, in what mode, and with what schedule is captured
here once so downstream code never has to re-derive it.

Mode semantics:
  "full"   — complete campaign, all values, full intended schedule.
             Highest-confidence, recommendation-grade.
  "custom" — user-directed exact scope.  User chose the values/shape;
             QuantMap preserves that intent without automatically narrowing.
             Honest about what was and was not tested.

This module has no imports from other QuantMap modules so both runner.py
and report.py can import it freely without circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------

def resolve_run_mode(values_override: list | None) -> str:
    """
    Resolve the effective run mode for this execution.

      Any user-directed value subset (--values)  →  "custom"
      Full campaign (no narrowing overrides)      →  "full"
    """
    if values_override is not None:
        return "custom"
    return "full"


# Human-readable mode labels used in reports and console output.
MODE_LABELS: dict[str, str] = {
    "full":   "Full",
    "custom": "Custom",
}

# One-line mode descriptions for report headers.
MODE_DESCRIPTIONS: dict[str, str] = {
    "full":   "complete sweep — all campaign values — highest-confidence",
    "custom": "user-directed — exact scope — targeted run",
}


# ---------------------------------------------------------------------------
# RunPlan
# ---------------------------------------------------------------------------

@dataclass
class RunPlan:
    """
    Resolved execution plan for a single QuantMap run.

    Attributes
    ----------
    parent_campaign_id : str
        The YAML campaign ID (e.g. "NGL_sweep").  Identifies the source
        campaign definition regardless of the effective run scope.

    effective_campaign_id : str
        The scoped DB/path identity for this run.  Equals parent_campaign_id
        for Full runs; is namespaced (e.g. "NGL_sweep__v30") for Custom runs
        so all DB rows, progress state, and report outputs are fully isolated.

    run_mode : str
        "custom" | "full"

    variable : str
        The campaign variable being swept.

    all_campaign_values : list
        Complete value list from the campaign YAML — the full search space.

    selected_values : list
        Values that will actually be tested in this run.  Equals
        all_campaign_values for Full runs; is a subset for Custom.

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
    filter_overrides: dict | None = None

    # Original user-provided CLI overrides — stored verbatim for audit trail.
    values_override: list | None = None
    cycles_override: int | None = None
    requests_per_cycle_override: int | None = None

    # ── Derived convenience properties ────────────────────────────────────────

    @property
    def is_custom(self) -> bool:
        """True when the run mode is Custom."""
        return self.run_mode == "custom"

    @property
    def is_full(self) -> bool:
        """True when the run mode is Full."""
        return self.run_mode == "full"

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
        """
        Values from the full campaign that are NOT being tested in this run.
        Empty for Full runs.
        """
        selected_set = {str(v) for v in self.selected_values}
        return [v for v in self.all_campaign_values if str(v) not in selected_set]

    @property
    def coverage_fraction(self) -> float:
        """
        Fraction of campaign values covered by this run (0.0–1.0).
        1.0 for Full runs; <1.0 for Custom runs.
        """
        if not self.all_campaign_values:
            return 1.0
        return len(self.selected_values) / len(self.all_campaign_values)

    @property
    def warm_samples_per_config(self) -> int:
        """Total warm request count per config across all cycles."""
        return self.cycles_per_config * (self.requests_per_cycle - 1)
