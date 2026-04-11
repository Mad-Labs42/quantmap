# Database Schema

QuantMap uses a single SQLite database (`lab.sqlite`) to store the entire lifecycle of a lab directory.

## 1. Table: `campaigns`
Detailed metadata about a specific benchmarking run.
- `id`: Unique campaign identifier (e.g. C01).
- `description`: Human-readable summary.
- `metadata_json`: Raw environment and configuration block.

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
- `snapshot_json`: Full copy of the Registry and Profile at runtime.
- `methodology_version`: e.g. "Governance v1.1".
