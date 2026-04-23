# Phase 1.1 Trust Bundle Stabilization Pre-Implementation Plan

**Status:** Pre-implementation plan, pending review  
**Date:** 2026-04-11  
**Scope:** Phase 1.1 Trust Bundle stabilization only  
**Primary inputs:** Phase 1 implementation plan, Phase 1 post-implementation validation memo, Phase 1 pre-implementation contract, existing-state inventories, post-audit synthesis memo, and current code interrogation.

---

## 1. Purpose

Phase 1.1 is a stabilization pass for the Phase 1 Trust Bundle core implementation.

It is not a new broad audit. It is not Phase 2. It is not a report redesign, telemetry architecture effort, backend abstraction, optimization implementation, or packaging cleanup.

Its purpose is to make the Phase 1 trust surfaces stable enough that Phase 1 can be called done: historical identity must be snapshot-first, methodology must not drift through live files, readers must converge on the same trust model, and legacy evidence must be labeled honestly instead of silently upgraded.

---

## 2. Why Phase 1.1 Exists

The Phase 1 core implementation pass added the right foundations:

- run-start snapshot extensions
- baseline content capture
- QuantMap code identity capture
- `methodology_snapshots`
- layered analysis/report status fields
- richer artifact columns
- `src/code_identity.py`
- `src/trust_identity.py`
- snapshot-locked baseline behavior in rescore
- export inclusion of trust tables and run/exporter identity separation

The post-implementation validation memo concluded that this is real progress, but not yet stable.

The central remaining problem is that some readers and scoring paths still treat current live files or live governance objects as truth after persisted trust snapshots exist. That creates shadow truth and undermines the reason Phase 1 exists.

---

## 3. Stabilization Goals

Before Phase 1 can be called stable:

1. Historical methodology authority must come from `methodology_snapshots`, not live governance/profile/registry objects.
2. Snapshot-complete historical rescore must be snapshot-locked for both baseline and methodology.
3. Legacy methodology must be formalized as partial evidence, not silently reconstructed.
4. Reports must not use implicit current-file fallback as historical identity or methodology authority.
5. Report methodology display must be snapshot-first.
6. Major readers must converge on shared trust helpers for historical trust claims.
7. Campaign-level report status must not overstate artifact success.
8. Artifact rows must be visible enough in reports/exports to expose failure, hash, and verification state.
9. Export must be non-misleading about redaction, provenance completeness, and legacy gaps.
10. Legacy runs must show weaker evidence labels instead of being silently upgraded from current files.

---

## 4. Locked Design Decisions

### 4.1 Methodology Authority

`methodology_snapshots` is the Phase 1.1 historical methodology authority.

Do not add another methodology truth store. Do not leave `notes_json.governance_methodology` as a parallel authority. Do not let historical scoring/reporting read current `governance.DEFAULT_PROFILE`, current profile files, or current registries when complete methodology snapshots exist.

Current-run scoring may still load live methodology at the start of the run, but it must persist the effective methodology snapshot and downstream historical readers must use that snapshot.

### 4.2 Historical Scoring vs Current-Input Rescoring

Snapshot-locked historical scoring/rescoring must require:

- baseline snapshot content
- methodology snapshot content or structured methodology data sufficient for scoring
- explicit legacy/quality labels

Current-input rescoring remains allowed only as an explicit mode and must be labeled as current-input.

### 4.3 Legacy Methodology

Legacy `campaigns.notes_json.governance_methodology` should be bridged into `methodology_snapshots` as `legacy_partial` where possible.

That bridge is for consistent display, export, audit, and compare behavior. It is not proof of complete historical scoring authority.

### 4.4 Report Fallback

Reports must not treat current files as historical truth by default.

If snapshot data is absent, reports should display weaker evidence labels such as `legacy_hash_only`, `legacy_partial_methodology`, `legacy_status_derived`, `legacy_artifact_path_only`, `unknown`, or `incomplete`.

Current-file fallback must require an explicit current-input mode or be labeled as non-authoritative convenience data.

### 4.5 Reader Convergence

`src/trust_identity.py` should remain a narrow shared trust read path. It should expose only the helpers needed for Phase 1.1:

