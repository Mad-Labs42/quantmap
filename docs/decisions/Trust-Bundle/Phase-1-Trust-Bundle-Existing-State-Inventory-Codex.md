# Phase 1 Trust Bundle Existing-State Inventory

**Status:** implementation-readiness inventory  
**Date:** 2026-04-11  
**Scope:** Phase 1 Trust Bundle only  
**Next artifact:** Phase 1 Trust Bundle Implementation Plan

## Mission

This inventory identifies what QuantMap can safely build on before Phase 1
trust work starts. It is intentionally not a broad audit, code review, or
implementation plan.

Project rule:

> Do not build Phase 1 on top of half-built, duplicated, stale, or misleading
> trust systems.

Inventoried areas:

1. Snapshotting / self-containment
2. QuantMap code identity capture
3. Snapshot-first report identity
4. Layered runtime state
5. Trust-critical path/settings assumptions

Disposition vocabulary:

- `keep`: already the right foundation.
- `extend`: good base, needs specific Phase 1 enhancement.
- `replace`: wrong shape for Phase 1; use only as transitional/legacy input.
- `remove`: should not survive as a trust-bundle mechanism.
- `leave for now`: not ideal, but not part of Phase 1 trust work.

Status vocabulary:

- `usable`: trustworthy enough to build on directly.
- `partial`: real mechanism, but incomplete.
- `duplicated`: overlapping mechanism or source-of-truth split.
- `misleading`: appears authoritative but is not.
- `dead/transitional`: stale, obsolete, or only useful as legacy compatibility.

In the area inventory sections below, the section heading is the `Area` field
for every mechanism in that section. The final decision table repeats the area
explicitly for quick scanning.

## A. Snapshotting / Self-Containment

| Mechanism | Where | Current status | Disposition |
|---|---|---|---|
| `campaign_start_snapshot` table | `src/db.py`, `src/runner.py`, `src/telemetry.py` | `partial` | `extend` |
| Verbatim campaign YAML in DB | `campaign_start_snapshot.campaign_yaml_content` | `usable` | `keep` |
| `campaign_yaml_snapshot.yaml` sidecar | `src/runner.py` | `misleading` | `replace` |
| Baseline YAML hash-only persistence | `campaigns.baseline_sha256`, `campaign_start_snapshot.baseline_yaml_sha256` | `misleading` | `extend` |
| Duplicate campaign/baseline hash fields | `campaigns`, `campaign_start_snapshot` | `duplicated` | `leave for now` |
| Prompt payload identity | `campaign_start_snapshot.prompt_sha256_json` | `partial` | `leave for now` |
| Sampling params snapshot | `campaign_start_snapshot.sampling_params_json` | `usable` | `keep` |
| Methodology anchors in `notes_json` | `campaigns.notes_json.governance_methodology` | `partial` | `replace` |
| Live registry/profile loaders | `src/governance.py`, `configs/metrics.yaml`, `configs/profiles/*.yaml` | `usable` | `extend` |
| Claimed `methodology_snapshots` table | `docs/system/database_schema.md`, `src/export.py` | `dead/transitional` | `remove` |
| `.qmap` export bundle | `src/export.py`, trust-surface docs | `misleading` | `replace` |

### A Decisions And Risks

