# Phase 1 Trust Bundle Pre-Implementation Contract & Migration Check

Date: 2026-04-11

Status: pre-implementation contract

Primary inputs:

- `docs/decisions/Phase-1-Trust-Bundle-Existing-State-Inventory.md`
- `docs/decisions/Phase-1-Trust-Bundle-Existing-State-Inventory-Codex.md`
- `docs/AUDITS/4-11/Post-Audit-Synthesis-Memo.md`
- `docs/system/known_issues_tracker.md`
- Targeted code inspection of the current trust surfaces in `src/db.py`, `src/runner.py`,
  `src/telemetry.py`, `src/score.py`, `src/report.py`, `src/report_campaign.py`,
  `src/report_compare.py`, `src/export.py`, `rescore.py`, `src/governance.py`,
  `src/config.py`, and `src/run_plan.py`.

## Purpose

This document is the final planning-quality control pass before Phase 1 Trust
Bundle implementation. It does not replace the implementation plan. It defines
the post-Phase-1 authority model, transition behavior, invariants, and failure
modes that the implementation plan must respect.

Scope is limited to:

1. Snapshotting / self-containment
2. QuantMap code identity capture
3. Snapshot-first report identity
4. Layered runtime state
5. Trust-critical path/settings assumptions

Out of scope except as direct dependencies: telemetry provider architecture,
backend adapter design, full packaging redesign, optimization implementation,
root-cause attribution implementation, and broad refactoring.

## Contract Decisions

| Decision | Contract |
| --- | --- |
| Primary authority | New Phase 1 trust claims must be backed by DB-persisted historical state, not by current live disk state. |
| Snapshot storage shape | Decision required before implementation: either extend `campaign_start_snapshot` as the single 1:1 trust snapshot row, or add a tightly linked first-class trust snapshot table. Do not allow both to become independently authoritative. |
| Legacy data | Legacy gaps must be visible. Missing historical data is shown as legacy/incomplete/unknown, not silently reconstructed from current files. |
| Live disk fallback | Allowed only as an explicitly labeled legacy fallback or migration input. It must never outrank an existing snapshot. |
| Status model | Measurement truth, interpretation truth, and artifact/report truth must be separate after Phase 1. `campaigns.status='complete'` cannot mean all three. |
| Report identity | Report, rescore, compare, and export must consume one snapshot-first identity model. They may format it differently, but must not re-infer it independently. |
| Sidecars | Sidecar files may be convenience artifacts. They must not override DB snapshot truth. |

## 1. Source-Of-Truth Contract

