# Decision History

This directory contains the forensic record of the **Why** behind QuantMap. While the `CHANGELOG` records *what* was built, these documents record the technical and scientific rationales for the core governance and methodology choices.

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
