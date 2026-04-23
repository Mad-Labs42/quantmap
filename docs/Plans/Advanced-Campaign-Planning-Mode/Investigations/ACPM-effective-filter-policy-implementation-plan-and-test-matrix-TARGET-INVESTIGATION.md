# ACPM Effective Filter Policy Implementation Plan and Test Matrix Target Investigation

Status: investigation-only

Scope: smallest safe implementation plan for the `campaign_start_snapshot.effective_filter_policy_json` seam

## Outcome

Recommended implementation posture: add the effective-filter-policy seam in one narrow vertical slice, with `campaign_start_snapshot.effective_filter_policy_json` as the only persisted authority for run-effective filter policy. Keep methodology truth in `methodology_snapshots.gates_json`, execution intent in `run_plan_json`, ACPM planner provenance outside this seam, and all reader-facing disclosures as projections through `src/trust_identity.py`.

Smallest correct v1 order:

1. Add a nullable DB column and schema migration.
2. Add a small filter-policy helper for canonical schema construction, hashing, layer ordering, and legacy projection support.
3. Have `src.runner.run_campaign()` build/write the policy after `score_campaign()` returns, then before report/export generation.
4. Have `src.trust_identity.load_run_identity()` expose a single shared filter-policy projection.
5. Update only the v1-required consumers: metadata export, report/report_campaign disclosure, compact list/history projection, compare warning, and explain trust context.
6. Add focused root-level tests matching the current repo style.

Do not write effective-filter truth into methodology snapshots, ACPM planning metadata, report artifacts, or `metadata.json` as authority. Do not let post-scoring confirmation become a second truth source; it is only a mismatch detector.

## Scope / What Was Inspected