| Concept | Authoritative source after Phase 1 | Current source(s) today | What must stop being authoritative | Legacy fallback allowed? | Notes |
| --- | --- | --- | --- | --- | --- |
| Effective campaign definition | DB-backed trust snapshot containing `campaign_yaml_content`, its hash, source path, and capture metadata | `campaign_start_snapshot.campaign_yaml_content`, campaign YAML on disk, in-memory runner config | Current `configs/campaigns/*.yaml` for historical runs when snapshot content exists | Yes, only for runs lacking snapshot content; label as legacy/live-disk fallback if loaded | Existing campaign content capture is one of the strongest foundations. |
| Effective baseline definition | DB-backed baseline snapshot with verbatim baseline content, hash, path, parsed identity fields, and capture metadata | `campaign_start_snapshot.baseline_sha256`, live baseline YAML loaded by runner/report/rescore | Live baseline object as historical report/rescore authority | Yes, hash-only legacy display; live disk may be migration evidence only and must be labeled | Hash-only is not self-contained. Phase 1 must add content or an equivalent immutable serialized baseline. |
| Effective methodology/governance definition | Formal methodology snapshot containing profile content, registry/metric definitions, gates, weights, anchors, methodology version, hashes, and source paths | Live `src/governance.py` registry/profile YAML plus partial `campaigns.notes_json.governance_methodology` anchors | Current profile/registry files as historical interpretation authority | Yes, partial `notes_json` anchors may be displayed as legacy/incomplete | `notes_json` is transitional evidence, not a complete methodology source. |
| QuantMap code identity | Run-start DB identity record with QuantMap version, git commit if available, dirty flag, source tree hash or equivalent, capture time, and identity source | `src/version.py`, `pyproject.toml`, CLI/export current version strings | Export-time or report-time current version as historical run identity | Yes, show `legacy unrecorded` or `unknown`; do not backfill exact commit without evidence | Existing `build_commit` is not QuantMap identity. |
| Backend/binary identity | Existing start snapshot backend fields plus clarified semantics: binary path/hash, model path/size/mtime, claimed backend build label, and verification status | `campaign_start_snapshot.server_binary_*`, model fields, baseline `runtime.build_commit` | Treating `build_commit` as verified backend commit or QuantMap commit | Yes, existing `build_commit` can remain as claimed backend build label | This is usable but needs clearer names and report wording. |
| Requested runtime intent | Persisted effective run plan: campaign id, run mode, selected values, schedule, overrides, requested baseline path, requested lab root, and derived DB/results/state paths | In-memory `RunPlan`, campaign YAML, CLI options, runner locals | Reconstructing intent from current YAML or current CLI defaults | Yes, derive limited intent from DB rows for legacy runs and label incomplete | `src/run_plan.py` is a good model but must be persisted. |
| Resolved runtime reality | DB runtime reality fields: `configs.resolved_command`, `runtime_env_json`, resolved model/server paths, cycle/request data, snapshot capture status | `configs.resolved_command`, `configs.runtime_env_json`, start snapshot, request/cycle rows, live env reconstruction in reports | Rebuilding production commands from current env/config when DB values exist | Yes, legacy report may show unavailable or derived-from-current with label | Requested intent and resolved reality must stay distinct. |
| Measurement success state | Explicit measurement status or a clearly scoped campaign measurement status plus `configs`, `cycles`, and `requests` as detailed evidence | `campaigns.status`, `configs.status`, `cycles.status`, `requests`, raw sidecars | `campaigns.status='complete'` as whole-pipeline success | Yes, legacy derived measurement status from existing rows, labeled derived | Measurement completion is already mostly present but not named cleanly. |
| Interpretation success state | Explicit analysis/scoring status tied to methodology snapshot and `scores` production | Side effect of `score.py` writing `scores`; report generation calls `analyze_campaign`/scoring | Inferring interpretation success from campaign status or report presence | Yes, legacy derived from `scores` presence/quality and labeled derived | Scoring has real evidence but no first-class status boundary. |
| Artifact/report success state | Artifact authority with artifact type, path, status, SHA-256, created time, error if failed, and producer identity | `artifacts` table paths, file existence, runner `report_ok` for `report.md`, non-fatal `report_v2` logging | File existence or primary `report.md` success as the only artifact truth | Yes, legacy artifacts may have null hash/status and visible legacy label | `artifacts` is the right base but currently too thin. |
| Report identity fields | Shared snapshot-first identity resolver reading DB trust snapshot, then explicit legacy fallback labels | Mixed DB snapshot plus live baseline/profile in `report.py` and `report_campaign.py` | Report-local inference from live baseline/profile when snapshot values exist | Yes, but every fallback field must expose source and confidence | One resolver should feed canonical report, compare, rescore display, and export. |
| Artifact identity/path authority | DB artifact rows for current artifacts; path derivation only for locating legacy artifacts or planned output paths | Derived campaign folders, report paths, partial artifacts writes | Re-derived paths as proof that an artifact exists or is trustworthy | Yes, legacy lookup may derive candidate paths and label them candidate/legacy | Path authority must separate intended path from verified artifact. |
| Export identity | Export payload must include historical run identity and separate exporter identity | `src/export.py` stamps export-time software/methodology version; stale table list | Treating exporter version as run-time QuantMap identity | Yes, legacy exports may declare incomplete provenance | Current export references nonexistent/stale schema surfaces and must not define Phase 1 truth. |
| Trust-critical paths/settings | Central runtime settings/path authority, preferably `src.config` plus persisted run plan values | `src.config`, runner `_derive_lab_root`, hardcoded report `LAB_ROOT` fallbacks, env vars | Report/rescore modules independently deriving lab root or DB location | Yes, only for legacy lookup and labeled as path fallback | Phase 1 should centralize trust-critical path decisions without doing full packaging. |