- run/baseline identity loading
- methodology snapshot loading and quality labels
- historical scoring material loading
- artifact status summaries
- legacy label helpers

Do not turn it into a broad framework.

### 4.6 Layered Status

Keep layered status on `campaigns` for Phase 1.1. Use artifact rows as per-artifact truth.

Add or standardize `report_status='partial'` for mixed outcomes where the primary report phase produced usable output but one or more expected artifacts failed or are incomplete. This decision needs approval because it changes visible status semantics.

### 4.7 Export Alignment

Export must be non-misleading before Phase 1 is closed. Full case-file redesign can wait.

Export should be schema-aware, distinguish run identity from exporter identity, preserve trust tables, and label provenance completeness and legacy gaps clearly.

---

## 5. Scope

### In Scope

- Methodology snapshot authority for historical scoring, rescore, reports, audit, compare, and export.
- Legacy partial methodology bridge/backfill.
- Snapshot-first report methodology and identity behavior.
- Reader convergence through narrow trust helpers.
- Campaign/report status semantics needed to avoid misleading completion claims.
- Artifact status visibility in reports and export metadata.
- Export redaction/schema honesty.
- Legacy labels and fallback tightening.
- Focused tests and validation scenarios.

### Out of Scope

- Telemetry provider architecture.
- Backend abstraction.
- Full report stack consolidation.
- Full export/case-file redesign.
- Optimization or recommendation implementation.
- Root-cause attribution implementation.
- Broad runner refactor.
- Broad packaging or deployment cleanup.
- General code cleanup unrelated to trust surfaces.

---

## 6. Workstreams

### Workstream A - Methodology Authority Stabilization

**Goal:** Make persisted methodology snapshots authoritative for historical trust behavior.

Work:

1. Add a narrow methodology snapshot loader in `src/trust_identity.py`.
2. Define a small rehydrated methodology structure for historical scoring inputs:
   - weights
   - gates
   - anchors/reference values
   - profile content/hash/path
   - registry content/hash/path
   - methodology version
   - capture quality/source
3. Update `src/score.py` so historical scoring/rescore can use rehydrated snapshot methodology rather than live governance objects.
4. Preserve current-run scoring behavior only as the source of the initial effective snapshot.
5. Add a legacy bridge/backfill path from `campaigns.notes_json.governance_methodology` to `methodology_snapshots` with `capture_quality='legacy_partial'`.
6. Block snapshot-locked rescore when methodology evidence is missing or only `legacy_partial`, unless explicit current-input mode is used.

Do not:

- create a new methodology store
- redesign governance profile loading
- infer full historical methodology from partial legacy notes

Primary files:

- `src/trust_identity.py`
- `src/score.py`
- `src/db.py`
- `rescore.py`
- `src/governance.py`
- tests around methodology/rescore/reporting

### Workstream B - Report Methodology and Identity Stabilization

**Goal:** Reports must show historical identity and methodology from persisted trust evidence.

Work:

1. Remove implicit current-file authority from report identity paths.
2. Replace default `allow_current_input=True` report behavior with snapshot-first/legacy-label behavior.
3. Update report methodology sections to read `methodology_snapshots` before any live/default profile.
4. Display legacy methodology as partial/incomplete when only legacy notes exist.
5. Ensure fallback labels distinguish:
   - snapshot-complete
   - legacy hash-only
   - legacy partial methodology
   - unknown/incomplete
   - explicit current-input
6. Apply the same trust evidence semantics to both report stacks without merging them.

Primary files:

- `src/report.py`
- `src/report_campaign.py`
- `src/trust_identity.py`
- `src/audit_methodology.py`

### Workstream C - Reader Convergence

**Goal:** Remove remaining independent trust readers where they make historical trust claims.

Work:

1. Update `src/compare.py` to stop querying `campaign_start_snapshot` directly for identity-like claims.
2. Confirm `src/report_compare.py` inherits the corrected compare behavior or adjust it if needed.
3. Confirm `src/audit_methodology.py` reads methodology identity through the shared trust path.
4. Inspect `src/explain.py` for historical trust claims and migrate only those claims if present.
5. Keep `src/doctor.py` and `src/selftest.py` out of scope unless they present historical trust claims.