| Mechanism | What it currently does | Why | Risks if kept as-is | Notes / dependencies |
|---|---|---|---|---|
| `campaign_start_snapshot` table | Stores run-start server binary path/hash, model metadata, backend build string, prompt hashes, sampling params, campaign YAML hash/content, baseline hash, and environment fields. | It is the strongest existing snapshot container. | Baseline content, methodology content, QuantMap source identity, and resolved run-plan identity remain absent. | Extend this or a tightly linked snapshot table. Do not add an unrelated second snapshot path. |
| Verbatim campaign YAML in DB | Stores the campaign YAML text at run start. | This is real historical content, not just a hash. | Low DB risk. | Use as the model for baseline and methodology content capture. |
| `campaign_yaml_snapshot.yaml` sidecar | Writes a human-readable copy beside reports. | Useful only as convenience. | On resume or rerun, it can be written from current YAML while DB preserves older truth. | Regenerate from DB snapshot truth or remove as a trust artifact. |
| Baseline YAML hash-only persistence | Stores baseline hashes but not text. | Hashes help integrity checks if the original file still exists. | Historical baseline flags, model labels, anchors, and runtime assumptions cannot be reconstructed. | Add verbatim effective baseline content plus hash and source path. |
| Duplicate hash fields | Stores similar campaign/baseline hashes in both campaign row and start snapshot. | Not the main Phase 1 blocker. | Future code can read the wrong hash location or mistake hash presence for content preservation. | Treat start snapshot as provenance authority; leave campaign hashes as indexes/legacy fields. |
| Prompt payload identity | Stores SHA256 hashes of prompt/request files. | Useful identity, but not Phase 1's primary blocker. | Full offline reconstruction can still depend on repo files. | Add prompt content only if Phase 1 includes self-contained export bundles. |
| Sampling params snapshot | Stores the `sampling` block from baseline. | Good subset of runtime intent. | Can be mistaken for full baseline capture. | Keep, but do not use as substitute for verbatim baseline content. |
| Methodology anchors in `notes_json` | Stores normalization reference values and provenance; reused on rescore. | Anchor preservation is useful. | It lacks verbatim registry/profile content, gates, weights, scoring code identity, and a first-class schema. | Preserve as legacy input during migration to formal methodology snapshots. |
| Live registry/profile loaders | Load and validate metric registry/profile from disk. | Strong live methodology foundation. | Historical scoring can drift if current disk is used for old runs. | Snapshot serialized effective registry/profile content. |
| Claimed `methodology_snapshots` table | Docs/export mention a table that `src/db.py` does not create. | False source-of-truth path. | Implementers may believe methodology snapshots already exist. | Remove/update once formal storage is chosen. |
| `.qmap` export bundle | Copies a hardcoded table list and writes export-time metadata. | Current shape does not match trust claims. | Omits start snapshots/background snapshots and references nonexistent methodology storage. | Replace or explicitly mark out of scope for Phase 1. |

## B. QuantMap Code Identity Capture

| Mechanism | Where | Current status | Disposition |
|---|---|---|---|
| Software/methodology version constants | `src/version.py`, `pyproject.toml`, `quantmap.py` | `partial` | `extend` |
| QuantMap git/source fingerprint | no first-class implementation found | `partial` | `extend` |
| Backend build commit string | baseline `runtime.build_commit`, `campaign_start_snapshot.build_commit` | `misleading` | `replace` |
| Server binary SHA256 | `campaign_start_snapshot.server_binary_sha256` | `usable` | `keep` |
| DB schema version | `src/db.py` `schema_version` | `usable` | `keep` |
| Export manifest version | `src/export.py` `_write_manifest` | `misleading` | `replace` |
| CLI `about` / `status` identity | `quantmap.py`, trust-surface docs | `usable` | `leave for now` |

### B Decisions And Risks

| Mechanism | What it currently does | Why | Risks if kept as-is | Notes / dependencies |
|---|---|---|---|---|
| Version constants | Defines current software and methodology version strings and displays them in CLI/export. | Useful current-process identity. | Regenerated reports/exports can show the current tool, not the tool that measured the run. | Persist run-time `quantmap_version` and methodology version in snapshot identity. |
| QuantMap source fingerprint | No per-run git commit, dirty flag, source hash, build metadata, or runner identity is stored. | Explicit missing piece. | Cannot prove which QuantMap code measured, analyzed, or rendered historical results. | Add git commit, dirty flag, source hash fallback, and capture errors/warnings. |
| Backend build commit string | Stores a user-supplied backend build string from baseline YAML. | It is backend identity, not QuantMap identity. | Reports imply a proven build commit when it may be only a baseline claim. | Rename/display as claimed backend build unless verified. |
| Server binary SHA256 | Hashes the `llama-server` executable. | Strong dependency identity. | Does not identify QuantMap itself. | Keep and pair with QuantMap source identity. |
| DB schema version | Tracks DB compatibility and blocks older code reading newer DBs. | Correct schema safety mechanism. | Could be mistaken for tool/source identity. | Keep separate from code identity. |
| Export manifest version | Writes software/methodology version at export time. | Export-time metadata is not run-time identity. | Later tools can stamp old measurements with current identity. | Export should read run snapshot identity and separately label exporter identity. |
| CLI identity display | Shows current version, methodology, profile, lab root, DB path. | Useful current environment diagnostic. | Docs imply historical trust guarantees that are not yet backed by per-run storage. | Leave as diagnostics, not historical evidence. |

