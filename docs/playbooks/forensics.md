# Forensics Playbook: Interpreting Evidence

In QuantMap, a benchmark result is a forensic artifact. This playbook provides the diagnostic reasoning required to move from "Raw Numbers" to "Evidence-Bound Findings."

---

## 1. The Margin of Victory

QuantMap only declares a winner if the evidence crosses a significance threshold.

- **High Confidence**: The lead is substantial (>10%) and stable (<3% CV). This is a **Clean Win**.
  - *Interpretation*: The variable (e.g. thread count) has a direct, observable impact on performance.
- **Caution**: The lead is within the noise band OR variance is high.
  - *Interpretation*: The lead is "Accidental." Config A is not meaningfully faster than Config B. Do not make permanent hardware decisions based on `Caution` results.

---

## 2. When to Escalate to Export (.qmap)

Not every run requires a deep audit. Create a `.qmap` bundle when you hit these **Escalation Triggers**:

1.  **Surprising Winner Pivot**: If a configuration that traditionally performs poorly suddenly wins by a large margin.
2.  **Stability Clusters**: When a middle-range config (e.g. 16 threads) consistently fails stability gates while others pass.
3.  **Methodology Mismatch**: When comparing two campaigns that report a `Mismatch` grade but require peer review to understand why.
4.  **Repeatable Thermal Failures**: When a specific hardware configuration consistently triggers thermal events before the cycle finishes.
5.  **Peer Review or Support**: When handing off findings to a manufacturer, researcher, or the QuantMap maintainers for debugging.

```powershell
# Redacted, portable case file generation
quantmap export <campaign_id> --strip-env --output Case_A_Audit.qmap
```

---

## 3. Diagnostic Decision Trees

If your campaign outcome is unexpected, use these trees to find the "Why."

### Scenario: "No Valid Winner Emerged" (Zero-Winner)
1.  **Check Elimination Reason**: Were all configs rejected for the same reason?
    - *If Thermal*: Your baseline is too aggressive for your cooling. The sweep is irrelevant if the environment throttles.
    - *If Stability (CV)*: You have background interference. Fix the environment, not the campaign.
2.  **Check Lead Size**: Did one config score 98% and others 95%?
    - *If Yes*: Methodological tie. Increase `cycles_per_config` for more statistical power.

### Scenario: The "Stability Cluster"
*Problem: Configs 4, 8, and 12 threads are stable, but 16 and 20 fail CV filters.*
- **Diagnosis**: You have hit a context-switching ceiling or thermal wall.
- **Action**: Lower ambient temp or check CPU Affinity settings to eliminate core-parking jitter.

---

## 4. Common Pitfalls

- **Ignoring Outliers**: A config with zero outliers and slightly lower throughput is forensicly superior to a "sprinter" config with high jitter.
- **The "Winner Vibes" Error**: Treating a `Caution` result as a recommendation. If the tool says `Caution`, it is explicitly warning you **not** to trust the rank.

> [!CAUTION]
> **When NOT to use `explain`**: Do not use the `explain` briefing to justify a config that has **Fatal Errors** (OOMs) recorded in the database, even if the score is high. Fatal errors indicate a fundamental lack of safe-to-use robustness.
