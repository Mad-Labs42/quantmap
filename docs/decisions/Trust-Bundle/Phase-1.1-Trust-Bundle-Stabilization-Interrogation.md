# Phase 1.1 Trust Bundle Stabilization Interrogation

**Status:** Pre-implementation interrogation and design resolution  
**Date:** 2026-04-11  
**Scope:** Phase 1.1 Trust Bundle stabilization only  
**Inputs:** Phase 1 implementation plan, Phase 1 post-implementation validation memo, pre-implementation contract, existing-state inventories, post-audit synthesis memo, and current code inspection.

---

## 1. Purpose

This document asks and answers the remaining high-value questions before Phase 1.1 implementation begins.

It is not a new broad audit and it is not an implementation pass. Its purpose is to remove the remaining ambiguity around the stabilization work that must happen before Phase 1 can be called stable.

The Phase 1 core implementation pass established real trust-bundle foundations: persisted run snapshots, QuantMap code identity capture, layered status fields, artifact status metadata, and a shared trust identity module. The validation pass showed that those foundations are not yet fully authoritative across readers. The biggest remaining danger is still shadow truth: especially live methodology influencing historical scoring and reports after persisted methodology snapshots exist.

---

## 2. Interrogation

Status labels:

- **verified** means the answer is grounded in current code or existing validation findings.
- **inferred** means the answer follows from current behavior but should still be confirmed during implementation.
- **decision required** means implementation should not proceed until the project accepts the stated policy.

### A. Methodology Authority

| Question | Answer | Evidence | Status |
| --- | --- | --- | --- |
| Exactly where does scoring still use live methodology instead of persisted methodology? | `src/score.py` still constructs scoring semantics from live governance objects: `governance.BUILTIN_REGISTRY`, `governance.DEFAULT_PROFILE`, `governance.load_profile(profile_name)`, `profile.weights`, `profile.gate_overrides`, and current registry/reference inputs. It persists a methodology snapshot, but that snapshot is not the authority for scoring semantics. | Current code inspection of `src/score.py`; validation memo high finding on persisted snapshots not being authoritative for scoring. | verified |
| Exactly where does report methodology display still use live/default/current profile objects? | `src/report_campaign.py` still falls back to `governance.DEFAULT_PROFILE` and uses `profile.weights` / `profile.gate_overrides` when building methodology sections. Report display can therefore reflect current methodology rather than the historical snapshot. | Current code inspection of `src/report_campaign.py`; validation memo high finding on live methodology display. | verified |
| Is `methodology_snapshots` structurally sufficient to become authoritative, or is schema/content still missing? | It is sufficient as the Phase 1.1 foundation, but not yet sufficient as consumed. It stores profile content, registry content, weights/gates/anchors JSON, paths/hashes, capture quality/source, and current flag. The missing part is a narrow reader/rehydration contract that treats those stored values as the historical authority. | Current schema in `src/db.py`; writer behavior in `src/score.py`. | verified |
| What minimum data must be read from `methodology_snapshots` for scoring/rescore/reporting to be truly snapshot-first? | At minimum: `weights_json`, `gates_json`, `anchors_json`, `profile_yaml_content`, `registry_yaml_content`, `profile_sha256`, `registry_sha256`, `methodology_version`, `capture_quality`, and `capture_source`. Scoring needs weights/gates/anchors and registry metric definitions. Reports need the same plus source/quality labels. Rescore must refuse snapshot-locked historical scoring if that minimum is absent or marked partial. | Inferred from current scoring use of profile weights/gates/registry and current report methodology fields. | inferred |
| Can scoring be made fully snapshot-driven for historical runs without destabilizing current-run scoring? | Yes, if Phase 1.1 separates two paths: current-run scoring may still load live methodology once and persist a complete snapshot; historical scoring/rescore/reporting must read the persisted snapshot. This avoids redesigning current campaign startup while removing historical shadow truth. | Existing current-run path already captures snapshots; rescore already has snapshot-locked baseline policy. | inferred |
| What should happen for legacy runs with only `notes_json.governance_methodology` and no formal methodology snapshot? | They should be bridged into a formal `methodology_snapshots` row with `capture_quality='legacy_partial'` where possible, but that row must not be treated as complete scoring authority. Reports/audits may display it as legacy partial methodology. Snapshot-locked rescore should not silently score from it. | Validation memo notes no backfill exists; pre-implementation contract forbids silently strengthening legacy evidence. | decision required |
| Should stabilization backfill legacy partial methodology rows now, or only bridge them lazily/on-demand? | Backfill now. Lazy bridging would leave multiple readers deciding legacy behavior independently and would preserve a shadow truth risk. A deterministic migration/backfill makes export, audit, compare, and reports see the same legacy label. | Migration consistency requirement from contract; reader convergence findings. | inferred |
| What is the cleanest model for historical scoring authority versus current-input rescoring? | Historical scoring authority is persisted methodology snapshot plus persisted baseline snapshot. Current-input rescoring is a separate explicit mode that loads current files and labels the result as current-input. The default for snapshot-complete runs must remain snapshot-locked. | Existing `rescore.py` already defaults baseline to snapshot-locked and requires `--current-input` for current baseline fallback. | verified |