## 2. Read/Write Ownership Map

| Concept | Today writes | Today reads | Post-Phase-1 writer | Post-Phase-1 readers | Shadow-truth note |
| --- | --- | --- | --- | --- | --- |
| Campaign snapshot | `src/telemetry.py` via `collect_campaign_start_snapshot`; `src/runner.py` calls it and writes sidecar | Reports, audit/compare helpers, runner sidecar logic | Run-start snapshot writer owned by runner/telemetry boundary | Snapshot identity resolver, reports, rescore, compare, export | Sidecar must be output-only, never source-of-truth. |
| Baseline snapshot | Hash written by telemetry; live content loaded by runner/report/rescore | `src/report.py`, `src/report_campaign.py`, `rescore.py`, `src/score.py` | Run-start trust snapshot writer | Snapshot identity resolver, scoring/rescore, report/compare/export | Add one baseline content authority; do not add parallel per-report caches. |
| Methodology snapshot | Partial anchors in `campaigns.notes_json` from `src/score.py`; live governance loaded from disk | `src/score.py`, reports, compare/audit helpers | Scoring/methodology snapshot writer, invoked before or with scoring | Score/rescore, report, compare, export | `notes_json` may migrate or be superseded, but cannot stay as full truth. |
| QuantMap code identity | No historical writer; export/CLI report current version | Export, docs/report text where present | Run-start identity writer | Snapshot identity resolver, report, export, compare/rescore metadata | Current process version is exporter identity, not run identity. |
| Backend/binary identity | `src/telemetry.py` start snapshot | Reports and diagnostics | Existing start snapshot writer, with clarified field semantics | Report, export, compare, attribution later | Rename/label semantics before readers treat fields as stronger than they are. |
| Run intent | `src/run_plan.py` constructs in memory; runner writes campaign/config rows | Runner, status/list/report indirectly | Runner writes persisted run-plan snapshot | Reports, status/list, rescore eligibility, export | Current run plan is useful but evaporates after process exit. |
| Resolved runtime reality | Runner writes `configs.resolved_command`, `runtime_env_json`, cycles, requests | Reports, status/list, analysis | Runner and server measurement code | Reports, status/list, compare/export | Reports must prefer DB reality fields over current env reconstruction. |
| Measurement state | Runner updates `campaigns`, `configs`, `cycles`, `requests`; raw sidecars | Runner resume/status, reports/analysis | Runner measurement-state writer | Status/list, reports, export, recovery tools | Campaign state must be narrowed or supplemented; do not overload it. |
| Interpretation state | `src/score.py` writes `scores`; analysis writes artifacts as side effects | Reports, compare, export | Analysis/scoring status writer | Status/list, report, compare/export | Scores alone prove score rows exist, not that interpretation completed cleanly. |
| Artifact/report state | Report modules register paths in `artifacts`; runner tracks `report_ok` locally | Reports indirectly, export poorly, user filesystem | Artifact writer owned by report/export generation boundary | Status/list, report index, export, doctor | Artifact rows need status/hash/error or a companion status surface. |
| Report identity | `src/report.py` and `src/report_campaign.py` each infer fields | Human reports, compare/export assumptions | Shared snapshot identity resolver | All report surfaces, compare, rescore display, export | Two report paths must not keep separate identity rules. |
| Path/settings authority | `src.config`, runner `_derive_lab_root`, report-local `LAB_ROOT`, CLI/env | Runner, report, rescore, export, server/doctor | Central path/settings resolver plus persisted run-plan values | Runner, report, rescore, compare/export, doctor | Report-local hardcoded fallbacks are trust leaks. |

