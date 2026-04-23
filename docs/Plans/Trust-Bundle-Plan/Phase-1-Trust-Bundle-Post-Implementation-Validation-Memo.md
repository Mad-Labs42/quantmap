# Phase 1 Trust Bundle Post-Implementation Validation Memo

Status: validation findings for core implementation pass 1
Date: 2026-04-11

## Bottom Line

Phase 1 Trust Bundle core implementation pass 1 is complete and ready for
deeper validation. It should not yet be called stable or done.

The remaining risk is behavioral, not planning. The new trust surfaces exist,
and several focused smoke checks pass, but reader convergence is incomplete.
The most important remaining issue is methodology: QuantMap now persists
`methodology_snapshots`, but scoring/reporting can still use live profile and
registry objects in paths that should be snapshot-locked before Phase 1 is
called stable.

## Validation Scope

This pass checked the implementation against three goals:

1. Historical truth validation: baseline/profile/model identity drift,
   regenerated reports, rescore, compare, and export behavior.
2. Migration and legacy behavior validation: old rows, partial methodology,
   artifact rows, duplicate snapshot detection, and legacy labels.
3. Reader convergence validation: whether report, rescore, compare, export,
   and methodology audit now use the same trust model.

This was a focused post-implementation validation pass. It was not new feature
work and not another broad audit.

## Commands And Probes Run

