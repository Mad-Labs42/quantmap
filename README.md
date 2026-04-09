# QuantMap

![Status](https://img.shields.io/badge/status-MVP%20%2F%20Active%20Development-orange)

**Stop guessing your inference settings. Measure them.**

QuantMap is a high-rigor measurement and reporting system for local LLM inference benchmarking. It runs structured campaigns that sweep server parameters (thread counts, batch sizes, GPU layer splits) and collects structured telemetry for statistically honest analysis and reporting

Instead of guessing settings or copying configurations without context, QuantMap provides a controlled experiment framework to evaluate and compare configurations with structured, evidence-based reporting.

---

## Project Status

QuantMap is currently in **active development (MVP stage)**.

Core benchmarking, validation, and reporting systems are functional, but:
- interfaces and workflows may change
- some analysis features are intentionally conservative or incomplete
- edge-case handling and reporting clarity are still being refined

QuantMap prioritizes **correctness and trustworthiness over completeness**, so some features may appear limited although the underlying system is stabilized.

This is not yet a finished product.

### What to Expect

- Results are **accurate within current constraints**, but may be limited in scope
- Some reports may be **intentionally conservative or incomplete**
- Not all edge cases are fully automated yet
- Output formats and scoring behavior may evolve

If something appears missing or cautious, it is more than likely **intentional rather than an oversight**.

---

## What QuantMap Is (And Is Not)

**QuantMap is:**
- A controlled experiment framework.
- A data collection and validation system.
- A traceable reporting engine.

**QuantMap is NOT:**
- A magic optimizer or a guaranteed "best config finder".
- A system that guarantees a conclusive winner for every campaign.
- A tool that automatically fixes bad data or hides uncertainty behind artificially clean outputs.
- A system that implies why something happened without evidentiary proof.

QuantMap is being built incrementally, with features introduced only when they can meet the system's standards for correctness and traceability.

---

## Why This Exists

Every local LLM user hits the same wall: you download a model, start a server with default settings, and then begin the process of manually testing dozens of parameter variations, eyeballing throughput numbers, and hoping you controlled for thermal throttling, background processes, and cold-start effects. This process is unreliable and time consuming.

QuantMap automates measurement and validation. It runs structured campaigns that test variables against one another across repeated trials, helping you define a sweep, execute it consistently, and determine whether the available evidence supports a valid comparison and a top-performing configuration.

---

## What It Does

- **Structured campaigns** — Define parameter sweeps in YAML. QuantMap generates all configs, runs them sequentially with controlled cooldowns, and collects measurements under consistent conditions.
- **Statistical validation** — Configs are filtered by success rate, outlier count, coefficient of variation, and thermal events. Survivors are ranked by observed performance metrics (throughput, latency, stability) (Ranking and elimination logic are campaign-configurable and intentionally conservative)
- **Full telemetry** — GPU temp, GPU utilization, CPU utilization, VRAM usage, RAM committed, CPU power draw, background interference (Defender, Windows Update, Search Indexer, AV scans), all sampled continuously and stored per-request.
- **Traceability and Reproducibility** — Every result is tied back to data. The schema-versioned SQLite database serves as the authoritative source of truth, and a `raw.jsonl` append-only trace preserves raw measurements. You can reproduce any run or share results with full context.
- **Separation of data and interpretation** — Raw data is immutable. Failures, invalid configs, and edge cases remain visible in the record rather than being silently dropped. Scoring thresholds can be adjusted and results re-scored in seconds without re-running hours of measurements.
- **Campaign-configurable thresholds** — Override elimination filters (`min_success_rate`, `max_outliers`, `max_cv`, `max_thermal_events`) per campaign in YAML. Different workloads have different stability requirements.
- **Pre-flight validation** — `--validate` checks your entire setup before a campaign runs: server binary existence, model file integrity, request file presence, baseline configuration, and Defender exclusion status.
- **Robust execution** — Handles crashes, OOM errors, and instability. Campaigns that crash or get interrupted (Ctrl+C) preserve all completed data. `--resume` picks up from the next incomplete config.

---

## Interpreting Results & Confidence

Evaluating inference configurations is inherently noisy. When reading QuantMap reports:
- **Top-performing doesn't imply absolute:** A configuration may score highest among tested variants, but this is bounded by the limited comparison cases and parameter ranges provided. "Winners" may not always emerge if data is sparse or statistical differences are negligible.
- **Failures are features:** Crashes, OOM errors, and thermal events are captured and surfaced, not hidden. A failed config is a valuable data point.
- **Confidence reflects evidence:** Statistical confidence is tied to sample size and variance. Small samples carry higher uncertainty. Ensure minimum sample requirements (requests per cycle, cycle counts) are adequate before drawing firm conclusions.
- **Data ≠ Interpretation:** Do not assume causality unless proven. The system reports what was measured, not necessarily *why* a configuration performed as it did.

---

## Requirements

### Hardware
- A machine with a CUDA-capable GPU (tested on RTX 3090, should work on any GPU supported by your inference backend)
- Enough RAM/VRAM to load your target model

### Software
- **Python 3.10+**
- **llama.cpp** — Built with CUDA support (`-DGGML_CUDA=ON`). QuantMap calls `llama-server` directly.
- **HWiNFO64** — Required for GPU/CPU telemetry (temperature, power draw, utilization). Must be running with Shared Memory enabled before starting a campaign.
  - Open HWiNFO → Settings → check **"Shared Memory Support"** → OK
  - Leave HWiNFO running in sensors-only mode during campaigns
- **Windows 10/11** — Current version is Windows-only. Linux/macOS support is planned for a future release (the codebase is structured for cross-platform expansion).

### Python Dependencies
```
pip install -r requirements.txt
```

Core dependencies: `httpx`, `numpy`, `psutil`, `rich`, `pyyaml`

---

## Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/Mad-Labs42/QuantMap.git
cd QuantMap
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure your environment
```bash
copy .env.example .env
```

Open `.env` and set your paths:
```ini
# Path to your llama-server binary
QUANTMAP_SERVER_BIN=D:\.store\tools\llama.cpp\build\bin\llama-server.exe

# Path to your model file (first shard if split)
QUANTMAP_MODEL_PATH=D:\.store\models\your-model\model-00001-of-00003.gguf

# Where QuantMap stores databases and results
QUANTMAP_LAB_ROOT=D:\Workspaces\QuantMap
```

### 4. Start HWiNFO64
Open HWiNFO64 in sensors-only mode with Shared Memory Support enabled.

### 5. Validate your setup
```bash
python -m src.runner --validate --campaign C01_threads_batch
```

This runs 13 checks across server binary, model file, request files, baseline config, and system environment. Fix anything that shows `FAIL` before proceeding.

### 6. Dry run (optional but recommended)
```bash
python -m src.runner --dry-run --campaign C01_threads_batch
```

Shows exactly what will run: config count, cycles per config, total requests, elimination thresholds, and per-config server args. Nothing is executed.

### 7. Run your first campaign
```bash
python -m src.runner --campaign C01_threads_batch
```

Results land in `results/C01_threads_batch/report.md`.

---

## CLI Reference

```
python -m src.runner [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--campaign ID` | Campaign to run (matches YAML filename in `campaigns/`) |
| `--validate` | Pre-flight check — verifies setup without running anything |
| `--dry-run` | Shows what would run without executing |
| `--resume` | Resume an interrupted campaign (skips completed configs) |
| `--no-resume` | Start fresh, ignoring crash recovery state |
| `--cycles N` | Override cycles_per_config for this run |
| `--requests-per-cycle N` | Override requests_per_cycle for this run |
| `--list` | Show all campaigns with status, top config, and report path |

### Rescoring
```bash
# Re-score a specific campaign with updated thresholds
python rescore.py CAMPAIGN_ID

# Re-score all completed campaigns
python rescore.py --all
```

### Campaign generation
```bash
# Generate C08 interaction campaign from C01-C07 top configurations
python -m src.score --generate-c08

# Generate Finalist validation campaign from C08 top configuration
python -m src.score --generate-finalist
```

---

## How It Works

QuantMap uses a **Measurement-Driven Development (MDD)** pipeline:

```
Campaign YAML           →  defines what to sweep
    ↓
Config Generation       →  all parameter combinations
    ↓
Sequential Execution    →  one config at a time, with cooldown between configs
    ↓
Per-Request Collection  →  every request logged with telemetry snapshot
    ↓
Statistical Analysis    →  median, p10, p90, CV, outlier detection per config
    ↓
Elimination Filtering   →  remove configs that fail stability thresholds
    ↓
Composite Scoring       →  rank survivors by throughput + latency + stability
    ↓
Report Generation       →  markdown report with highest observed config, Pareto frontier, and full data
```

### Elimination Filters (defaults, overridable per campaign)

| Filter | Default | What it catches |
|--------|---------|----------------|
| `min_success_rate` | 0.90 | Configs where >10% of requests failed |
| `max_outliers` | 3 | Configs with too many anomalous measurements |
| `max_cv` | 0.05 | Configs with >5% throughput variance (unstable) |
| `max_thermal_events` | 0 | Configs that triggered thermal throttling |

Override in your campaign YAML:
```yaml
elimination_overrides:
  min_success_rate: 0.95
  max_cv: 0.03
```

### What Gets Measured

**Per request:** token generation speed (t/s), time to first token (ms), prompt processing speed (t/s), success/failure outcome, full SSE stream parsed and validated.

**Per telemetry sample (continuous background):** GPU temperature, GPU utilization %, GPU VRAM usage, CPU temperature, CPU utilization %, CPU power draw, system RAM committed, server process private bytes, background interference flags (Defender, Windows Update, AV scans, Search Indexer, high-CPU process count).

---

## Campaign YAML Structure

Campaigns live in `configs/campaigns/` and sweep one variable from the baseline:

```yaml
campaign_id: "C01_threads_batch"
description: "Sweep --threads-batch across 4, 8, 12, 16, 20"
variable: "threads_batch"
values: [4, 8, 12, 16, 20]
type: "primary_sweep"

# Optional: override cycles for this campaign
# cycles_per_config: 5

# Optional: override elimination thresholds
elimination_overrides: {}
```

### Baseline

`configs/baseline.yaml` defines your model, hardware profile, default server args, and request definitions. This is your "known good" configuration — campaigns sweep one variable at a time against this baseline.

Cycles and requests are configurable at three levels (highest priority wins):
1. CLI flags: `--cycles N`, `--requests-per-cycle N`
2. Campaign YAML: `cycles_per_config`, `requests_per_cycle` keys
3. `baseline.yaml` lab section (global default: 3 cycles, 6 requests)

---

## Report Output

Each campaign generates `results/{campaign_id}/report.md` containing:

- **Highest Scoring Configuration** — top performing configuration based on observed metrics
- **Full config ranking** — all configs with their pass/fail status and measured metrics
- **Pareto frontier** — configs that aren't strictly outclassed on any measured metric (includes outlier count and thermal events for stability context)
- **Telemetry summary** — GPU util, CPU util, RAM, VRAM, CPU power, background interference per config
- **Background interference detail** — Defender/AV/Update/Indexer activity per config with snapshot counts
- **Speed degradation analysis** — flags configs where throughput dropped significantly from baseline
- **Production command** — copy-paste server launch command with full environment setup (including `CUDA_VISIBLE_DEVICES` and `CUDA_DEVICE_ORDER` if set)
- **Confidence statement** — model, quant, build commit, measurement methodology summary

Additionally:
- `results/{campaign_id}/campaign_yaml_snapshot.yaml` — exact YAML that was used
- Campaign data stored in SQLite with schema migrations for forward compatibility

---

## Project Structure

```
QuantMap/
├── src/
│   ├── config.py          # Shared infrastructure constants (LAB_ROOT, ports, paths)
│   ├── runner.py           # Campaign orchestration, CLI entry point
│   ├── server.py           # llama-server lifecycle management
│   ├── measure.py          # SSE stream measurement, request execution
│   ├── telemetry.py        # HWiNFO shared memory + system telemetry
│   ├── analyze.py          # Statistical analysis (median, CV, outliers)
│   ├── score.py            # Elimination filtering + composite scoring
│   ├── report.py           # Markdown report generation
│   └── db.py               # SQLite schema, migrations, data access
├── configs/
│   ├── baseline.yaml       # Default server configuration
│   └── campaigns/          # Campaign YAML definitions (C01-C15, Finalist, NGL_sweep)
├── requests/               # Request payload files (prompts for benchmarking)
├── results/                # Campaign outputs (reports, YAML snapshots) [gitignored]
├── rescore.py              # Re-score campaigns without re-collecting data
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
└── README.md
```

---

## Tips for Best Results

**Before your first campaign:**
- Add your llama.cpp build directory and model path to Windows Defender exclusions. QuantMap's `--validate` will warn you if they're not excluded.
- Disable Windows Search Indexer on the drive where your models live (`services.msc` → Windows Search → Disabled`).
- Close browsers, game launchers, and anything that creates background CPU/GPU load.
- Make sure HWiNFO64 is running with Shared Memory enabled.

**Interpreting results:**
- **CV (coefficient of variation)** is your stability indicator. Below 1% is excellent. Below 5% is acceptable. Above 5% means something is introducing variance — thermal throttling, background interference, or an unstable parameter combination.
- **Outlier count** tells you how many individual measurements deviated significantly. A config with high throughput but 3+ outliers is statistically weaker than a slightly slower config with zero outliers.
- **The Pareto frontier** shows configs that aren't strictly outclassed by any other on all metrics simultaneously. If the top-scoring config and the Pareto leader differ, it indicates a tradeoff between throughput and stability — and the table now shows outlier count and thermal events so you can see the tradeoff.
- **The production command** in the report represents the strongest observed configuration under tested conditions. Copy it, paste it, run it. It includes the full environment setup.

**Campaign design:**
- Sweep one variable at a time. QuantMap's elimination pipeline assumes single-variable campaigns where the baseline anchors everything else.
- Start with thread counts (`--threads`, `--threads-batch`, `--threads-http`) — they're fast to sweep and have an observable impact on most setups.
- Use `--dry-run` to verify the measurement budget before committing to a long campaign. A 10-config × 3-cycle campaign at 6 requests per cycle is 180 total requests. Use `--cycles 5` for higher statistical confidence when needed.

---

## Roadmap

### v1.0 (current)
- Single-variable parameter sweep campaigns
- Thread count, batch size measurement
- Full telemetry with background interference tracking
- Statistical evaluation and composite scoring
- Campaign-configurable thresholds
- Pre-flight validation and dry-run
- Resume support for interrupted campaigns

### v1.x (planned)
- **Context length degradation** — throughput curves across escalating context depths
- **KV cache quantization + flash attention sweep** — combinatorial parameter exploration
- **Stress/soak test** — sustained load over time to validate thermal stability
- **Preset campaign library** — predefined campaign templates for common parameter sweeps
- **Actionable reporting** — synthesized observation summary with explanatory notes
- **Cross-platform support** — Linux and macOS

### v2.0 (future)
- Hardware discovery and profiling (VRAM ceiling, RAM bandwidth, PCIe throughput, thermal sustain limits)
- Community comparison database (opt-in, anonymized, `share_results: false` by default)
- Multi-model comparison workflows

---

## FAQ

**Q: Do I need HWiNFO64?**
A: Yes, for GPU/CPU telemetry. Without it, QuantMap can still run campaigns and measure throughput, but telemetry columns (temperature, power draw, utilization) will be null and thermal event detection won't work.

**Q: Can I run this on Linux?**
A: Not yet. The codebase is structured for cross-platform support (platform-specific functions are isolated behind `sys.platform` branches), but the current release is Windows-only. Linux support is a priority for an upcoming release.

**Q: How long does a campaign take?**
A: Depends on the model, config count, and cycle count. A typical 5-config × 3-cycle campaign takes 10–30 minutes including cooldowns. Use `--dry-run` to see the exact measurement budget before committing.

**Q: Can I re-score results without re-running the campaign?**
A: Yes — that's what `rescore.py` is for. Raw measurement data is immutable. You can adjust performance thresholds and re-score in seconds.

**Q: What inference backends are supported?**
A: Currently llama.cpp (`llama-server`) only. The architecture is designed for backend-agnostic expansion (vLLM, Ollama, exllamav2) in a future release.

**Q: My campaign shows 0 passing configs. What happened?**
A: Usually means the elimination thresholds are too strict for your data, or the tested conditions are heavily unstable. Run `rescore.py` with relaxed `elimination_overrides` in your campaign YAML, or check the report for which filter eliminated each config. Common causes: a single transient failure pushing success rate below threshold, or borderline CV from background interference.

---

## Contributing

QuantMap is in active development. If you want to contribute, open an issue first to discuss the change — the architecture has specific design constraints (single-source-of-truth constants, backend-agnostic interfaces, measurement-driven methodology) that should be understood before submitting PRs.

---

## License

This project is licensed under the [Business Source License 1.1](LICENSE).

You are free to use QuantMap for personal, non-commercial purposes. Commercial use requires written permission from the author. See the [LICENSE](LICENSE) file for full terms.

---

**Built by [Mad-Labs42](https://github.com/Mad-Labs42)** — because guessing is not engineering.
