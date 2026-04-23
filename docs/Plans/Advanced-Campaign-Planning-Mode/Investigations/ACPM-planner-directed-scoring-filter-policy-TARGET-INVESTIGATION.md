# ACPM Planner-Directed Scoring Filter Policy Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: v1 scoring/filter policy for ACPM planner-directed partial runs

## Outcome

Recommended v1 policy: ACPM planner-directed partial runs should not inherit Custom-style scoring/filter relaxation by default. They also should not inherit mode relaxations by `run_mode` alone without an explicit policy reason.

Use one explicit scoring/filter policy axis separate from `run_mode`, `scope_authority`, and planner identity:

- default ACPM policy: use the same methodology/profile gate floor as normal scoring
- allow depth-required relaxation only when the execution schedule structurally cannot satisfy the default floor
- require any ACPM-specific relaxation to be explicit, persisted, and disclosed as planner/scoring policy, not as accidental `custom` behavior

For current code, this mostly means: do not let planner-directed partial scope become `run_mode=custom`, because that silently applies `{"min_valid_warm_count": 1}`.

## Scope / What Was Inspected

Primary code/config surfaces:

- `src/runner.py`
- `src/run_plan.py`
- `src/score.py`
- `src/analyze.py`
- `src/governance.py`
- `configs/profiles/default_throughput_v1.yaml`
- `configs/metrics.yaml`

Downstream disclosure/history surfaces:

- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/compare.py`
- `src/report_compare.py`
- `src/explain.py`
- `src/trust_identity.py`

Relevant ACPM context docs checked for consistency:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-weight-and-gate-spec-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-legacy-custom-mode-compatibility-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-caveat-code-severity-policy-TARGET-INVESTIGATION.md`

## Current Filter / Scoring Override Behavior

The scoring path is:

1. `src/runner.py` resolves `RunPlan`.
2. `src/runner.py` injects mode-level `RunPlan.filter_overrides`.
3. `src/runner.py` merges campaign YAML `elimination_overrides` on top; YAML wins.
4. `src/score.py::score_campaign()` merges `profile.gate_overrides` with those caller overrides.
5. `src/score.py::apply_elimination_filters()` applies the effective filters before rankability and composite scoring.

Current mode effects:

- `full`: no mode-level filter override.
- `standard`: no mode-level filter override.
- `quick`: `{"min_valid_warm_count": 3}` in `src/runner.py`.
- `custom`: `{"min_valid_warm_count": 1}` in `src/runner.py`.

Current active profile floor:

- `configs/profiles/default_throughput_v1.yaml` sets `min_valid_warm_count: 3`.
- `src.score.ELIMINATION_FILTERS` resolves from the default profile and currently returns `min_valid_warm_count: 3.0`.
- Some comments/fallbacks still say `10`, including `src/score.py` header text and `src/report_campaign.py` fallback display. That is stale or at least not the current live floor.

What `min_valid_warm_count` actually controls:

- `src/analyze.py` counts valid warm speed-short TG samples.
- `src/score.py::_check_filters()` eliminates configs with fewer valid warm samples than the effective floor.
- Passing configs then go through rankability: missing primary TG metrics become eliminations; missing secondary metrics become unrankable evidence.

Semantics of existing overrides:

- Custom's `min_valid_warm_count=1` is sparse-user-scope semantics: current comments say it prevents intentionally sparse targeted user runs from being gate-kept as insufficient data.
- Quick's `min_valid_warm_count=3` is execution-depth semantics: current comments explain Quick's one-cycle schedule yields only four warm speed-short samples, so the old/default larger floor would eliminate all Quick configs. Under the current active profile floor of 3, the Quick override is redundant but still documents schedule-driven intent.
- Standard and Full use the active profile gates unchanged.
- Campaign YAML `elimination_overrides` are explicit campaign-level policy and win over mode defaults.

Policy by accident:

- The default profile says profiles may tighten gates but never relax below Registry minimums, yet `validate_profile_against_registry()` currently validates recognized gate keys and only no-ops the `min_sample_gate` comparison.
- The active default profile uses `min_valid_warm_count=3` while Registry metric `min_sample_gate` values for primary TG metrics are 10.
- This means the live floor is governed by profile gate overrides in practice, but the surrounding comments still contain older/stale trust language.

## Candidate ACPM Policies Considered

### 1. Inherit Custom-style relaxation

Reject for v1.

This would give planner-directed partial runs `min_valid_warm_count=1`, a floor intended for user-directed sparse custom subsets. It would make planner-directed recommendations rankable with extremely thin per-config evidence and would inherit Custom wording/report assumptions unless every downstream branch was corrected.

### 2. Inherit only depth-based relaxations

Partially acceptable, but only if made explicit.

If ACPM uses a one-cycle Quick-depth schedule, a lower floor may be structurally necessary. But inheriting this through `run_mode` alone is ambiguous because ACPM adds a separate planner-directed partial-scope axis. The report/history record should say whether the floor is profile-default, depth-required, or ACPM-policy-specific.

### 3. Use no relaxation by default

Best default v1 posture.

Planner-directed partial scope is not automatically sparse data. If the planner selects fewer values but each selected config still receives enough cycles/requests to satisfy normal scoring gates, there is no trust reason to weaken filters.

### 4. Add a distinct explicit ACPM scoring/filter policy

Recommended as the durable seam.

The policy can initially be conservative: no relaxation unless structurally required by the execution depth, with any exception named, persisted, and disclosed. This avoids mixing scoring validity with planner identity, run depth, or legacy Custom behavior.

