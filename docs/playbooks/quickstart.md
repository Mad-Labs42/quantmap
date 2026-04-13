# QuantMap Quickstart Guide: The Golden Path

This guide takes you through the full operator lifecycle. We provide "Expected Output" examples so you can verify your results at every step.

---

## 1. Installation

```powershell
pip install .
quantmap --version
```
**Expected Output (Success)**: 
`QuantMap v0.9.0 (Governance Methodology v1.1)`

> [!TIP]
> **Next Step**: Run `quantmap about` to see your provenance and software registry details.

---

## 2. Initialization

```powershell
quantmap init
```
**Expected Output (Success)**: 
`✓ Lab Root initialized at D:\MyLab`
`✓ .env updated with SERVER_BIN and MODEL_PATH`

---

## 3. Environment Pulse Check (`doctor`)

```powershell
quantmap doctor
```

| Output Example | Meaning | Action |
|---|---|---|
| `✓ ENVIRONMENT READY` | All clinical gates passed. | **Proceed** to benchmarking. |
| `⚠️  READY WITH WARNINGS` | Sub-optimal state (e.g. HWiNFO missing). | **Check** if you need thermal telemetry. |
| `✗ BLOCKED` | Critical failure (e.g. Path not found). | **Fix** the recommended item before run. |

---

## 4. Integrity Validation (`self-test`)

```powershell
quantmap self-test
```
**Expected Result**:
`  ✓ Registry Intake: Verified`
`  ✓ Persistence (DB): Verified`
`  ✓ Scoring Engine: Ready`
`✓ ENVIRONMENT READY`

---

## 5. Dry Run & Execution

Always verify your measurement budget before committing to a campaign.

```powershell
quantmap run --campaign C01 --mode quick --dry-run
```
**Expected Output**: A summary showing config counts, cycles, and total requests. Zero measurements performed.

```powershell
quantmap run --campaign C01 --mode quick
```
**Success Signature**: The console will show real-time progress for each cycle and config.

---

## 6. Technical Briefing (`explain`)

```powershell
quantmap explain C01
```

| Section | Expected Detail |
|---|---|
| **Outcome** | Winner ID or "No Valid Winner Emerged" |
| **Margin of Victory** | Lead size relative to the noise band. |
| **Confidence** | `High`, `Moderate`, or `Caution`. |

---

## 7. Comparative Audit (`compare`)

```powershell
quantmap compare Baseline_Run C01
```
**Success Signature**:
`  ✓ Audit: Compatible (Identical scoring rules)`
`  Winner Shift: +12.4% TG`
`  ✓ Forensic report written to: results/comparisons/Baseline_vs_C01.md`

---

## 8. Forensic Export (`export`)

```powershell
# Create a shareable, redacted case file
quantmap export C01 --strip-env --output Case_A.qmap
```
**Expected Output**: A manifest summary showing the bundle size, fidelity (Full/Lite), and privacy level (Redacted).

---

## Common Pitfalls
- **Mistaking `Caution` for an error**: In forensics, a "Statistical Tie" is a valid finding.
- **Ignoring HWiNFO Warnings**: Running without thermal telemetry means you cannot prove your config is heat-stable.
- **Root contamination**: Avoid running `quantmap` from your `C:\` drive; use your `D:\` Lab Root.
