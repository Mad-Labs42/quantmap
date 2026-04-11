# Rescore & Migration Playbook

QuantMap is built on the principle of **Immutable Evidence**. While the raw data of a benchmark never changes, your *interpretation* of that data can evolve. This playbook explains how to manage that evolution.

## 1. The "Scale" vs. The "Weight"

- **Raw Data (Immutable)**: Every request and telemetry sample is preserved exactly as measured.
- **Methodology (Fluid)**: The rules (weights and gates) you use to determine the winner.

**Rescoring** is the act of re-applying a methodology to raw data.
```powershell
quantmap rescore Campaign_ID
```

---

## 2. Methodology Snapshots & History

Every campaign execution captures a **Methodology Snapshot**. This is a JSON record of the EXACT Registry and Profile used at that moment.

- **Forensic Default**: When you open an old report, QuantMap uses the *snapshot* to ensure you see exactly what the operator saw six months ago.
- **Migration**: When you run `rescore`, you are explicitly choosing to **discard** the old snapshot and replace it with the new current standard.

---

## 3. The Anchor Preservation Logic

Benchmarks are relative. We compare Config B to Config A (the Anchor). 

- **By Default**: QuantMap preserves the original anchor config ID. This ensures that even if you rescore, your "0%" delta floor doesn't move.
- **`--force-new-anchors`**: This forces QuantMap to look at the **Metric Registry** and select the most accurate anchor config based on *current* definitions.
  - *WARNING*: Use this only if the original anchor was discovered to be an outlier or invalid.

---

## 4. Common Pitfalls

- **Rescoring as a "Fix"**: You cannot rescore away a poor success rate or high thermal activity. If the raw measurements are throttled, they are fundamentally invalid.
- **Mixing Snapshots in Comparison**: If Campaign A uses Methodology v1.0 and Campaign B uses v1.1, the `compare` command will report a **Mismatch**. You **must** rescore A to v1.1 before an authoritative comparison is possible.
- **Re-anchoring Jitter**: Frequent use of `--force-new-anchors` can cause your historical "performance floor" to slide, making multi-month trend analysis impossible.

> [!CAUTION]
> **When NOT to use `rescore`**: Do not rescore a campaign to v1.1 and publish it as "Comparable" to a v1.0 run without noting the change. Rescoring changes the interpretation floor, which can mask real regressions or create artificial gains.