## 3. Migration Behavior Table

| Field / concept | Legacy condition | Allowed behavior | Disallowed behavior | Why |
| --- | --- | --- | --- | --- |
| `campaign_yaml_content` | Missing in old `campaign_start_snapshot` row | Display `legacy campaign definition unavailable`; optionally load current YAML only as explicitly labeled live-disk fallback | Silently present current YAML as historical campaign definition | Historical campaign identity must not drift when a file changes. |
| Baseline content | Only `baseline_sha256` exists | Display hash-only legacy baseline identity; optionally show current file as non-authoritative candidate if hash matches | Use current baseline YAML to fill report identity without a legacy label | Hash proves content equality only if content is available; it is not self-contained. |
| Methodology/profile content | Only `campaigns.notes_json.governance_methodology` or no row exists | Display partial methodology anchor with `legacy incomplete methodology`; use current profile only if explicitly requested and labeled | Re-score or report as if current profile was the historical methodology | Interpretation claims require the methodology used, not the methodology installed today. |
| QuantMap code identity | No run-time QuantMap identity exists | Show `legacy unrecorded` or `unknown`; backfill only from explicit run artifact evidence | Guess commit/version from current checkout or package metadata | Current checkout is not historical evidence. |
| Backend `build_commit` | Existing field came from baseline runtime config | Treat as claimed backend build label | Treat as verified backend hash or QuantMap code identity | Name collision can create false provenance. |
| Persisted run intent | No persisted `RunPlan` snapshot exists | Derive minimal legacy intent from `campaigns`, `configs`, and run mode fields; mark as derived/incomplete | Reconstruct full intent from current campaign YAML | Intent includes choices and overrides that may no longer be present on disk. |
| Resolved runtime reality | `configs.resolved_command` or `runtime_env_json` missing | Show unavailable or legacy-derived; use request/cycle evidence where available | Reconstruct production command from current environment without label | Resolved reality is what ran, not what would run now. |
| Measurement status | No new layered fields exist | Derive legacy measurement state from `campaigns`, `configs`, `cycles`, and `requests`; mark `derived_legacy` | Convert old `campaigns.status='complete'` into full-pipeline success | Measurement success and post-run success are different claims. |
| Interpretation status | No explicit analysis/scoring status exists | Derive from score rows and known analysis artifacts; mark `derived_legacy` | Claim successful interpretation because measurement completed | Scores can be absent or partial after valid measurement. |
| Artifact/report status | Artifacts lack status/hash/error | Keep nulls; show `legacy unverified artifact`; optionally compute hash only as post-hoc verification with source label | Backfill as `success` solely because a file path exists | File presence is not the same as generation success or identity. |
| Report regeneration | Old run lacks some snapshot fields | Generate report with visible legacy/incomplete provenance fields | Fill gaps from live baseline/profile/config and omit fallback labels | Regeneration must not make old evidence look stronger than it is. |
| `campaign_yaml_snapshot.yaml` sidecar | Sidecar exists but DB row differs or is absent | Treat as convenience artifact; prefer DB if present; label sidecar-only as legacy external evidence | Let sidecar override DB snapshot | DB is the canonical run record. |
| Existing exports | Export files omit start snapshot or use stale table assumptions | Mark old exports as incomplete provenance exports | Treat old export schema as Phase 1-compatible evidence bundle | Current export does not include the needed trust surfaces. |

## 4. No-Shadow-Truth Checklist

