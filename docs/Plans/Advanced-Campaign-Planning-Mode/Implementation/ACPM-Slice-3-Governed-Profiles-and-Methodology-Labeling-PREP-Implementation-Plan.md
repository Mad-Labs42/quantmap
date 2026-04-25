# ACPM Slice 3: Governed Profiles and Methodology Labeling — PRE Implementation Plan

Date: 2026-04-23
Branch: bughunt/phase-1-baseline

---

## 1. Current-State Grounding

### What Slice 1 and Slice 2 established that Slice 3 builds on

**`src/acpm_planning.py`** (Slice 1):
- `ACPMPlanningMetadata` already carries `profile_name: str` and `repeat_tier: str` as required provenance fields.
- `ACPMPlannerOutput` already carries `profile_name` and `repeat_tier` at the output level.
- Current validation: `profile_name` must be non-empty — no check against an allowed set. `test_acpm_slice1.py` uses `profile_name="Balanced"` (mixed-case), so that convention is established.
- `_FORBIDDEN_PLANNING_METADATA_KEYS` already blocks shadow-truth fields.

**`src/run_plan.py`** (Slice 1):
- `scope_authority` seam exists with `SCOPE_AUTHORITY_PLANNER`.

**`src/db.py`** (Slices 1 and 2):
- Schema v14. `campaign_start_snapshot` has `acpm_planning_metadata_json` (Slice 1) and `effective_filter_policy_json` (Slice 2), both nullable.
- No DB changes required in Slice 3.

**`src/trust_identity.py`** (Slice 2):
- `filter_policy` field exists and is projected via the `snapshot` / `legacy_*` seam.
- `sources` dict includes `filter_policy`.
- This is the shared read seam for all consumers.

**`src/governance.py`** (pre-existing):
- `ExperimentProfile` Pydantic model: `name`, `version`, `experiment_family`, `active_metrics`, `weights`, `gate_overrides`, `min_sample_gate`, `confidence_policy`, `report_emphasis`.
- `load_profile(profile_name, profiles_dir)`: loads a YAML by name, parses, returns `ExperimentProfile`.
- `validate_profile_against_registry(profile, registry)`: enforces active-metric compatibility, gate key validity, `min_sample_gate` floor, and family-tag compatibility.
- These are the correct primitives to use — Slice 3 calls them, not bypasses them.

**`configs/profiles/default_throughput_v1.yaml`** (pre-existing):
- The only current profile. `experiment_family: throughput`, `min_sample_gate: 10`, six active metrics including `warm_ttft_p90_ms` at weight `0.10`.
- Gate values: `max_cv: 0.05`, `max_thermal_events: 0`, `max_outliers: 3`, `max_warm_ttft_p90_ms: 500.0`, `min_success_rate: 0.90`, `min_warm_tg_p10: 7.0`, `min_valid_warm_count: 3`.

**`src/export.py`** (Slice 2):
- `metadata.json` now includes `filter_policy` block via `trust_identity.filter_policy`.
- `methodology.eligibility_filters` remains unchanged.
- Profile name/version flow through the existing methodology snapshot seam via `trust_identity`.

**Key constraint from source inspection**: `metrics.yaml` sets `experiment_family_tags: [all]` on all six score-capable metrics, so `experiment_family: throughput` is valid for all three ACPM profiles. The highest `min_sample_gate` among active metrics is `10` — ACPM profiles must use `min_sample_gate: 10` to satisfy `validate_profile_against_registry()`.

---

## 2. Exact Slice 3 Scope

### What this slice implements

1. **Three governed ACPM scoring profile YAML files** under `configs/profiles/`:
   - `acpm_balanced_v1.yaml`
   - `acpm_ts_v1.yaml`
   - `acpm_ttft_v1.yaml`
   - Each uses the v1 weight vectors locked in `ACPM-profile-weight-values-TARGET-INVESTIGATION.md`.
   - All three share identical gates (same as `default_throughput_v1`).
   - All three use the same six-key metric shape with `warm_ttft_p90_ms` explicitly at `0.00`.
   - All three validate cleanly via `governance.validate_profile_against_registry()`.

2. **ACPM profile registry in `src/acpm_planning.py`** (additive only):
   - `V1_ACPM_PROFILE_IDS: frozenset[str]` — canonical ACPM profile identifiers matching what `profile_name` carries in `ACPMPlanningMetadata`.
   - `_ACPM_PROFILE_REGISTRY: dict[str, dict]` — maps ACPM profile ID → scoring profile YAML name, display label, one-line description, T/S expansion. This is structured truth; wording derived from it, not stored independently in report code.
   - `get_acpm_profile_info(profile_id: str) -> dict` — safe lookup raising `ValueError` for unknown IDs.
   - `load_acpm_scoring_profile(profile_id: str, profiles_dir=None) -> ExperimentProfile` — calls `governance.load_profile()` then `governance.validate_profile_against_registry()`. This is the single entry point for any consumer needing a live ACPM profile object.
   - Tighten `ACPMPlanningMetadata.__post_init__` to validate `profile_name` against `V1_ACPM_PROFILE_IDS`.

