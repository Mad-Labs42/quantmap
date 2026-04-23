# ACPM v1 Decision Baseline

Purpose: establish the compact ACPM v1 decision baseline from the investigation matrix so implementation prep can start without reopening settled questions.

Primary source: `ACPM-Decision-Extraction-Matrix.md`.

## Outcome

ACPM v1 should be implemented as a conservative planner/orchestrator layer over the existing QuantMap execution, scoring, artifact, and reporting engine.

The v1 baseline is now sufficiently converged to move into prep/refactor planning. The remaining work is not another broad investigation pass; it is to implement the seams that keep execution truth, methodology truth, planner provenance, effective filter-policy truth, and recommendation claim truth separate.

## What ACPM v1 Is

ACPM v1 is:

- A planner that selects and stages existing campaign work from committed YAML semantics.
- A profile-aware methodology lens using governed scoring profiles for Balanced, T/S, and TTFT.
- A conservative partial-coverage system where planner-directed scope is explicitly labeled and not confused with legacy `custom`.
- A recommendation workflow that may emit provisional or validated recommendations only through a post-scoring recommendation record and status policy.
- A trust-preserving projection layer over existing reports, export, history, compare, and explain surfaces.

ACPM v1 is not:

- A new execution engine.
- A hidden scoring/gating override system.
- A new ACPM-specific `run_mode`.
- A report-prose authority.
- A machine-handoff generator without a recommendation-status gate.

## Locked Decisions

### Profile / Methodology Semantics

- Lock Balanced, T/S, and TTFT as methodology-primary profiles with paired planner heuristics.
- Lock shared validity floors across profiles.
- Lock profile-specific weights only for v1; no profile-specific elimination gates.
- Lock the six-key score shape: `warm_tg_median`, `warm_tg_p10`, `warm_ttft_median_ms`, `warm_ttft_p90_ms`, `cold_ttft_median_ms`, `pp_median`.
- Lock `warm_ttft_p90_ms` as present but zero-weighted in v1, with tail-latency semantics handled as gate/disclosure.
- Lock the v1 weight vectors from `ACPM-profile-weight-values-TARGET-INVESTIGATION.md`.

### Planner / Execution Contract

- Lock `RunPlan` as execution truth.
- Lock ACPM planning metadata as adjacent planner provenance, not as execution truth.
- Lock `scope_authority` as a generic execution-truth field needed for partial-scope honesty.
- Lock no ACPM-specific `run_mode` values in v1.
- Lock legacy `custom` as user-directed subset semantics, not planner-directed ACPM semantics.

### Planner Behavior

- Lock staged, rule-based narrowing from committed campaign/YAML semantics.
- Lock conservative applicability pruning before profile/budget prioritization.
- Lock no speculative value pruning by live noise, guessed optimum, or profile preference.
- Lock repeat-tier policy as planner-budget behavior, not methodology or gating behavior.
- Lock the fixed `1x` `NGL_sweep` scaffold `[10, 30, 50, 70, 90, 999]` with full NGL coverage required at `3x` and `5x`.

### Effective Filter-Policy Truth

- Lock `campaign_start_snapshot.effective_filter_policy_json` as the sole v1 persisted authority for run-effective filter policy.
- Lock `metadata.json` as projection only.
- Lock `trust_identity` as the shared read/projection seam.
- Lock methodology snapshots as base methodology truth only; do not move effective filter-policy provenance into them.
- Lock ACPM planning metadata as planner provenance only; do not let it own threshold maps.
- Lock post-scoring confirmation as a cross-check, not a second authority.

### Trust / Reporting / History / Compare

- Lock four ownership lanes across surfaces: execution truth, methodology truth, planner provenance, recommendation claim truth.
- Lock report/export/history/compare/explain as consumers of structured truth, not owners of ACPM logic.
- Lock coverage-class disclosure for scaffolded/partial NGL evidence.
- Lock compare/history preservation of coverage class, selected values, authority, and scaffold policy label/ID where applicable.
- Lock human-facing wording as derived projection, not persisted authority.

