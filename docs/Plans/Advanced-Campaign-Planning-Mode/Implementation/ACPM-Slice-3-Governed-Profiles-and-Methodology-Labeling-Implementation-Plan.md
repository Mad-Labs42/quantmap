# ACPM Slice 3: Governed Profiles and Methodology Labeling — Implementation Plan

Date: 2026-04-23
Branch: bughunt/phase-1-baseline
Precursor: ACPM-Slice-3-Governed-Profiles-and-Methodology-Labeling-PREP-Implementation-Plan.md

---

## Source-Inspection Findings That Refine the PRE Plan

Two gaps found during this planning turn that the PRE plan did not capture:

1. **`ExperimentProfile` has a required `description: str` field** (line 304 of `src/governance.py`). The PRE plan's shared-fields table omits it. All three YAML files must include a `description` block or Pydantic will reject them at parse time.

2. **Registry-loading function name is `load_registry()`**, not `load_metric_registry()`. Exact import: `from src.governance import load_profile, load_registry, validate_profile_against_registry`.

Everything else in the PRE plan is confirmed correct.

---

## 1. Exact Touched Files

### New files

| File | Purpose |
|---|---|
| `configs/profiles/acpm_balanced_v1.yaml` | Governed ExperimentProfile for Balanced ACPM lens |
| `configs/profiles/acpm_ts_v1.yaml` | Governed ExperimentProfile for T/S (Throughput/Speed) lens |
| `configs/profiles/acpm_ttft_v1.yaml` | Governed ExperimentProfile for TTFT (latency) lens |
| `test_acpm_slice3.py` | 16-test validation suite for Slice 3 |

### Edited files

| File | Scope |
|---|---|
| `src/acpm_planning.py` | Additive only: one `import`, two constants, two functions, one validation hunk in `ACPMPlanningMetadata.__post_init__` |

### Intentionally no-touch (deferred)

| File | Reason |
|---|---|
| `src/runner.py` | Profile wiring into execution — Slice 4 |
| `src/score.py` | Profile wiring into scoring — Slice 4 |
| `src/report.py` | ACPM lens disclosure — Slice 6 |
| `src/report_campaign.py` | ACPM methodology section — Slice 6 |
| `src/explain.py` | Profile lens statement — Slice 6 |
| `src/export.py` | Planner block — Slice 6 |
| `src/compare.py` / `src/audit_methodology.py` | Profile-weight-aware grading — Slice 6 |
| `src/governance.py` | Must not grow ACPM-specific content |
| `src/db.py` | No schema changes in this slice |
| `src/trust_identity.py` | Already flows profile_name via methodology seam; no changes needed |

---

## 2. Per-File Edit Plan

### `src/acpm_planning.py`

**Import to add** (after existing `from typing import Any`):

```python
from pathlib import Path
```

**Constants to add** (after `_FORBIDDEN_PLANNING_METADATA_KEYS`, before `_reject_shadow_truth_fields`):

```python
V1_ACPM_PROFILE_IDS: frozenset[str] = frozenset({"Balanced", "T/S", "TTFT"})

_ACPM_PROFILE_REGISTRY: dict[str, dict[str, str]] = {
    "Balanced": {
        "scoring_profile_name": "acpm_balanced_v1",
        "display_label": "Balanced",
        "display_name": "Balanced",
        "lens_description": (
            "Mixed practical recommendation lens. "
            "Ranking balances throughput and latency."
        ),
    },
    "T/S": {
        "scoring_profile_name": "acpm_ts_v1",
        "display_label": "T/S (Throughput/Speed)",
        "display_name": "Throughput/Speed (T/S)",
        "lens_description": (
            "Throughput-biased lens. "
            "Prioritizes sustained token generation rate and floor."
        ),
    },
    "TTFT": {
        "scoring_profile_name": "acpm_ttft_v1",
        "display_label": "TTFT",
        "display_name": "Time-to-First-Token (TTFT)",
        "lens_description": (
            "Latency-biased lens. "
            "Prioritizes warm and cold first-token responsiveness."
        ),
    },
}
```