Primary files:

- `src/trust_identity.py`
- `src/compare.py`
- `src/report_compare.py`
- `src/audit_methodology.py`
- `src/explain.py`

### Workstream D - Report and Artifact Status Semantics

**Goal:** Campaign-level status must not imply artifact/report success that did not happen.

Work:

1. Define `report_status` values and meaning:
   - `pending`
   - `running`
   - `complete`
   - `partial`
   - `failed`
   - `skipped`
   - `legacy_unknown`
2. Treat `complete` as all required report artifacts for that phase succeeded.
3. Treat `partial` as usable report output with one or more failed/missing expected artifacts.
4. Keep per-artifact detail in `artifacts`.
5. Update readers so `campaigns.status='complete'` and `campaigns.report_status='complete'` are not conflated.

Primary files:

- `src/db.py`
- `src/runner.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/trust_identity.py`

Approval needed:

- New/standardized `report_status='partial'` visible semantics.

### Workstream E - Artifact Reader Convergence

**Goal:** Artifact rows become visible enough to support trust decisions.

Work:

1. Add a narrow artifact summary helper in `src/trust_identity.py` or reuse an existing DB helper if present.
2. Reports should display artifact status, hash, verification source, and error message when available.
3. Reports should label legacy path-only artifacts as legacy/path-only rather than verified.
4. Export should include artifact status/completeness in manifest-level metadata.
5. File existence checks may remain as legacy fallback but must not override artifact row truth.

Primary files:

- `src/trust_identity.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/db.py`

### Workstream F - Export Alignment

**Goal:** Export should be trust-bundle aligned and non-misleading.

Work:

1. Fix stale redaction assumptions in `src/export.py`.
2. Make redaction schema-aware for current tables/columns.
3. Do not swallow redaction failures silently when they affect trust claims.
4. Add export manifest labels for:
   - run identity completeness
   - methodology completeness
   - artifact completeness
   - legacy/incomplete evidence
   - exporter identity
5. Preserve the distinction between historical run identity and current exporter identity.

Primary files:

- `src/export.py`
- `src/trust_identity.py`
- export tests/smoke checks

### Workstream G - Legacy and Migration Behavior Tightening

**Goal:** Legacy rows must behave predictably and honestly.

Work:

1. Backfill legacy methodology partial rows from `notes_json.governance_methodology` where possible.
2. Keep missing baseline content as `legacy_hash_only` or `unknown`; do not fill from current baseline as historical truth.
3. Keep duplicate campaign snapshots as fail-loud migration blockers if they do not match cleanly.
4. Add stable labels for incomplete analysis/report/artifact status:
   - `legacy_status_derived`
   - `legacy_artifact_path_only`
   - `legacy_unknown`
5. Ensure report/rescore/compare/export all use the same labels.

Primary files:

- `src/db.py`
- `src/trust_identity.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/compare.py`
- `src/export.py`
- `rescore.py`

### Workstream H - Tests and Validation

**Goal:** Prove the stabilization removed shadow truth without broad workflow churn.

Required scenarios:

1. New run persists complete baseline and methodology snapshots.
2. Mutating current baseline after a run does not change regenerated report identity.
3. Mutating current profile/registry after a run does not change regenerated methodology display.
4. Snapshot-locked rescore uses snapshot methodology or refuses if incomplete.
5. Explicit current-input rescore remains possible and is clearly labeled.
6. Legacy run with only `notes_json.governance_methodology` gets a `legacy_partial` snapshot row or equivalent migration result.
7. Legacy partial methodology is displayed but not treated as complete scoring authority.
8. Report artifact failure produces `report_status='partial'` or `failed` according to the approved semantics.
9. Reports display artifact status/hash/error/verification when present.
10. Compare reads identity through the shared trust path.
11. Export manifest labels provenance completeness and does not rely on stale redaction columns.
12. Duplicate non-identical campaign snapshots fail loudly in migration.

Primary files:

- existing tests if available
- focused new tests around `src/trust_identity.py`, `src/score.py`, reports, rescore, compare, export, and migrations

---

## 7. File-Level Responsibilities