## C. Snapshot-First Report Identity

| Mechanism | Where | Current status | Disposition |
|---|---|---|---|
| Evidence-first report header | `src/report_campaign.py` `_section_header` | `partial` | `replace` |
| Legacy `report.md` metadata | `src/report.py` `_build_markdown` | `misleading` | `replace` |
| Report regeneration / rescore identity inputs | `rescore.py`, `src/score.py`, report modules | `misleading` | `replace` |
| Methodology display in reports | `src/report_campaign.py`, `src/report.py`, `src/score.py` | `partial` | `replace` |
| Baseline-relative score percentages | `src/score.py`, report modules | `partial` | `replace` |
| Production command identity | `configs.resolved_command`, `runtime_env_json`, report modules | `duplicated` | `extend` |
| Artifact registration | `src/report.py`, `src/report_campaign.py`, `artifacts` table | `partial` | `extend` |
| Generic fallback labels | report modules | `partial` | `replace` |
| Compare report identity | `src/compare.py`, `src/audit_methodology.py`, `src/report_compare.py` | `partial` | `extend` |

### C Decisions And Risks

| Mechanism | What it currently does | Why | Risks if kept as-is | Notes / dependencies |
|---|---|---|---|---|
| Evidence-first report header | Reads campaign row and start snapshot for some fields, but live baseline for machine/model/quant/model size. | Good DB-backed shell, wrong identity source for key labels. | Historical reports can inherit changed model name, quant label, or machine labels. | Source identity from DB snapshots first; legacy fallback must be explicit. |
| Legacy `report.md` metadata | Uses DB for some fields and live baseline for machine, BIOS, model, anchors, and command context. | Still primary success path in runner. | Live-disk identity leakage is not confined to a deprecated report. | Harden snapshot-first or demote after `report_v2` becomes canonical. |
| Report regeneration / rescore inputs | Loads current baseline/campaign YAML and reruns scoring/reporting. | Clearest historical drift path. | Old reports can be regenerated using current baseline references, current campaign overrides, and current profile defaults. | Consume historical snapshots unless explicit migration mode is requested. |
| Methodology display | Uses hardcoded labels/current profile objects plus partial anchor refs. | Anchor refs are useful but incomplete. | Reports can display methodology text that does not match stored or current semantics. | Formal snapshot must include display identity, profile, registry, gates, weights, anchors, and migration status. |
| Baseline-relative percentages | Computes deltas from live `baseline.reference` unless preserved refs are available. | Good concept, weak source. | Baseline reference edits can change interpretation. | Move into formal methodology/baseline snapshot consumption. |
| Production command identity | Runner stores DB command/env; `report_campaign` uses DB; `report.py` reconstructs from config/env first. | DB command is a strong foundation. | Legacy reconstruction can leak current env paths. | Prefer `configs.resolved_command` plus `runtime_env_json` everywhere. |
| Artifact registration | Writes report/scores artifact rows after success. | Good seed for artifact truth. | No hashes, no failure rows, and raw/telemetry/run-context artifacts are not consistently registered. | Extend with artifact status, hash, stage, and failure detail. |
| Generic fallback labels | Displays `unknown`, `N/A`, or `--` for missing values. | Missingness is visible. | Reader cannot distinguish true unknown, legacy missing snapshot, and live-disk fallback. | Implement legacy fallback labels before report hardening is complete. |
| Compare report identity | Compares environment fields from start snapshot and methodology anchors from notes JSON. | Environment comparison is useful. | Methodology compatibility can be judged from incomplete anchor snapshots. | Extend after formal methodology snapshots exist. |

## D. Layered Runtime State

