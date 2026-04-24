# Command Reference

This is the authoritative lookup for the `quantmap` CLI. For detailed workflows, see the [Operator Playbooks](../../docs/playbooks/README.md).

Start here:

- `quantmap doctor`
- `quantmap run --campaign <ID> --validate`
- `quantmap run --campaign <ID>`
- `quantmap list`
- `quantmap explain <campaign-id> --evidence`

For agent maintenance and automation commands, see [Agent Command Catalog](../instructions/agent_command_catalog.md).

---

## 🧰 General & Utility

### `about`

- **Purpose**: Displays system identity, provenance, and active registry counts.
- **Mutates?**: NO.
- **Example**: `quantmap about`

### `status`

- **Purpose**: Displays a situational dashboard of your lab (campaign counts, readiness pulse).
- **Mutates?**: NO.
- **Example**: `quantmap status`

### `init`

- **Purpose**: Interactive setup wizard for Lab Root and path configuration.
- **Mutates?**: YES (`.env`).
- **Example**: `quantmap init`

### `doctor`

- **Purpose**: Runs environment health checks (Readiness Model).
- **Mutates?**: NO (Unless `--fix` is passed for filesystem scaffolding).
- **Example**: `quantmap doctor`

### `self-test`

- **Purpose**: Verifies tool integrity (math, I/O, registry loading).
- **Mutates?**: NO (Uses a temporary in-memory database).
- **Example**: `quantmap self-test --live`

---

## 🚀 Benchmarking & Analysis

### `run`

- **Purpose**: Orchestrates a benchmarking campaign.
- **Mutates?**: YES (`lab.sqlite`, `results/`).
- **Flags**: `--campaign`, `--mode`, `--values`, `--validate`, `--dry-run`, `--resume`, `--baseline`.
- **Example**: `quantmap run --campaign C01 --mode standard`

### `list`

- **Purpose**: Displays a history of campaigns with status, winners, and campaign summary discoverability.
- **Mutates?**: NO.
- **Example**: `quantmap list`

### `explain`

- **Purpose**: Generates an evidence-bound technical briefing for an outcome.
- **Mutates?**: NO.
- **Flags**: `--evidence` (Includes denser factual audit basis).
- **Example**: `quantmap explain C01 --evidence`

### `compare`

- **Purpose**: Performs a forensic audit and delta analysis between two campaigns.
- **Mutates?**: NO (Writes a report to `results/comparisons/`).
- **Flags**: `--force` (Proceed despite methodology mismatch).
- **Example**: `quantmap compare Baseline C01`

### `artifacts`

- **Purpose**: Discovers artifact paths and DB-registered status for a campaign.
- **Mutates?**: NO.
- **Flags**: `--db` (Path to lab.sqlite override).
- **Example**: `quantmap artifacts B_low_sample__v512`

### `export`

- **Purpose**: Generates a portable `.qmap` forensic case file.
- **Mutates?**: NO.
- **Flags**: `--lite`, `--strip-env`.
- **Example**: `quantmap export C01 --strip-env --output Case_A.qmap`

### `acpm`

- **Purpose**: ACPM-guided campaign planning (preview, validate, profile discovery).
- **Mutates?**: NO. Execution wiring (`acpm run`) is a separate bundle.
- **Subcommands**:
  - `quantmap acpm info [--profile <name>]` — list all profiles or show details for one
  - `quantmap acpm plan --campaign <ID> --profile <name> [--tier <n>x]` — preview effective plan
  - `quantmap acpm validate --campaign <ID> --profile <name> [--tier <n>x]` — check input validity
- **Example**: `quantmap acpm plan --campaign NGL_sweep --profile Balanced --tier 1x`

---

## 🧪 Interpretation & Maintenance

### `rescore`

- **Purpose**: Re-processes raw data using updated profiling rules.
- **Mutates?**: YES (Updates the `scores` table in `lab.sqlite`).
- **Flags**: `--all`, `--force-new-anchors`.
- **Example**: `quantmap rescore --all`

### `audit`

- **Purpose**: Verifies methodological integrity between two campaign IDs.
- **Mutates?**: NO.
- **Example**: `quantmap audit C01 C02`

---

## 🚩 Global Flags Reference

- **`--plain`**: Disables all Rich formatting, colors, and symbols for raw text ingestion.

## Command-Specific Path Flags

- **`--db`**: Available on `artifacts`, `audit`, `compare`, `explain`, `explain-compare`, and `export`.
- **`--output`**: Available on `compare` and `export`.
