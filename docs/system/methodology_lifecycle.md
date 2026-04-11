# Methodology Lifecycle

QuantMap treats benchmarking logic as a governed system. This document explains how we manage the evolution of the "Analytical Scale" without destroying historical reproducibility.

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
3.  **Migration**: You can move a campaign to the new methodology by running `quantmap rescore`. This creates a new snapshot and updates the "Trust Surface."

## 3. Preservation of Anchors

When comparing campaigns across months, the "Anchor" config must be preserved.

- **Stable Basis**: Even if the methodology changes, the relative performance against an anchor remains the most important data point.
- **Anchor Lockdown**: QuantMap locks the anchor config at the moment of first creation. This prevents results from "sliding" over time as new models are tested.

## 4. Reproducibility Guarantee

Every `.qmap` export contains a full **Methodology Snapshot**. 

- **Self-Documenting**: A year from now, any version of QuantMap can read that snapshot and know exactly why a config was chosen as champion—even if the current "defaults" have changed significantly.
- **Audit Basis**: Auditors can verify that the rules weren't "fixed" to favor a specific manufacturer or model.