| Mechanism | Where | Current status | Disposition |
|---|---|---|---|
| `campaigns.status` | `src/db.py`, `src/runner.py` | `misleading` | `extend` |
| `configs.status` | `src/db.py`, `src/runner.py`, `src/telemetry.py` | `duplicated` | `replace` |
| `cycles.status` and `cycle_id` linkage | `src/db.py`, `src/runner.py`, `src/analyze.py` | `usable` | `keep` |
| Request outcome and request `cycle_status` | `src/db.py`, `src/measure.py`, `src/analyze.py` | `usable` | `keep` |
| `scores` table | `src/db.py`, `src/score.py` | `usable` | `extend` |
| Analysis completion is implicit | `src/analyze.py`, `src/score.py`, `src/runner.py` | `partial` | `extend` |
| Report success/failure handling | `src/runner.py`, report modules | `partial` | `extend` |
| Runtime `artifacts` table | `src/db.py`, report modules | `partial` | `extend` |
| Crash recovery `progress.json` | `src/runner.py`, `LAB_ROOT/state/progress.json` | `partial` | `leave for now` |
| Per-cycle `run_context` JSON sidecars | `src/run_context.py`, `src/runner.py`, `src/report_campaign.py` | `partial` | `extend` |
| Severity B/degraded signaling | `src/telemetry.py`, `src/score.py` | `partial` | `extend` |
| Diagnostics readiness model | `src/diagnostics.py`, `src/doctor.py`, `quantmap.py status` | `usable` | `leave for now` |

### D Decisions And Risks

| Mechanism | What it currently does | Why | Risks if kept as-is | Notes / dependencies |
|---|---|---|---|---|
| `campaigns.status` | Tracks campaign `pending/running/complete/failed/aborted`; runner marks `complete` before analysis/report generation. | Useful as measurement-lifecycle state. | A campaign can be marked complete while analysis/report/artifacts failed. | Add or rename layers: measurement, interpretation, artifact/presentation. |
| `configs.status` | Tracks execution states such as complete/OOM/skipped; telemetry can set degraded; comments mention eliminated. | Conflates measurement, degradation, and interpretation concepts. | Score eliminations live in `scores`, but some code queries config status; degraded update lacks campaign scope. | Split measurement status from interpretation status and fix campaign-scoped writes. |
| `cycles.status` / `cycle_id` | Tracks pending/started/complete/invalid and links requests/telemetry/background rows. | Strong measurement boundary. | Legacy rows with null `cycle_id` need explicit handling. | Keep as bottom-layer measurement truth. |
| Request outcome / cycle status | Stores individual request outcomes and invalidates requests when cycle invalidates. | Solid measurement truth. | Low risk if not mixed with report/interpretation state. | Keep. |
| `scores` table | Stores stats, filters, eliminations, ranking, winner flags, and baseline deltas. | Strong interpretation layer seed. | Lacks scoring-run status, methodology snapshot key, and code identity. | Extend rather than replace. |
| Implicit analysis completion | Analysis/scoring success is inferred from scores side effects. | Data path is sound. | Cannot query failed, not-run, no-rankable, or succeeded states cleanly. | Add analysis/scoring status and failure detail. |
| Report success/failure handling | Primary report success controls exit code; v2 failure is logged and non-fatal. | Existing code already knows post-run failure differs from measurement loss. | DB still says campaign complete while report state is unknown/failed. | Persist presentation/artifact state. |
| `artifacts` table | Records generated artifact paths/timestamps. | Good seed. | No failed artifact records, hashes, or stage ownership. | Extend with status, hash, error, artifact class. |
| `progress.json` | Atomic resume sidecar for current config/cycle and completed configs. | Correct resume implementation detail. | Not DB-queryable and cleared after measurement. | Keep for resume; do not build trust reporting on it. |
| `run_context` sidecars | Capture per-cycle environment quality/confidence and are loaded by reports. | Strong evidence-quality vocabulary. | Not DB-queryable; missing sidecars are not first-class state. | Persist summary/status or register artifacts. |
| Severity B/degraded | Telemetry write failure marks config degraded; scoring invalidates it. | Valuable distinction. | Update uses config id without campaign id; reason stored in `elimination_reason`. | Formalize degraded state and campaign-scoped updates. |
| Diagnostics readiness | Collapses current checks into READY/WARNINGS/BLOCKED. | Useful current readiness model. | Could be confused with historical campaign quality. | Leave outside Phase 1 except wording clarity. |

## E. Trust-Critical Path / Settings Assumptions