| Shadow truth risk | How implementation should prevent it | Test or assertion that catches it |
| --- | --- | --- |
| Live baseline keeps influencing reports after baseline snapshot exists | Report identity resolver must read baseline identity from DB snapshot first and must expose source per field | Modify live baseline after a run; regenerated report must keep original snapshot identity and mark no live-disk source. |
| Live profile/registry keeps influencing historical interpretation | Scoring must persist methodology snapshot; report/rescore/compare must read that snapshot for historical claims | Change `configs/profiles/default_throughput_v1.yaml`; old report/rescore must not change methodology labels or weights when snapshot exists. |
| Export stamps current tool identity as run identity | Export schema must separate `run_quantmap_identity` from `exporter_identity` | Export an old legacy run and a new run; run identity must differ from exporter identity when historical identity is missing or older. |
| Rescore silently uses current profile/baseline | Rescore must require snapshot identity when available and must label or reject legacy fallbacks explicitly | Run rescore after changing baseline/profile; result must either use snapshot or report an explicit legacy/current-input mode. |
| Campaign status and layered status disagree invisibly | Add explicit layered statuses or a derived status view with source labels | A run with successful measurement but failed report must show measurement success and artifact failure separately. |
| Old artifact path derivation survives beside artifact authority | Artifact consumers must read verified artifact rows first; derived paths may only be candidates | Delete or move an artifact file while path row remains; status must not claim verified success without hash/status validation. |
| Multiple snapshot stores become half-authoritative | Select one primary DB snapshot authority; any auxiliary tables must be linked and documented as components of that authority | Schema review assertion: every trust snapshot reader goes through one resolver/API, not direct ad hoc table reads. |
| `build_commit` is mistaken for QuantMap identity | Rename/report it as backend claimed build identity and add separate QuantMap identity fields | Report must contain distinct QuantMap and backend identity fields; `build_commit` must not populate QuantMap commit. |
| Sidecar snapshot beats DB snapshot on resume/rerun | Sidecar writer must emit from DB canonical snapshot when a row already exists | Resume/rerun with changed campaign YAML; sidecar and report must reflect DB snapshot or label sidecar regeneration source. |
| Path fallbacks produce a second DB/report root | Centralize trust-critical path resolution and persist resolved paths in run plan snapshot | Set `QUANTMAP_LAB_ROOT` to a different value during report generation; historical report must use persisted run paths when available. |
| Legacy inference becomes silent backfill | Migration must track `source=derived_legacy` or equivalent for any inferred status/identity | Migration test verifies derived fields carry source labels and are not indistinguishable from run-time captured values. |
| Dual report stack keeps two identity models | Both `report.md` and canonical evidence report must use the same identity resolver during transition | Snapshot field mutation test must affect both report paths identically or mark one as transitional. |

## 5. Compatibility And Rollout Risks

| Risk | Phase 1 concern | Required control |
| --- | --- | --- |
| Schema migration risk | Adding snapshot/status fields without a single authority can create two partial truth stores | Choose the storage shape first; document table ownership and reader API before implementation. |
| Partial rollout risk | Writers may start persisting new truth while reports/export/rescore still read live disk | Land writer, resolver, and primary readers as one trust bundle, or gate new fields until readers are updated. |
| Legacy interpretation risk | Old runs can look better documented than they are if fallbacks are silent | Every legacy fallback must carry a visible `legacy`, `unknown`, `hash-only`, `derived`, or `current-input` label. |
| Report regeneration risk | Regenerating old reports after Phase 1 can accidentally mix old measurements with current baseline/methodology | Report generator must expose field source and prefer snapshot; tests must mutate live files before regeneration. |
| Rescore/compare/export compatibility risk | These tools currently assume live methodology/baseline or stale export schema surfaces | Make them consume the shared identity resolver and degrade explicitly for legacy incomplete runs. |
| Artifact compatibility risk | Existing artifacts table rows do not prove artifact integrity or success | Leave legacy hash/status nulls visible; do not infer success solely from path rows. |
| Docs drift risk | Existing docs may keep describing current version/current files as historical evidence | Update trust-surface docs with the authority model and legacy labels as part of Phase 1 completion. |

## 6. Post-Phase-1 Invariants

These invariants are implementation-review and test-review gates. Phase 1 is not
complete if any of these are false.