**Functions to add** (after `_ACPM_PROFILE_REGISTRY`, before `_reject_shadow_truth_fields`):

```python
def get_acpm_profile_info(profile_id: str) -> dict[str, str]:
    if profile_id not in _ACPM_PROFILE_REGISTRY:
        raise ValueError(
            f"Unknown ACPM profile ID {profile_id!r}. "
            f"Valid IDs: {sorted(V1_ACPM_PROFILE_IDS)}"
        )
    return _ACPM_PROFILE_REGISTRY[profile_id]


def load_acpm_scoring_profile(
    profile_id: str,
    profiles_dir: Path | None = None,
) -> Any:
    from src.governance import load_profile, load_registry, validate_profile_against_registry
    info = get_acpm_profile_info(profile_id)
    profile = load_profile(info["scoring_profile_name"], profiles_dir=profiles_dir)
    registry = load_registry()
    validate_profile_against_registry(profile, registry)
    return profile
```

Return type is `Any` — governance import is lazy to guard against any future circular import chain. The implementation turn may upgrade to `TYPE_CHECKING` import of `ExperimentProfile` if circular-import analysis confirms safety. Document this decision in a one-line comment if upgraded.

**Existing symbol to modify — `ACPMPlanningMetadata.__post_init__`:**

Add after the existing `for field_name in (...): if not getattr(...)` block and before `_reject_shadow_truth_fields(self.narrowing_steps)`:

```python
if self.profile_name not in V1_ACPM_PROFILE_IDS:
    raise ValueError(
        f"profile_name must be one of {sorted(V1_ACPM_PROFILE_IDS)}, "
        f"got {self.profile_name!r}"
    )
```

---

## 3. Concrete YAML Plan

`ExperimentProfile` (confirmed from `src/governance.py` lines 294–334) requires all of:
`name`, `version`, `experiment_family`, `description`, `active_metrics`, `primary_metrics`, `secondary_metrics`, `weights`, `ranking_mode`, `composite_basis`, `confidence_policy`, `min_sample_gate`, `outlier_policy`, `outlier_fence_method`, `gate_overrides`, `report_emphasis`, `diagnostic_metrics`.

`normalize_weights` is optional (defaults to `True`) but should be explicit for readability.

### Shared fields (identical across all three profiles)

```yaml
version: "1.0.0"
experiment_family: throughput

active_metrics:
  - warm_tg_median
  - warm_tg_p10
  - warm_ttft_median_ms
  - warm_ttft_p90_ms
  - cold_ttft_median_ms
  - pp_median

normalize_weights: true
ranking_mode: composite
composite_basis: lcb_score
confidence_policy: lcb_k1
min_sample_gate: 10
outlier_policy: flag_symmetric
outlier_fence_method: iqr_1_5

gate_overrides:                   # identical to default_throughput_v1 — no profile-specific gates in v1
  max_cv: 0.05
  max_thermal_events: 0
  max_outliers: 3
  max_warm_ttft_p90_ms: 500.0
  min_success_rate: 0.90
  min_warm_tg_p10: 7.0
  min_valid_warm_count: 3

diagnostic_metrics:
  - warm_tg_cv
  - thermal_events
  - success_rate
  - outlier_count
```

### `configs/profiles/acpm_balanced_v1.yaml` — full file

