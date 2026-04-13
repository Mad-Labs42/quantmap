# Comparative Analysis Playbook

Comparative Analysis is the core of the QuantMap evidence model. This playbook provides the reasoning required to interpret shifts, pivots, and environment drift with precision.

## 1. Safety First: The Compatibility Audit

When you run `quantmap compare A B`, the first action is a **Methodology Audit**. This ensures your comparison is grounded in compatible rules.

| Grade | Meaning | Practical Impact |
|---|---|---|
| **Compatible** | Identical scoring rules, weights, and gates. | **Evidence-bound comparison.** Deltas reflect real changes. |
| **Warnings** | Minor changes (e.g. gates tightened or weights shifted <5%). | **Exercise Caution.** The relative rank is likely accurate, but the `composite_score` delta is skewed. |
| **Mismatch** | Major changes (Different Profile or Metric Registry). | **Blocked.** Comparisons are mathematically invalid without the `--force` flag. |

---

## 2. Worked Example: A vs. B

*Scenario: You have a "Stable Baseline" (Campaign A) and you run a "Threads Optimization" (Campaign B) on the same model.*

### The Data
- **Campaign A**: Threads=16, Config_ID=`C01_T16`, TG=`12.4`
- **Campaign B**: Threads=24, Config_ID=`C01_T24`, TG=`14.1`

### The Audit Result
- **Methodology Grade**: `Compatible` (Both used Governance v1.1).
- **Winner Pivot**: Config `C01_T24` (+1.7 t/s) now beats the original anchor.
- **Shared-Config Median Shift**: `-0.2%` (The environment is stable).

### The Interpretation
1. **Confidence check**: The lead is ~13%, exceeding the 3% noise band.
2. **Environment check**: The shared-config shift is near zero, meaning the gain in B isn't just background "luck."
3. **Formal Outcome**: The hardware benefits from higher thread counts in this specific context.

---

## 3. Interpreting the "Noise Band"

Measurement jitter is a reality of local inference. 

- **Inside the Noise Band (< 3% delta)**: If Config B is 1% faster than Config A, but both have intrinsic jitter (CV) of 2%, this is a **Statistical Tie**. No "Winner" should be declared for hardware procurement purposes.
- **Evidence-Bound Win (> 10% delta)**: If the lead clearly exceeds the combined variance of both configurations, the shift is operationally significant.

---

## 4. Understanding the "Winner Pivot"

A Winner Pivot occurs when Config X wins in Campaign A, but Config Y wins in Campaign B. 

### Diagnostic Logic:
1.  **Check Environment Deltas**: Did Run B have more thermal events?
    - *If Yes*: Config X likely won in A but was disqualified in B for safety. Config Y is the new **Safe Winner**.
2.  **Check Lead Size**: Is the pivot > 5%?
    - *If No*: It's a "Jitter Pivot." Both configs are nearly identical; chose the one with the lowest variance.
3.  **Check Reach (Eliminations)**: Did Run B have more rejections?
    - *If Yes*: The environment in B was harsher. Config Y's win represents **Superior Robustness**.

---

## 5. Common Pitfalls

- **Comparing across Backends**: A `llama.cpp` run is not directly comparable to a `vLLM` run without manual methodology normalization.
- **Ignoring Reach Shifts**: If Campaign A had 10 passing configs and Campaign B has only 2, B is **operationally fragile**, even if the "winner" throughput is higher.

> [!CAUTION]
> **When NOT to use `compare`**: Do not use `compare` to justify a purchase if the Methodology Grade is **Mismatch**. The composite scores are calculated on different scales and cannot be subtracted or compared with any degree of certainty.