3. **Freeze the T/S acronym expansion**: canonical display name is "Throughput/Speed (T/S)". This lives in `_ACPM_PROFILE_REGISTRY`, not in report prose.

### What this slice must explicitly defer

| Deferred | Reason |
|---|---|
| Wiring profile into `score.score_campaign(profile_name=...)` at run time | Slice 4 (planner heuristics and execution compilation) |
| Planner campaign ordering, applicability pruning, repeat-tier expansion per profile | Slice 4 |
| `report_campaign.py` ACPM-specific methodology section | Slice 6 |
| `report.py` compact ACPM lens disclosure | Slice 6 |
| `explain.py` profile lens statement | Slice 6 |
| `export.py` planner block and shared-shape/shared-constraint identifiers | Slice 6 |
| `compare.py` / `audit_methodology.py` profile-weight-aware grading | Slice 6 |
| Recommendation record / status / caveat | Slice 5 |
| Machine handoff | Slice 6+ |
| NGL scaffold coverage-class disclosure | Slice 4/6 |
| DB schema changes | None needed |
| Broad runner changes | None needed |

---

## 3. Proposed Implementation Shape

### Profile YAML ownership

New files: `configs/profiles/acpm_balanced_v1.yaml`, `acpm_ts_v1.yaml`, `acpm_ttft_v1.yaml`.

Each follows the existing `ExperimentProfile` schema exactly. Shared fields across all three:

```yaml
experiment_family: throughput
active_metrics: [warm_tg_median, warm_tg_p10, warm_ttft_median_ms, warm_ttft_p90_ms, cold_ttft_median_ms, pp_median]
primary_metrics: [warm_tg_median, warm_tg_p10]       # varies by profile for report_emphasis
secondary_metrics: [warm_ttft_median_ms, warm_ttft_p90_ms, cold_ttft_median_ms, pp_median]
normalize_weights: true
ranking_mode: composite
composite_basis: lcb_score
confidence_policy: lcb_k1
min_sample_gate: 10
outlier_policy: flag_symmetric
outlier_fence_method: iqr_1_5
gate_overrides:                    # identical to default_throughput_v1 — no profile-specific gates in v1
  max_cv: 0.05
  max_thermal_events: 0
  max_outliers: 3
  max_warm_ttft_p90_ms: 500.0
  min_success_rate: 0.90
  min_warm_tg_p10: 7.0
  min_valid_warm_count: 3
```

Weight vectors (locked):

| Key | `Balanced` | `T/S` | `TTFT` |
|---|---:|---:|---:|
| `warm_tg_median` | 0.25 | 0.35 | 0.10 |
| `warm_tg_p10` | 0.15 | 0.25 | 0.05 |
| `warm_ttft_median_ms` | 0.35 | 0.15 | 0.50 |
| `warm_ttft_p90_ms` | 0.00 | 0.00 | 0.00 |
| `cold_ttft_median_ms` | 0.20 | 0.10 | 0.30 |
| `pp_median` | 0.05 | 0.15 | 0.05 |
| **Sum** | **1.00** | **1.00** | **1.00** |

Profile name fields inside YAMLs: `acpm_balanced_v1`, `acpm_ts_v1`, `acpm_ttft_v1`. Version: `1.0.0`.

### ACPM profile registry ownership

**Module: `src/acpm_planning.py`** (additive only).

The registry is a small `dict` constant mapping `ACPMPlanningMetadata.profile_name` values (e.g., `"Balanced"`) to their scoring profile YAML name and display metadata. This is the right home because:
- `acpm_planning.py` already owns planner-facing contracts.
- A separate `acpm_profiles.py` is premature; the registry is small.
- `governance.py` must not grow ACPM-specific awareness.
- `runner.py` must not own ACPM profile policy.

```python
V1_ACPM_PROFILE_IDS: frozenset[str] = frozenset({"Balanced", "T/S", "TTFT"})

_ACPM_PROFILE_REGISTRY: dict[str, dict[str, str]] = {
    "Balanced": {
        "scoring_profile_name": "acpm_balanced_v1",
        "display_label": "Balanced",
        "display_name": "Balanced",
        "lens_description": "Mixed practical recommendation lens. Ranking balances throughput and latency.",
    },
    "T/S": {
        "scoring_profile_name": "acpm_ts_v1",
        "display_label": "T/S (Throughput/Speed)",
        "display_name": "Throughput/Speed (T/S)",
        "lens_description": "Throughput-biased lens. Prioritizes sustained token generation rate and floor.",
    },
    "TTFT": {
        "scoring_profile_name": "acpm_ttft_v1",
        "display_label": "TTFT",
        "display_name": "Time-to-First-Token (TTFT)",
        "lens_description": "Latency-biased lens. Prioritizes warm and cold first-token responsiveness.",
    },
}
```

