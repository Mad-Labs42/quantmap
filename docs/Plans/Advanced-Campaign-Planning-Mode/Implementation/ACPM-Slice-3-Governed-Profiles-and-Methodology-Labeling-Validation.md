# ACPM Slice 3: Governed Profiles and Methodology Labeling — Post-Implementation Validation

Date: 2026-04-23
Branch: feat/acpm-slice-3
Validator: Claude Code (automated validation pass)
Precursor: ACPM-Slice-3-Governed-Profiles-and-Methodology-Labeling-Implementation-Plan.md

---

## Status

**PASS — Ready for Slice 4.**

All 9 definition-of-done criteria met. All 16 Slice 3 tests pass. Full regression (27 tests) passes. No deferred files touched. Ruff clean on all touched paths.

---

## Validated Scope

### Files added (new, untracked)

| File | Role |
|---|---|
| `configs/profiles/acpm_balanced_v1.yaml` | Governed ExperimentProfile — Balanced lens |
| `configs/profiles/acpm_ts_v1.yaml` | Governed ExperimentProfile — Throughput/Speed lens |
| `configs/profiles/acpm_ttft_v1.yaml` | Governed ExperimentProfile — TTFT lens |
| `test_acpm_slice3.py` | 16-test Slice 3 validation suite |

### Files modified

| File | Change |
|---|---|
| `src/acpm_planning.py` | Additive only: `V1_ACPM_PROFILE_IDS`, `_ACPM_PROFILE_REGISTRY`, `get_acpm_profile_info()`, `load_acpm_scoring_profile()`, `ACPMPlanningMetadata.__post_init__` tightening |

### Deferred files — confirmed untouched

`git diff HEAD` on all deferred paths returned empty (no output):
`runner.py`, `score.py`, `report.py`, `report_campaign.py`, `explain.py`, `export.py`, `compare.py`, `audit_methodology.py`, `governance.py`, `db.py`.

---

## Checks Performed and Results

### 1. YAML parse and weight-sum check

Command:
```
.venv/Scripts/python.exe -c "from src.governance import load_profile; p = load_profile('<name>'); print(p.name, sum(p.weights.values()))"
```

| Profile | Output | Result |
|---|---|---|
| `acpm_balanced_v1` | `acpm_balanced_v1 1.0` | PASS |
| `acpm_ts_v1` | `acpm_ts_v1 1.0` | PASS |
| `acpm_ttft_v1` | `acpm_ttft_v1 1.0` | PASS |

All three profiles load via `governance.load_profile()` without exception. Weight sums are exactly 1.0.

### 2. Ruff lint

Command: `.venv/Scripts/python.exe -m ruff check src/acpm_planning.py test_acpm_slice3.py`

Output: `All checks passed!`

Result: **PASS**

### 3. Slice 1 regression

Command: `.venv/Scripts/python.exe -m pytest -q test_acpm_slice1.py`

Output: `9 passed in 1.25s`

Result: **PASS** — no regressions from `ACPMPlanningMetadata.__post_init__` tightening. Confirmed: `profile_name="Balanced"` used in Slice 1 fixtures is a valid member of `V1_ACPM_PROFILE_IDS`.

### 4. Slice 3 tests (all 16)

Command: `.venv/Scripts/python.exe -m pytest -q test_acpm_slice3.py`

Output: `16 passed in 1.40s`

Result: **PASS**

| # | Test | Result |
|---|---|---|
| 1 | `test_balanced_profile_loads` | PASS |
| 2 | `test_ts_profile_loads` | PASS |
| 3 | `test_ttft_profile_loads` | PASS |
| 4 | `test_all_profiles_validate_against_registry` | PASS |
| 5 | `test_weight_sums_are_one` | PASS |
| 6 | `test_gates_match_shared_floor` | PASS |
| 7 | `test_warm_ttft_p90_weight_is_zero` | PASS |
| 8 | `test_six_metric_shape_preserved` | PASS |
| 9 | `test_v1_profile_ids_constant` | PASS |
| 10 | `test_registry_covers_all_v1_ids` | PASS |
| 11 | `test_get_acpm_profile_info_valid` | PASS |
| 12 | `test_get_acpm_profile_info_invalid` | PASS |
| 13 | `test_load_acpm_scoring_profile_round_trip` | PASS |
| 14 | `test_planning_metadata_rejects_unknown_profile` | PASS |
| 15 | `test_planning_metadata_accepts_known_profiles` | PASS |
| 16 | `test_ts_display_name_includes_expansion` | PASS |

### 5. Full regression suite

Command: `.venv/Scripts/python.exe -m pytest -q test_governance.py test_acpm_slice1.py test_acpm_slice3.py`

Output: `27 passed in 1.61s`

Result: **PASS**

