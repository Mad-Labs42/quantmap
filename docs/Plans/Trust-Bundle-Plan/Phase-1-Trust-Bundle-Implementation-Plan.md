# Phase 1 Trust Bundle Implementation Plan

Status: verified planning draft
Date: 2026-04-11
Scope: Phase 1 Trust Bundle only

Primary inputs:

- `docs/decisions/Phase-1-Trust-Bundle-Existing-State-Inventory.md`
- `docs/decisions/Phase-1-Trust-Bundle-Existing-State-Inventory-Codex.md`
- `docs/decisions/Phase-1-Trust-Bundle-Pre-Implementation-Contract.md`
- `docs/AUDITS/4-11/Post-Audit-Synthesis-Memo.md`
- Targeted verification of `src/db.py`, `src/runner.py`, `src/telemetry.py`,
  `src/score.py`, `src/report.py`, `src/report_campaign.py`,
  `src/report_compare.py`, `src/compare.py`, `src/export.py`, `rescore.py`,
  `src/audit_methodology.py`, `src/config.py`, `src/run_plan.py`, and
  `src/server.py`.

## 1. Purpose

Phase 1 hardens QuantMap's trust surfaces before broader portability,
telemetry expansion, optimization, or backend work. The goal is to make run
evidence self-contained enough to survive disk changes, report regeneration,
rescoring, comparison, export, and time.

Phase 1 covers only:

1. Snapshotting / self-containment
2. QuantMap code identity capture
3. Snapshot-first report identity
4. Layered runtime state
5. Trust-critical path/settings assumptions

Explicit non-goals:

- No telemetry provider architecture work.
- No backend abstraction.
- No broad packaging redesign.
- No optimization/search implementation.
- No root-cause attribution implementation.
- No broad runner/report refactor beyond what Phase 1 trust behavior requires.

## 2. Codebase Verification Summary

The first draft is directionally right, but one storage recommendation needs
tightening.

| Finding | Verified current reality | Plan consequence |
| --- | --- | --- |
| `campaign_start_snapshot` is the strongest run-start foundation | It stores campaign YAML content, campaign/baseline hashes, backend binary/model metadata, prompt hashes, sampling params, and environment fingerprint fields | Extend it for run-start trust state rather than creating a competing run-start snapshot table. |
| Methodology snapshotting is interpretation-time, not run-start | `src/score.py` writes partial anchors into `campaigns.notes_json.governance_methodology`; rescore can force new anchors | Add a real `methodology_snapshots` table and link scores/interpretation to it. Do not force methodology content into `campaign_start_snapshot`. |
| Existing export already references `methodology_snapshots` | `src/export.py` lists a nonexistent table and omits `campaign_start_snapshot`, `background_snapshots`, and `artifacts` | Create the real table, then fix export to copy the actual trust surfaces. |
| `campaign_start_snapshot` is treated as one row per campaign but not enforced by schema | Runner checks before insert, but compare reads the newest row via `ORDER BY id DESC`; table has no unique constraint | Migration must audit duplicates, choose or quarantine a canonical row, and enforce one canonical start snapshot per campaign. |
| Reports still mix DB snapshot and live baseline/profile state | `src/report.py` and `src/report_campaign.py` read live `baseline` for model/machine/methodology fields | Add one snapshot-first identity resolver and route reports through it. |
| `campaigns.status='complete'` is written before analysis/report | Runner marks campaign complete immediately after measurement, then runs scoring and reports | Treat `campaigns.status` as measurement lifecycle only and add explicit analysis/report/artifact status. |
| `artifacts.sha256` exists but is not populated | Report writers insert artifact path/type/time only | Extend artifact truth with status, hash use, producer, and error semantics. |
| `RunPlan` is the right runtime intent model but is in-memory only | Runner constructs it with effective campaign id, mode, selected values, paths, and overrides | Persist `RunPlan` as run-start intent JSON in the start snapshot. |
| Trust-critical path logic is split | `src.config` is a good foundation; runner derives baseline-specific lab roots; reports have hardcoded fallback roots; rescore assumes default baseline path | Centralize trust-critical path resolution and persist effective run paths. |

## 3. Critical Design Decision

### Decision: use a strict lifecycle split, not a second run-start snapshot

Adopt this storage shape:

1. Extend `campaign_start_snapshot` for run-start trust state.
2. Add first-class `methodology_snapshots` for interpretation/scoring truth.
3. Expose both through one shared snapshot-first identity resolver.

This is a verified refinement of the draft's Option A vs Option B choice. The
code supports Option A for run-start truth, but methodology is not truly a
run-start concept. A separate methodology table is not a competing truth store
if it has a different lifecycle owner and every consumer reaches it through the
same resolver.