```yaml
# QuantMap — Experiment Profile: acpm_balanced_v1
# ACPM Balanced lens. Mixed practical recommendation; balances throughput and latency.
# IMPORTANT: Changing values in this file changes scoring behavior.

name: acpm_balanced_v1
version: "1.0.0"
experiment_family: throughput
description: >
  ACPM Balanced profile. Mixed practical recommendation lens that balances
  throughput and latency. Use when no strong preference for either dimension.

active_metrics:
  - warm_tg_median
  - warm_tg_p10
  - warm_ttft_median_ms
  - warm_ttft_p90_ms
  - cold_ttft_median_ms
  - pp_median

primary_metrics:
  - warm_tg_median
  - warm_tg_p10

secondary_metrics:
  - warm_ttft_median_ms
  - warm_ttft_p90_ms
  - cold_ttft_median_ms
  - pp_median

weights:
  warm_tg_median: 0.25
  warm_tg_p10: 0.15
  warm_ttft_median_ms: 0.35
  warm_ttft_p90_ms: 0.00
  cold_ttft_median_ms: 0.20
  pp_median: 0.05

normalize_weights: true
ranking_mode: composite
composite_basis: lcb_score
confidence_policy: lcb_k1
min_sample_gate: 10
outlier_policy: flag_symmetric
outlier_fence_method: iqr_1_5

gate_overrides:
  max_cv: 0.05
  max_thermal_events: 0
  max_outliers: 3
  max_warm_ttft_p90_ms: 500.0
  min_success_rate: 0.90
  min_warm_tg_p10: 7.0
  min_valid_warm_count: 3

report_emphasis:
  - warm_tg_median
  - warm_ttft_median_ms
  - warm_tg_p10

diagnostic_metrics:
  - warm_tg_cv
  - thermal_events
  - success_rate
  - outlier_count
```

### `configs/profiles/acpm_ts_v1.yaml` — full file

```yaml
# QuantMap — Experiment Profile: acpm_ts_v1
# ACPM Throughput/Speed (T/S) lens. Throughput-biased; prioritizes TG rate and floor.
# IMPORTANT: Changing values in this file changes scoring behavior.

name: acpm_ts_v1
version: "1.0.0"
experiment_family: throughput
description: >
  ACPM Throughput/Speed (T/S) profile. Throughput-biased recommendation lens.
  Prioritizes sustained token generation rate and consistency floor.
  Use when maximizing tokens-per-second is the primary goal.

active_metrics:
  - warm_tg_median
  - warm_tg_p10
  - warm_ttft_median_ms
  - warm_ttft_p90_ms
  - cold_ttft_median_ms
  - pp_median

primary_metrics:
  - warm_tg_median
  - warm_tg_p10

secondary_metrics:
  - warm_ttft_median_ms
  - warm_ttft_p90_ms
  - cold_ttft_median_ms
  - pp_median

weights:
  warm_tg_median: 0.35
  warm_tg_p10: 0.25
  warm_ttft_median_ms: 0.15
  warm_ttft_p90_ms: 0.00
  cold_ttft_median_ms: 0.10
  pp_median: 0.15

normalize_weights: true
ranking_mode: composite
composite_basis: lcb_score
confidence_policy: lcb_k1
min_sample_gate: 10
outlier_policy: flag_symmetric
outlier_fence_method: iqr_1_5

gate_overrides:
  max_cv: 0.05
  max_thermal_events: 0
  max_outliers: 3
  max_warm_ttft_p90_ms: 500.0
  min_success_rate: 0.90
  min_warm_tg_p10: 7.0
  min_valid_warm_count: 3

report_emphasis:
  - warm_tg_median
  - warm_tg_p10
  - pp_median

diagnostic_metrics:
  - warm_tg_cv
  - thermal_events
  - success_rate
  - outlier_count
```

### `configs/profiles/acpm_ttft_v1.yaml` — full file

