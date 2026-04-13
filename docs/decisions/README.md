# Decision History

This directory contains the forensic record of the **Why** behind QuantMap. While the `CHANGELOG` records *what* was built, these documents record the technical and scientific rationales for the core governance and methodology choices.

## Current Phase Note

As of 2026-04-12, Phase 1 Trust Bundle and Phase 1.1 Trust Bundle Stabilization are considered stable by the real-workflow validation record. Phase 2 Operational Robustness and Phase 2.1 Settings/Environment Bridge are closed by validation. Phase 3 Platform Generalization is now active, beginning with boundary-aware telemetry/provider design. This index is updated as a living navigation aid; the linked decision and validation records are not rewritten retroactively.

## 1. Governance Lifecycle

1.  **Immutability**: Once a decision is codified into a "Methodology Version," it is never silently changed.
2.  **Audit Basis**: These records provide the evidentiary basis for auditors to verify the fairness and rigor of the analytical pipeline.
3.  **Handoff Quality**: New maintainers should read these records to understand the architectural constraints before proposing changes.

## 2. Reading the Records

Records are prefixed by date: `YYYY-MM-DD-title.md`.

- **Context**: The problem we were trying to solve.
- **Methodology**: The specific scoring math or gate logic chosen.
- **Rationale**: Why this approach was prioritized over alternatives.
- **Impact**: How it affected historical benchmark reproducibility.

---

| Record | Topic | Methodology Version |
|---|---|---|
| [2026-04-10-scoring-and-elimination](2026-04-10-scoring-and-elimination.md) | Normalization & Gates | v1.0 |
| [2026-04-10-readiness-and-diagnostics](2026-04-10-readiness-and-diagnostics.md) | Environment Trust Layer | v1.1 |
| [2026-04-11-root-cause-attribution-mvp-amendment](<../Design Memo's/Root-Cause-Attribution/2026-04-11-root-cause-attribution-mvp-amendment.md>) | Root-Cause Attribution MVP Scope Amendment | Attribution MVP |

## 3. Trust Bundle Records

| Record | Role |
|---|---|
| [Phase 1 Trust Bundle Existing-State Inventory](Phase-1-Trust-Bundle-Existing-State-Inventory.md) | Pre-plan inventory of trust-bundle foundations and dead ends. |
| [Phase 1 Trust Bundle Existing-State Inventory - Codex](Phase-1-Trust-Bundle-Existing-State-Inventory-Codex.md) | Parallel inventory preserved as an alternate review artifact. |
| [Phase 1 Trust Bundle Pre-Implementation Contract](Phase-1-Trust-Bundle-Pre-Implementation-Contract.md) | Source-of-truth and migration contract used before implementation. |
| [Phase 1 Trust Bundle Implementation Plan](Phase-1-Trust-Bundle-Implementation-Plan.md) | Approved Phase 1 implementation plan. |
| [Phase 1 Trust Bundle Post-Implementation Validation Memo](Phase-1-Trust-Bundle-Post-Implementation-Validation-Memo.md) | Historical validation memo showing the first pass was not yet stable. |
| [Phase 1.1 Trust Bundle Stabilization Interrogation](Phase-1.1-Trust-Bundle-Stabilization-Interrogation.md) | Stabilization question-and-resolution record. |
| [Phase 1.1 Trust Bundle Stabilization Pre-Implementation Plan](Phase-1.1-Trust-Bundle-Stabilization-Pre-Implementation-Plan.md) | Approved stabilization implementation plan. |
| [Phase 1.1 Real-Workflow Validation Memo](Phase-1.1-Real-Workflow-Validation-Memo.md) | Validation record marking the trust bundle stable and identifying Phase 2 operational brittleness. |

## 4. Phase 2 Operational Robustness Records

| Record | Role |
|---|---|
| [Phase 2 Operational Robustness Interrogation](Phase-2-Operational-Robustness-Interrogation.md) | Pre-implementation design interrogation for the operational shell-hardening pass. |
| [Phase 2 Operational Robustness Pre-Implementation Plan](Phase-2-Operational-Robustness-Pre-Implementation-Plan.md) | Approved implementation plan for narrow lazy methodology loading, command-local imports, diagnostics, and reader containment. |
| [Phase 2 Closure Readiness Assessment](Phase-2-Closure-Readiness-Assessment.md) | Evidence-based closure gate review; concludes Phase 2 is nearly ready but still closure-pending. |
| [Current Phase Status and Roadmap Alignment](Current-Phase-Status-and-Roadmap-Alignment.md) | Living roadmap note recording Phase 2/2.1 closure and the Phase 3 activation boundary. |
| [Phase 2 Final Closure Pass](Phase-2-Final-Closure-Pass.md) | Final closure check; confirms Phase 2 needs one tiny dry-run/readiness patch before closure. |
| [Phase 2 Operational Robustness Closure Validation Memo](Phase-2-Operational-Robustness-Closure-Validation-Memo.md) | Final validation record closing Phase 2 and handing off to Phase 2.1. |
| [Phase 2.1 Bridge Recommendation](Phase-2.1-Bridge-Recommendation.md) | Recommended narrow settings/environment bridge before Phase 3 provider work. |
| [Phase 2.1 Settings/Environment Bridge Interrogation](Phase-2.1-Settings-Environment-Bridge-Interrogation.md) | Focused pre-implementation interrogation for the settings/environment bridge. |
| [Phase 2.1 Settings/Environment Bridge Pre-Implementation Plan](Phase-2.1-Settings-Environment-Bridge-Pre-Implementation-Plan.md) | Approved implementation plan for the narrow settings/environment bridge. |
| [Phase 2.1 Settings/Environment Bridge Implementation Validation Memo](Phase-2.1-Settings-Environment-Bridge-Implementation-Validation-Memo.md) | Validation record closing Phase 2.1 and unblocking Phase 3 activation. |

## 5. Phase 3 Platform Generalization Records

| Record | Role |
|---|---|
| [Current Phase Status and Roadmap Alignment](Current-Phase-Status-and-Roadmap-Alignment.md) | Living roadmap note marking Phase 3 active and carrying boundary-enforcement policy forward. |