| Mechanism | Where | Current status | Disposition |
|---|---|---|---|
| Core path constants | `src/config.py`, `.env.example` | `usable` | `keep` |
| Baseline-derived lab-root namespacing | `src/runner.py` `_derive_lab_root` | `partial` | `extend` |
| `RunPlan` resolved runtime intent | `src/run_plan.py`, built in `src/runner.py` | `usable` | `extend` |
| Report module lab-root fallbacks | `src/report.py`, `src/report_campaign.py` | `misleading` | `replace` |
| Rescore DB/baseline path handling | `rescore.py`, `quantmap.py cmd_rescore` | `misleading` | `replace` |
| `quantmap list` DB visibility | `src/runner.py list_campaigns` | `partial` | `leave for now` |
| Backend path constants | `src/server.py` | `usable` | `extend` |
| Supporting artifact path derivation | `src/report_campaign.py` | `partial` | `extend` |
| Export table/path assumptions | `src/export.py` | `dead/transitional` | `replace` |

### E Decisions And Risks

| Mechanism | What it currently does | Why | Risks if kept as-is | Notes / dependencies |
|---|---|---|---|---|
| Core path constants | Requires `QUANTMAP_LAB_ROOT`; defines configs, requests, host, and production port. | Clear infrastructure authority. | Low risk. | Keep as base path authority. |
| Baseline lab-root namespacing | Default baseline uses `LAB_ROOT`; other baselines write to `LAB_ROOT/profiles/<stem>`. | Useful isolation for multiple baselines/models. | Other commands can miss namespaced DB/log/result paths. | Centralize outside runner or expose an official resolver. |
| `RunPlan` | Captures effective campaign id, mode, selected values, schedule, baseline path, lab root, DB path, state file, and results dir. | Best model of requested intent plus resolved run shape. | Not persisted; regenerated reports lose mode/scope when `RunPlan` is absent. | Serialize effective run plan into DB snapshot state. |
| Report lab-root fallbacks | Use `Path(os.getenv("QUANTMAP_LAB_ROOT", "D:/Workspaces/QuantMap"))`. | Duplicates path authority. | Can silently read/write wrong lab root. | Replace with injected lab root or centralized resolver. |
| Rescore path handling | Uses default `LAB_ROOT/db/lab.sqlite`; `--baseline` changes loaded baseline, not DB namespace. | Historical reinterpretation path must be path-safe. | Namespaced runs can be rescored against the wrong DB or current baseline. | Make rescore snapshot-first and path-resolver based. |
| `quantmap list` visibility | Lists only default runner `DB_PATH`. | Operator UX issue. | Namespaced campaign histories can be hidden. | Leave unless Phase 1 touches status/list. |
| Backend path constants | Reads server/model/MKL/CUDA env vars at import time; runner snapshots some resolved paths. | Correct current backend authority. | Requested vs resolved runtime reality is not fully persisted/labeled. | Snapshot resolved backend paths/commands with source labels. |
| Supporting artifact paths | Infers logs from DB path and files from results dir. | Works in current lab layout. | Moved/exported reports can have stale absolute paths. | Artifact table should become durable artifact identity. |
| Export assumptions | Copies hardcoded tables and references stale columns. | Stale relative to current schema. | Can omit trust-critical tables and fail redaction assumptions. | Replace after snapshot/artifact schema is chosen. |

## Decision Table

