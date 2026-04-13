# QuantMap

![Status](https://img.shields.io/badge/status-MVP%20%2F%20Active%20Development-orange)

**Stop guessing your inference settings. Measure them.**

QuantMap is a measurement and reporting system for local LLM inference benchmarking. It runs structured campaigns that sweep server parameters (thread counts, batch sizes, GPU layer offloading) and collects structured telemetry for evidence-bound analysis and reporting.

---

## Current Development Phase

The Phase 1 Trust Bundle and Phase 1.1 stabilization pass are stable after real-workflow validation. QuantMap now treats snapshot-first historical identity, methodology evidence, layered runtime/report state, and non-misleading export/report trust behavior as the foundation for future work.

The active focus is **Phase 3: Platform Generalization**. Phase 2 Operational Robustness and Phase 2.1 Settings/Environment Bridge are closed after validation. Phase 3 begins with boundary-aware telemetry/provider design, not scattered provider conditionals in existing high-blast-radius modules.

---

## 🔬 The QuantMap Philosophy

QuantMap is built on the principle that **benchmarking is a forensic science**. 

### What QuantMap Is
- **A Monitored Environment**: A system that observes and logs background interference to ensure data transparency.
- **An Evidence-Bound Narrator**: A briefing engine that only speaks when statistical margins are significant.
- **A Durable Forensic Record**: A persistent, traceable history of every request, response, and thermal event.

### What QuantMap Is NOT
- **A Magic Optimizer**: It will not "fix" a bad configuration; it will provide evidence that it is sub-optimal.
- **An Inference Engine**: It calls `llama-server`. It does not perform the calculations itself.
- **A vibes-based ranker**: If Config A is 1% faster but 5x more unstable, it will not win.

### Boundaries: What QuantMap Will NOT Tell You
- **It cannot make invalid comparisons valid**: If you compare two campaigns using different methodologies, the result is technically a mismatch.
- **It cannot repair bad raw data**: No amount of `rescore` will fix a run that was corrupted by thermal throttling or background indexing.
- **It cannot infer missing telemetry**: If HWiNFO is not running, thermal events are recorded as "Unknown."

---

## 🏗️ Methodology vs. Software

We separate the tool from the rules.

| Feature | Software Updates | Methodology Updates |
|---|---|---|
| **Focus** | CLI ergonomics, diagnostics, reports. | Scoring weights, gates, thresholds. |
| **Impact** | Changes *how* you see the data. | Changes *what* the data concludes. |
| **Historical Data** | Raw measurements are never altered. | Rescoring creates a new interpretation floor. |

> [!NOTE]
> **What Changed vs. What Did Not**:
> - Software changes may affect the UI, packaging, or diagnostic speed. Historical outcomes remain untouched.
> - Methodology changes (Registry/Profile) affect winner selection and comparison validity. 
> - **Rescoring** a campaign under persisted historical methodology is snapshot-locked. Current-input rescoring is an explicit migration-like mode and must be labeled as such.

---

## 🚀 Operational Workflow: End-to-End

A standard successful run follows this clinical sequence:

```powershell
# 1. Setup and Pulse Check
quantmap init
quantmap doctor
quantmap self-test

# 2. Execution (Dry-run first to verify budget)
quantmap run --campaign C01 --mode quick --dry-run
quantmap run --campaign C01 --mode quick

# 3. Analysis and Briefing
quantmap explain C01
```

---

## 🆘 Support Triage: Under Pressure

If results are surprising or the tool behavior is unexpected, run these five commands in sequence to gather a forensic baseline:

1. `quantmap about` — *Who am I and what are my rules?*
2. `quantmap status` — *Is my lab currently healthy?*
3. `quantmap doctor` — *Is my background currently silent?*
4. `quantmap self-test` — *Is my core math still valid?*
5. `quantmap export <id> --strip-env` — *Generate a redacted case file for peer review.*

---

## 📖 Technical Library

- [**Operator Playbooks**](docs/README.md) — How to actually think and operate with this tool.
- [**Command Reference**](docs/system/command_reference.md) — Compact lookup for all flags and mutations.
- [**Trust Surface**](docs/system/trust_surface.md) — How QuantMap proves its findings.
- [**System Architecture**](docs/system/architecture.md) — The technical design of the pipeline.

---

**Built by [Mad-Labs42](https://github.com/Mad-Labs42)** — because guessing is not engineering.
