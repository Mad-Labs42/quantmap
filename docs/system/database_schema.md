# Database Schema

QuantMap uses a single SQLite database (`lab.sqlite`) to store the entire lifecycle of a lab directory.

> [!NOTE]
> `src/db.py` is the authoritative schema source. This document is a human overview and should be refreshed when schema details matter for implementation.

## Current Trust-Bundle Schema State

As of 2026-04-12, Phase 1/1.1 trust stabilization is stable. The current trust-critical schema surfaces include:

- `campaign_start_snapshot`: run-start authority for campaign YAML content, baseline content/identity, QuantMap code identity, effective run plan, and environment/backend snapshot fields.
- `methodology_snapshots`: historical methodology authority for profile/registry content, weights, gates, anchors, source hashes/paths, capture source, and capture quality.
- `campaigns.analysis_status` and `campaigns.report_status`: layered interpretation/report state separate from measurement lifecycle status.
- `artifacts.status`, `artifacts.sha256`, `artifacts.error_message`, and `artifacts.verification_source`: per-artifact evidence for produced, partial, failed, or legacy/path-only artifacts.

Phase 2 Operational Robustness should continue from this schema state without introducing a second historical trust model.

## 1. Table: `campaigns`
Detailed metadata about a specific benchmarking run.
- `id`: Unique campaign identifier (e.g. C01).
- `description`: Human-readable summary.
- `status`: Measurement lifecycle state.
- `analysis_status`: Interpretation/scoring lifecycle state.
- `report_status`: Report/artifact lifecycle state; may be `partial` when primary report output exists but expected artifacts failed, are incomplete, or are unverified.
- `notes_json`: Legacy notes and transition metadata.

## 2. Table: `configs`
The specific variable configurations tested in a campaign.
- `id`: Configuration identifier.
- `campaign_id`: Foreign key to `campaigns`.
- `variable_name`: The variable being swept (e.g. threads).
- `variable_value`: The specific value for this config.
- `config_values_json`: Full llama-server override dictionary.

## 3. Table: `cycles`
Operational records of each execution cycle.
- `id`: Cycle UUID.
- `status`: `complete`, `failed`, or `invalidated` (e.g. thermal event).
- `start_time`: ISO8601.

## 4. Table: `requests`
Individual inference measurements.
- `outcome`: `success`, `error`, or `timeout`.
- `warm_tg_median`: Token Generation rate (T/S).
- `warm_ttft_p90_ms`: Time To First Token for the tail.
- `raw_json`: Full response metadata from the server.

## 5. Table: `telemetry`
High-frequency hardware sensor data.
- `raw_json`: Snapshot of HWiNFO sensors (CPU Temp, Power, Throttling Status).

## 6. Table: `scores`
The analytical layer (Derived data).
- `composite_score`: Normalized [0,1] ranking.
- `passed_filters`: Boolean (1=Rankable, 0=Eliminated).
- `elimination_reason`: Textual rationale for rejection.
- `is_score_winner`: Boolean (The champion config).

## 7. Table: `methodology_snapshots`
Immutable records of the scoring rules used.
- `profile_yaml_content`: Verbatim profile content when captured.
- `registry_yaml_content`: Verbatim registry content when captured.
- `weights_json`, `gates_json`, `anchors_json`: Parsed methodology components used by readers.
- `capture_quality`: `complete`, `legacy_partial`, or another explicit evidence-quality label.
- `methodology_version`: e.g. "Governance v1.1".

## 8. Table: `campaign_start_snapshot`
Run-start trust snapshot for historical identity.
- `campaign_yaml_content`: Verbatim campaign definition captured at run start.
- `baseline_yaml_content`: Verbatim baseline definition when available.
- `baseline_identity_json`: Parsed baseline identity fields.
- `quantmap_identity_json`: QuantMap code identity captured at run start.
- `run_plan_json`: Effective requested runtime intent.

## 9. Table: `artifacts`
Produced or attempted artifact records.
- `artifact_type`: Report, export, score, or other artifact class.
- `path`: Produced path when available.
- `sha256`: Content hash when available.
- `status`: Artifact outcome.
- `verification_source`: How the artifact evidence was verified.
- `error_message`: Failure detail when production failed.