## Recommended v1 Policy

Use this minimum model:

- `run_mode`: execution depth and schedule class.
- `scope_authority`: who selected the scope.
- planner metadata: planner/policy/profile/repeat-tier provenance.
- `scoring_filter_policy`: explicit scoring/filter authority for any non-default floor.

Recommended v1 values:

- `profile_default`: use `profile.gate_overrides` unchanged.
- `depth_required_relaxation`: schedule cannot meet profile-default sample floor; e.g. Quick-depth sample density.
- `user_directed_sparse_custom`: legacy manual Custom compatibility only.
- `acpm_exception`: reserved; requires separate approval/evidence and must be disclosed.

Concrete policy:

- New ACPM planner-directed partial runs default to `profile_default`.
- ACPM should never receive `user_directed_sparse_custom` merely because it is partial.
- If ACPM uses Quick-depth one-cycle execution, use `depth_required_relaxation` only if needed by the actual effective profile floor and schedule. Under current live floor `3`, Quick's explicit override is redundant but harmless; if the floor later rises, this policy becomes load-bearing again.
- Any ACPM-specific relaxation below the profile/depth floor must be an explicit `acpm_exception`, not hidden in `run_mode=custom` or campaign YAML.

This is the smallest v1 policy that preserves trust: partial coverage affects recommendation scope, while filter floors remain validity/certainty semantics.

## Trust / Methodology Implications

Filters are trust-bearing methodology, not cosmetic display.

Evidence:

- `src/report_campaign.py` calls elimination filters "pre-committed before data collection" and says configs failing filters are excluded from ranking entirely.
- `src/score.py` treats filters as pre-score eliminators; eliminated configs cannot become winners.
- `src/score.py` persists methodology snapshots with profile gates, but not the fully effective per-run mode/campaign overrides.
- `src/export.py` exports methodology `eligibility_filters` from methodology snapshot gates, not necessarily the effective filters used in a run.

Implication:

- If ACPM changes scoring/filter floors, that policy must be persisted/disclosed alongside run intent or scoring metadata.
- A hidden ACPM relaxation would create a second methodology layer outside methodology snapshots.
- Reusing Custom's `min_valid_warm_count=1` would lower the certainty floor while presenting planner-directed output as governed automation.

## Surface Implications

`src/runner.py`:

- Must not use `custom` mode as the route for ACPM partial scope.
- Needs an explicit source for `filter_overrides` if ACPM ever differs from profile defaults.

`src/run_plan.py`:

- `filter_overrides` already persists in `run_plan_json`; future policy should also persist why those overrides exist.

`src/score.py`:

- Already accepts `filter_overrides` and returns `effective_filters`.
- It does not know whether overrides are legacy Custom, depth-required, campaign YAML, or future ACPM. That provenance must come from caller/run metadata.

`src/report.py` and `src/report_campaign.py`:

- Must disclose effective filters and the policy source when ACPM uses any non-profile-default filters.
- Current Custom wording is not safe for planner-directed scope.

`src/export.py`:

- Should not export only methodology snapshot gates if effective per-run filters differed.
- Needs a projection of effective filters and filter-policy provenance for portable cases.

`src/compare.py` / `src/report_compare.py`:

- Compare currently counts eliminations but does not compare filter-policy provenance.
- ACPM compare should flag runs with different effective filter floors as lower-comparability or methodology mismatch/warning.

`src/explain.py`:

- Should avoid explaining ACPM recommendations without exposing whether the recommendation used profile-default, depth-required, or exception filters.

`src/trust_identity.py`:

- Good future place for a narrow reader helper that reconstructs effective filter policy from `run_plan_json`, methodology snapshots, and any ACPM metadata.

## Risks of Getting This Wrong

- Planner-directed ACPM runs could rank configs from one valid warm sample if they inherit Custom semantics.
- Filter relaxations could be mistaken for recommendation confidence instead of disclosed as lower evidence density.
- Compare/export/history could report methodology gates while the actual run used different effective filters.
- Profile gate policy could drift through hidden planner behavior, contradicting prior ACPM guidance that profiles should not secretly change validity floors.
- Users could treat planner-directed partial runs as more validated than manual Custom runs despite having weaker or equivalent evidence.

## Remaining Open Questions

- Should `scoring_filter_policy` live in `RunPlan`, ACPM planning metadata, methodology snapshot metadata, or a small derived history projection?
- Should effective filters be persisted as first-class history truth outside `scores_result`, since `scores_result` is not itself the durable snapshot lane?
- What exact threshold should Quick-depth ACPM use if the active profile floor changes above 3?
- Are campaign YAML `elimination_overrides` still allowed for ACPM-generated campaigns, or should ACPM forbid planner-authored gate relaxation in v1?
- Should any ACPM `acpm_exception` require a named policy ID and a report caveat that caps recommendation status?

## Recommended Next Investigations

- Effective filter provenance persistence: `RunPlan` vs methodology snapshot vs ACPM metadata.
- ACPM compare/report/export disclosure matrix for effective filters and recommendation status.
- Quick-depth repeat-tier sufficiency under the active profile floor and future stricter floors.
- Campaign YAML `elimination_overrides` governance for generated/planner-directed campaigns.
- Historical reader shim for old runs with `run_plan_json.filter_overrides` but no explicit filter-policy source.

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/scripts/helpers/verify_dev_contract.py`
