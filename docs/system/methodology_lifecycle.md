# Methodology Lifecycle

QuantMap treats benchmarking logic as a governed system. This document explains how we manage the evolution of the "Analytical Scale" without destroying historical reproducibility.

## Current State

As of 2026-04-12, historical methodology authority comes from persisted `methodology_snapshots`. Snapshot-complete historical reports, compare/explain readers, exports, and snapshot-locked rescore paths must not silently consult current profile or registry files.

Legacy rows with only partial methodology evidence remain weaker evidence. Snapshot-locked rescore refuses `legacy_partial` methodology; explicit current-input rescoring is allowed only when it is clearly labeled as current-input behavior.

## 1. Version Separation

To ensure that the "Report" doesn't change just because of a "UI fix," QuantMap versions the software and the methodology independently.

- **Software Version (SemVer)**: Updates to CLI, reporting layouts, or performance of the tool.
  - *Example: 0.9.0 -> 0.9.1.*
- **Methodology Version (Governance)**: Updates to scoring weights, outlier definitions, or elimination gates.
  - *Example: Governance v1.0 -> v1.1.*

## 2. When Methodology Shifts

A methodology shift occurs when we learn something new about the science of LLM benchmarking (e.g. realizing that *Prompt Processing* weight was too high).

1.  **Immutability**: Historical reports are not automatically changed.
2.  **Detection**: `quantmap status` or `about` will show a **Mismatch** if you use a new tool build with an old campaign.
3.  **Migration**: You can rescore with historical snapshots when complete evidence exists. Current-input rescoring is an explicit mode and must be labeled so it cannot masquerade as historical truth.

## 3. Preservation of Anchors

When comparing campaigns across months, the "Anchor" config must be preserved.

- **Stable Basis**: Even if the methodology changes, the relative performance against an anchor remains the most important data point.
- **Anchor Lockdown**: QuantMap locks the anchor config at the moment of first creation. This prevents results from "sliding" over time as new models are tested.

## 4. Reproducibility Boundary

New snapshot-complete runs preserve the methodology evidence needed to explain historical scoring without depending on current defaults.

- **Self-Documenting**: A year from now, QuantMap should read the persisted snapshot and know why a config was chosen as champion even if current defaults have changed significantly.
- **Audit Basis**: Auditors can verify that the rules weren't "fixed" to favor a specific manufacturer or model.
- **Legacy Boundary**: Older runs without complete methodology snapshots must stay labeled as weaker evidence rather than being silently upgraded from current files.