New functions (no import side effects, lazy governance import inside `load_acpm_scoring_profile` to avoid circular import risk):

```python
def get_acpm_profile_info(profile_id: str) -> dict[str, str]: ...
def load_acpm_scoring_profile(profile_id: str, profiles_dir=None) -> ExperimentProfile: ...
```

`ACPMPlanningMetadata.__post_init__` gains one new check: `profile_name in V1_ACPM_PROFILE_IDS`.

### Labeling seam

Slice 3 does not add report prose. What it provides is the structured truth that Slice 6 will read:
- `get_acpm_profile_info(profile_id)` → `display_label`, `display_name`, `lens_description`.
- Any report/explain code in Slice 6 derives its wording from this function, not from hardcoded strings.
- The existing `trust_identity` → `export.py` methodology seam already flows `profile_name` and `weights` from the methodology snapshot. Slice 3 does not change that path; it just ensures the scored profile data that flows through it is one of the three governed ACPM profiles.

---

## 4. Blast Radius / Watch-Outs

### Trust-bearing risks

| Risk | Detail |
|---|---|
| **`min_sample_gate` value** | Must be `10` to pass `validate_profile_against_registry()` for metrics that require it. Do not reduce below the registry's metric-level floor. Implementation turn must confirm via `governance.validate_profile_against_registry()` call in tests. |
| **Gate drift** | All three profiles must copy gates verbatim from `default_throughput_v1`. A typo (e.g., `min_valid_warm_count: 10` instead of `3`) would silently change elimination behavior if ever selected. Tests must assert gate identity against the default profile. |
| **`warm_ttft_p90_ms` weight** | Must be `0.00` in all three. A non-zero value would add a near-constant offset to all passing configs (the gate duplicate problem). Tests must assert this explicitly. |
| **Weight sums** | Must equal exactly `1.00` per profile. `ExperimentProfile` validator enforces this, but test round-trip also confirms. |

### Overreach risks

| Risk | Detail |
|---|---|
| **Runner or scorer wiring** | Slice 3 must not wire `load_acpm_scoring_profile()` into `runner.run_campaign()` or `score.score_campaign()`. That call site belongs to the planner entry (Slice 4). Adding it now would make ACPM profile selection active for non-ACPM runs. |
| **Report/explain changes** | `report_campaign.py`, `report.py`, `explain.py` must not be touched. The profile YAML files and registry constants provide structured truth; Slice 6 reads them. |
| **`ACPMPlanningMetadata` validation tightening impact** | `test_acpm_slice1.py` already uses `profile_name="Balanced"` which is in `V1_ACPM_PROFILE_IDS`, so existing tests should pass. Verify before tightening. |
| **`governance.py` growth** | Do not add ACPM-specific functions or constants to `governance.py`. ACPM-specific profile loading lives in `acpm_planning.py`. |

### Wording drift

The `lens_description` strings in `_ACPM_PROFILE_REGISTRY` are the single owned wording source. Slice 6 must derive display copy from this, not invent parallel strings in `report.py`. Any wording edit later must change only the registry, not scattered report code.

---

## 5. Validation / Test Plan

### Test file

New file: `test_acpm_slice3.py` (or `test_acpm_profiles.py`).

### Minimum strong test matrix

| Test | What it proves |
|---|---|
| `test_balanced_profile_loads` | `governance.load_profile("acpm_balanced_v1")` succeeds |
| `test_ts_profile_loads` | `governance.load_profile("acpm_ts_v1")` succeeds |
| `test_ttft_profile_loads` | `governance.load_profile("acpm_ttft_v1")` succeeds |
| `test_all_profiles_validate_against_registry` | Each loads + validates via `validate_profile_against_registry(profile, registry)` |
| `test_weight_sums_are_one` | Each profile's `sum(weights.values()) == 1.0` |
| `test_gates_match_shared_floor` | Each profile's `gate_overrides` equals `default_throughput_v1`'s |
| `test_warm_ttft_p90_weight_is_zero` | `profile.weights["warm_ttft_p90_ms"] == 0.00` for all three |
| `test_six_metric_shape_preserved` | Each profile has exactly the same six active metric keys |
| `test_registry_covers_all_v1_ids` | `V1_ACPM_PROFILE_IDS` == `set(_ACPM_PROFILE_REGISTRY.keys())` |
| `test_get_acpm_profile_info_valid` | Returns expected fields for each of the three IDs |
| `test_get_acpm_profile_info_invalid` | Raises `ValueError` for unknown ID |
| `test_load_acpm_scoring_profile_round_trip` | Returns `ExperimentProfile` with correct `name` for each ID |
| `test_planning_metadata_rejects_unknown_profile` | `ACPMPlanningMetadata(profile_name="Unknown", ...)` raises `ValueError` |
| `test_planning_metadata_accepts_known_profiles` | Valid construction succeeds for all three `V1_ACPM_PROFILE_IDS` values |
| `test_ts_display_name_includes_expansion` | `"Throughput/Speed"` in `get_acpm_profile_info("T/S")["display_name"]` |
| `test_existing_slice1_tests_still_pass` | `test_acpm_slice1.py` — no regressions from validation tightening |