Rules:

- Do not add a generic competing `trust_snapshot` table in Phase 1.
- Do not leave `campaigns.notes_json.governance_methodology` as the formal
  methodology authority.
- Do not let readers independently decide whether to use
  `campaign_start_snapshot`, `methodology_snapshots`, `notes_json`, or live disk.

## 4. Target Authority Model

After Phase 1:

| Concept | Authority |
| --- | --- |
| Campaign definition | `campaign_start_snapshot.campaign_yaml_content` and related metadata |
| Baseline definition | New baseline content/path/identity fields on `campaign_start_snapshot` |
| QuantMap code identity | New run-start QuantMap identity JSON on `campaign_start_snapshot` |
| Backend/binary identity | Existing backend/model fields on `campaign_start_snapshot`, with clarified labels |
| Requested runtime intent | New persisted `RunPlan` JSON on `campaign_start_snapshot` |
| Resolved runtime reality | Existing `configs.resolved_command`, `configs.runtime_env_json`, request/cycle evidence, and snapshot fields |
| Methodology/governance definition | New `methodology_snapshots` rows |
| Measurement state | `campaigns.status`, explicitly narrowed to measurement lifecycle for new writes |
| Interpretation/scoring state | New campaign-level analysis status fields and methodology snapshot linkage |
| Artifact/report state | Extended `artifacts` rows plus campaign-level report/artifact status |
| Report identity | One shared snapshot-first identity resolver |
| Legacy fallback | Explicitly labeled weaker evidence, never silent live-disk substitution |

## 5. Schema Plan

All schema changes should be append-only migrations in `src/db.py`.

### 5.1 `campaign_start_snapshot` run-start extensions

Add fields for new runs:

- `baseline_yaml_path TEXT`
- `baseline_yaml_content TEXT`
- `baseline_identity_json TEXT`
- `quantmap_identity_json TEXT`
- `run_plan_json TEXT`
- `snapshot_schema_version INTEGER`
- `snapshot_capture_quality TEXT`

Use JSON for identity groups that may evolve, rather than adding many model,
quantization, profile, and source-control columns. Keep existing scalar fields
where they are already useful.

Also add a duplicate-safety migration:

- Detect duplicate `campaign_start_snapshot.campaign_id` rows.
- If duplicates exist, choose the earliest row as canonical only if all
  duplicate hashes/content match; otherwise quarantine by leaving the unique
  index unapplied and failing loudly with an operator-facing migration error.
- Add `CREATE UNIQUE INDEX IF NOT EXISTS ux_campaign_start_snapshot_campaign_id
  ON campaign_start_snapshot(campaign_id)` after duplicates are safe.

Why: current writer preserves the original row, but the schema does not enforce
that and compare currently reads the newest row. Phase 1 must remove that
ambiguity.

### 5.2 `methodology_snapshots`

Create the table that export already assumes exists, but define it as the
formal interpretation-time authority:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `campaign_id TEXT NOT NULL REFERENCES campaigns(id)`
- `created_at TEXT NOT NULL`
- `snapshot_kind TEXT NOT NULL` (`scoring`, `rescore`, `legacy_partial`)
- `methodology_version TEXT`
- `profile_name TEXT`
- `profile_version TEXT`
- `profile_yaml_content TEXT`
- `registry_yaml_content TEXT`
- `weights_json TEXT`
- `gates_json TEXT`
- `anchors_json TEXT`
- `source_paths_json TEXT`
- `source_hashes_json TEXT`
- `capture_quality TEXT NOT NULL`
- `capture_source TEXT NOT NULL`
- `replaces_snapshot_id INTEGER`
- `is_current INTEGER NOT NULL DEFAULT 1`

Add a linkage field:

- `scores.methodology_snapshot_id INTEGER`

Recommended optional linkage:

- `campaigns.current_methodology_snapshot_id INTEGER`

Migration behavior:

- Backfill one `legacy_partial` row from
  `campaigns.notes_json.governance_methodology` where present.
- Set `capture_quality='legacy_partial'` for backfilled rows.
- Do not invent missing profile or registry content for legacy rows.

### 5.3 Layered status fields

Keep `campaigns.status` for compatibility, but define new writes as measurement
lifecycle only. Add:

- `analysis_status TEXT`
- `analysis_started_at TEXT`
- `analysis_completed_at TEXT`
- `analysis_failed_at TEXT`
- `analysis_failure_reason TEXT`
- `report_status TEXT`
- `report_started_at TEXT`
- `report_completed_at TEXT`
- `report_failed_at TEXT`
- `report_failure_reason TEXT`
- `status_model_version INTEGER`

