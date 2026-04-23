# ACPM Legacy Custom Mode Compatibility Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: legacy `custom` compatibility once ACPM adds planner-directed partial coverage and generic `scope_authority`

## 1. Outcome

Recommended v1 policy: preserve literal `custom` as the legacy-compatible user-directed subset mode, but stop treating `run_mode` alone as full truth once ACPM partial coverage exists.

Use a small hybrid model:

- execution truth: `RunPlan.run_mode`, selected values/configs, schedule, effective IDs, and filter overrides
- authority truth: new generic `RunPlan.scope_authority`
- planner identity: adjacent ACPM planning metadata, not `run_mode`
- presentation wording: derived from execution truth + authority truth + coverage truth

For v1, do not add ACPM-specific run modes. ACPM planner-directed subsets should not be labeled `custom` unless the user literally chose the subset through the legacy manual/custom path.

## 2. Scope / What Was Inspected

Code surfaces inspected:

- `quantmap.py`
- `src/run_plan.py`
- `src/runner.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/compare.py`
- `src/report_compare.py`
- `src/trust_identity.py`
- `src/telemetry.py`
- `src/db.py`
- `src/governance.py`

Relevant planning docs inspected as context, not as sole authority:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-run-mode-and-scope-authority-semantics-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-history-surface-scope-and-coverage-projection-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planning-metadata-schema-TARGET-INVESTIGATION.md`

Repo-agent surfaces used:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/scripts/helpers/verify_dev_contract.py`

## 3. What `custom` Means Today

`custom` currently means a manual/user-directed exact subset, not just "partial coverage."

CLI / argument semantics:

- `quantmap.py` exposes `--mode` choices only as `full`, `standard`, and `quick`; `custom` is not a direct `--mode` value.
- `quantmap.py` parses `--values` and passes it as `values_override` to runner.
- `src/runner.py`'s standalone CLI help says `--values` triggers Custom mode and cannot combine with `--mode`.
- The standalone runner explicitly rejects `--mode ... --values ...` as ambiguous.

`RunPlan`:

- `src/run_plan.py` documents `custom` as "user-directed exact scope."
- `resolve_run_mode(values_override, mode_flag)` returns `custom` for any non-`None` `values_override`.
- `RunPlan.to_snapshot_dict()` persists `run_mode`, `selected_values`, `all_campaign_values`, schedule, paths, `filter_overrides`, `mode_flag`, and user CLI overrides.
- `RunPlan.is_custom` is a direct `run_mode == "custom"` property used by downstream readers.

Runner validation / dry-run:

- `src/runner.py` derives effective IDs from values, e.g. `NGL_sweep__v30_80_999`, isolating DB rows, progress state, logs, and outputs from full/standard/quick runs.
- `validate_campaign()` validates that all `--values` entries exist in the campaign values list.
- `run_campaign()` filters configs to `values_override`.
- `custom` injects `{"min_valid_warm_count": 1}` as a scoring filter override.
- dry-run and validate wording say Custom sparse data is intentional and valid only within the tested subset.

Report wording:

- `src/report.py` prints `Mode: Custom - user-directed - exact scope - targeted run`.
- It emits a Run Scope table with tested/skipped values and coverage.
- It warns that Custom is user-directed, not a full campaign recommendation, and that untested values may outperform the tested result.
- It changes result labels from "Winner" / "Score Winner" to "Best tested config."
- Production command comments say "Custom Run - Best Tested Config" and recommend Full validation before permanent deployment.

`report_campaign` wording:

- `src/report_campaign.py` renders `Run mode` from `campaigns.run_mode` or `run_plan.run_mode`.
- It prints coverage/tested values from `run_plan`.
- Its limitations section says Custom rankings reflect only the tested subset and untested values may differ.

Export/history/trust surfaces:

- `src/db.py` migration 6 adds `campaigns.run_mode` with allowed semantic set `full | custom | standard | quick`.
- `src/db.py` migration 9 adds `campaign_start_snapshot.run_plan_json`.
- `src/telemetry.py` stores `run_plan_json` at campaign start.
- `src/trust_identity.py` loads `run_plan_json` and marks run-plan source as `snapshot` when present.
- `src/export.py` writes `campaign.run_mode` into `metadata.json`, but does not currently project coverage authority.

Compare where relevant:

- `src/compare.py` loads `campaigns.run_mode` into `CampaignMeta`, but current comparison rendering in `src/report_compare.py` does not display mode or coverage authority.
- This makes compare less immediately misleading today, but also means it has no durable way to distinguish planner-directed partial scope from user-directed custom scope later.