**Methodology authority resolution:** Use `methodology_snapshots` as the only Phase 1.1 historical methodology authority. Add the minimum reader/rehydration behavior needed for scoring, rescore, reports, audit, compare, and export to consume it. Do not create a second methodology store.

---

### B. Report Methodology / Identity Behavior

| Question | Answer | Evidence | Status |
| --- | --- | --- | --- |
| Exactly where do reports still allow live fallback by default? | `src/report.py` and `src/report_campaign.py` call `load_baseline_for_historical_use(... allow_current_input=True)`. That means report generation can still pull current baseline data by default when snapshots are incomplete. `src/report_campaign.py` also uses live/default governance profile objects for methodology display. | Current code inspection of report modules; validation memo medium fallback finding. | verified |
| Is the current fallback labeling honest enough, or does it overstate user intent? | It overstates user intent. The label `current_input_explicit` is appropriate only when a user explicitly asks to use current files. Current report generation enables fallback internally by default, so that label is too strong. | Validation memo medium finding on current-input labeling. | verified |
| Should reports ever allow current-file fallback implicitly? | No for historical identity claims. If a report needs current files for convenience rendering, it must label that data as current-file fallback and must not present it as historical truth. For snapshot-complete runs, live disk must not affect identity or methodology. | Contract invariant: reports must not source historical identity from live disk when snapshots exist. | inferred |
| If not, what should fallback behavior be for legacy-incomplete runs? | Reports should render weaker evidence: `legacy`, `hash-only`, `legacy_partial`, `unknown`, or `incomplete`. They may optionally display current-input data only under a visibly separate label such as `current-input fallback`, and only if the caller explicitly requested that behavior. | Pre-implementation contract and Phase 1 implementation plan legacy policy. | inferred |
| Which report fields are still not fully sourced through the shared resolver? | Baseline identity is partially sourced through `trust_identity`. Methodology display is not fully resolver/snapshot-backed. Artifact status display is not fully sourced from artifact rows. Some path/root fallback behavior remains report-local. | Code inspection of `src/report.py`, `src/report_campaign.py`, and validation memo findings. | verified |
| Are both report stacks now close enough to converge, or do they still need separate stabilization treatment? | They need separate stabilization treatment but not full consolidation. Both should consume the same trust identity and methodology helpers, but Phase 1.1 should not attempt to merge the report stacks. | Existing modules remain distinct and both have trust-relevant behavior. | inferred |

**Report behavior resolution:** Reports must become snapshot-first and honest-label-first. Remove implicit current-file authority from historical report identity and methodology display. Keep both report stacks, but force them through shared trust helpers for historical claims.

---

### C. Reader Convergence