```yaml
# QuantMap — Experiment Profile: acpm_ttft_v1
# ACPM Time-to-First-Token (TTFT) lens. Latency-biased; prioritizes first-token responsiveness.
# IMPORTANT: Changing values in this file changes scoring behavior.

name: acpm_ttft_v1
version: "1.0.0"
experiment_family: throughput
description: >
  ACPM Time-to-First-Token (TTFT) profile. Latency-biased recommendation lens.
  Prioritizes warm and cold first-token responsiveness. Use when minimizing
  time-to-first-token is the primary goal.

active_metrics:
  - warm_tg_median
  - warm_tg_p10
  - warm_ttft_median_ms
  - warm_ttft_p90_ms
  - cold_ttft_median_ms
  - pp_median

primary_metrics:
  - warm_ttft_median_ms
  - cold_ttft_median_ms

secondary_metrics:
  - warm_tg_median
  - warm_tg_p10
  - warm_ttft_p90_ms
  - pp_median

weights:
  warm_tg_median: 0.10
  warm_tg_p10: 0.05
  warm_ttft_median_ms: 0.50
  warm_ttft_p90_ms: 0.00
  cold_ttft_median_ms: 0.30
  pp_median: 0.05

normalize_weights: true
ranking_mode: composite
composite_basis: lcb_score
confidence_policy: lcb_k1
min_sample_gate: 10
outlier_policy: flag_symmetric
outlier_fence_method: iqr_1_5

gate_overrides:
  max_cv: 0.05
  max_thermal_events: 0
  max_outliers: 3
  max_warm_ttft_p90_ms: 500.0
  min_success_rate: 0.90
  min_warm_tg_p10: 7.0
  min_valid_warm_count: 3

report_emphasis:
  - warm_ttft_median_ms
  - cold_ttft_median_ms
  - warm_tg_median

diagnostic_metrics:
  - warm_tg_cv
  - thermal_events
  - success_rate
  - outlier_count
```

### Weight vector summary (verify sums before committing)

| Metric | Balanced | T/S | TTFT |
|---|---:|---:|---:|
| `warm_tg_median` | 0.25 | 0.35 | 0.10 |
| `warm_tg_p10` | 0.15 | 0.25 | 0.05 |
| `warm_ttft_median_ms` | 0.35 | 0.15 | 0.50 |
| `warm_ttft_p90_ms` | **0.00** | **0.00** | **0.00** |
| `cold_ttft_median_ms` | 0.20 | 0.10 | 0.30 |
| `pp_median` | 0.05 | 0.15 | 0.05 |
| **Sum** | **1.00** | **1.00** | **1.00** |

---

## 4. Concrete Python Plan for `src/acpm_planning.py`

### Full additions summary

```
from pathlib import Path                          ← new import

V1_ACPM_PROFILE_IDS: frozenset[str]              ← new module constant
_ACPM_PROFILE_REGISTRY: dict[str, dict[str, str]] ← new module constant

def get_acpm_profile_info(profile_id: str) -> dict[str, str]         ← new
def load_acpm_scoring_profile(profile_id: str, profiles_dir=None) -> Any  ← new

ACPMPlanningMetadata.__post_init__:
    + if self.profile_name not in V1_ACPM_PROFILE_IDS: raise ValueError  ← modified
```

### Import strategy

- `governance` is **not** imported at module level.
- `load_acpm_scoring_profile` uses `from src.governance import load_profile, load_registry, validate_profile_against_registry` inside the function body.
- Rationale: defensive against future circular chains. `acpm_planning.py` already imports `run_plan.py`. If future slices make `governance.py` import `acpm_planning.py`, a top-level import would create a cycle. Lazy import avoids the risk at zero runtime cost (called rarely, not in tight loops).
- Pre-implementation check: confirm `src/governance.py` does not import from `src/acpm_planning.py` (expected: it does not). If confirmed clean, lazy import is still the right choice as a defensive practice.

### Insertion order in file

Place new content between `_FORBIDDEN_PLANNING_METADATA_KEYS` and `_reject_shadow_truth_fields`. The file currently reads:

```
_FORBIDDEN_PLANNING_METADATA_KEYS = {...}       ← existing

                                                 ← INSERT HERE:
                                                 V1_ACPM_PROFILE_IDS
                                                 _ACPM_PROFILE_REGISTRY
                                                 get_acpm_profile_info()
                                                 load_acpm_scoring_profile()

def _reject_shadow_truth_fields(...)            ← existing, unchanged
```

---

## 5. Concrete Test Plan

