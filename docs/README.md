# QuantMap Documentation

Welcome to the QuantMap technical library. This documentation is organized by **goal** and **audience** to ensure you can find the right evidence and guidance quickly.

---

## Current Project State

As of 2026-04-12, the Phase 1 Trust Bundle and Phase 1.1 Trust Bundle Stabilization are treated as stable after real-workflow validation. **Phase 2: Operational Robustness** and **Phase 2.1: Settings/Environment Bridge** are closed after validation.

Historical audits, response memos, and validation memos remain preserved as records of what was known at the time. Current actionable status lives in K.I.T. and TO-DO. **Phase 3: Platform Generalization** is now active, beginning with boundary-aware telemetry/provider design.

---

## 🏎️ First 15 Minutes

*Goal: Get setup and build technical confidence.*
1.  [**Quickstart: Step 1-4**](playbooks/quickstart.md) — Install, Init, Doctor, Self-Test.
2.  [**Command Reference**](system/command_reference.md) — Glance at the toolset.
3.  [**Trust Surface**](system/trust_surface.md) — Understand the proof model.

---

## 🎯 Route by Task

### How do I benchmark safely?
*   [**Environment Hardening**](playbooks/environment.md) — Eliminate Windows noise.
*   [**Tuning Guide**](playbooks/tuning.md) — Customizing campaigns and profiles.
*   [**Quickstart: Step 5-6**](playbooks/quickstart.md) — Dry running and execution.

### How do I interpret results?
*   [**Forensics Manual**](playbooks/forensics.md) — Interpreting winners and the "Margin of Victory."
*   [**Command: explain**](system/command_reference.md#explain) — Generating the technical briefing.

### How do I compare or audit drift?
*   [**Comparative Analysis**](playbooks/compare.md) — Methodology grades and shared-config deltas.
*   [**Command: compare**](system/command_reference.md#compare) — Running the forensic audit.

### How do I manage / migrate?
*   [**Rescore & Migration**](playbooks/rescore_and_migration.md) — Preserving history while updating rules.
*   [**Methodology Lifecycle**](system/methodology_lifecycle.md) — Understanding version shifts.

### I need to audit or extend the tool
*   [**System Architecture**](system/architecture.md) — Pipeline design.
*   [**Database Schema**](system/database_schema.md) — Field-level reference.
*   [**Contributing Guide**](system/contributing.md) — Safety rules and support flow.
*   [**Decision History**](decisions/README.md) — Historical logic records.

---

## 🛠️ Global Readiness Model

QuantMap uses a unified vocabulary across all documentation and CLI outputs:

| Model | Success State | Warning State | Blocked State |
|---|---|---|---|
| **Readiness** | `READY` | `WARNINGS` | `BLOCKED` |
| **Comparison** | `Compatible` | `Warnings` | `Mismatch` |
| **Confidence** | `High` | `Moderate` | `Caution` |

---

**Built by [Mad-Labs42](https://github.com/Mad-Labs42)** — because guessing is not engineering.
