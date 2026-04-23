# ACPM Decision Extraction Matrix

Purpose: compact the ACPM investigation set into decision candidates so v1 can move from repeated investigation into prep and implementation planning.

Use this as a decision dataset, not a prose summary. The baseline in `ACPM-v1-Decision-Baseline.md` should be updated from this matrix when decisions change.

## Domain Coverage Check

Major ACPM decision domains covered:

- Profile / methodology semantics
- Planner / execution contract
- Planner behavior / narrowing / applicability
- Scope authority / legacy custom compatibility
- Effective filter-policy truth and projection
- Trust / reporting / export / history / compare surfaces
- Recommendation status / record / machine handoff
- Prep / refactor / implementation order

## Disposition Legend

- `lock now`: enough converged evidence exists for v1 prep.
- `defer intentionally`: not needed to preserve v1 truth, or safe to decide during implementation.
- `still blocking`: must be decided before the related implementation can start.

## Matrix

| Domain | Source doc | Question answered | Recommended answer | Why it fits the repo | What remains open | Confidence | Blocking? | Follow-up needed? | Disposition |
|---|---|---|---|---|---|---|---|---|---|
| Prep / refactor | `ACPM-blast-radius-INVESTIGATION.md` | Can ACPM reuse the existing engine, and where is the blast radius? | Reuse the existing execution/artifact engine, but add a dedicated planner/orchestrator seam before putting ACPM logic into runner/report surfaces. | Current `quantmap -> runner -> score -> report/export` path is strong for execution, but no planner seam exists. | Exact CLI entry and generated-campaign materialization details. | high | yes | yes | lock now |
| Prep / refactor | `ACPM-refactor-seams-INVESTIGATION.md` | What prep is required before ACPM implementation? | Create planner/execution and recommendation seams first; avoid embedding ACPM policy in `src/runner.py`. | Runner and report modules are already overloaded; `RunPlan` is a usable execution seam. | Whether planner intent extends `RunPlan` directly or lives beside it is mostly settled by later reports as adjacent metadata plus generic `scope_authority`. | high | yes | yes | lock now |
| Planner / execution contract | `ACPM-plan-contract-TARGET-INVESTIGATION.md` | What should `RunPlan` own versus ACPM planner metadata? | `RunPlan` remains execution truth; ACPM planner state lives adjacent; only generic execution-truth additions belong in `RunPlan`. | Preserves current execution semantics and avoids turning `RunPlan` into a planner-provenance container. | Exact persistence location for ACPM planning metadata during implementation. | high | yes | yes | lock now |
| Scope authority | `ACPM-run-mode-and-scope-authority-semantics-TARGET-INVESTIGATION.md` | How should run mode, partial scope, and planner authority be represented? | Use two axes: `run_mode` for execution depth/repetition, `scope_authority` for who selected scope. Do not add ACPM-specific run modes. | Existing mode labels cannot carry both execution depth and planner authority without becoming misleading. | Planner-directed full-coverage edge case. | high | yes | yes | lock now |
| Scope authority | `ACPM-legacy-custom-mode-compatibility-TARGET-INVESTIGATION.md` | What should happen to legacy `custom` once ACPM has planner-directed partial scope? | Preserve literal `custom` for user-directed subset workflows; ACPM planner-directed subsets must not be labeled `custom`. | Keeps old persisted runs interpretable and prevents ACPM from being mislabeled as manual user scope. | Whether `custom` eventually becomes presentation-only after v1. | high | no | yes | lock now |
| Planner metadata | `ACPM-planning-metadata-schema-TARGET-INVESTIGATION.md` | What belongs in ACPM planning metadata? | Keep metadata small, immutable, and planner-side: planner identity, policy, profile, repeat tier, narrowing provenance. Do not duplicate execution, methodology, filter, or recommendation truth. | Matches repo snapshot patterns while avoiding shadow methodology or shadow execution records. | Exact DB/file home and field naming during implementation. | high | yes | yes | lock now |
| Profile / methodology | `ACPM-profile-to-governance-mapping-TARGET-INVESTIGATION.md` | Are ACPM profiles methodology, planner policy, or both? | Treat Balanced, T/S, and TTFT as methodology-primary hybrids: governed scoring profiles plus paired planner heuristics. | QuantMap already treats scoring profiles as methodology/trust objects; planner heuristics can guide execution without replacing scoring semantics. | Final user-facing expansion of `T/S`. | high | yes | yes | lock now |
| Profile / methodology | `ACPM-profile-weight-and-gate-spec-TARGET-INVESTIGATION.md` | Should profiles vary gates or weights? | Keep viability, trust, and safety floors global; vary weights only in v1. | Elimination gates are trust-bearing validity floors in current scoring, not preference filters. | Whether later versions introduce governed profile-specific gates. | high | yes | no | lock now |
| Profile / methodology | `ACPM-profile-weight-values-TARGET-INVESTIGATION.md` | What v1 metric set and weight vectors should ACPM use? | Use the same six metric keys across Balanced, T/S, and TTFT; vary weights; keep `warm_ttft_p90_ms` at `0.00` as gate/disclosure, not a rank axis. | Preserves current six-key methodology shape while avoiding double-counting a gate-like tail-latency signal. | Naming clarity for `T/S`; whether current default profile ever evolves separately. | high | no | yes | lock now |
| Profile / reporting | `ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md` | How should profile identity be shown? | Present profile as a methodology lens with shared validity floor, shared score shape, profile weight lens, and planner policy. | Keeps scoring truth visible without overloading short report headlines. | Exact wording and projection shape per surface. | high | no | yes | lock now |
| Planner behavior | `ACPM-planner-narrowing-and-candidate-selection-INVESTIGATION.md` | How should ACPM narrow candidates? | Use staged, rule-based narrowing from committed campaign YAML: universe assembly, applicability pruning, profile prioritization, repeat-tier expansion, execution compilation. | Avoids open-ended heuristic search and preserves committed campaign semantics. | Exact implementation of the planner catalog. | high | yes | yes | lock now |
| Planner behavior | `ACPM-applicability-and-pruning-rule-catalog-TARGET-INVESTIGATION.md` | What pruning is allowed before execution? | Allow only narrow structural applicability pruning; do not prune ordinary YAML values by profile preference, live noise, or guessed optima. | Keeps ACPM from hiding valid search space behind speculative planner judgment. | Optional family labels and topology-specific policy details. | high | no | yes | lock now |
| Planner behavior | `ACPM-profile-planner-policy-and-repeat-tier-matrix-TARGET-INVESTIGATION.md` | How should profiles and repeat tiers affect planner budget? | Applicability is the lower layer; profile and repeat tier form a budget layer. Repeat tiers expand execution depth first, family count second, value coverage only in one narrow case. | Keeps planner policy from becoming a second scoring or gating system. | Exact policy-table serialization and final repeat-tier thresholds. | high | yes | yes | lock now |
| NGL scaffold | `ACPM-NGL-scaffold-subset-policy-TARGET-INVESTIGATION.md` | Can v1 use a partial `NGL_sweep` scaffold? | Allow exactly one fixed `1x` scaffold `[10, 30, 50, 70, 90, 999]`; require full NGL coverage at `3x`/`5x` and for explicit threshold recommendations. | The subset is predeclared, YAML-backed, ordered, and easy to disclose. | Whether future machine-topology variants exist. | high | no | yes | lock now |
| NGL scaffold | `ACPM-NGL-report-and-audit-wording-TARGET-INVESTIGATION.md` | How should scaffolded NGL evidence be worded? | Disclose scaffold use as coverage-class limitation, not methodology truth or recommendation authority. | Prevents coarse scaffold evidence from being mistaken for full ladder coverage. | Exact report/export strings. | high | no | yes | lock now |
| Coverage surfaces | `ACPM-compare-surface-coverage-class-labeling-TARGET-INVESTIGATION.md` | How should compare/history distinguish scaffolded versus full or custom NGL coverage? | Preserve `ngl_coverage_class`, `selected_ngl_values`, `coverage_authority`, and scaffold policy label/ID when applicable. | Compare cannot infer scope intent safely from `run_mode` or selected values alone. | Whether exact selected values display by default or only on difference. | high | no | yes | lock now |
| Coverage surfaces | `ACPM-history-surface-scope-and-coverage-projection-TARGET-INVESTIGATION.md` | What scope/coverage truth should history expose? | Keep canonical scope in `RunPlan`, planner identity in ACPM metadata, and a small immutable history-grade projection for compare/export/audit. | Avoids reverse-engineering intent later while keeping prose out of persisted truth. | Exact projection schema and storage home. | high | yes | yes | lock now |
| Filter policy | `ACPM-planner-directed-scoring-filter-policy-TARGET-INVESTIGATION.md` | Should ACPM inherit existing mode-based scoring/filter relaxations? | No default relaxation for ACPM planner-directed partial runs; any exception needs explicit policy. | Existing relaxations mix execution depth and historical convenience; ACPM partial scope is different authority truth. | Whether future governed ACPM exception policy is needed. | high | no | yes | lock now |
| Filter policy | `ACPM-effective-filter-provenance-and-surface-disclosure-TARGET-INVESTIGATION.md` | Where should effective filter truth live and how should surfaces consume it? | Persist small run-effective filter provenance adjacent to `run_plan_json`; surfaces consume through `trust_identity` projection. | Prevents report/export/compare from re-deriving threshold truth independently. | Exact schema, later resolved by schema-specific investigation. | high | yes | yes | lock now |
| Filter policy | `ACPM-filter-policy-persistence-history-and-export-TARGET-INVESTIGATION.md` | What is the physical home and legacy policy for effective filters? | Persist `campaign_start_snapshot.effective_filter_policy_json`; export/history read through `trust_identity`; `metadata.json` is projection only. | Aligns with snapshot-first history and keeps methodology snapshots as base methodology truth. | Exact JSON contract, later resolved by schema-specific investigation. | high | yes | yes | lock now |
| Filter policy | `ACPM-effective-filter-policy-json-schema-and-projection-TARGET-INVESTIGATION.md` | What is the v1 JSON contract for effective filter policy? | Use one nullable JSON column with schema ID/version, policy ID, truth status, effective filters, base source, layers, hash, and confirmation. `campaign_override` is a modifier/layer. | Captures applied thresholds and provenance without making metadata or planner records a second authority. | Exact mismatch handling and compact list projection. | high | yes | yes | lock now |
| Filter policy | `ACPM-effective-filter-policy-implementation-plan-and-test-matrix-TARGET-INVESTIGATION.md` | What is the smallest implementation/test plan for the filter-policy seam? | Add DB column/helper, write from runner after scoring, read through `trust_identity`, project minimally to export/report/history/compare/explain. Include post-score confirmation as cross-check only. | Matches current write/read seams and avoids shadow methodology. | Exact status mutation on confirmation mismatch; compact list default. | high | yes | yes | lock now |
| Recommendation | `ACPM-recommendation-record-contract-TARGET-INVESTIGATION.md` | What should a recommendation record own? | Persist a small post-scoring outcome record with status, leading/recommended config, evidence, caveats, source references, and machine-handoff projection. | Keeps recommendation claim truth separate from execution, planner, methodology, and report prose. | Exact machine-handoff policy for withheld statuses, resolved by status policy. | high | yes | yes | lock now |
| Recommendation | `ACPM-recommendation-status-policy-TARGET-INVESTIGATION.md` | What statuses control ACPM claims and handoff? | Use four statuses: `strong_provisional_leader`, `best_validated_config`, `needs_deeper_validation`, `insufficient_evidence_to_recommend`; handoff only when `recommended_config_id` exists. | Separates score leader from allowed recommendation claim. | Exact caveat classification and validated-status thresholds. | high | yes | yes | lock now |
| Recommendation | `ACPM-caveat-code-severity-policy-TARGET-INVESTIGATION.md` | How should caveats qualify or block recommendations? | Use compact caveat codes with governed behavior classes; status remains the primary claim-control field. | Avoids a second severity/status system while preserving machine-readable qualifiers. | Exact caveat catalog and thresholds. | medium | yes | yes | defer intentionally |
| Trust surfaces | `ACPM-trust-output-and-handoff-surfaces-INVESTIGATION.md` | Which surfaces should own ACPM truth? | Use four ownership lanes: execution, methodology, planner provenance, recommendation claim. Machine handoff is a serializer output, not authority. | Prevents reports, exports, and handoff files from becoming independent truth systems. | Whether machine handoff joins the formal 4-artifact contract in v1. | high | no | yes | lock now |