### Recommendation / Machine Handoff

- Lock a post-scoring recommendation record as the recommendation claim authority.
- Lock four statuses: `strong_provisional_leader`, `best_validated_config`, `needs_deeper_validation`, `insufficient_evidence_to_recommend`.
- Lock `leading_config_id` as distinct from `recommended_config_id`.
- Lock machine handoff as allowed only when `recommended_config_id` exists.
- Lock caveat codes as compact qualifiers governed by recommendation policy, not as a second status system.

## Deferred Decisions

These are intentionally deferred because they do not change v1 ownership truth:

- Exact CLI command spelling for ACPM entry.
- Exact file/table home for ACPM planning metadata, as long as it remains adjacent and immutable.
- Whether machine handoff becomes a formal artifact family in v1 or remains a derived supporting output.
- Exact compact list/history default display.
- Exact compare wording for equal non-full coverage classes.
- Whether future ACPM versions add governed profile-specific gates.
- Whether future ACPM versions add topology-specific or dynamic NGL scaffold policies.
- Whether legacy `custom` eventually becomes presentation-only after v1.
- Exact caveat-code threshold catalog, except where needed to block or allow handoff.

## Prep / Refactor Work Before Implementation

Required prep order:

1. Define the ACPM planner/orchestrator module boundary.
2. Define the planner output contract: selected scope, planner metadata, repeat tier, profile, and execution compilation inputs.
3. Add or prepare the generic `scope_authority` execution-truth field.
4. Add the effective filter-policy seam: DB column, helper/schema, runner write path, `trust_identity` projection, and minimal consumer projections.
5. Resolve stale `min_valid_warm_count` wording before trust-bearing filter-policy disclosure.
6. Define the ACPM recommendation record and status-policy seam.
7. Add minimal report/export/history/compare/explain projections from existing truth lanes.
8. Add planner implementation only after the above seams exist.

Do not start ACPM by:

- Adding planner logic to `src/runner.py` directly.
- Reusing `custom` to mean planner-directed partial scope.
- Putting effective filter-policy truth in methodology snapshots, planner metadata, or `metadata.json`.
- Emitting machine handoff from report markdown.
- Creating a broad compare/export redesign before the core truth seams exist.

## True Blockers

These are still blocking for implementation:

- Planner/orchestrator seam and output contract.
- Generic `scope_authority` truth for planner-directed partial scope.
- Effective filter-policy persistence/projection seam.
- Recommendation record/status seam before recommendation-grade claims.
- Stale `min_valid_warm_count` wording before filter-policy disclosure or any new relaxation policy.

No remaining investigation appears to block the v1 decision baseline itself.

## Implementation Planning Baseline

A practical prep plan should split implementation into small vertical slices:

- Slice 1: structural truth prep, especially `scope_authority` and planning metadata contract.
- Slice 2: effective filter-policy persistence/projection and tests.
- Slice 3: governed ACPM profile definitions and methodology/report labeling.
- Slice 4: planner catalog, applicability rules, repeat tiers, and fixed NGL scaffold.
- Slice 5: recommendation record/status/caveat contract.
- Slice 6: thin ACPM-aware projections for report, export, history, compare, explain, and optional handoff serializer.

The first ACPM implementation should be considered incomplete until the first two slices preserve history/export truth for partial planner-directed runs.

## Risks / Guardrails

- If `run_mode` carries ACPM authority, legacy `custom` history becomes misleading.
- If effective filter-policy truth is projected without persistence, compare/export/history drift will be hard to detect.
- If planner metadata stores thresholds or recommendation outcomes, it becomes a shadow methodology/recommendation system.
- If machine handoff bypasses recommendation status, ACPM can emit unsafe or overclaimed operator guidance.
- If NGL scaffold evidence is not labeled as a coverage class, users may mistake coarse sampling for full ladder coverage.

## Questions

NA for baseline convergence.

Open implementation questions are deferred and bounded in `ACPM-Decision-Extraction-Matrix.md`; they should be answered inside the relevant prep slice, not by reopening the full investigation set.