Repo-agent surfaces:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/scripts/helpers/verify_dev_contract.py`

Code surfaces:

- `src/db.py`
- `src/runner.py`
- `src/score.py`
- `src/run_plan.py`
- `src/trust_identity.py`
- `src/export.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/compare.py`
- `src/explain.py`
- `src/governance.py`

Existing tests / verification surfaces:

- `test_artifact_contract.py`
- `test_governance.py`
- `test_determinism.py`
- `pyproject.toml`

Prior ACPM decisions used as starting point:

- `ACPM-effective-filter-policy-json-schema-and-projection-TARGET-INVESTIGATION.md`
- `ACPM-filter-policy-persistence-history-and-export-TARGET-INVESTIGATION.md`
- `ACPM-effective-filter-provenance-and-surface-disclosure-TARGET-INVESTIGATION.md`
- `ACPM-planner-directed-scoring-filter-policy-TARGET-INVESTIGATION.md`
- `ACPM-legacy-custom-mode-compatibility-TARGET-INVESTIGATION.md`

## Current State / Live Touchpoints

Persistence:

- `src/db.py` currently has `SCHEMA_VERSION: int = 12`.
- `campaign_start_snapshot` already contains snapshot-lane fields including `run_plan_json`, `snapshot_schema_version`, telemetry provider fields, and `execution_environment_json`.
- `methodology_snapshots.gates_json` stores base methodology/profile gates.
- There is no `effective_filter_policy_json` column today.

Write path:

- `src/telemetry.py::collect_campaign_start_snapshot()` serializes `run_plan_json`.
- `src.runner.run_campaign()` inserts `campaign_start_snapshot` before scoring and preserves an existing start snapshot if present.
- `src.runner.run_campaign()` builds `effective_filter_overrides` later by merging `run_plan.filter_overrides` and campaign YAML `elimination_overrides`.
- `src.score.score_campaign()` merges `profile.gate_overrides` plus caller `filter_overrides` into `effective_filters`, applies them, persists methodology snapshots, and returns `effective_filters`, `methodology_snapshot_id`, `methodology_source`, and `scoring_profile`.

Read/projection path:

- `src.trust_identity.load_run_identity()` already reads `campaign_start_snapshot`, `run_plan_json`, methodology snapshots, and legacy labels.
- Export, report, report_campaign, compare, explain, and audit_methodology already depend on `trust_identity` for persisted context.

Surface gaps:

- `src.export.generate_metadata_json()` writes `methodology.eligibility_filters` from base gates, not final run-effective filters.
- `src.report.py` shows `RunPlan.filter_overrides`, not final merged policy.
- `src.report_campaign.py` uses live `scores_result.effective_filters` when available, otherwise falls back to methodology gates and a stale `min_valid_warm_count` display default of `10`.
- `src.compare.py` loads snapshot context but does not compare effective-filter policy.
- `src.runner.list_campaigns()` lists mode/status/environment but not filter-policy truth status.

## Decisions Locked For Implementation

- Persist exactly one new nullable column: `campaign_start_snapshot.effective_filter_policy_json TEXT`.
- Do not index the JSON column in v1; history/list can project after loading rather than query by policy at scale.
- Do not backfill legacy rows during migration.
- Use `trust_identity` as the reader/projection seam.
- Keep `metadata.json` as a projection only.
- Keep methodology snapshot gates unchanged as base methodology truth.
- Keep ACPM planning metadata limited to planner identity, selection rationale, and optional exception references; no threshold maps.
- Include post-scoring confirmation in v1 as a cross-check.
- Treat confirmation mismatch as a trust failure before normal report/export generation.

## Recommended Implementation Order

### 1. Migration / Schema

Files:

- Modify `src/db.py`
- Test in new `test_effective_filter_policy.py`

Plan:

- Increment `SCHEMA_VERSION` from `12` to `13`.
- Add `effective_filter_policy_json TEXT` to the `campaign_start_snapshot` DDL.
- Add migration `13` with `ALTER TABLE campaign_start_snapshot ADD COLUMN effective_filter_policy_json TEXT`.
- Keep the column nullable.
- Do not backfill old rows.
- Do not add a separate table or index in v1.

Acceptance checks:

- New DBs contain the column.
- Migrated v12 DBs contain the column.
- Existing rows remain null.
- `schema_version` advances to `13`.

### 2. Effective Filter Policy Helper

Files:

- Create `src/effective_filter_policy.py`
- Test in new `test_effective_filter_policy.py`

Responsibilities:

- Define the v1 schema keys and allowed labels.
- Canonicalize JSON and compute `effective_filters_sha256`.
- Build ordered override layers from known inputs.
- Merge base gates plus override layers into expected effective filters.
- Build the persisted policy JSON.
- Compare expected effective filters with `score_campaign()` returned `effective_filters`.
- Build bounded legacy projections for `trust_identity`.

Non-responsibilities:

- Do not load campaign DB rows directly.
- Do not decide ACPM planning scope.
- Do not mutate reports/export.
- Do not own methodology selection.

Recommended helper shape:

- `canonical_json_sha256(value: Mapping[str, Any]) -> str`
- `build_override_layers(run_plan: Mapping[str, Any], yaml_filter_overrides: Mapping[str, float] | None) -> list[dict[str, Any]]`
- `build_effective_filter_policy(base_gates: Mapping[str, float], base_source: Mapping[str, Any], override_layers: list[dict[str, Any]], score_effective_filters: Mapping[str, float] | None = None) -> dict[str, Any]`
- `project_legacy_filter_policy(methodology: Mapping[str, Any], run_plan: Mapping[str, Any], campaign_yaml: Mapping[str, Any] | None) -> dict[str, Any]`

Implementation note:

- The helper may use plain dicts for v1 to fit the repo style, but tests should lock exact required keys and enum labels.

### 3. Write Path

Files:

- Modify `src/runner.py`
- Use `src/effective_filter_policy.py`
- No direct write from `src/score.py`

Plan:

- Preserve the existing `campaign_start_snapshot` insert before scoring.
- Preserve the existing `effective_filter_overrides` merge rule: run-plan/mode overrides first, campaign YAML overrides second, YAML wins.
- After `score_campaign()` returns and before report/metadata generation, build the policy JSON using:
  - `scores["scoring_profile"].gate_overrides` as base gates
  - `scores["methodology_snapshot_id"]`
  - `scores["methodology_source"]`
  - `scores["effective_filters"]`
  - `run_plan.to_snapshot_dict()`
  - campaign YAML `elimination_overrides`
- Update the existing `campaign_start_snapshot` row with `effective_filter_policy_json`.
- Set `scoring_confirmation.status` to `confirmed` when helper-computed expected filters match `scores["effective_filters"]`.
- If mismatch, persist a mismatch payload if possible and stop before normal report/export generation.

Why post-score write is the smallest repo fit:

- The current methodology snapshot ID is not known until `score_campaign()` runs.
- Moving methodology resolution before start-snapshot insertion would be a larger refactor.
- Building the policy after scoring avoids duplicating methodology selection logic.
- The record still lives in the snapshot-authoritative lane and is written before trust-bearing artifacts are generated.

### 4. Read / Projection Path

Files:

- Modify `src/trust_identity.py`
- Use `src/effective_filter_policy.py`
- Test in `test_effective_filter_policy.py`

Plan:

- Add a `filter_policy` field to `TrustIdentity`.
- Parse `campaign_start_snapshot.effective_filter_policy_json` when present.
- Add `sources["filter_policy"]` labels:
  - `snapshot`
  - `legacy_reconstructed`
  - `legacy_inferred_limited`
  - `unknown`
- If JSON is absent, synthesize a projection without writing it back:
  - `reconstructed` when persisted methodology gates, `run_plan_json.filter_overrides`, and campaign YAML content support reconstruction.
  - `inferred_limited` when only mode convention is available.
  - `unknown` when effective filters cannot be safely reconstructed.
- Never use current live profile gates as historical truth for old rows.

### 5. Surface Consumption

Files:

- Modify `src/export.py`
- Modify `src/report.py`
- Modify `src/report_campaign.py`
- Modify `src/runner.py`
- Modify `src/compare.py`
- Modify `src/explain.py`

V1-required consumption:

- `src/export.py`: add top-level `filter_policy` projection to `metadata.json`, preserve `methodology.eligibility_filters` as base methodology gates, and add `provenance_sources.filter_policy`.
- `src/report.py`: replace or augment `RunPlan.filter_overrides` display with shared filter-policy projection when present, especially for non-default or non-explicit policies.
- `src/report_campaign.py`: use `trust_identity.filter_policy.effective_filters` as persisted truth for methodology/filter disclosure; only use live `scores_result.effective_filters` as an immediate same-run source before the DB projection is available.
- `src.runner.list_campaigns()`: add compact policy/truth labels only, not full threshold maps.
- `src.compare.py`: compare `effective_filters_sha256` and `truth_status`; warn or mark reduced comparability when hashes differ or either side is non-explicit. Do not add recommendation re-scoring.
- `src.explain.py`: include the policy label/truth status in trust context and gate explanations; do not invent new recommendation logic.

V1 non-goals:

- No full compare methodology redesign.
- No new ACPM-specific run mode.
- No report prose rewrite beyond filter-policy disclosure.
- No export-only schema authority.
- No planner metadata threshold ownership.

### 6. Legacy Row Handling

Files:

- Modify `src/trust_identity.py`
- Test in `test_effective_filter_policy.py`

Plan:

- Leave legacy DB rows physically null.
- For rows with complete methodology snapshot and run-plan override evidence, return `truth_status=reconstructed`.
- For rows with only `campaigns.run_mode`, return `truth_status=inferred_limited` and avoid full threshold claims unless base gates are persisted.
- For rows with no safe evidence, return `truth_status=unknown` and `effective_filters=null`.
- Do not persist synthesized projections.
- Do not treat null as equivalent to default profile gates.

### 7. Post-Scoring Confirmation

Files:

- Implement in `src/effective_filter_policy.py`
- Call from `src/runner.py`
- Surface through `src/trust_identity.py`

Recommended v1 behavior:

- Include confirmation in v1.
- Store it inside `effective_filter_policy_json`.
- Confirmation compares helper-built expected effective filters to `scores["effective_filters"]`.
- `confirmed` means the persisted policy and scorer output agree.
- `mismatch` means the run has a trust failure and should not produce normal trust-bearing reports/export.
- `unavailable` is for legacy or explicit exceptional cases only.

Why it is worth adding:

- The current intended override merge happens in `runner.py`, while final application happens in `score.py`.
- The seam deliberately avoids making `score.py` write snapshot policy.
- A tiny hash comparison catches drift between those two paths without creating a second authority.

## Minimum Test Matrix

Create a new root-level `test_effective_filter_policy.py` to match the current repo pattern (`test_artifact_contract.py`, `test_governance.py`, `test_determinism.py`). Keep tests small and mostly helper/SQLite focused.

| Area | Test | Expected |
| --- | --- | --- |
| DB migration | `init_db(tmp_path / "lab.sqlite")` creates `campaign_start_snapshot.effective_filter_policy_json` | Column exists and `schema_version` is current. |
| DB migration | Simulated older DB migrates to v13 | Column added and existing rows remain null. |
| Canonical hash | Same effective filter map with reordered keys | Same `effective_filters_sha256`. |
| Profile default | Base gates with no layers | `policy_id=profile_default`, empty modifiers, effective filters equal base gates. |
| Custom mode layer | `run_plan.filter_overrides={"min_valid_warm_count": 1}` | `policy_id=user_directed_sparse_custom`, layer source is `run_plan.filter_overrides`, changed key includes `min_valid_warm_count`. |
| Quick mode layer | `run_plan.filter_overrides={"min_valid_warm_count": 3}` with base gate `3` | `policy_id=depth_required_relaxation`, no changed key when value is unchanged, authority chain still records execution mode. |
| YAML override | YAML override layered on top of custom/quick | `policy_modifiers=["campaign_override"]`, YAML layer wins on conflicting keys. |
| Confirmation success | Expected effective filters equal score result | `scoring_confirmation.status=confirmed`. |
| Confirmation mismatch | Expected effective filters differ from score result | `scoring_confirmation.status=mismatch` and caller can fail before reports/export. |
| Trust identity explicit | Row has v1 JSON | `load_run_identity(...).filter_policy` returns it with `sources.filter_policy=snapshot`. |
| Trust identity reconstructed | No v1 JSON, but methodology gates + run_plan overrides + campaign YAML snapshot exist | Projection is `truth_status=reconstructed`; no DB write-back. |
| Trust identity inferred | Only legacy `run_mode=custom` exists | Projection is `truth_status=inferred_limited`; no fake full threshold map. |
| Trust identity unknown | No useful persisted evidence | Projection is `truth_status=unknown`; effective filters are null. |
| Metadata projection | `generate_metadata_json()` with explicit policy | Top-level `filter_policy` exists; `methodology.eligibility_filters` remains base gates. |
| Export DB copy | `.qmap` export with source column populated | Exported DB includes and preserves `effective_filter_policy_json` via existing introspection copy. |
| List projection | Campaign list row has explicit policy | Compact label can be derived without loading full threshold display. |
| Compare projection | Two runs have different `effective_filters_sha256` | Compare emits reduced-comparability warning without recomputing rankings. |
| Report disclosure | Report surfaces filter policy from trust identity | No stale `10` fallback when persisted policy says `3`. |
| Explain disclosure | Explain includes policy/truth status in trust context | No new recommendation logic; only disclosure. |

Targeted command set for implementation verification:

- `.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick`
- `.\.venv\Scripts\python.exe -m pytest test_effective_filter_policy.py -q`
- `.\.venv\Scripts\python.exe -m pytest test_artifact_contract.py::test_trust_identity_artifact_completeness -q`
- `.\.venv\Scripts\python.exe -m pytest test_governance.py -q`
- `.\.venv\Scripts\ruff.exe check src\\effective_filter_policy.py src\\trust_identity.py src\\runner.py src\\export.py src\\report.py src\\report_campaign.py src\\compare.py src\\explain.py src\\db.py test_effective_filter_policy.py`

If mypy is used during implementation, run it narrowly on touched files first and report any imported backlog separately. The current repo has historically had imported mypy noise when checking broad modules.

## `min_valid_warm_count` Drift Policy

Do not block the DB migration or helper contract on the live-vs-stale `min_valid_warm_count` drift.

Do fix or neutralize the stale user-facing fallback before enabling report/report_campaign disclosure that depends on this seam. The schema can capture actual values and sources; reports must not continue displaying `10` when the persisted effective policy says `3`.

Governance boundary:

- The drift must be resolved before approving any new ACPM-specific relaxation.
- The drift should not delay persistence/projection infrastructure.
- The first implementation bundle should at least replace stale report fallback behavior with the persisted projection or an explicit unknown label.

## Risks of Getting This Wrong

- If write logic goes into `score.py`, scoring starts mutating snapshot identity and the ownership boundary blurs.
- If helper logic duplicates methodology loading before scoring, the persisted policy can diverge from the scorer's actual methodology.
- If readers bypass `trust_identity`, export/report/compare/history will grow separate shadow reconstruction rules.
- If `metadata.json` is treated as source of truth, regenerated exports can rewrite filter-policy history.
- If legacy null rows are backfilled as explicit, older runs become over-certified.
- If confirmation mismatch only logs a warning, normal reports may present untrusted methodology as valid.
- If compare/report are overbuilt in v1, this seam may become a broader recommendation-system refactor rather than a trust projection.

## Remaining Open Questions

- Should a confirmation mismatch fail the whole run status, set analysis status only, or stop only trust-bearing artifacts? Recommendation here is to stop normal trust-bearing reports/export, but exact status mutation needs implementation design.
- Should `src/effective_filter_policy.py` expose dataclasses or plain dict helpers? Plain dicts fit current surfaces, but dataclasses may reduce typo risk.
- Should `list_campaigns()` show filter policy by default, or only in a future verbose/details mode? The minimum v1 need is that a compact projection exists.
- Should `rankability_affecting_keys` initially include every changed elimination key, or only keys known to affect pass/eliminate/rankability in current scoring?

## Recommended Next Step

Use this report as the implementation-prep basis for a narrow plan that starts with `src/db.py`, `src/effective_filter_policy.py`, `src/trust_identity.py`, and `test_effective_filter_policy.py`, then layers `runner.py` write-path confirmation and finally small consumer projections.

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/scripts/helpers/verify_dev_contract.py`
