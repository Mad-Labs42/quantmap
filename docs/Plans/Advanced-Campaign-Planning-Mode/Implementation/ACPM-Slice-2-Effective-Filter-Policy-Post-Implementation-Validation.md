# ACPM Slice 2: Effective Filter Policy — Post-Implementation Validation

Date: 2026-04-22
Branch: bughunt/phase-1-baseline

## Outcome

Slice 2 is implemented and verified. `campaign_start_snapshot.effective_filter_policy_json` is now the sole persisted authority for run-effective filter policy on v1+ rows. Legacy rows remain null; `trust_identity` synthesizes a bounded projection for them without backfill or over-certification.

## What Was Implemented

### 1. DB / Schema (`src/db.py`)

- `SCHEMA_VERSION` bumped: `13` → `14`.
- `effective_filter_policy_json TEXT` added to the `campaign_start_snapshot` DDL (nullable, adjacent to `run_plan_json` and `acpm_planning_metadata_json`).
- Migration 14 added: `ALTER TABLE campaign_start_snapshot ADD COLUMN effective_filter_policy_json TEXT`. No backfill. Legacy rows remain null.

### 2. Filter Policy Helper (`src/effective_filter_policy.py`) — new file

Responsibilities (only):
- `canonical_json_sha256(value)` — stable sha256 of a JSON-serializable mapping (key-order-independent).
- `build_override_layers(run_plan_snapshot, yaml_filter_overrides)` — ordered override layer list from mode overrides (run_plan.filter_overrides) then YAML (YAML wins on conflict).
- `build_effective_filter_policy(base_gates, base_source, override_layers, score_effective_filters)` — builds the complete v1 policy record: effective filters, classification labels, hash, and scoring confirmation.
- `project_legacy_filter_policy(methodology, run_plan, campaign_yaml)` — synthesizes bounded legacy projections for null rows without DB write-back.

Does not: load DB rows directly, own methodology selection, mutate reports/export, or own ACPM planner logic.

### 3. Write Path (`src/runner.py`)

Inserted after `score_campaign()` returns and before `generate_report()`. Sequence:
1. Extracts `scoring_profile.gate_overrides` (base gates) and `methodology_snapshot_id` from `scores`.
2. Calls `build_override_layers(run_plan.to_snapshot_dict(), campaign.get("elimination_overrides"))`.
3. Calls `build_effective_filter_policy(...)` with `score_effective_filters=scores["effective_filters"]` — this triggers the post-scoring confirmation.
4. `UPDATE campaign_start_snapshot SET effective_filter_policy_json=? WHERE campaign_id=?`.
5. If `scoring_confirmation.status == "mismatch"`, logs a `TRUST FAILURE` error before report/export generation.
6. Entire block is wrapped in a non-fatal try/except so a helper failure cannot silently block report generation (logged as warning).

### 4. Read / Projection Seam (`src/trust_identity.py`)

- `filter_policy: dict[str, Any]` field added to `TrustIdentity` dataclass (defaults to `{}`).
- `load_run_identity()` now:
  - Parses `effective_filter_policy_json` when present → `sources["filter_policy"] = "snapshot"`.
  - Falls back to `project_legacy_filter_policy(methodology, run_plan, campaign_yaml)` for null rows → `sources["filter_policy"] = "legacy_{truth_status}"`.
  - Never writes back to the DB for legacy rows.
  - Campaign YAML content is parsed from `campaign_yaml_content` (stored as raw YAML text) via `yaml.safe_load`.

### 5. Export Projection (`src/export.py`)

- `metadata.json` now includes a top-level `filter_policy` object alongside the existing `methodology` section.
- `methodology.eligibility_filters` is preserved unchanged as base methodology/profile gates (backward-compatible).
- `filter_policy.effective_filters` is the run-effective threshold set from `trust_identity.filter_policy`.
- `filter_policy.source` identifies whether the projection came from the snapshot column or a legacy synthesis.
- `provenance_sources` now includes `filter_policy` with the source label from `trust_identity.sources`.

