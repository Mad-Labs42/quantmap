# Decision: Scoring & Elimination Logic (v1.0)

- **Date**: 2026-04-10
- **Status**: Codified in Governance Methodology v1.0
- **Authors**: Antigravity, Josh

## 1. Context

The original "Baseline" scoring mixed raw Token/Second values with Prompt Processing metrics. Because Prompt Processing values are orders of magnitude larger (~100 vs ~10), they dominated the score regardless of the intended weight.

Additionally, non-deterministic elimination (e.g. dropping configs without explicit reasons) was causing research instability.

## 2. Decision: Absolute-Reference Normalization

We moved to a **Min-Max Normalization** model applied to the passing candidate set.

- **Formula**: `score = (val - min) / (max - min)`
- **Benefit**: Every metric is correctly weighted according to the **Experiment Profile**. A 5% weight on Prompt Processing now actually represents 5% of the composite score.
- **Latency Inversion**: Metrics like TTFT are inverted so that lower latency correctly produces a higher score.

## 3. Decision: Deterministic Elimination Gates

We established four "Clinical Gates" that every config must pass:
1.  **Success Rate (>90%)**: Ensures basic server reliability.
2.  **Stability (CV < 5%)**: Eliminates configs with high measurement jitter.
3.  **Thermal Throttling (0 events)**: Any frequency capping during a run invalidates the config.
4.  **Outlier Count (< 3 per run)**: Prevents bursty performance from skewing the median.

## 4. Rationale

This approach prioritizes **Statistical Honesty** over "Marketing Scores." By rejecting noisy or throttled data, we ensure that the final "Winner" is a configuration that is both fast AND reliable enough for production deployment.

## 5. Impact

- Successfully separated the "Acquisition" of data from the "Interpretation" of results.
- Enabled the `rescore` utility, allowing researchers to adjust weights without repeating measurements.