| Mechanism | Area | Status | Disposition | Short reason |
|---|---|---|---|---|
| `campaign_start_snapshot` table | Snapshotting | `partial` | `extend` | Best snapshot container, missing trust-bundle identity content. |
| Verbatim campaign YAML in DB | Snapshotting | `usable` | `keep` | Real historical content snapshot. |
| `campaign_yaml_snapshot.yaml` sidecar | Snapshotting | `misleading` | `replace` | Can drift from preserved DB snapshot. |
| Baseline YAML hash-only persistence | Snapshotting | `misleading` | `extend` | Hash is not reconstructible content. |
| Duplicate campaign/baseline hashes | Snapshotting | `duplicated` | `leave for now` | Harmless if start snapshot is authoritative. |
| Prompt payload hashes | Snapshotting | `partial` | `leave for now` | Useful hash identity; not Phase 1 core unless export is included. |
| Sampling params JSON | Snapshotting | `usable` | `keep` | Good subset snapshot. |
| `notes_json.governance_methodology` | Snapshotting | `partial` | `replace` | Useful anchors, wrong full-methodology shape. |
| Live registry/profile loaders | Snapshotting | `usable` | `extend` | Strong live source; needs historical snapshot. |
| Claimed `methodology_snapshots` table | Snapshotting | `dead/transitional` | `remove` | Referenced but not implemented. |
| `.qmap` export bundle | Snapshotting | `misleading` | `replace` | Omits trust-critical data and uses stale assumptions. |
| Version constants | Code identity | `partial` | `extend` | Current identity exists, not per-run identity. |
| QuantMap source fingerprint | Code identity | `partial` | `extend` | Missing historical git/source identity. |
| Backend build commit string | Code identity | `misleading` | `replace` | User-supplied backend claim, not QuantMap identity. |
| Server binary SHA256 | Code identity | `usable` | `keep` | Strong backend executable identity. |
| DB schema version | Code identity | `usable` | `keep` | Valid schema compatibility signal, not code identity. |
| Export manifest version | Code identity | `misleading` | `replace` | Captures export-time tool version. |
| CLI identity display | Code identity | `usable` | `leave for now` | Current diagnostics only. |
| Evidence-first report header | Report identity | `partial` | `replace` | Mixes DB snapshot and live baseline identity. |
| Legacy `report.md` identity | Report identity | `misleading` | `replace` | Primary report path still uses live baseline. |
| Rescore/report regeneration inputs | Report identity | `misleading` | `replace` | Historical identity can come from current disk. |
| Methodology report display | Report identity | `partial` | `replace` | Hardcoded/current labels, no full snapshot. |
| Baseline-relative percentages | Report identity | `partial` | `replace` | Good concept, unsafe live source. |
| Production command identity | Report identity | `duplicated` | `extend` | DB command is good; legacy reconstruction leaks env. |
| Artifact registration | Report identity | `partial` | `extend` | Good seed; lacks status/hash/failure semantics. |
| Generic fallback labels | Report identity | `partial` | `replace` | Missing source provenance labels. |
| Compare report identity | Report identity | `partial` | `extend` | Env snapshot useful; methodology check too narrow. |
| `campaigns.status` | Runtime state | `misleading` | `extend` | Measurement completion conflates whole-run success. |
| `configs.status` | Runtime state | `duplicated` | `replace` | Execution/degradation/interpretation concepts collide. |
| `cycles.status` / `cycle_id` | Runtime state | `usable` | `keep` | Strong measurement boundary. |
| Request outcome / request cycle status | Runtime state | `usable` | `keep` | Solid measurement truth. |
| `scores` table | Runtime state | `usable` | `extend` | Strong interpretation layer; needs methodology/status linkage. |
| Implicit analysis completion | Runtime state | `partial` | `extend` | Success inferred from side effects. |
| Report success/failure handling | Runtime state | `partial` | `extend` | Exit/log only, not durable state. |
| Runtime `artifacts` table | Runtime state | `partial` | `extend` | Needs status, hashes, failures. |
| `progress.json` | Runtime state | `partial` | `leave for now` | Resume state, not durable truth. |
| `run_context` sidecars | Runtime state | `partial` | `extend` | Good quality model; not queryable. |
| Severity B/degraded signaling | Runtime state | `partial` | `extend` | Valuable concept, weak persistence shape. |
| Diagnostics readiness model | Runtime state | `usable` | `leave for now` | Current environment status, not historical run state. |
| Core path constants | Paths/settings | `usable` | `keep` | Clear path authority. |
| Baseline-derived lab-root namespacing | Paths/settings | `partial` | `extend` | Good isolation, missed by other commands. |
| `RunPlan` | Paths/settings | `usable` | `extend` | Best resolved runtime intent model; not persisted. |
| Report lab-root fallbacks | Paths/settings | `misleading` | `replace` | Silent hardcoded lab path. |
| Rescore DB/baseline paths | Paths/settings | `misleading` | `replace` | Can rescore wrong DB with current baseline. |
| `quantmap list` default DB visibility | Paths/settings | `partial` | `leave for now` | Hidden namespaced histories; not Phase 1 core. |
| Backend path constants | Paths/settings | `usable` | `extend` | Good current backend authority; needs historical labels. |
| Supporting artifact path derivation | Paths/settings | `partial` | `extend` | Works locally; artifact table should be durable authority. |
| Export schema/path assumptions | Paths/settings | `dead/transitional` | `replace` | Stale table/column assumptions. |