| File | Phase 1.1 responsibility |
| --- | --- |
| `src/trust_identity.py` | Shared snapshot-first trust readers: run/baseline identity, methodology snapshots, legacy labels, artifact summaries. Keep narrow. |
| `src/code_identity.py` | No major Phase 1.1 change expected. Preserve current QuantMap identity capture behavior. |
| `src/db.py` | Migration/backfill for legacy partial methodology; status vocabulary/schema support if needed; duplicate snapshot policy alignment. |
| `src/score.py` | Historical scoring/rescore must use methodology snapshot authority; current-run scoring remains the initial snapshot producer. |
| `rescore.py` | Enforce snapshot-locked baseline and methodology by default; current-input mode remains explicit and labeled. |
| `src/report.py` | Remove implicit live fallback authority; consume shared methodology/artifact trust readers; display honest labels. |
| `src/report_campaign.py` | Same as `src/report.py`, with special attention to methodology section currently using live/default profile. |
| `src/report_compare.py` | Confirm compare/report identity comes from shared trust path; adjust if direct assumptions remain. |
| `src/compare.py` | Replace direct snapshot SQL for identity-like claims with shared trust helper. |
| `src/export.py` | Fix stale redaction assumptions; add provenance completeness labels; preserve run/exporter identity split. |
| `src/audit_methodology.py` | Ensure methodology audit uses shared methodology snapshot authority and labels legacy partial evidence. |
| `src/explain.py` | Inspect for historical trust claims; migrate only if it bypasses trust authority. |
| `src/runner.py` | Adjust report/artifact status semantics, especially `partial`, if approved. |
| `src/governance.py` | Avoid broad redesign; may provide small parse/rehydration helpers only if needed. |
| `src/run_plan.py` | No major Phase 1.1 change expected unless trust identity readers need clearer runtime intent labels. |

---

## 8. Sequence of Work

### Step 1 - Lock Remaining Approval Items

Approve or reject:

1. `report_status='partial'` semantics.
2. Blocking snapshot-locked rescore when methodology evidence is only `legacy_partial`.

### Step 2 - Build Shared Methodology Read Model

Add narrow `trust_identity` helpers for:

- loading the authoritative methodology snapshot
- classifying completeness
- returning scoring material for complete snapshots
- returning display material for partial legacy snapshots
- emitting consistent legacy/current-input labels

### Step 3 - Stabilize Scoring and Rescore

Update historical scoring/rescore behavior:

- complete snapshot: score from snapshot
- legacy partial: refuse snapshot-locked scoring, display/label partial
- missing: refuse snapshot-locked scoring
- explicit current-input: allow current files and label result

### Step 4 - Stabilize Reports

Update `report.py` and `report_campaign.py`:

- no implicit current-file identity authority
- snapshot-first methodology display
- legacy labels
- artifact row-first status display
- no live profile/default display when snapshot evidence exists

### Step 5 - Converge Readers

Update:

- `compare.py`
- `report_compare.py`
- `audit_methodology.py`
- `src/explain.py` if needed

to consume shared trust helpers for historical trust claims.

### Step 6 - Status and Artifact Semantics

Implement approved `report_status` semantics and artifact-reader convergence:

- campaign report aggregate status
- artifact row truth
- legacy path-only labels
- failed artifact visibility

### Step 7 - Export Alignment

Fix export redaction/schema assumptions and add provenance completeness labels.

### Step 8 - Legacy Migration and Backfill Validation

Run migration/backfill checks:

- legacy methodology partial rows
- duplicate snapshot fail-loud behavior
- old artifact/status labels
- no current-file silent upgrades

### Step 9 - Focused Validation Pass

Run the Phase 1.1 verification scenarios and update the validation memo or create a Phase 1.1 findings addendum.

---

## 9. Verification Plan

### Required Behavioral Checks