| Question | Answer | Evidence | Status |
| --- | --- | --- | --- |
| Which major readers are now fully aligned to the shared trust model? | None should be considered fully aligned yet. `audit_methodology.py` and `export.py` are closest because they call `load_run_identity`, but export still has stale schema assumptions and methodology snapshot consumption is not yet authoritative. | Code inspection and validation memo. | verified |
| Which readers are only partial? | `report.py`, `report_campaign.py`, `rescore.py`, `compare.py`, `report_compare.py`, `export.py`, and `audit_methodology.py` are partial in different ways. `rescore.py` is strong on baseline snapshot locking but not methodology authority. Reports are strong enough to use snapshot baseline but still allow fallback and live methodology. Compare reads snapshots directly. Export includes trust tables but has stale redaction assumptions. | Current code inspection. | verified |
| What exactly is `compare.py` still doing directly that should move into `trust_identity` or another shared path? | It queries `campaign_start_snapshot` directly with `ORDER BY id DESC LIMIT 1` for environment/config deltas. It should use a shared loader that respects the unique campaign snapshot authority and exposes explicit legacy/quality labels. | Current code inspection of `src/compare.py`. | verified |
| Are any hidden or secondary readers still bypassing the trust model? | `src/explain.py` appears to be a secondary reader worth checking during Phase 1.1 because it may present historical reasoning or score details. `src/selftest.py` and `src/doctor.py` read live governance/config but are not primarily historical trust readers. | File discovery and targeted search. | inferred |
| What is the smallest change set needed to achieve real reader convergence without broad refactoring? | Add narrow shared trust-reading helpers for methodology snapshot, baseline/run identity, artifact status summary, and legacy labels. Update readers where they make historical claims. Do not consolidate report modules, rebuild compare, or create a generic trust framework. | Current code layout supports small helper usage through `src/trust_identity.py`. | inferred |

**Reader convergence resolution:** Expand `src/trust_identity.py` narrowly into the single shared read path for historical trust identity, methodology authority, legacy labels, and artifact summaries. Migrate direct readers to it only where they make trust claims.

---

### D. Layered Runtime State

| Question | Answer | Evidence | Status |
| --- | --- | --- | --- |
| Is `report_status` currently defined clearly enough? | Not yet. The current behavior can mark campaign-level `report_status='complete'` while a secondary report artifact such as `report_v2.md` fails, because the failure is captured at artifact level. | Validation memo medium finding on report status ambiguity. | verified |
| Does it mean primary report succeeded, all report artifacts succeeded, or something else? | In practice it currently behaves closer to primary report phase success, not all artifact success. That meaning is not clearly documented enough to be stable. | Inferred from runner/report behavior and validation memo. | inferred |
| Is a `partial` report status needed? | Yes. Without `partial`, a campaign can look fully report-complete while an artifact failed. `partial` should mean the primary report phase produced usable output but one or more expected artifacts failed or are incomplete. | Current artifact failure handling creates a distinction that campaign status cannot express. | decision required |
| Are campaign-level status fields enough, or is there still pressure toward a separate artifact/report phase model? | Campaign-level fields plus per-artifact rows are enough for Phase 1.1. A separate status table would be broader than necessary unless later evidence shows many independent report phases need queryable lifecycle history. | User preference and implementation plan favored smallest clean model; current schema already has campaign fields and artifact rows. | inferred |
| What is the minimum stabilization change needed so campaign-level report/artifact truth is not misleading? | Define `report_status` as aggregate report/artifact phase status and allow `partial`. Readers must display artifact row failures instead of treating campaign `complete` as proof that every report artifact succeeded. | Validation finding and layered-state contract. | inferred |

**Layered state resolution:** Keep status on `campaigns` for Phase 1.1, add/standardize `partial`, and make artifact rows the per-artifact truth. Do not introduce a separate status table now.

---

### E. Artifact Truth

| Question | Answer | Evidence | Status |
| --- | --- | --- | --- |
| Are richer artifact fields being written consistently enough to treat them as trustworthy? | They are trustworthy as first-pass per-artifact evidence when written, especially for report artifacts, but not yet complete enough to be the only reader surface. Legacy and some artifact types may still be path-only or absent. | Schema and writer changes in Phase 1; validation memo artifact reader finding. | verified |
| Which readers still ignore artifact `status` / `sha256` / `error_message` / `verification_source`? | Report artifact sections still do not consistently surface these fields. Some report paths still infer artifact presence from paths/files. Export includes artifacts but does not fully explain artifact completeness. | Validation memo medium finding; code inspection of report/export paths. | verified |
| Should artifact sections in reports be upgraded in Phase 1.1, or is that too far? | Yes, minimally. Reports are a trust surface, so they must not hide failed or unverified artifact rows. This does not require a report redesign; it requires artifact table-first display and honest legacy/file-existence fallback labels. | Artifact truth is already a Phase 1 scope item. | inferred |
| What is the minimum acceptable artifact-reader convergence for calling Phase 1 stable? | Reports and exports must display artifact status/verification/error where available; campaign report status must not imply all artifacts succeeded; legacy artifacts must be labeled path-only or legacy-unverified. | Layered artifact contract and validation findings. | inferred |

