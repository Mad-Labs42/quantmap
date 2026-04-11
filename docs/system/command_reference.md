# Command Reference

This is the authoritative lookup for the `quantmap` CLI. For detailed workflows, see the [Operator Playbooks](../README.md).

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
- **Example**: `quantmap doctor --mode quick`

### `self-test`
- **Purpose**: Verifies tool integrity (math, I/O, registry loading).
- **Mutates?**: NO (Uses a temporary in-memory database).
- **Example**: `quantmap self-test --live`

---

## 🚀 Benchmarking & Analysis

### `run`
- **Purpose**: Orchestrates a benchmarking campaign.
- **Mutates?**: YES (`lab.sqlite`, `results/`).
- **Flags**: `--campaign`, `--mode`, `--dry-run`, `--resume`, `--baseline`.
- **Example**: `quantmap run --campaign C01 --mode standard`

### `list`
- **Purpose**: Displays a history of campaigns with status and winners.
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

### `export`
- **Purpose**: Generates a portable `.qmap` forensic case file.
- **Mutates?**: NO.
- **Flags**: `--lite`, `--strip-env`.
- **Example**: `quantmap export C01 --strip-env --output Case_A.qmap`

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
- **`--db`**: Path to a specific `lab.sqlite` file, allowing you to run any command against a forensic `.qmap` or backup.