1. Generate a report for a snapshot-complete run, mutate current baseline, regenerate, and verify baseline identity does not drift.
2. Generate a report for a snapshot-complete run, mutate current profile/registry, regenerate, and verify methodology display does not drift.
3. Rescore a snapshot-complete run after current methodology changes and verify snapshot methodology is used.
4. Rescore a legacy partial methodology run in snapshot-locked mode and verify refusal with clear reason.
5. Rescore the same run with explicit current-input mode and verify labels say current-input.
6. Compare two runs and verify trust identity comes from shared resolver, not direct snapshot SQL.
7. Export a snapshot-complete run and verify manifest includes run identity, exporter identity, methodology completeness, artifact completeness, and no stale redaction assumptions.
8. Export a legacy-incomplete run and verify the bundle does not claim complete provenance.
9. Simulate secondary report artifact failure and verify report status is `partial` or `failed` as defined.
10. Display artifacts in reports and verify status/hash/error/verification source are visible.
11. Run migration against duplicate non-identical snapshots and verify fail-loud behavior.
12. Run migration/backfill against legacy methodology notes and verify `legacy_partial` rows/labels.

### Test Priorities

Highest priority:

- methodology snapshot authority
- report fallback honesty
- rescore snapshot lock
- export non-misleading behavior

Second priority:

- compare/audit/explain reader convergence
- artifact display completeness
- legacy status labels

### Tooling Note

The Phase 1 validation memo noted that `pytest` was unavailable in the active environment. Phase 1.1 should either install/enable the test runner in the development environment or continue using focused direct test scripts plus compile checks until the environment is corrected.

---

## 10. Risks and Controls

| Risk | Control |
| --- | --- |
| Methodology snapshots remain write-only evidence | Make scoring/rescore/reporting read them before Phase 1 closure. |
| Current files still influence historical reports | Disable implicit current-file authority and add explicit labels. |
| `trust_identity.py` becomes a framework | Limit it to narrow trust read helpers and labels. |
| Legacy partial methodology is treated as complete | Use `legacy_partial` capture quality and block snapshot-locked scoring. |
| Report status overstates artifact success | Add/standardize `partial` and surface artifact row failures. |
| Export overclaims bundle fidelity | Add provenance completeness labels and fix schema-aware redaction. |
| Reader convergence misses secondary commands | Inspect `src/explain.py` and migrate only historical trust claims. |
| Phase 1.1 expands into Phase 2 | Keep architecture, provider, optimization, and report consolidation out of scope. |

---

## 11. Exit Criteria

Phase 1 can be called stable after Phase 1.1 only when:

1. Complete methodology snapshots are authoritative for historical scoring/rescore/reporting.
2. Legacy methodology is labeled partial and not silently promoted.
3. Reports do not use current baseline/profile/registry as historical truth by default.
4. Snapshot-locked rescore refuses incomplete baseline or methodology evidence.
5. Explicit current-input behavior remains available and visibly labeled.
6. Report methodology display is snapshot-first.
7. Compare/report_compare/audit/export no longer maintain separate identity truth paths for historical claims.
8. Campaign report status cannot imply all report artifacts succeeded when some failed.
9. Artifact status/hash/error/verification source is visible in report/export trust surfaces where available.
10. Export redaction and completeness labels are schema-aware and non-misleading.
11. Legacy rows show stable weak-evidence labels.
12. Focused validation scenarios pass or any residual gaps are documented as non-blocking with explicit owner/next step.

---

## 12. Open Decisions Requiring Review

### Decision 1 - Report Status `partial`

Approve adding/standardizing `report_status='partial'` for cases where the primary report phase succeeds but one or more expected report artifacts fail or are incomplete.

Recommended answer: approve.

Reason: without `partial`, campaign-level report state can overstate artifact success.

### Decision 2 - Snapshot-Locked Rescore With Legacy Partial Methodology

Approve blocking snapshot-locked rescore when methodology evidence is only `legacy_partial`, while allowing explicit current-input rescoring with visible labels.

Recommended answer: approve.

Reason: partial legacy notes are useful display/audit evidence but not enough to reproduce historical scoring semantics.

---

## 13. Final Recommendation

Proceed to Phase 1.1 implementation after reviewing the two approval items.

This should remain a small stabilization pass if the implementation stays disciplined:

- strengthen methodology authority
- tighten fallback labels
- converge readers through narrow helpers
- clarify report/artifact status
- make export non-misleading

Do not expand the work into report consolidation, telemetry architecture, backend abstraction, optimization, or full export redesign.