| Probe | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m py_compile ...` over changed Python modules | Passed |
| `.venv\Scripts\python.exe test_governance.py` | Passed |
| `.venv\Scripts\python.exe test_determinism.py` | Passed |
| Fresh temp DB schema v9 initialization | Passed |
| Temp DB duplicate `campaign_start_snapshot` migration guard | Passed; migration fails loudly |
| Temp DB resolver check with snapshot baseline vs live fallback | Passed; snapshot baseline wins |
| Temp DB export smoke check | Passed; export includes trust tables |
| Rescore legacy row without baseline snapshot | Passed; refuses snapshot-locked rescore |
| `.venv\Scripts\python.exe -m pytest ...` | Not runnable; `pytest` is not installed in `.venv` |
| `git diff --check` | Passed |

## What Worked As Intended

| Area | Validation result |
| --- | --- |
| Schema foundation | Schema v9 initializes with run-start snapshot extensions, `methodology_snapshots`, layered status fields, and artifact status fields. |
| Duplicate snapshot handling | Unsafe duplicate `campaign_start_snapshot` rows stop migration instead of being silently quarantined. |
| Snapshot baseline resolution | `load_baseline_for_historical_use()` returns persisted baseline YAML before live fallback. |
| QuantMap identity capture | `src/code_identity.py` captures version/git/source-tree identity as a narrow run-start helper. |
| Rescore default | Legacy run without baseline content is refused unless `--current-input` is used. |
| Export shape | Export now includes `campaign_start_snapshot`, `methodology_snapshots`, `artifacts`, and separates run identity from exporter identity. |
| Basic regression scripts | Governance and determinism scripts pass in the project `.venv`. |

## Findings

| Severity | Area | Finding | Evidence | Required action before stable |
| --- | --- | --- | --- | --- |
| High | Methodology truth | Persisted `methodology_snapshots` are not yet fully authoritative for scoring. `score_campaign()` still builds scoring behavior from live `governance.BUILTIN_REGISTRY`, live `governance.DEFAULT_PROFILE`, `profile.weights`, and `profile.gate_overrides`. Existing snapshots preserve anchors, but not the full profile/registry behavior. | `src/score.py` uses live `governance` objects around registry/profile loading and scoring. | Make snapshot-complete scoring/rescore construct weights, gates, active metrics, and registry definitions from `methodology_snapshots`, or explicitly block historical rescoring when full methodology content is missing. |
| High | Report methodology display | `report_campaign.py` still displays methodology from `scores_result["scoring_profile"]` or live `governance.DEFAULT_PROFILE`. This can show current profile details even when historical methodology should be snapshot-first. | `src/report_campaign.py` reads `scores_result.get("scoring_profile", governance.DEFAULT_PROFILE)` and then `profile.weights` / `profile.gate_overrides`. | Route methodology display through `TrustIdentity.methodology` / `methodology_snapshots`, with legacy labels for incomplete rows. |
| High | Legacy methodology migration | Schema v9 creates `methodology_snapshots`, but does not backfill legacy rows from `campaigns.notes_json.governance_methodology`. The resolver can read `notes_json`, but the formal table remains empty until scoring runs. | Migration v9 creates the table; `_load_methodology_snapshot()` has a `notes_json` fallback. | Add an explicit legacy backfill or document that first rescore creates `legacy_partial` snapshots. Prefer migration/backfill for export and compare consistency. |
| Medium | Report fallback semantics | `report.py` and `report_campaign.py` pass `allow_current_input=True` to baseline resolution. This labels missing snapshot fallback as `current_input_explicit`, but report generation did not necessarily receive an explicit user flag. | `src/report.py` and `src/report_campaign.py` call `load_baseline_for_historical_use(... allow_current_input=True)`. | Use a clearer label such as `current_input_report_fallback`, or require explicit report/regeneration mode for current-file fallback. |
| Medium | Compare convergence | `compare.py` still reads `campaign_start_snapshot` directly and uses `ORDER BY id DESC`. The new unique index reduces duplicate risk after migration, but compare does not yet consume the shared trust identity resolver for run identity/source labels. | `src/compare.py` has direct snapshot query. | Either route compare through `trust_identity` or explicitly document that compare reads only environment deltas directly and identity/methodology through resolver-backed paths. |
| Medium | Artifact/report state | `report_status='complete'` can be written even when `report_v2.md` fails, because primary report success is treated as the campaign-level report status. The failed `report_v2_md` artifact is recorded, but the campaign-level status can hide partial artifact failure. | Runner records failed `report_v2_md` artifact but later marks report status complete. | Define whether `report_status` means primary report success or all report artifacts success. Consider `artifact_status` or `report_status='partial'`. |
| Medium | Artifact readers | New artifact rows can store status/hash/error, but report artifact sections still mostly display path/existence and do not surface richer artifact truth consistently. | `report_campaign.py` supporting artifacts query shows `artifact_type`, `path`, `created_at`; report compact index uses filesystem checks. | Update artifact sections/status views to display artifact status, hash/verification source, and failure metadata. |
| Medium | Export privacy redaction | Export now includes trust tables, but `_redact_env()` still references stale `campaigns.metadata_json` and `requests.raw_json` columns and swallows failures. | `src/export.py` `_redact_env()` queries stale columns inside broad `except`. | Replace redaction with schema-aware redaction for actual columns or label strip mode as not yet trust-validated. |
| Medium | Plan/doc drift | The implementation plan still contains older wording about choosing/quarantining duplicate snapshots, while the locked decision section says fail loudly. | Section 5.1 and Section 13 conflict. | Update the plan so duplicate handling is consistently fail-loud. |
| Low | Snapshot uniqueness | Fresh DBs get the unique index through migration v9, not the base `CREATE TABLE`. This is acceptable, but uniqueness depends on migration execution. | DDL lacks inline unique constraint; migration adds index. | Keep as-is if `init_db()` is mandatory before writes; add a schema assertion test. |
| Low | Pytest availability | Direct scripts pass, but pytest cannot run because the dependency is missing in `.venv`. | `.venv\Scripts\python.exe -m pytest` fails with `No module named pytest`. | Install/test-dependency path or keep direct-script validation as the supported local check. |

## Reader Convergence Status

| Reader | Current convergence status | Notes |
| --- | --- | --- |
| `src/report.py` | Partial | Uses snapshot baseline and run identity resolver, but still permits current-input fallback by default and can invoke live methodology through scoring. |
| `src/report_campaign.py` | Partial | Uses snapshot baseline and run identity resolver, but methodology display still uses live/scoring profile objects. |
| `rescore.py` | Mostly good for baseline | Snapshot-locked baseline default works; methodology still depends on live score profile/registry behavior. |
| `src/compare.py` | Partial | Methodology path is resolver-backed through `audit_methodology`, but environment/start snapshot and identity are still direct. |
| `src/report_compare.py` | Mostly indirect | Renders `CompareResult`; remaining risk comes from `compare.py` data model. |
| `src/export.py` | Improved, needs privacy check | Exports trust tables and run/exporter identity split; redaction logic is stale. |
| `src/audit_methodology.py` | Good direction | Reads methodology through `trust_identity`, but legacy backfill/table completeness still matters. |

## Historical Truth Validation Checklist

These scenarios should be run before calling Phase 1 stable:

- Run a new campaign, then change baseline model name/quantization/reference
  values on disk, regenerate both reports, and verify report identity stays
  snapshot-sourced.
- Change profile weights/gates and registry metric definitions on disk, then
  rescore a snapshot-complete run. Verify scoring either uses the methodology
  snapshot or refuses to proceed without an explicit current-input/migration
  mode.
- Change model path labels/environment paths and regenerate reports. Verify
  report identity uses snapshot/run-plan values where available.
- Export a snapshot-complete run and verify the bundle contains run identity,
  exporter identity, baseline content, methodology snapshot content, artifact
  rows, and legacy labels where relevant.
- Compare two campaigns with matching and mismatched methodology snapshots.
  Verify warnings come from stored methodology, not current profile files.

## Migration And Legacy Checklist

These legacy cases still need direct validation:

- Old row with `baseline_yaml_sha256` but no `baseline_yaml_content`.
- Old row with `campaigns.notes_json.governance_methodology` but no
  `methodology_snapshots` row.
- Old row with no QuantMap code identity.
- Old artifacts with null `sha256`, null `status`, and existing paths.
- DB with duplicate `campaign_start_snapshot` rows.
- Legacy report regeneration where current baseline/profile files differ from
  the historical run.

Expected behavior:

- No silent upgrade from current files to historical truth.
- Labels such as `legacy_hash_only`, `legacy_incomplete`,
  `legacy_unrecorded`, `derived_legacy`, or a clearly named current-input
  fallback must be visible.
- Duplicate snapshots must stop migration until manually remediated.

## Stabilization Items Before Calling Phase 1 Stable

1. Make methodology snapshots actually authoritative for scoring/rescore/report
   methodology display, not just persisted beside live methodology behavior.
2. Backfill or formally bridge legacy `notes_json.governance_methodology` into
   `methodology_snapshots`.
3. Tighten report fallback labeling so current-file fallback is not called
   explicit unless the user chose it.
4. Decide and implement campaign-level `report_status` semantics for partial
   artifact success.
5. Surface artifact status/hash/error in artifact readers and report sections.
6. Fix export redaction against the real schema.
7. Align the implementation plan text with the fail-loud duplicate decision.
8. Add dedicated tests for resolver behavior, duplicate migration failure,
   legacy labels, report regeneration drift, rescore snapshot-locking, and
   export identity separation.

## Validation Verdict

Core implementation pass 1 is meaningful progress. The DB shape, run-start
snapshot extensions, code identity capture, resolver, rescore baseline lock,
and export shape are all moving in the right direction.

The bundle is not yet stable because methodology and some report/artifact
readers still have shadow-truth risk. The next work should be stabilization of
this pass, especially methodology snapshot authority and reader convergence,
before moving to any broader subsystem.