## Do Not Build On These

These mechanisms are especially dangerous Phase 1 foundations:

- **Baseline hash-only identity**: keep hashes, but never treat them as
  self-contained historical truth.
- **Live baseline object in reports/rescore**: `report.py`,
  `report_campaign.py`, `score.py`, and `rescore.py` can still derive old-run
  identity or anchors from current disk.
- **`campaigns.notes_json.governance_methodology` as full methodology truth**:
  it preserves anchors, not the full registry/profile/scoring semantics.
- **The claimed `methodology_snapshots` table**: docs and export mention it,
  but the DB schema does not implement it.
- **Current `.qmap` export**: it omits start snapshots, references nonexistent
  methodology storage, and stamps export-time versions.
- **`campaign_yaml_snapshot.yaml` as authoritative evidence**: it can be
  overwritten from current YAML while DB snapshot preservation remains correct.
- **`build_commit` as QuantMap identity**: it is a backend build string sourced
  from baseline YAML.
- **`campaigns.status='complete'` as whole-run success**: it currently means
  measurement loop completion, not analysis/report/artifact success.
- **`configs.status` for interpretation truth**: score eliminations are in
  `scores`, while comments/code paths still imply config-level eliminated state.
- **Report module hardcoded lab-root fallbacks**: they can silently read/write
  `D:/Workspaces/QuantMap`.
- **Rescore path assumptions**: rescore does not derive namespaced lab roots
  from baseline override and is not snapshot-first.

## Best Foundations To Build On

QuantMap has several strong foundations worth extending:

- **`campaign_start_snapshot`** is the right central run-start snapshot base.
- **`campaign_yaml_content`** proves verbatim snapshotting already exists.
- **`server_binary_sha256` and model file metadata** provide real dependency
  identity.
- **`configs.resolved_command` and `runtime_env_json`** are strong resolved
  runtime artifacts.
- **`cycles.status`, `cycle_id`, request outcomes, telemetry, and background
  snapshots** form a solid measurement-truth layer.
- **`scores`** is already a real interpretation layer with pass/fail,
  unrankable, ranking, and winner semantics.
- **`governance.py` plus `metrics.yaml` and profile YAML** are good live
  methodology foundations; they need snapshotting, not replacement.
- **`RunPlan`** is the best existing model of resolved runtime intent.
- **`config.py`** is a good infrastructure path authority.
- **`run_context.py`** has a useful evidence-quality vocabulary; it needs
  persistence/queryability.
- **`artifacts`** is a useful seed for artifact truth once status/hash/failure
  fields are added.

## Readiness Conclusion

Usable foundations already exist for:

- run-start snapshot container shape
- verbatim campaign YAML persistence
- backend binary/model identity
- measurement truth through cycles, requests, telemetry, and background data
- interpretation truth through scores
- resolved runtime intent through `RunPlan`
- infrastructure path authority through `config.py`

Mostly partial or misleading areas:

- baseline self-containment
- methodology/governance self-containment
- QuantMap code identity
- snapshot-first report identity
- export/case-file self-containment
- layered completion state
- report/regeneration path resolution

Clean replacement is needed for:

- the fake/stale `methodology_snapshots` contract
- current `.qmap` export assumptions
- live-disk report/rescore identity sourcing
- hardcoded report lab-root fallbacks
- treating `campaigns.status='complete'` as whole-campaign success
- using `configs.status` as both measurement and interpretation state

Phase 1 can now be planned cleanly if the implementation plan declares one
authoritative historical source of truth for:

- effective baseline content
- effective methodology/governance content
- QuantMap code/source identity
- resolved runtime intent and resolved runtime reality
- report/artifact generation state

The biggest cleanup decision before implementation planning is whether Phase 1
extends `campaign_start_snapshot` directly or introduces a tightly linked
first-class trust snapshot table. Either choice can work. What must not happen
is a second shadow snapshot path beside the existing one without a migration
and consumption rule. Reports, rescore, compare, and export should read the
same snapshot-first identity model, with live disk used only as an explicitly
labeled legacy fallback or explicit migration input.