**Artifact truth resolution:** Treat artifact rows as the first-class artifact truth when present. Upgrade reports and export manifest behavior enough that artifact failures, hashes, and verification source are visible.

---

### F. Export Trust Behavior

| Question | Answer | Evidence | Status |
| --- | --- | --- | --- |
| Exactly what stale redaction/schema assumptions remain? | `src/export.py` still contains redaction logic referencing stale columns such as `metadata_json` and `raw_json`, while swallowing exceptions. This can make strip/redaction behavior look safer than it is. | Current code inspection; validation memo medium finding. | verified |
| Does export currently overclaim trust/fidelity in any way? | It can. Export now includes trust tables and run/exporter identity separation, but stale redaction assumptions and incomplete legacy/methodology semantics can make a bundle appear more complete than its evidence supports. | Export smoke passed, but validation memo flagged redaction and fidelity gaps. | verified |
| What must export do before it can be considered aligned with the trust bundle? | It must be schema-aware for redaction, include trust completeness/legacy labels, distinguish run identity from exporter identity, include methodology/artifact status evidence where available, and avoid claiming full historical fidelity for legacy-incomplete runs. | Phase 1 contract and export findings. | inferred |
| Is export required to be fully stable for Phase 1 closure, or only non-misleading? | Non-misleading is the Phase 1.1 closure requirement. Full case-file fidelity can wait for later export work, but Phase 1.1 must prevent export from silently overstating provenance completeness. | Scope constraint against broad export redesign. | inferred |

**Export resolution:** Align export enough to be honest and schema-aware. Do not turn Phase 1.1 into a full export/case-file redesign.

---

### G. Legacy and Migration Behavior

| Question | Answer | Evidence | Status |
| --- | --- | --- | --- |
| Which legacy cases are still unverified or underdefined? | Legacy methodology without formal snapshots, baseline hash-only rows, old artifact rows without status/hash/error fields, old campaigns without layered analysis/report statuses, and duplicate snapshot migration behavior are the main cases. | Validation memo and schema/migration review. | verified |
| What legacy labels still need tightening? | `current_input_explicit` must not be used when the fallback was not user-requested. Need stable labels for `legacy_hash_only`, `legacy_partial_methodology`, `legacy_status_derived`, `legacy_artifact_path_only`, `unknown`, and `incomplete`. | Validation memo fallback finding and contract legacy policy. | verified |
| What should happen when historical trust data is incomplete but some current-file data exists? | Current-file data must not silently fill historical truth. It can be used only in explicit current-input mode or clearly separated as current-file fallback. Historical displays should prefer weaker legacy labels over stronger inferred claims. | Contract and implementation plan. | inferred |
| What should be blocked versus labeled versus allowed? | Block snapshot-locked rescoring when baseline or methodology authority is incomplete. Label reports/audit/export for legacy incomplete evidence. Allow current-input rescoring/reporting only with explicit user request and visible labels. Fail migration on unsafe duplicate snapshots. | Existing rescore baseline refusal behavior; trust-bundle philosophy. | decision required |

**Legacy resolution:** Prefer visible weak evidence and fail-loud ambiguity. Backfill legacy partial methodology into formal rows, but do not treat those rows as complete historical scoring authority.

---

### H. Future-Proofing Without Overbuilding

| Question | Answer | Evidence | Status |
| --- | --- | --- | --- |
| Which stabilization changes are clearly needed now? | Methodology snapshot authority, report fallback honesty, reader convergence through narrow helpers, `report_status`/artifact display semantics, export redaction honesty, and legacy label/backfill behavior. | Validation memo findings. | verified |
| Which tempting changes should be deferred because they belong to later phases? | Telemetry provider architecture, backend abstraction, report stack consolidation, full export/case-file redesign, optimization/recommendation semantics, broad packaging cleanup, and generalized methodology audit architecture. | User scope constraints and Phase 1.1 purpose. | verified |
| How do we solve the current stabilization problems without accidentally starting Phase 2 work early? | Keep `src/code_identity.py` and `src/trust_identity.py` narrow. Add only the helpers needed to read existing Phase 1 authority surfaces. Do not introduce plugin frameworks, provider abstractions, generalized status engines, or report rewrites. | Existing implementation plan caution about avoiding mini-frameworks. | inferred |

