# The Trust Surface

QuantMap is built on the philosophy that **benchmarking is a forensic science**. To be trustworthy, a tool must not just produce numbers—it must prove its identity, its methodology, and the integrity of its data.

---

## Current State

As of 2026-04-12, the Phase 1/1.1 Trust Bundle is treated as stable. New runs use snapshot-first historical identity for campaign, baseline, methodology, QuantMap code identity, layered runtime/report state, and trust-relevant artifact evidence.

The active phase is **Phase 3: Platform Generalization**. Phase 2 Operational Robustness and Phase 2.1 Settings/Environment Bridge are closed after validation. Phase 3 provider work must preserve the snapshot-first trust model and use the Phase 2.1 settings/environment boundary.

---

## 1. Provenance & Identity (`about`)

The `quantmap about` command is the first pillar of the trust surface. It exposes the environment and logic currently in effect:
- **Software Version**: The version of the QuantMap code (SemVer).
- **Methodology Version**: The version of the scoring and governance logic (e.g. *Governance v1.1*).
- **Active Profile**: The weightings and gates currently in effect.

> [!IMPORTANT]
> **Separational Trust**: Because Software and Methodology are versioned separately, you can upgrade the CLI without affecting historical benchmark interpretation—or vice-versa. This prevents "Interpretation Drift" during software maintenance.

---

## 2. Integrity Verification (`self-test`)

The `quantmap self-test` command proves that the tool math is sane. It runs deterministic tests against:
- **Registry Intake**: Ensuring metric definitions are loaded correctly.
- **Persistence (DB)**: Verifying SQLite I/O.
- **Scoring Engine**: Running internal fixtures through the analytical module to verify math correctness.

---

## 3. Evidence-Bound Rationales (`explain`)

The `explain` briefing engine provides rationales, not prose. 
- **Margin of Victory**: A quantitative lead analysis comparing the winner vs. the runner-up.
- **Confidence Note**: Explicit labeling (`High/Moderate/Caution`) based on sample counts and variance (CV).

---

## 4. Methodology Snapshots and Export

Historical methodology authority now lives in persisted methodology snapshots, not in whatever profile or registry files happen to be on disk today.

- **Snapshot-first interpretation**: New snapshot-complete runs preserve the registry/profile evidence used for scoring.
- **Legacy honesty**: Older or incomplete runs are labeled with weaker evidence states such as `legacy_partial`, `hash-only`, `unknown`, or `incomplete` instead of being silently strengthened from current files.
- **Export boundary**: Export should distinguish historical run identity from exporter identity and avoid claiming full case-file fidelity when historical evidence is incomplete.

---

## 5. Boundaries: What QuantMap Will NOT Tell You

Trust is built on knowing where the evidence model stops.

- **It cannot validate an invalid environment**: If your machine is thermal-throttling, the tool will record it, but it cannot "normalize" it away. Throttled data is forensicly toxic.
- **It cannot make non-comparable runs comparable**: If the `audit` command reports a **Mismatch**, the tool explicitly warns that any compared deltas are mathematically unreliable.
- **It cannot "Find" a winner if one doesn't exist**: QuantMap is bias-neutral. It will report "No Valid Winner Emerged" if every config violates a gate.

---

## 🛡️ Summarizing Trust

| Feature | Audit Goal |
|---|---|
| **about** | Who ran this and with what rules? |
| **status** | Is the lab currently healthy? |
| **doctor** | Was the environment silent during the run? |
| **self-test** | Is the toolmath correct for this build? |
| **explain** | Why was this specific config chosen as champion? |
| **export** | Where is the forensic evidence I can review? |