1. If a DB snapshot field exists for campaign, baseline, methodology, QuantMap identity, backend identity, run intent, or resolved runtime reality, reports must use that field before any live disk value.
2. Live disk state may be used only as a new-run input, an explicit migration input, or a labeled legacy fallback. It must not silently define historical truth.
3. `campaigns.status='complete'` must not imply interpretation success, report success, export success, or artifact integrity.
4. Measurement truth, interpretation truth, and artifact/report truth must be represented as distinct states or as a derived view with explicit source labels.
5. New score rows must be tied to a methodology snapshot or to an explicit legacy/current-input interpretation label.
6. New runs must persist QuantMap code identity at run start. Exporter identity may not substitute for run identity.
7. Backend identity and QuantMap identity must be separate concepts in storage and in reports.
8. Baseline identity for new runs must be self-contained enough to regenerate historical report identity without current baseline YAML.
9. Methodology identity for new or newly interpreted runs must be self-contained enough to explain weights, gates, anchors, and metric definitions without current profile files.
10. Report, rescore, compare, and export must share one snapshot-first identity resolver or equivalent API.
11. Legacy nulls must remain visible as weaker evidence. They must not be overwritten with guessed current values.
12. Artifact/report authority must distinguish planned path, produced path, generation status, hash verification, and generation error.
13. Sidecar files must not override DB trust snapshot values.
14. Path/settings resolution for trust surfaces must be centralized or injected from the persisted run plan; report-local lab-root fallbacks must not decide historical identity.
15. Any backfilled or derived migration field must record that it is derived legacy evidence, not run-time captured evidence.
16. A failed report or export must not invalidate persisted measurement data.
17. New trust snapshot writes must have one owner. Other modules may request or read snapshots but must not independently write competing snapshot rows.
18. `build_commit` or similarly named backend fields must not populate QuantMap code identity.

## 7. Must Verify In Implementation

Before Phase 1 is considered ready to merge, the implementation plan and code
review must verify:

- The chosen snapshot storage shape has exactly one authoritative reader API.
- New runs persist campaign, baseline, methodology, QuantMap identity, backend identity, run intent, and runtime reality at the right lifecycle point.
- Legacy runs display missing data as `legacy`, `unknown`, `hash-only`, `derived`, or `incomplete` rather than silently filling from live files.
- Reports source identity from the snapshot resolver and show field source or fallback quality where needed.
- Rescore, compare, and export use the same identity authority and degrade explicitly for incomplete legacy rows.
- Layered measurement, interpretation, and artifact/report status cannot be collapsed into `campaigns.status`.
- Artifact rows include or are paired with status/hash/error semantics for new artifacts.
- Report regeneration tests mutate live baseline/profile/config files and prove historical identity does not drift.
- Migration tests cover old rows with missing baseline content, missing methodology content, missing code identity, and legacy artifact rows.
- Hardcoded trust-critical path fallbacks in report/rescore/export paths are removed, centralized, or downgraded to explicit legacy lookup behavior.

## Final Pre-Implementation Conclusion

Phase 1 can now be planned cleanly if one unresolved storage decision is made
first: whether the trust snapshot is an extension of `campaign_start_snapshot`
or a first-class linked snapshot surface. The authority contract is clear either
way: the post-Phase-1 source of truth is DB-backed historical snapshot state,
read through one snapshot-first identity model.

The strongest foundations to build on are `campaign_start_snapshot`,
`campaign_yaml_content`, backend binary/model snapshot fields,
`configs.resolved_command`, `configs.runtime_env_json`, `cycles`, `requests`,
`scores`, `artifacts`, `src/run_plan.py`, `src/config.py`, and the governance
registry/profile model. The weakest current surfaces are baseline hash-only
capture, partial methodology anchors in `campaigns.notes_json`, live-disk report
identity, current export identity, report-local path fallbacks, and the
collapsed campaign completion state.

The biggest cleanup decision before implementation planning is not whether to
add more fields. It is to prevent multiple partially authoritative stores from
surviving. Phase 1 should create one trust snapshot authority, one identity
resolver, and one layered status model that every trust-bundle reader must use.