**Future-proofing resolution:** Stabilize Phase 1 trust authority through small shared readers and explicit labels. Defer platform architecture.

---

## 3. Resolution Matrix

| Issue | Current reality | Why it matters | Design options | Recommended resolution | Why this is best | Explicitly deferred | Decision status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Methodology snapshots are persisted but not authoritative for scoring | `src/score.py` writes snapshots but still computes from live governance/profile/registry | Historical scoring can drift after profile/registry changes | A. Keep live scoring and label it. B. Rehydrate from snapshots for historical scoring. C. Build new methodology engine | B. Add a narrow snapshot rehydration path and make historical scoring/rescore/reporting use it | Removes the biggest shadow truth without a broad governance redesign | Full methodology architecture/versioning overhaul | ready |
| Legacy `notes_json.governance_methodology` has no formal bridge | Legacy partial methodology exists outside `methodology_snapshots` | Readers will keep special-casing notes or ignoring legacy methodology | A. Lazy bridge per reader. B. Backfill partial rows. C. Ignore | B. Backfill `legacy_partial` methodology snapshot rows where safe | Gives all readers one table and one label model | Full legacy reconstruction | ready, with blocking behavior needing approval |
| Snapshot-locked rescore lacks methodology authority | Rescore locks baseline but still relies on score path methodology behavior | Rescore can silently use current methodology | A. Continue current behavior. B. Block until snapshot methodology exists. C. Use current method but label | B. Snapshot-locked rescore requires complete baseline and methodology snapshots; explicit `--current-input` remains escape hatch | Matches Phase 1 trust philosophy | Automatic full reconstruction of old methodology | needs approval |
| Report fallback uses current input by default | Report paths pass `allow_current_input=True`; label can say explicit even when implicit | User can believe current-file data is historical | A. Keep and relabel. B. Disable implicit current fallback for trust identity. C. Add new report mode only | B. Default historical reports use snapshot/legacy labels; current input requires explicit request | Prevents silent identity strengthening | Full report UX redesign | ready |
| Report methodology display uses live profile/defaults | Report methodology sections can reflect current `governance.DEFAULT_PROFILE` | Historical reports can drift | A. Leave as display only. B. Read `methodology_snapshots`. C. Remove methodology display | B. Display persisted methodology snapshot first; legacy partial labels if incomplete | Keeps useful report content while making it trustworthy | Full report consolidation | ready |
| Compare reads snapshot rows directly | `src/compare.py` queries `campaign_start_snapshot` with direct SQL | Compare can become another identity source | A. Leave direct SQL. B. Wrap through trust helper. C. Rewrite compare | B. Move trust identity reads into `trust_identity` helper and update compare | Small convergence win without compare rewrite | Recommendation/optimization compare semantics | ready |
| Secondary readers may bypass trust model | `src/explain.py` and similar readers need confirmation | Hidden trust surfaces can retain shadow truth | A. Ignore. B. Search/patch only if historical claims. C. Broad reader audit | B. Inspect secondary readers during Phase 1.1 and migrate only historical trust claims | Disciplined scope | Broad audit of all commands | ready |
| `report_status` lacks clear aggregate semantics | Primary report can complete while secondary artifact fails | Campaign state can overstate report/artifact success | A. Add separate status table. B. Add/standardize `partial` on campaign. C. Use artifact rows only | B. Keep campaign fields, define `partial`, and surface artifact rows | Smallest model satisfying layered-state contract | Separate report/artifact phase table | needs approval |
| Artifact rows are richer but readers underuse them | Reports/export do not consistently show `status`, `sha256`, `error_message`, `verification_source` | Failed/unverified artifacts remain hidden | A. Leave for later. B. Minimal artifact-reader convergence. C. New artifact browser | B. Reports/export use artifact rows first and label legacy path-only artifacts | Makes existing artifact truth visible | Full artifact subsystem | ready |
| Export redaction references stale schema | `_redact_env()` mentions old `metadata_json`/`raw_json` and swallows errors | Strip exports may appear safer than they are | A. Remove redaction. B. Make redaction schema-aware and label completeness. C. Full export redesign | B. Fix redaction assumptions and add explicit completeness/legacy labels | Keeps export non-misleading without expanding scope | Full case-file fidelity/export redesign | ready |
| Legacy incomplete rows can be silently upgraded by current files | Some paths still allow current fallback | Historical truth can be strengthened without evidence | A. Allow but label. B. Block all. C. Allow only explicit current-input modes | C. Default to historical weak labels; explicit current-input only | Preserves usability while preventing shadow truth | Automatic migration to complete historical evidence | ready |
| Duplicate snapshot migration policy | Existing migration guard fails duplicates; docs drift still exists | Duplicate authority rows are dangerous | A. Quarantine. B. Fail loudly. C. Pick newest | B. Fail loudly and require manual remediation for non-identical duplicates | Trust work should not hide ambiguity | Auto-quarantine tooling | ready |