**File:** `test_acpm_slice3.py` (repo root — matches `test_acpm_slice1.py`, `test_governance.py` placement)

### Imports needed in test file

```python
import pytest
from src.governance import load_profile, load_registry, validate_profile_against_registry
from src.acpm_planning import (
    V1_ACPM_PROFILE_IDS,
    _ACPM_PROFILE_REGISTRY,
    get_acpm_profile_info,
    load_acpm_scoring_profile,
    ACPMPlanningMetadata,
)
from src.run_plan import SCOPE_AUTHORITY_PLANNER
```

### Module-level fixtures (load once, reuse)

```python
_REFERENCE_PROFILE = load_profile("default_throughput_v1")
_REGISTRY = load_registry()
_ACPM_YAML_NAMES = {
    "Balanced": "acpm_balanced_v1",
    "T/S": "acpm_ts_v1",
    "TTFT": "acpm_ttft_v1",
}
```

### 16 test cases — exact names and minimal assertions

| # | Test name | Assert |
|---|---|---|
| 1 | `test_balanced_profile_loads` | `load_profile("acpm_balanced_v1").name == "acpm_balanced_v1"` |
| 2 | `test_ts_profile_loads` | `load_profile("acpm_ts_v1").name == "acpm_ts_v1"` |
| 3 | `test_ttft_profile_loads` | `load_profile("acpm_ttft_v1").name == "acpm_ttft_v1"` |
| 4 | `test_all_profiles_validate_against_registry` | For each yaml name: `validate_profile_against_registry(load_profile(n), _REGISTRY)` raises no exception |
| 5 | `test_weight_sums_are_one` | For each yaml name: `abs(sum(load_profile(n).weights.values()) - 1.0) < 1e-6` |
| 6 | `test_gates_match_shared_floor` | For each yaml name: `load_profile(n).gate_overrides == _REFERENCE_PROFILE.gate_overrides` |
| 7 | `test_warm_ttft_p90_weight_is_zero` | For each yaml name: `load_profile(n).weights["warm_ttft_p90_ms"] == 0.0` |
| 8 | `test_six_metric_shape_preserved` | For each yaml name: `set(load_profile(n).active_metrics) == set(_REFERENCE_PROFILE.active_metrics)` |
| 9 | `test_v1_profile_ids_constant` | `V1_ACPM_PROFILE_IDS == {"Balanced", "T/S", "TTFT"}` |
| 10 | `test_registry_covers_all_v1_ids` | `set(_ACPM_PROFILE_REGISTRY.keys()) == V1_ACPM_PROFILE_IDS` |
| 11 | `test_get_acpm_profile_info_valid` | For each id: returned dict has keys `scoring_profile_name`, `display_label`, `display_name`, `lens_description` |
| 12 | `test_get_acpm_profile_info_invalid` | `pytest.raises(ValueError): get_acpm_profile_info("Unknown")` |
| 13 | `test_load_acpm_scoring_profile_round_trip` | For each id: `load_acpm_scoring_profile(id).name == get_acpm_profile_info(id)["scoring_profile_name"]` |
| 14 | `test_planning_metadata_rejects_unknown_profile` | `pytest.raises(ValueError): ACPMPlanningMetadata(profile_name="UnknownProfile", ...)` |
| 15 | `test_planning_metadata_accepts_known_profiles` | For each id: `ACPMPlanningMetadata(profile_name=id, ...)` constructs without exception |
| 16 | `test_ts_display_name_includes_expansion` | `"Throughput/Speed" in get_acpm_profile_info("T/S")["display_name"]` |

**Note for test 14 and 15:** `ACPMPlanningMetadata` requires `scope_authority=SCOPE_AUTHORITY_PLANNER`, `schema_id=ACPM_PLANNING_METADATA_SCHEMA_ID`, `schema_version=ACPM_PLANNING_METADATA_SCHEMA_VERSION`, and all required string fields non-empty. Mirror the fixture pattern from `test_acpm_slice1.py`.