### 6. Changed-path verification

Command: `.venv/Scripts/python.exe .agent/scripts/changed_path_verify.py --paths src/acpm_planning.py configs/profiles/acpm_balanced_v1.yaml configs/profiles/acpm_ts_v1.yaml configs/profiles/acpm_ttft_v1.yaml test_acpm_slice3.py`

Output:
```
status: pass
interpreter: D:\Workspaces\QuantMap_agent\.venv\Scripts\python.exe
interpreter_is_repo_venv: True
python_version: 3.13.13
base_is_devstore: True
changed_files: 5
changed_python_files: 2
test_targets: 1
report: D:\Workspaces\QuantMap_agent\.agent\artifacts\changed_path_verify.json
```

Result: **PASS**

---

## YAML Truth Verification (source-level)

### Shared-fields invariants — all three profiles

| Field | Required value | Balanced | T/S | TTFT |
|---|---|---|---|---|
| `experiment_family` | `throughput` | ✅ | ✅ | ✅ |
| `min_sample_gate` | `10` | ✅ | ✅ | ✅ |
| `ranking_mode` | `composite` | ✅ | ✅ | ✅ |
| `composite_basis` | `lcb_score` | ✅ | ✅ | ✅ |
| `confidence_policy` | `lcb_k1` | ✅ | ✅ | ✅ |
| `normalize_weights` | `true` | ✅ | ✅ | ✅ |
| `outlier_policy` | `flag_symmetric` | ✅ | ✅ | ✅ |
| `outlier_fence_method` | `iqr_1_5` | ✅ | ✅ | ✅ |
| `description` (non-empty) | required | ✅ | ✅ | ✅ |

### Gate overrides — identical to `default_throughput_v1`

| Gate key | Required value | Confirmed identical |
|---|---|---|
| `max_cv` | `0.05` | ✅ all three |
| `max_thermal_events` | `0` | ✅ all three |
| `max_outliers` | `3` | ✅ all three |
| `max_warm_ttft_p90_ms` | `500.0` | ✅ all three |
| `min_success_rate` | `0.90` | ✅ all three |
| `min_warm_tg_p10` | `7.0` | ✅ all three |
| `min_valid_warm_count` | `3` | ✅ all three |

Confirmed by test 6 (`test_gates_match_shared_floor`) comparing `profile.gate_overrides` against loaded `default_throughput_v1`.

### Weight vectors

| Metric | Balanced | T/S | TTFT |
|---|---:|---:|---:|
| `warm_tg_median` | 0.25 | 0.35 | 0.10 |
| `warm_tg_p10` | 0.15 | 0.25 | 0.05 |
| `warm_ttft_median_ms` | 0.35 | 0.15 | 0.50 |
| `warm_ttft_p90_ms` | **0.00** | **0.00** | **0.00** |
| `cold_ttft_median_ms` | 0.20 | 0.10 | 0.30 |
| `pp_median` | 0.05 | 0.15 | 0.05 |
| **Sum** | **1.00** | **1.00** | **1.00** |

`warm_ttft_p90_ms: 0.00` in all three confirmed by test 7 and source inspection.

### Six-metric shape

All three profiles use `active_metrics` identical to `default_throughput_v1`:
`warm_tg_median`, `warm_tg_p10`, `warm_ttft_median_ms`, `warm_ttft_p90_ms`, `cold_ttft_median_ms`, `pp_median`.
Confirmed by test 8.

---

## Planning Seam Verification (source-level)

### `acpm_planning.py` additions — confirmed present

| Symbol | Location | Confirmed |
|---|---|---|
| `from pathlib import Path` | Line 14 | ✅ |
| `V1_ACPM_PROFILE_IDS = frozenset({"Balanced", "T/S", "TTFT"})` | Line 35 | ✅ |
| `_ACPM_PROFILE_REGISTRY` (dict, 3 keys) | Lines 37–65 | ✅ |
| `get_acpm_profile_info(profile_id)` | Lines 68–74 | ✅ |
| `load_acpm_scoring_profile(profile_id, profiles_dir)` | Lines 77–87 | ✅ |
| `if self.profile_name not in V1_ACPM_PROFILE_IDS: raise ValueError` | Lines 154–158 | ✅ |

### Lazy import strategy — confirmed

`load_acpm_scoring_profile` uses `from src.governance import load_profile, load_registry, validate_profile_against_registry` inside the function body (line 81). `governance` is not imported at module level. Matches plan rationale (defensive against future circular chains).

### `ACPMPlanningMetadata` validation ordering — confirmed

The `profile_name` guard (`lines 154–158`) executes after the required-field emptiness check loop and before `_reject_shadow_truth_fields`. Matches plan insertion point.

### Registry-to-YAML name mapping — confirmed