---

## 4. Future-Fit Check

### Telemetry / Provider Strategy

Phase 1.1 should make later telemetry/provider work easier by separating historical trust evidence from current provider behavior. Snapshot methodology and baseline authority should not know whether future telemetry came from llama.cpp, another backend, or a provider adapter. The stabilization plan should avoid provider abstractions now; it only needs persisted evidence and honest readers.

**Future-fit result:** Easier, if Phase 1.1 keeps snapshot identity backend-neutral and does not introduce provider frameworks.

### Architecture / Generalization

The narrow `trust_identity` approach is future-fit if it remains a small read model over persisted trust surfaces. It becomes harmful if it grows into a generic application service layer during stabilization.

**Future-fit result:** Easier, if helper APIs stay narrow and behavior-focused.

### Report Consolidation

Phase 1.1 should not merge `report.py` and `report_campaign.py`. It should make both consume the same trust evidence. That makes later consolidation safer because report content will already agree on identity and methodology semantics.

**Future-fit result:** Easier, because future consolidation can focus on presentation rather than source-of-truth disputes.

### Recommendation / Optimization Semantics

Optimization and recommendation work will need stable measurement, interpretation, and artifact truth. Phase 1.1 should not implement optimization semantics, but it should make sure historical scoring authority is not current-input by accident.

**Future-fit result:** Easier, because future recommendations can depend on stable historical evidence.

### Methodology Audit / Compare Behavior

Methodology audit and compare will benefit from formal `methodology_snapshots` rows, including legacy partial rows. Compare should not grow independent methodology logic; it should consume shared trust summaries.

**Future-fit result:** Easier, if compare and audit converge on shared trust readers now.

### Export / Case-File Fidelity

Export does not need full case-file fidelity in Phase 1.1, but it must stop overstating completeness. Adding provenance completeness labels now creates a clean foundation for later richer exports.

**Future-fit result:** Easier, because later export work can improve fidelity without revisiting whether old bundles were misleading.

---

## 5. Locked Design Conclusions

1. `methodology_snapshots` is the Phase 1.1 historical methodology authority. Do not create another methodology store.
2. Current-run scoring may load live methodology once, but historical scoring/rescore/reporting must use the persisted methodology snapshot when complete.
3. Legacy methodology should be bridged into `methodology_snapshots` as `legacy_partial`, not reconstructed into full truth.
4. Snapshot-locked rescore should require complete baseline and methodology evidence. Current-input rescoring must stay explicit.
5. Reports must not use implicit current-file fallback as historical authority.
6. Both report stacks should be stabilized through shared readers, not merged.
7. `compare.py` should stop directly reading trust snapshot rows for identity-like claims.
8. Campaign-level status fields remain the Phase 1.1 status surface, with artifact rows as per-artifact truth.
9. `report_status='partial'` should be added/standardized for mixed report/artifact outcomes, pending approval.
10. Export Phase 1.1 target is non-misleading trust behavior, not full case-file redesign.

---

## 6. Decisions Requiring Human Approval

1. **Report status vocabulary:** Approve adding/standardizing `report_status='partial'` for cases where the primary report phase succeeds but one or more expected report artifacts fail or are incomplete.
2. **Legacy methodology rescore policy:** Approve blocking snapshot-locked rescoring when methodology evidence is only `legacy_partial`, while allowing explicit current-input rescoring with visible labels.

These are the only remaining decisions that meaningfully affect user-visible behavior. The rest of the stabilization choices are ready to plan against.