### Regression suites that must pass without modification

- `test_acpm_slice1.py` — uses `profile_name="Balanced"` which is in `V1_ACPM_PROFILE_IDS`; should pass
- `test_governance.py` — governance.py untouched; should pass

---

## 6. Validation Plan

Run commands in this exact order. Each step must pass before proceeding to the next.

```powershell
# 1. Preflight — must pass before the first edit
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick

# 2. After creating each YAML — quick parse check per file
.\.venv\Scripts\python.exe -c "from src.governance import load_profile; p = load_profile('acpm_balanced_v1'); print(p.name, sum(p.weights.values()))"
.\.venv\Scripts\python.exe -c "from src.governance import load_profile; p = load_profile('acpm_ts_v1'); print(p.name, sum(p.weights.values()))"
.\.venv\Scripts\python.exe -c "from src.governance import load_profile; p = load_profile('acpm_ttft_v1'); print(p.name, sum(p.weights.values()))"

# 3. After editing acpm_planning.py — lint before any test run
.\.venv\Scripts\python.exe -m ruff check src\acpm_planning.py

# 4. After ACPMPlanningMetadata tightening — confirm slice 1 still passes
.\.venv\Scripts\python.exe -m pytest -q test_acpm_slice1.py

# 5. After writing test_acpm_slice3.py — lint the test file
.\.venv\Scripts\python.exe -m ruff check test_acpm_slice3.py

# 6. Slice 3 tests
.\.venv\Scripts\python.exe -m pytest -q test_acpm_slice3.py

# 7. Full regression (governance + slice 1 + slice 3 together)
.\.venv\Scripts\python.exe -m pytest -q test_governance.py test_acpm_slice1.py test_acpm_slice3.py

# 8. Changed-path verification
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths src\acpm_planning.py configs\profiles\acpm_balanced_v1.yaml configs\profiles\acpm_ts_v1.yaml configs\profiles\acpm_ttft_v1.yaml test_acpm_slice3.py
```

**Pass criteria:** all 16 `test_acpm_slice3.py` tests green; all `test_acpm_slice1.py` and `test_governance.py` tests green; `ruff check` clean on all touched paths; `changed_path_verify.py` exits 0.

---

## 7. Risk Controls and Rollback Notes

### If YAML parsing fails at load time

Check first:
- `description` field present (required, easy to miss — gaps in PRE plan)
- `weights` keys exactly match `active_metrics` (Pydantic `_metrics_consistency` validator)
- `primary_metrics` and `secondary_metrics` are each a subset of `active_metrics`

Rollback boundary: delete the offending YAML file. No code changes at that point.

### If `validate_profile_against_registry` raises `ProfileValidationError`

Check first:
- `min_sample_gate: 10` — must equal or exceed per-metric floor from `metrics.yaml`
- All gate override keys are in `recognized_gates` (defined in `governance.py` line ~427): `max_cv`, `max_thermal_events`, `max_outliers`, `max_warm_ttft_p90_ms`, `min_success_rate`, `min_warm_tg_p10`, `min_valid_warm_count`
- `experiment_family: throughput` and all active metrics have `family_tags: [all]` or `[throughput]`

Rollback boundary: fix YAML content only. No code changes at this point.

### If `ACPMPlanningMetadata` tightening breaks `test_acpm_slice1.py`

Check first:
- Inspect `test_acpm_slice1.py` for `profile_name=` values used in test fixtures
- Known value: `"Balanced"` (confirmed in PRE plan grounding). If test uses another value, check if it can be updated to a valid ACPM ID.

Rollback boundary: revert only the single validation hunk in `ACPMPlanningMetadata.__post_init__`. Registry constants and helpers are unaffected.

### If lazy import fails at runtime in `load_acpm_scoring_profile`

Check first:
- `from src.governance import load_profile, load_registry, validate_profile_against_registry` — all three confirmed to exist (lines 475, 514, 402 of `src/governance.py`)
- `src/` on sys.path — guaranteed by editable install (`pip install -e .`)

