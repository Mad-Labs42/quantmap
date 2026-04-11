# Contributor Guide

Thank you for contributing to QuantMap. This project is a forensic tool, which means maintainability and methodology integrity are our highest priorities.

---

## 🏗️ Safety Rules for Development

- **No Methodology Mixing**: Never bundle scoring math changes (Methodology) with CLI/UX changes (Software) in the same PR. This makes it impossible to audit *why* a benchmark result shifted.
- **Rule of Parsimony**: Do not add new metrics to the **Metric Registry** unless they pass the "Forensic Value" test. 
- **Deterministic UX**: All CLI outputs must remain deterministic. Avoid free-form prose.

---

## 🩺 Support Triage: Under Pressure

When a user reports unexpected results, follow this direct sequence to gather a forensic baseline.

```powershell
# 1. Identity & Provenance
quantmap about

# 2. Lab Situation
quantmap status

# 3. Environment Readiness
quantmap doctor

# 4. Core Math Validation
quantmap self-test

# 5. Redacted Forensic Export
quantmap export <id> --strip-env --output Support_Case.qmap
```

---

## 🖇️ Stakeholder-Safe Sharing

When sharing results with stakeholders (e.g. manufacturers or researchers), use these commands for professional, high-fidelity handoff:

- **For raw text ingestion (Slack/GitHub)**:
  `quantmap explain CAMPAIGN_ID --plain`
- **For forensic peer-review**:
  `quantmap export CAMPAIGN_ID --strip-env --output Forensic_Audit.qmap`
- **To prove methodology version**:
  `quantmap audit ID1 ID2`

---

## 🛠️ Implementation Guidance

### How to add a Metric
1.  **Registry**: Add the definition to `src/governance.py`.
2.  **Acquisition**: Update `src/measure.py` to capture the raw value.
3.  **Analysis**: Update `src/analyze.py` to compute the required statistics.
4.  **Scoring**: Update `src/score.py` to include the metric in composite ranking.
5.  **Documentation**: Update `database_schema.md` and `command_reference.md`.

---

## 📜 Decision Records

Before implementing a major change to the scoring or governance logic, you **must** author a new record in `docs/decisions/`.
- **Primary Goal**: Document the impact on historical reproducibility.
- **Tone**: Technical, intentional, and source-of-truth.