### 6. Stale Fallback Fix (`src/report_campaign.py`)

- `min_valid_warm_count` display default changed from `10` → `3` in the filter table fallback. The live profile gate is `3`; the `10` was stale wording creating trust-bearing disclosure drift.
- Pre-existing lint debt in this file (E402 from constants-before-imports, F541 unused f-strings, F601 duplicate dict keys, F401 unused imports) was also resolved since `changed_path_verify.py` applies ruff to all touched files. The duplicate dict-key bug (F601: `top_interferers` and `top_reasons` defined twice in one dict, silently dropping the first occurrence) was a pre-existing correctness defect; the second pair was removed.

## What Was Deferred (Intentionally)

Per scope boundaries:
- No planner heuristics, profile weights, or recommendation record/status logic.
- No `compare.py` effective-filter hash comparison or reduced-comparability warning.
- No `explain.py` trust context disclosure.
- No `runner.list_campaigns()` compact policy label projection.
- No `report.py` filter-policy section (beyond the existing `filter_overrides` display).
- No ACPM-specific `run_mode` values.
- No machine handoff.
- No export-only schema authority.
- The `min_valid_warm_count` 3-vs-10 drift is fixed at the report fallback level. The deeper governance reconciliation (Registry `min_sample_gate` semantics, code comment alignment) remains deferred and must block any new ACPM relaxation approval.

## Verification

| Check | Result |
|---|---|
| Dev preflight (`verify_dev_contract.py --quick`) | PASS |
| Ruff on new/touched files | All checks passed |
| `test_effective_filter_policy.py` (28 tests) | 28/28 PASS |
| `test_artifact_contract.py` (10 tests) | 10/10 PASS |
| `test_governance.py` (2 tests) | 2/2 PASS |
| `test_acpm_slice1.py` (9 tests) | 9/9 PASS |
| `changed_path_verify.py` (7 touched paths) | PASS |

### Test Coverage (test_effective_filter_policy.py)

- DB schema: new DB has column; nullable; migration from v13 adds column, preserves null on existing rows; round-trip persists and parses correctly.
- `canonical_json_sha256`: key-order stability; different-value discrimination.
- `build_override_layers`: no-override, custom mode, quick mode, YAML stacking.
- `build_effective_filter_policy`: profile default, custom (changed key), quick (no changed key when same as base), YAML override, custom+YAML stacking including YAML-wins-on-conflict.
- Scoring confirmation: confirmed, mismatch (with distinct sha256 fields), not_confirmed.
- `project_legacy_filter_policy`: unknown (no evidence), inferred_limited (custom mode), inferred_limited (quick mode), reconstructed (complete methodology + overrides), reconstructed + campaign_override modifier.
- Trust identity: explicit row → `sources["filter_policy"]="snapshot"`, truth_status=explicit; null row → `sources["filter_policy"]` starts with `"legacy_"`, no DB write-back.
- Metadata projection: explicit source label; methodology.eligibility_filters coexists with filter_policy.effective_filters.

## Risks / Open Items

- The runner write block is non-fatal by design (try/except logs a warning). A future slice should consider whether a persistent helper failure should elevate to a run-level failure. For now, the mismatch case is the only path that logs at `ERROR` level.
- `TrustIdentity.filter_policy` defaults to `{}` (not `None`) so callers can `.get(...)` safely. This is a minor API choice; if a typed dataclass approach is preferred, a future pass can add a `FilterPolicy` dataclass.
- Compare and explain surfaces do not yet consume `filter_policy`; runs with different effective-filter hashes will not be flagged for reduced comparability until Slice 6.

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/policies/boundaries.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/ACPM-v1-Decision-Baseline.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-filter-policy-persistence-history-and-export-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-effective-filter-policy-json-schema-and-projection-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-effective-filter-policy-implementation-plan-and-test-matrix-TARGET-INVESTIGATION.md`