## 4. Candidate Compatibility Models Considered

### A. Keep `custom` as the only partial-scope token

Rejected for ACPM.

It would label planner-directed narrowing as user-directed Custom across existing report, dry-run, production-command, and limitation text. It would also inherit Custom's scoring filter override, which is an execution/scoring behavior, not just a label.

### B. Add ACPM-specific run modes

Rejected for v1 unless later evidence proves no existing depth token can represent the execution schedule.

This would fuse planner identity into execution mode and spread ACPM branching across runner/report/export/history surfaces. Current evidence supports generic authority separation instead.

### C. Make `custom` presentation-only over a broader internal truth model

Rejected as a migration target for v1.

`custom` is already persisted in `campaigns.run_mode`, captured in `run_plan_json`, and used for load-bearing runtime/scoring/report branches. Treating it as presentation-only would create backwards-compatibility drift.

### D. Preserve literal `custom`, add `scope_authority`, and derive presentation from both

Recommended.

This keeps old manual workflows stable, prevents ACPM from being mislabeled as user-directed Custom, and gives readers a durable way to separate depth, coverage, authority, and planner provenance.

## 5. Recommended v1 Compatibility Policy

Preserve literal `custom` indefinitely for legacy/manual user-directed subsets.

Add `scope_authority` as a generic `RunPlan` field with at least:

- `system_defined`
- `user_directed`
- `planner_directed`

Recommended meanings:

- `run_mode`: execution-depth/repetition token and any mode-level execution/scoring defaults
- `selected_values` / `all_campaign_values`: coverage truth
- `scope_authority`: who selected the scope
- ACPM planning metadata: planner ID/version, planner policy ID/version, profile, repeat tier, scaffold/narrowing provenance
- presentation label: derived from the above, never from `run_mode` alone

Concrete v1 cases:

- Old manual Custom runs: `run_mode=custom`, no explicit `scope_authority`; readers infer `user_directed` with legacy provenance.
- New manual `--values` runs: `run_mode=custom`, `scope_authority=user_directed`.
- New Full/Standard/Quick built-in runs: `run_mode=full|standard|quick`, `scope_authority=system_defined`.
- New ACPM planner-directed partial runs: use the execution-depth token that matches the actual repetition/schedule, plus `scope_authority=planner_directed`, partial `selected_values`, and planner identity in ACPM metadata.

Do not describe ACPM partial runs as Custom unless the user actually supplied a manual/custom subset. Use wording like "planner-directed partial scope" or "ACPM planner-directed subset" while preserving the depth label separately, e.g. "Quick-depth, planner-directed partial scope."

## 6. Persisted History / Backward-Compatibility Implications

Old persisted runs must remain interpretable without rewriting history.

Minimum reader shim:

- if `scope_authority` exists, use it
- else if `run_mode == "custom"`, infer `scope_authority=user_directed` with source `inferred_legacy`
- else if `run_mode in {"full", "standard", "quick"}`, infer `scope_authority=system_defined` with source `inferred_legacy`
- else preserve `unknown_legacy`

For old runs with `run_plan_json`, coverage can be reconstructed from `selected_values` and `all_campaign_values`. For older runs without `run_plan_json`, do not silently claim full or partial scope beyond what `campaigns.run_mode` and configs can prove.

Serialization shims needed:

- `RunPlan.to_snapshot_dict()` should include `scope_authority` once added.
- `metadata.json` should project `scope_authority` and coverage facts, not just `campaign.run_mode`.
- Reports should show legacy-inferred authority honestly when authority is missing from old snapshots.
- Compare/history readers should prefer snapshot `run_plan_json` plus authority over DB `run_mode` alone.

No immediate DB rewrite is required by the evidence. If list/history needs queryable authority later, add a small derived projection or reader path rather than overloading `campaigns.run_mode`.

## 7. Surface-by-Surface Consequences

`quantmap.py`:

- Keep existing manual CLI semantics: `--values` means user-directed Custom.
- If ACPM gets a CLI entry, do not route planner-selected values through the same surface in a way that appears user-directed.

`src/run_plan.py`:

- Add generic `scope_authority`.
- Keep `custom` as a valid literal `run_mode`.
- Stop describing all mode semantics as if `run_mode` alone encodes coverage and authority once ACPM exists.

`src/runner.py`:

- Keep `--values` identity isolation and validation for manual Custom.
- ACPM partial execution should still isolate effective IDs and persist exact selected values, but the identity reason should be planner-directed, not `--values scope`.
- Filter overrides should follow explicit execution/scoring policy, not accidental reuse of Custom. Assigning ACPM to `custom` would silently inherit `min_valid_warm_count=1`.

`src/report.py`:

- Current Custom wording is honest for manual user-directed subsets.
- It would be misleading for ACPM planner-directed subsets.
- Update future wording branches to derive from depth + coverage + authority: "Best tested config among planner-selected subset" is not the same as "Custom Run - user-directed."

`src/report_campaign.py`:

- Same risk as `src/report.py`, but concentrated in identity, coverage, and limitations sections.
- Its plain `Run mode | custom` line is insufficient once `scope_authority` exists.

`src/export.py`:

- Current metadata only records `campaign.run_mode` under `campaign`.
- Add authority/coverage projection so exported cases do not force downstream consumers to guess from `run_mode`.

`src/trust_identity.py`:

- Already reads `run_plan_json`; this is the right shared reader seam for authority reconstruction.
- Add a narrow helper later rather than making every report/export/compare surface parse authority ad hoc.

`src/compare.py` / `src/report_compare.py`:

- Current compare loads `run_mode` but does not render it.
- Future compare should flag mismatched authority/coverage classes, especially `user_directed` vs `planner_directed`, before interpreting winner deltas.

`src/db.py`:

- `campaigns.run_mode` should remain as-is for compatibility.
- Do not redefine historical `custom`; add authority alongside persisted run intent instead.

## 8. Risks of Getting This Wrong

- ACPM planner-directed subsets could be mislabeled as user-directed Custom, falsifying human-facing provenance.
- Manual Custom users could lose stable semantics if `custom` is redefined as any partial coverage.
- Reports could overstate ACPM subset recommendations by inheriting the wrong "Custom" or "Quick complete coverage" wording.
- Scoring could drift if ACPM accidentally inherits Custom's sparse-data filter override.
- Export and compare consumers could treat `run_mode` as complete truth and lose planner-vs-user distinction permanently.
- Old history could be silently strengthened if readers infer authority or coverage without marking legacy inference.

## 9. Questions Answered in This Pass

What does `custom` mean today?

- A user-directed exact subset triggered by `--values`, persisted as literal `run_mode=custom`, isolated by effective campaign ID, and reported as scope-limited.

Is `custom` load-bearing or presentation-only?

- Load-bearing. It affects identity isolation, config filtering, `RunPlan`, DB history, scoring filter overrides, dry-run/validate wording, report labels, and production-command warnings.

Should ACPM planner-directed partial scope use `custom`?

- No, not as the default v1 policy. The repo evidence says Custom means user-directed; ACPM authority is planner-directed.

Should v1 add ACPM-specific run modes?

- No, not unless later implementation evidence shows no existing execution-depth token can represent the actual ACPM schedule.

What is the smallest durable compatibility policy?

- Preserve literal `custom` for manual/user subsets; add generic `scope_authority`; derive wording from execution depth, coverage, and authority.

## 10. Remaining Open Questions

- Exact field name: prior docs use both `scope_authority` direction and `coverage_authority`; this pass recommends `scope_authority` in `RunPlan` and allows a derived export/history projection, but final naming should be normalized before implementation.
- Effective ID format for ACPM partial subsets is unresolved: it should be isolated like Custom, but should not imply user `--values` scope.
- Whether `campaigns` needs a queryable `scope_authority` column is unresolved; current evidence supports starting with `run_plan_json` plus export/report projections.
- Exact scoring filter policy for ACPM partial depths needs a separate scoring-policy pass; do not inherit Custom's override by accident.
- CLI shape for ACPM planner-directed runs is outside this pass.

## 11. Recommended Next Investigations

- ACPM effective run ID and artifact path policy for planner-directed subsets.
- ACPM scoring filter override policy by repeat tier/depth, separate from user-directed Custom.
- Shared `trust_identity` reader shape for `scope_authority`, coverage class, and legacy inference.
- Compare/report/export wording matrix for combinations of depth, coverage, authority, and planner metadata.
- Migration/read-shim test matrix using: pre-v6 no `run_mode`, run-mode-only legacy, run-plan snapshot without authority, new manual Custom, new ACPM partial.

## 12. .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/scripts/helpers/verify_dev_contract.py`