Allowed status values:

- measurement: current `campaigns.status` values (`pending`, `running`,
  `complete`, `failed`, `aborted`)
- analysis/report: `pending`, `running`, `complete`, `failed`, `skipped`,
  `legacy_unknown`, `derived_legacy`

Do not backfill old rows as native complete. If derived statuses are written,
mark them `derived_legacy`.

### 5.4 Artifact truth extensions

Extend `artifacts`:

- `status TEXT`
- `producer TEXT`
- `error_message TEXT`
- `updated_at TEXT`
- `verification_source TEXT`

Use existing `sha256` for new successful artifacts. For legacy rows, leave
`sha256` and `status` null unless a deliberate migration computes a hash and
marks `verification_source='posthoc_legacy_hash'`.

### 5.5 Export-compatible trust surfaces

Update export to include:

- `campaign_start_snapshot`
- `methodology_snapshots`
- `artifacts`
- `background_snapshots` unless lite mode explicitly excludes them
- `schema_version`
- manifest fields for run identity and exporter identity separately

Remove stale assumptions about nonexistent columns such as `metadata_json` and
`raw_json`.

## 6. New Shared Modules

### 6.1 `src/code_identity.py`

Responsible for capturing QuantMap code identity at run start.

Minimum output:

- `quantmap_version`
- `methodology_version_label`
- `git_commit`
- `git_dirty`
- `git_describe`
- `source_tree_sha256`
- `identity_source`
- `capture_time_utc`
- `capture_errors`

Rules:

- Git metadata is best effort.
- Source tree hash is the fallback when git metadata is unavailable.
- This is QuantMap identity only; backend `build_commit` must never populate it.

### 6.2 `src/trust_identity.py`

Responsible for one shared snapshot-first identity model.

Minimum API shape:

- `load_run_identity(campaign_id, db_path) -> TrustIdentity`
- `load_legacy_identity(campaign_id, db_path) -> TrustIdentity`
- `format_identity_sources(identity) -> dict`

Readers must use this module instead of independently loading live baseline,
profile, campaign YAML, or path defaults for historical identity.

Consumers:

- `src/report.py`
- `src/report_campaign.py`
- `rescore.py`
- `src/compare.py`
- `src/report_compare.py`
- `src/export.py`
- `src/audit_methodology.py`

## 7. Workstreams

### A. Snapshotting and self-containment

File-level responsibilities:

| File | Responsibility |
| --- | --- |
| `src/db.py` | Add migrations for run-start snapshot fields, methodology snapshots, status fields, and artifact fields. |
| `src/telemetry.py` | Extend `collect_campaign_start_snapshot` to include baseline content/path, baseline identity JSON, QuantMap identity JSON, and capture quality. |
| `src/runner.py` | Pass persisted `RunPlan` JSON into snapshot capture; preserve original DB snapshot on resume; write sidecar from DB canonical content if a row already exists. |
| `src/run_plan.py` | Add serialization helper for JSON-safe persisted run intent. |
| `src/governance.py` | Provide serializable profile/registry content or helper data for methodology snapshotting. |

Key implementation details:

- Baseline content must be verbatim text.
- Baseline hash must be computed from the same bytes persisted.
- Baseline identity JSON may include parsed `name`, model name, quantization,
  reference anchors, runtime build label, and source path, but the content is
  the authority.
- `campaign_yaml_snapshot.yaml` remains convenience-only and must not override
  DB snapshot content.

### B. QuantMap code identity capture

File-level responsibilities:

| File | Responsibility |
| --- | --- |
| `src/code_identity.py` | New capture helper for version/git/source hash. |
| `src/version.py` | Continue providing current process version labels. |
| `src/telemetry.py` / `src/runner.py` | Persist code identity at campaign start. |
| `src/report.py`, `src/report_campaign.py`, `src/export.py` | Display run identity separately from exporter/current-process identity. |

Key implementation details:

- `build_commit` remains a claimed backend build label.
- Report wording should use labels like `QuantMap run identity` and
  `Backend build label`.
- Legacy rows with no QuantMap identity show `legacy unrecorded` or `unknown`.

### C. Snapshot-first identity resolver

File-level responsibilities:

| File | Responsibility |
| --- | --- |
| `src/trust_identity.py` | New shared resolver and fallback labeling. |
| `src/report.py` | Stop using live baseline/profile fields for historical identity when resolver data exists. |
| `src/report_campaign.py` | Use resolver for model, quant, baseline, methodology, runtime, and source labels. |
| `rescore.py` | Use resolver to decide snapshot-complete vs legacy-incomplete behavior. |
| `src/compare.py`, `src/report_compare.py` | Use resolver/methodology snapshots for compatibility and identity display. |
| `src/export.py` | Export resolver-backed run identity and separate exporter identity. |

