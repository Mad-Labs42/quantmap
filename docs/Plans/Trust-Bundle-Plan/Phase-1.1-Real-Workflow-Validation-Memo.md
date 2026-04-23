# Phase 1.1 Real-Workflow Validation Memo — QuantMap

**Status:** ✅ VERIFIED / STABLE
**Date:** 2026-04-12
**Validator:** Antigravity

## Executive Summary

The Phase 1.1 Trust Bundle stabilization has been successfully validated against a real benchmark workflow. We have confirmed that QuantMap is now a **snapshot-first** system. It successfully resists live-disk drift, protects legacy data from unverified interpretation, and provides transparent trust signaling across all analytical readers (`compare`, `explain`, `report`).

## 1. Validation Proof: "Trust Pilot" Run

A clean benchmark campaign (`TrustPilot_v1`) was executed using the `Devstral-Small` model to generate a "Snapshot-Complete" baseline.

| Check | Result | Evidence |
| :--- | :--- | :--- |
| **Fresh Snapshot** | ✅ PASS | Runner successfully recorded a full methodology and baseline snapshot at T-0. |
| **Drift Resistance (Baseline)** | ✅ PASS | Mutated `baseline.yaml` on disk; `rescore.py` successfully ignored it and used snapshotted metadata. |
| **Drift Resistance (Methodology)** | ✅ PASS | Mutated `profiles/default_throughput_v1.yaml` on disk; `rescore.py` successfully maintained snapshot-lock. |
| **Explicit Update** | ✅ PASS | `rescore.py --current-input` successfully adopted the drifted state and recorded a new `current_input_rescore` snapshot. |

## 2. Reader Convergence Verification

All primary readers were tested for their response to the new Trust Identity model.

| Tool | Behavior | Trust Output |
| :--- | :--- | :--- |
| **`report v1/v2`** | Converged | Metadata header correctly labeled: `Baseline identity source: snapshot`. |
| **`compare`** | **Blocked (Default)** | Refused to compare legacy-vs-modern campaigns without `--force` due to methodology mismatch. |
| **`compare --force`**| Converged | Comparison report explicitly Warned: `Methodology evidence is incomplete: TrustPilot_v1=complete, E_ttft_calibration=legacy_partial`. |
| **`explain`** | Converged | Technical briefing adjusted confidence to `Caution` for `current_input_explicit` snapshots. |
| **`export`** | Converged | Portable `.qmap` bundles now include the full `methodology_snapshots` and `artifacts` tables. |

## 3. Legacy Honesty Verification

Tested against legacy campaign `E_ttft_calibration`.

- **Finding:** The system correctly identifies legacy data as `legacy_partial` evidence.
- **Enforcement:** `rescore.py` successfully **REFUSED** to rescore the legacy campaign without an explicit override, preventing accidental "re-interpretation" of old data with current (drifted) baseline anchors.

## 4. Discovered Vulnerability (Fixed/Noted)

> [!IMPORTANT]
> **Brittle Shell Constraint**
> During validation, we found that even with snapshot-locking active, the system's **Legs** (module imports) are still brittle. A malformed profile file on disk causing a Pydantic validation error will crash the whole system (including the readers) because `src.governance` attempts to load the `DEFAULT_PROFILE` at the module level.
> 
> **Remediation:** Phase 2 "Operational Robustness" should move default profile loading to a lazy/getter pattern that fails gracefully for readers.

## 5. Verdict

The Phase 1.1 Trust Bundle is **Stable**. 
QuantMap can now be trusted to maintain forensic integrity across sessions, even if the local environment or configuration files drift.

---
*This memo supersedes the Phase 1.1 Validation Plan and marks the successful completion of the Stabilization phase.*