Rollback boundary: revert function body only. Registry constants, `get_acpm_profile_info`, and the `__post_init__` hunk are unaffected.

### Smallest rollback boundaries per edit cluster

| Edit cluster | Rollback scope |
|---|---|
| Three YAML files | Delete all three — no Python code affected |
| Registry constants + helpers in `acpm_planning.py` | Revert additions above `_reject_shadow_truth_fields` — `__post_init__` change unaffected |
| `ACPMPlanningMetadata.__post_init__` hunk | Revert one `if` block — registry/helpers unaffected |
| `test_acpm_slice3.py` | Delete file — no production code affected |

---

## 8. Implementation Order

Run each step sequentially. Steps 2–4 (YAML creation) may be done in parallel but each must be parse-checked before proceeding.

| Step | Action | Gate |
|---|---|---|
| 1 | Run `verify_dev_contract.py --quick` | Must PASS — do not proceed if it fails |
| 2 | Create `configs/profiles/acpm_balanced_v1.yaml` | Parse check: step 2 inline command above |
| 3 | Create `configs/profiles/acpm_ts_v1.yaml` | Parse check: step 2 inline command above |
| 4 | Create `configs/profiles/acpm_ttft_v1.yaml` | Parse check: step 2 inline command above |
| 5 | Add `from pathlib import Path` import to `acpm_planning.py` | Lint passes |
| 6 | Add `V1_ACPM_PROFILE_IDS`, `_ACPM_PROFILE_REGISTRY`, `get_acpm_profile_info()`, `load_acpm_scoring_profile()` to `acpm_planning.py` | Lint passes; no tests yet |
| 7 | Tighten `ACPMPlanningMetadata.__post_init__` with `profile_name in V1_ACPM_PROFILE_IDS` check | `test_acpm_slice1.py` PASS |
| 8 | Write `test_acpm_slice3.py` with all 16 tests | All 16 PASS; full regression PASS |
| 9 | Run `changed_path_verify.py` on all touched paths | Exits 0 |

Do not merge steps 6 and 7. Add registry/helpers first; tighten validation separately so rollback scope stays minimal if slice 1 tests break.

---

## 9. Definition of Done

The slice is complete when all of the following are true:

1. `configs/profiles/acpm_balanced_v1.yaml`, `acpm_ts_v1.yaml`, `acpm_ttft_v1.yaml` exist and each loads without exception via `governance.load_profile(name)`.
2. All three profiles pass `governance.validate_profile_against_registry(profile, registry)` with no exception.
3. All three profiles have `warm_ttft_p90_ms: 0.00` in `weights` and `gate_overrides` identical to `default_throughput_v1`.
4. `src/acpm_planning.py` exports `V1_ACPM_PROFILE_IDS`, `get_acpm_profile_info()`, and `load_acpm_scoring_profile()`.
5. `ACPMPlanningMetadata.__post_init__` raises `ValueError` for `profile_name` values not in `V1_ACPM_PROFILE_IDS`.
6. `test_acpm_slice3.py` contains all 16 tests and all 16 pass.
7. `test_acpm_slice1.py` and `test_governance.py` pass without modification.
8. `ruff check` is clean on all touched paths.
9. `changed_path_verify.py` exits 0.
10. No changes in `runner.py`, `score.py`, `report.py`, `report_campaign.py`, `explain.py`, `export.py`, `compare.py`, `audit_methodology.py`, `governance.py`, or `db.py`.

---

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.github/instructions/quantmap-agent.instructions.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Implementation/ACPM-Slice-3-Governed-Profiles-and-Methodology-Labeling-PREP-Implementation-Plan.md`
- `src/governance.py` (lines 294–470, 514–549) — source inspection to resolve exact field names, function signatures, and `ExperimentProfile` schema
- `configs/profiles/default_throughput_v1.yaml` — gate values, field structure, and `description` field presence confirmed