Key implementation details:

- Every field should carry a source category where needed:
  `snapshot`, `methodology_snapshot`, `legacy_hash_only`, `derived_legacy`,
  `current_input_explicit`, `unknown`.
- Report regeneration tests must mutate live baseline/profile files and prove
  output identity does not drift when snapshots exist.

### D. Layered runtime state

File-level responsibilities:

| File | Responsibility |
| --- | --- |
| `src/runner.py` | Treat `campaigns.status` as measurement state; write analysis/report statuses around post-measurement processing. |
| `src/score.py` | Create/update methodology snapshot; link scores to methodology snapshot; write analysis status outcomes. |
| `src/report.py`, `src/report_campaign.py` | Write artifact/report status rows and campaign report status. |
| `src/db.py` | Add status migrations and helper functions if useful. |
| `quantmap.py` / list/status paths | Display layered state without collapsing it into campaign complete. |

Key implementation details:

- A report failure after successful measurement must leave measurement complete
  and report failed.
- A scoring failure after successful measurement must leave measurement complete
  and analysis failed.
- `report_v2.md` non-fatal failure should still be persisted as an artifact or
  report warning, not only logged.

### E. Trust-critical path/settings assumptions

File-level responsibilities:

| File | Responsibility |
| --- | --- |
| `src/config.py` | Remain the shared infrastructure path foundation. |
| `src/runner.py` | Persist effective lab root, DB path, results path, state path, and baseline path in `run_plan_json`. |
| `src/report.py`, `src/report_campaign.py` | Remove report-local hardcoded lab-root authority for historical identity; use persisted run paths or explicit legacy lookup. |
| `rescore.py` | Avoid default-baseline assumptions for historical identity; require snapshot or explicit current-input mode for legacy rescoring. |
| `src/export.py` | Stop deriving trust surfaces from stale path/table assumptions. |

Key implementation details:

- Full packaging/generalization remains out of scope.
- Phase 1 only centralizes path behavior that directly affects historical trust
  claims and report/export/rescore identity.

## 8. Legacy Behavior Policy

For legacy runs:

- Missing baseline content displays `legacy hash-only`.
- Missing methodology content displays `legacy incomplete methodology`.
- Missing QuantMap identity displays `legacy unrecorded` or `unknown`.
- Missing run plan displays `derived legacy intent` if reconstructed from DB.
- Missing analysis/report status displays `legacy unknown` or `derived legacy`.
- Existing artifact rows with no hash/status display `legacy unverified artifact`.

Disallowed:

- Silently filling baseline identity from current `configs/baseline.yaml`.
- Silently filling methodology identity from current profile/registry files.
- Guessing historical QuantMap commit from the current checkout.
- Treating old `campaigns.status='complete'` as whole-pipeline success.
- Treating artifact path existence as proof of successful artifact generation.

## 9. Implementation Sequence

### Step 1. Schema and authority migrations

- Add run-start snapshot fields.
- Add duplicate audit and unique index for `campaign_start_snapshot.campaign_id`.
- Add `methodology_snapshots`.
- Add score/methodology linkage.
- Add analysis/report status fields.
- Add artifact status/hash/error fields.

### Step 2. Writers

- Extend campaign-start snapshot capture in `src/telemetry.py` and `src/runner.py`.
- Persist `RunPlan` JSON.
- Persist QuantMap code identity.
- Update `src/score.py` to write formal methodology snapshots.
- Update analysis/report generation to write layered statuses.
- Update artifact registration to write status, hash, producer, and errors.

### Step 3. Shared identity resolver

- Add `src/trust_identity.py`.
- Encode fallback labeling in one place.
- Add tests for snapshot-complete and legacy-incomplete campaigns.

### Step 4. Reader migration

- Migrate `src/report.py`.
- Migrate `src/report_campaign.py`.
- Migrate `rescore.py`.
- Migrate `src/compare.py` / `src/report_compare.py`.
- Migrate `src/export.py`.
- Migrate `src/audit_methodology.py`.

### Step 5. Legacy labels and docs

- Ensure reports/export/rescore visibly label weak legacy evidence.
- Update docs describing trust surfaces, report identity, export fidelity, and
  status semantics.

### Step 6. Cleanup

- Demote `campaign_yaml_snapshot.yaml` to convenience-only output.
- Retire `campaigns.notes_json.governance_methodology` as authoritative after
  migration readers move to `methodology_snapshots`.