## Convergence Summary

The investigation set converges on a small number of durable v1 principles:

- ACPM is a planner/orchestrator over existing QuantMap execution, not a replacement execution engine.
- `RunPlan` remains execution truth; ACPM planner metadata remains adjacent.
- `scope_authority` is required to keep planner-directed partial coverage distinct from legacy `custom`.
- ACPM profiles are governed methodology lenses with shared validity floors and profile-specific weights.
- Planner narrowing must be conservative, YAML-backed, and explainable.
- Effective filter-policy truth belongs in `campaign_start_snapshot.effective_filter_policy_json` and is projected through `trust_identity`.
- Recommendation claim truth needs its own post-scoring record and status policy before machine handoff can be trusted.
- Human-facing wording should be derived from structured truth lanes, not stored as authority.

## Real Blockers

These block implementation prep or the first implementation slice:

- Define the ACPM planner/orchestrator module boundary and contract.
- Add the generic `scope_authority` truth model before planner-directed subsets are surfaced.
- Add effective filter-policy persistence/projection before ACPM partial runs can be history/export honest.
- Define the recommendation record/status seam before ACPM emits recommendation-grade claims or machine handoff.
- Resolve stale `min_valid_warm_count` wording before trust-bearing filter-policy disclosure.

These do not block v1 baseline convergence:

- Exact default compare wording.
- Exact compact list projection.
- Future profile-specific gates.
- Future dynamic NGL scaffold variants.
- Whether `custom` becomes presentation-only after v1.