### Validation commands (exact)

```
# Preflight
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick

# Lint touched paths
.\.venv\Scripts\python.exe -m ruff check configs\profiles\acpm_balanced_v1.yaml configs\profiles\acpm_ts_v1.yaml configs\profiles\acpm_ttft_v1.yaml src\acpm_planning.py test_acpm_slice3.py

# Slice 3 tests only
.\.venv\Scripts\python.exe -m pytest -q test_acpm_slice3.py

# Regression: governance + slice 1 must still pass
.\.venv\Scripts\python.exe -m pytest -q test_governance.py test_acpm_slice1.py test_acpm_slice3.py

# Changed path verify
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths src\acpm_planning.py configs\profiles\acpm_balanced_v1.yaml configs\profiles\acpm_ts_v1.yaml configs\profiles\acpm_ttft_v1.yaml test_acpm_slice3.py
```

---

## 6. Recommended Implementation Order

This is the smallest safe sequence for the implementation turn. Each step is independently verifiable.

| Step | Action | Verifiable after |
|---|---|---|
| 1 | Run preflight (`verify_dev_contract.py --quick`) | Must PASS before first edit |
| 2 | Create `configs/profiles/acpm_balanced_v1.yaml` | `governance.load_profile("acpm_balanced_v1")` in isolation |
| 3 | Create `configs/profiles/acpm_ts_v1.yaml` | Same |
| 4 | Create `configs/profiles/acpm_ttft_v1.yaml` | Same |
| 5 | Add `V1_ACPM_PROFILE_IDS`, `_ACPM_PROFILE_REGISTRY`, `get_acpm_profile_info()`, `load_acpm_scoring_profile()` to `src/acpm_planning.py` | No tests yet — lint first |
| 6 | Tighten `ACPMPlanningMetadata.__post_init__` to check `profile_name in V1_ACPM_PROFILE_IDS` | Verify `test_acpm_slice1.py` still PASS |
| 7 | Write `test_acpm_slice3.py` with full matrix above | All tests PASS |
| 8 | Run `changed_path_verify.py` on all touched paths | PASS |
| 9 | Write Slice 3 post-implementation validation doc | Done signal |

**Do not combine steps 5 and 6**: add the registry/helpers first, then tighten validation — so that if the tightening breaks existing tests, the rollback scope is minimal.

---

## 7. Open Questions (Only If Blocking)

| Question | Status |
|---|---|
| Should `primary_metrics` differ per ACPM profile (e.g., TTFT leads with `warm_ttft_median_ms`)? | Low-risk deferral: `primary_metrics` and `report_emphasis` fields are metadata today (not runtime-enforced for winner selection); they can mirror the weight ranking emphasis per profile without risk. Balanced: `[warm_tg_median, warm_tg_p10]`. T/S: `[warm_tg_median, warm_tg_p10]`. TTFT: `[warm_ttft_median_ms, cold_ttft_median_ms]`. Resolve during implementation. |
| Should the `experiment_family` field use a new value like `acpm` or stay `throughput`? | Stay `throughput`. Metrics use `family_tags: [all]` or `[throughput, ...]`; a new family would require metrics.yaml changes and registry updates. Not needed for Slice 3. |
| Should `normalize_weights: true` be kept even though weights already sum to 1.0? | Yes. Matches default profile convention and is harmless. |

No open question blocks implementation start.

---

## 8. .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.github/instructions/quantmap-agent.instructions.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/ACPM-v1-Decision-Baseline.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/ACPM-Decision-Extraction-Matrix.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Implementation/ACPM-Slice-1-Structural-Truth-PREP-Implementation-Plan.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Implementation/ACPM-Slice-1-Structural-Truth-Post-Implementation-Validation.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Implementation/ACPM-Slice-2-Effective-Filter-Policy-Post-Implementation-Validation.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-weight-values-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-to-governance-mapping-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-weight-and-gate-spec-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`
