# QuantMap

**Stop guessing your inference settings. Measure them.**

QuantMap is a measurement-driven optimization lab for local LLM inference. It runs structured campaigns that sweep server parameters (thread counts, batch sizes, GPU layer splits), collects statistically rigorous telemetry, and tells you exactly which configuration is best for your hardware — with proof.

No vibes. No "try 30 layers and see what happens." No copying someone else's settings from Reddit and hoping your rig behaves the same. QuantMap gives you a statistically validated answer for *your* machine, *your* model, *your* workload.

---

## Why This Exists

Every local LLM user hits the same wall: you download a model, start a server with default settings, and wonder if you're leaving performance on the table. You probably are. But finding the optimal config means manually testing dozens of parameter combinations, eyeballing throughput numbers, and hoping you controlled for thermal throttling, background processes, and cold-start effects.

QuantMap automates that entire process. Define what you want to sweep, run a campaign, get a winner.

---

## What It Does

- **Structured campaigns** — Define parameter sweeps in YAML. QuantMap generates all configs, runs them sequentially with controlled cooldowns, and collects measurements under consistent conditions.
- **Statistical elimination** — Configs are filtered by success rate, outlier count, coefficient of variation, and thermal events. Survivors are ranked by a composite score (throughput, latency, stability). No config passes on vibes alone.
- **Full telemetry** — GPU temp, GPU utilization, CPU utilization, VRAM usage, RAM committed, CPU power draw, background interference (Defender, Windows Update, Search Indexer, AV scans), all sampled continuously and stored per-request.
- **Reproducible results** — Every campaign stores the exact server launch command, runtime environment variables (including ambient `CUDA_VISIBLE_DEVICES`), campaign YAML snapshot (with SHA-256), and schema-versioned SQLite database. You can reproduce any run or share results with full context.
- **Separation of collection and analysis** — Raw data is immutable. Scoring thresholds can be adjusted and results re-scored in seconds without re-running hours of measurements. The `rescore.py` utility exists for exactly this.
- **Campaign-configurable thresholds** — Override elimination filters (`min_success_rate`, `max_outliers`, `max_cv`, `max_thermal_events`) per campaign in YAML. Different workloads have different stability requirements.
- **Pre-flight validation** — `--validate` checks your entire setup before a campaign runs: server binary existence and size, model file integrity, request file presence, baseline configuration, and Defender exclusion status.
- **Resume support** — Campaigns that crash or get interrupted (Ctrl+C) preserve all completed data. `--resume` picks up from the next incomplete config.

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
| `--list` | Show all campaigns with status, winner, and report path |

### Rescoring
```bash
# Re-score a specific campaign with updated thresholds
python rescore.py CAMPAIGN_ID

# Re-score all completed campaigns
python rescore.py --all
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
Report Generation       →  markdown report with winner, Pareto frontier, and full data
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

Campaigns live in `campaigns/` and reference a baseline configuration:

```yaml
name: C01_threads_batch
description: Sweep --threads-batch to find optimal batch threading
baseline: baseline.yaml

variable: threads_batch
values: [4, 8, 12, 16, 20]

cycles: 5
warmup_strategy:
  mode: single_cycle

elimination_overrides: {}  # use defaults
```

### Baseline

`baseline.yaml` defines your model, server binary, default server args, and request definitions. This is your "known good" configuration — campaigns sweep one variable at a time against this baseline.

---

## Report Output

Each campaign generates `results/{campaign_id}/report.md` containing:

- **Winner** — best config with composite score breakdown
- **Full config ranking** — all configs with pass/fail status and metrics
- **Pareto frontier** — configs that aren't dominated on any metric (includes outlier count and thermal events for stability context)
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
├── campaigns/              # Campaign YAML definitions
├── requests/               # Request payload files (prompts for benchmarking)
├── results/                # Campaign outputs (reports, YAML snapshots)
├── baseline.yaml           # Default server configuration
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
- **Outlier count** tells you how many individual measurements deviated significantly. A config with high throughput but 3+ outliers is less reliable than a slightly slower config with zero outliers.
- **The Pareto frontier** shows configs that aren't strictly worse than any other on all metrics simultaneously. If the winner and the Pareto leader differ, the Pareto leader trades throughput for stability or vice versa — and the table now shows outlier count and thermal events so you can see the tradeoff.
- **The production command** in the report is your final answer. Copy it, paste it, run it. It includes the full environment setup.

**Campaign design:**
- Sweep one variable at a time. QuantMap's elimination pipeline assumes single-variable campaigns where the baseline anchors everything else.
- Start with thread counts (`--threads`, `--threads-batch`, `--threads-http`) — they're fast to sweep and have the biggest impact on most setups.
- Use `--dry-run` to verify the measurement budget before committing to a long campaign. A 10-config × 5-cycle campaign at 6 requests per cycle is 300 total requests.

---

## Roadmap

### v1.0 (current)
- Single-variable parameter sweep campaigns
- Thread count, batch size optimization
- Full telemetry with background interference tracking
- Statistical elimination and composite scoring
- Campaign-configurable thresholds
- Pre-flight validation and dry-run
- Resume support for interrupted campaigns

### v1.x (planned)
- **`n_gpu_layers` sweep** — find optimal GPU/CPU layer split for partial offload
- **Context length degradation** — throughput curves across escalating context depths
- **KV cache quantization + flash attention sweep** — combinatorial parameter exploration
- **Stress/soak test** — sustained load over time to validate thermal stability
- **Preset campaign library** — predefined campaign templates for common optimization scenarios
- **Actionable recommendations** — synthesized, copy-pasteable optimal server configuration with explanatory notes
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
A: Depends on the model, config count, and cycle count. A typical 5-config × 5-cycle campaign takes 15–45 minutes including cooldowns. Use `--dry-run` to see the exact measurement budget before committing.

**Q: Can I re-score results without re-running the campaign?**
A: Yes — that's what `rescore.py` is for. Raw measurement data is immutable. You can adjust elimination thresholds and re-score in seconds.

**Q: What inference backends are supported?**
A: Currently llama.cpp (`llama-server`) only. The architecture is designed for backend-agnostic expansion (vLLM, Ollama, exllamav2) in a future release.

**Q: My campaign shows 0 passing configs. What happened?**
A: Usually means the elimination thresholds are too strict for your data. Run `rescore.py` with relaxed `elimination_overrides` in your campaign YAML, or check the report for which filter eliminated each config. Common causes: a single transient failure pushing success rate below threshold, or borderline CV from background interference.

---

## Contributing

QuantMap is in active development. If you want to contribute, open an issue first to discuss the change — the architecture has specific design constraints (single-source-of-truth constants, backend-agnostic interfaces, measurement-driven methodology) that should be understood before submitting PRs.

---

## License

This project is licensed under the [Business Source License 1.1](LICENSE).

You are free to use QuantMap for personal, non-commercial purposes. Commercial use requires written permission from the author. See the [LICENSE](LICENSE) file for full terms.

---

**Built by [Mad-Labs42](https://github.com/Mad-Labs42)** — because guessing is not engineering.
