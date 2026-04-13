# Decision: Environment Readiness & Diagnostics (v1.1)

- **Date**: 2026-04-10
- **Status**: Codified in Governance Methodology v1.1
- **Authors**: Antigravity, Josh

## 1. Context

Early versions of QuantMap relied on "Eyeballing" the console for errors. This led to "Garbage In, Garbage Out" scenarios where benchmarks were run while Windows Search was indexing or while the server binary was missing, resulting in wasted hours of measurement.

## 2. Decision: The Three-State Readiness Model

We implemented a unified `Readiness` model used across `init`, `doctor`, and `self-test`:

1.  **READY**: All clinical gates passed. Measurement environment is silent.
2.  **WARNINGS**: Non-critical issues (e.g. HWiNFO missing). The run can proceed, but with reduced fidelity (no thermal events).
3.  **BLOCKED**: Critical failures (e.g. Server binary missing, Lab Root un-writable). **Execution is hard-stopped.**

## 3. Decision: Instructional over Active Fixes

We decided that `doctor --fix` should only perform **safe, non-destructive filesystem operations** (creating folders, scaffolding configs).

OS-level security changes (Defender exclusions, Power plans) must remain **Instructional Only**.

## 4. Rationale

To earn "Absolute Trust," the tool must be an expert advisor, not a system invader. By telling the operator *exactly* what command to run to fix their machine, we preserve the operator's control while ensuring the measurement stage remains clean.

## 5. Impact

- Dramatically reduced "False Positive" benchmarks caused by background noise.
- Established a "Situational Awareness" layer via `quantmap status`.
- Integrated `self-test` to prove tool math is sane before ingestion.