| Profile ID | `scoring_profile_name` | YAML file |
|---|---|---|
| `Balanced` | `acpm_balanced_v1` | `configs/profiles/acpm_balanced_v1.yaml` |
| `T/S` | `acpm_ts_v1` | `configs/profiles/acpm_ts_v1.yaml` |
| `TTFT` | `acpm_ttft_v1` | `configs/profiles/acpm_ttft_v1.yaml` |

---

## Scope-Discipline Audit

| Concern | Finding |
|---|---|
| Score wiring added? | No. `score.py` untouched. |
| Runner changes? | No. `runner.py` untouched. |
| Report/export/explain/compare work? | No. All six files untouched. |
| DB schema changes? | No. `db.py` untouched. |
| Governance changes? | No. `governance.py` untouched. |
| Profile-specific gates added? | No. `gate_overrides` identical across all three profiles and equals `default_throughput_v1`. Profile Gate Rule (v1) preserved. |

---

## Deviations from Plan

**None material.**

Two minor observations:

1. `from pathlib import Path` was already present in `acpm_planning.py` before the Slice 3 edits (line 14 in the as-delivered file). The plan called for adding it; it was already there. The result is identical either way — no functional deviation.

2. `test_acpm_slice3.py` imports `ACPM_PLANNING_METADATA_SCHEMA_ID` and `ACPM_PLANNING_METADATA_SCHEMA_VERSION` from `acpm_planning` (used in the `_make_metadata()` helper). The plan's imports table omitted these. This is a correct implementation refinement required to construct valid `ACPMPlanningMetadata` instances in tests — not a scope deviation.

---

## Watch-Outs / Residual Risks

**1. `warm_ttft_p90_ms` weight is 0.00 in all three profiles — normalization behavior.**
`normalize_weights: true` is set. If `score.py` normalizes weights before applying them and `warm_ttft_p90_ms` is included in the normalization denominator at a future weight of 0.00, no division-by-zero risk exists (denominator is the sum of non-zero weights). Wiring into score.py (Slice 4) should verify normalization behavior explicitly with a zero-weight metric present.

**2. Lazy governance import in `load_acpm_scoring_profile`.**
Correct and intentional. If Slice 4 or later introduces a module-level `governance` import in `acpm_planning.py`, the lazy import should be reconverted to a top-level import to avoid confusing dual-import paths.

**3. `CLAUDE.md` appears as untracked in the working tree.**
This file predates the current session (it was already listed as untracked `??` in the session's opening git status). It is not a Slice 3 artifact and is not an implementation file. No action needed from Slice 3.

**4. Pytest WinError 5 in atexit cleanup.**
A `PermissionError: [WinError 5] Access is denied` is printed after some test runs when pytest attempts to clean up a temp dir symlink. This is a known Windows/pytest infrastructure issue — not a test failure. All asserted test results are unaffected.

---

## Definition of Done — Final Check

| Criterion | Status |
|---|---|
| 1. All three YAMLs exist and load via `governance.load_profile()` | ✅ PASS |
| 2. All three pass `validate_profile_against_registry()` | ✅ PASS (test 4) |
| 3. `warm_ttft_p90_ms: 0.00`; `gate_overrides` identical to `default_throughput_v1` | ✅ PASS (tests 6, 7) |
| 4. `acpm_planning.py` exports `V1_ACPM_PROFILE_IDS`, `get_acpm_profile_info()`, `load_acpm_scoring_profile()` | ✅ PASS |
| 5. `ACPMPlanningMetadata.__post_init__` raises `ValueError` for unknown `profile_name` | ✅ PASS (test 14) |
| 6. `test_acpm_slice3.py` contains all 16 tests and all 16 pass | ✅ PASS |
| 7. `test_acpm_slice1.py` and `test_governance.py` pass without modification | ✅ PASS (9 + 2 = 11 tests; full 27 regression green) |
| 8. `ruff check` clean on all touched paths | ✅ PASS |
| 9. `changed_path_verify.py` exits 0 | ✅ PASS |
| 10. No changes in deferred files | ✅ PASS |

---

## Conclusion

Slice 3 is complete and correct. All 10 definition-of-done criteria are met. The three governed ACPM scoring profiles are parse-valid, registry-validated, weight-sum-correct, gate-invariant, and connected to `acpm_planning.py` through a clean, tested seam. Scope discipline held: no execution, scoring, reporting, or schema work leaked into this slice.

**Ready for Slice 4** (profile wiring into execution: `runner.py` / `score.py`).

---

## .agent Files Used This Turn

- `AGENTS.md`
- `CLAUDE.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Implementation/ACPM-Slice-3-Governed-Profiles-and-Methodology-Labeling-Implementation-Plan.md`