- Remove stale export table/column references.
- Remove or quarantine report-local hardcoded lab-root identity paths.

## 10. Verification Plan

### Required tests

- New run persists campaign content, baseline content, baseline identity,
  QuantMap identity, backend identity, run plan JSON, methodology snapshot,
  layered statuses, and artifact metadata.
- Regenerated report uses snapshot identity after live baseline/profile/config
  files are changed.
- Legacy run with only baseline hash displays `legacy hash-only`, not current
  baseline as historical truth.
- Legacy run with only `notes_json.governance_methodology` displays
  `legacy incomplete methodology`.
- Rescore on snapshot-complete run uses snapshot baseline/methodology or
  requires explicit current-input mode.
- Rescore on legacy-incomplete run labels current-input behavior explicitly.
- Compare blocks or warns based on `methodology_snapshots`, not live profile
  state.
- Export includes start snapshot, methodology snapshots, artifact rows, and
  separates run identity from exporter identity.
- Measurement success plus analysis failure is displayed as measurement
  complete and analysis failed.
- Measurement success plus report failure is displayed as measurement complete
  and report failed.
- Artifact rows for new reports include status and hash when produced.
- Duplicate `campaign_start_snapshot` rows are detected before applying the
  unique index.

### High-value scenario tests

1. Run campaign, mutate baseline/model/profile labels on disk, regenerate both
   reports, verify identity does not drift.
2. Force scoring failure after measurement, verify DB status layering and
   operator output.
3. Force `report_v2.md` failure, verify primary measurement/scoring truth and
   artifact failure truth remain separate.
4. Export old and new campaigns, verify legacy labels and run/exporter identity
   separation.
5. Run compare across campaigns with matching and mismatched methodology
   snapshots.

## 11. Risks And Controls

| Risk | Control |
| --- | --- |
| Creating two run-start snapshot authorities | Extend `campaign_start_snapshot`; do not add a generic competing trust snapshot table. |
| Making methodology a run-start field when it is interpretation-time truth | Add `methodology_snapshots` and link scores/analysis to it. |
| Writer/reader partial rollout | Land snapshot writers, resolver, and primary report readers in the same Phase 1 bundle. |
| Silent legacy inference | Centralize fallback labels in `src/trust_identity.py` and test legacy rows. |
| Breaking legacy campaign listing/resume | Keep `campaigns.status` column, but document and write it as measurement lifecycle for new runs. |
| Export overclaiming forensic fidelity | Export actual trust tables and declare incomplete legacy provenance where applicable. |
| Report stack retaining two identity paths | Both report paths must consume the resolver before Phase 1 is complete. |

## 12. Phase 1 Deliverables

Phase 1 is complete only when QuantMap has:

- Extended run-start snapshot authority in `campaign_start_snapshot`.
- Formal interpretation-time `methodology_snapshots`.
- Persisted QuantMap code identity for new runs.
- Persisted `RunPlan` intent for new runs.
- One shared snapshot-first identity resolver.
- Layered measurement, analysis, and report/artifact status.
- Artifact rows with status/hash/error semantics for new artifacts.
- Snapshot-first report/rescore/compare/export behavior.
- Explicit legacy fallback labels.
- Trust-critical path behavior centralized or persisted where it affects
  historical identity.

## 13. Execution Decisions Locked Before Coding

1. `baseline_identity_json`, `quantmap_identity_json`, and `run_plan_json`
   remain narrow JSON payloads with documented source labels. Do not expand
   them into a framework unless implementation pressure proves the need.
2. Use `scores.methodology_snapshot_id` first. Add
   `campaigns.current_methodology_snapshot_id` only if reader code becomes
   simpler with the campaign-level pointer.
3. Analysis/report status lives directly on `campaigns` for Phase 1. A separate
   phase-status table is deferred unless direct columns become visibly awkward.
4. Duplicate `campaign_start_snapshot` rows fail migration loudly with a manual
   remediation message. Do not silently quarantine ambiguous trust history.
5. Rescore defaults to snapshot-locked mode for snapshot-complete runs. Current
   live baseline/profile rescoring must require an explicit current-input flag.

## 14. Final Recommendation

Proceed with the strict lifecycle split:

- `campaign_start_snapshot` is the run-start trust authority.
- `methodology_snapshots` is the interpretation-time trust authority.
- `src/trust_identity.py` is the only public identity authority for reports,
  rescore, compare, and export.

This preserves the best existing foundation without forcing methodology into
the wrong lifecycle bucket. It also avoids the biggest Phase 1 failure mode:
adding a second generic snapshot mechanism while old live-disk readers continue
to quietly define historical truth.
