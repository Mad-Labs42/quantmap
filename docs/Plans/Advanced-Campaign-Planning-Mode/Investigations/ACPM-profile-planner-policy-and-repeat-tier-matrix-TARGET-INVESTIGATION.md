# ACPM Profile Planner Policy and Repeat-Tier Matrix Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 planner-budget policy matrix only

## Outcome

Recommended v1 planner-policy model:

- keep applicability as the lower truth layer
- put profile behavior and repeat-tier behavior in a separate planner-budget layer above it
- make repeat tiers expand:
  - execution depth first
  - family count second
  - value coverage only in one narrow special case
- keep a shared cross-profile core so planner policy does not become a second scoring/gating system

Recommended v1 structure:

- shared base core across all profiles:
  - `C01_threads_batch`
  - `C04_context_size`
  - `C05_threads`
  - `C06_ubatch`
  - `C07_batch`
- shared secondary core across all profiles by `3x` and `5x`:
  - `C02_n_parallel`
  - `C03_kv_cache_type`
- conditional special family:
  - `NGL_sweep` when applicability says GPU offload is a real surface
- optional extended family:
  - `C10_mmap`
  - `C12_mlock`
  - `C13_defrag_thold`
  - `C14_cont_batching`
  - `C15_threads_http`
- special conditional optional family:
  - `C09_tensor_placement`
  - `C11_cpu_affinity`
- derived validation family:
  - `C08_interaction`
  - `Finalist`

Recommended repeat-tier meaning in repo terms:

- `1x`
  - quick-like execution depth
  - smallest safe family bundle
  - no derived validation
  - no value scaffolding except a tightly bounded `NGL_sweep` special case if that family is selected
- `3x`
  - standard-like execution depth
  - full shared core coverage
  - profile-promoted optional families
  - full YAML values for all selected families
- `5x`
  - full-like execution depth
  - broadest selected-family coverage
  - derived validation eligibility
  - full YAML values for all selected families, including `NGL_sweep`

Strongest repo-grounded reason:

- the current engine already has clear execution-depth semantics in `RunPlan` and clear campaign/value truth in YAML. The safest planner layer is therefore a governed family-ordering and expansion policy that compiles into ordinary runs, not a speculative value-search layer.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/run_plan.py`
- `src/runner.py`
- `src/score.py`
- `src/report.py`

Config surfaces inspected:

- `configs/campaigns/*.yaml`
- `configs/baseline.yaml`

Supporting ACPM investigations inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-applicability-and-pruning-rule-catalog-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planner-narrowing-and-candidate-selection-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-to-governance-mapping-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-weight-and-gate-spec-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-run-mode-and-scope-authority-semantics-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-plan-contract-TARGET-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`
- `.agent/policies/architecture.md`

Validation used:

- targeted source/doc inspection
- one light proportional verification pass that summarized the live campaign family counts and confirmed the current auto-generated dependency chain:
  - `C08_interaction` depends on `C01`–`C07`
  - `Finalist` depends on `C08`
- no product-code edits

## Current Planner-Policy Constraints

### 1. Execution depth already has a strong repo meaning

`RunPlan` and current mode semantics already mean:

- `quick` = 1 cycle, full campaign values
- `standard` = 3 cycles, full campaign values
- `full` = 5 cycles, full campaign values

Implication:

- `1x / 3x / 5x` should primarily map to execution-depth strength in repo terms
- planner-budget policy can add family expansion on top, but should not invent a competing meaning for repetition

### 2. Derived campaigns already enter the flow explicitly

`score.generate_c08()` combines winners from `C01`–`C07`.  
`score.generate_finalist()` then builds `Finalist` from the `C08` winner.

Implication:

- derived validation is already a staged, explicit, engine-compatible pattern
- repeat tiers can gate when that path becomes eligible

### 3. Applicability already settled the lower truth layer

The current applicability investigation established:

- applicability is conservative campaign-family gating
- inner YAML value lists should remain intact inside applicability
- profile preference must not masquerade as applicability truth

Implication:

- this pass can decide inclusion, ordering, and expansion only after applicability is resolved

### 4. The live campaign family structure supports staged planning

Verification confirmed:

- `primary_sweep`: 7 campaigns
- `extended_sweep`: 7 campaigns
- `interaction`: 1 campaign
- `validation`: 1 campaign
- `auto_generated`: `C08_interaction`, `Finalist`

Implication:

- the repo already has a natural staged family model:
  - primary search
  - extended/runtime refinement
  - derived validation

### 5. Profiles are allowed to shape acquisition, not truth

Prior ACPM findings already constrain:

- profiles may change weights
- planner policy may change order and expansion
- profiles must not change validity floors, gates, or the meaning of scored truth

Implication:

- the clean planner-policy question is not “what is valid for T/S?”
- it is “which already-applicable families does T/S spend earlier budget on?”

## Candidate Planner-Policy Models Considered

### 1. Repeat tiers as depth only

Meaning:

- `1x / 3x / 5x` only change cycles per config
- family selection stays nearly fixed

Assessment:

- too weak

Why:

- leaves little planner behavior beyond scheduling
- does not explain how ACPM budget should widen search responsibly

### 2. Family expansion only, with fixed execution depth

Meaning:

- repeat tiers change campaign count but not cycles/repetition

Assessment:

- reject

Why:

- conflicts with the repo’s current strong depth semantics
- weak fit with existing report/confidence language

### 3. Aggressive family and value scaffolding by profile/tier

Meaning:

- profiles and tiers both trim many families and many inner value lists early

Assessment:

- reject for v1

Why:

- too much false-pruning risk
- highest chance of hidden heuristics and interior-optimum loss

### 4. Hybrid depth-first expansion with conservative family growth and minimal value scaffolding

Meaning:

- repeat tiers map to depth first
- profile changes family order and optional-family promotion
- family count widens with tier
- inner value coverage stays full except for one narrowly bounded special case

Assessment:

- best v1 fit

Why:

- aligns with current engine semantics
- keeps planner policy explicit
- provides real budget behavior without speculative search

## Recommended v1 Profile Planner Policy and Repeat-Tier Matrix

### Shared family buckets

| Bucket | Families | Meaning |
|---|---|---|
| Shared base core | `C01`, `C04`, `C05`, `C06`, `C07` | Always important tradeoff levers for practical recommendation |
| Shared secondary core | `C02`, `C03` | Still core to a full primary pass, but slightly less urgent for first-budget narrowing |
| Conditional special | `NGL_sweep` | High-impact when GPU offload is real; not universal |
| Optional extended | `C10`, `C12`, `C13`, `C14`, `C15` | Real runtime/refinement families, but not always first-pass priorities |
| Special conditional optional | `C09`, `C11` | Explicitly machine/model-specific campaigns |
| Derived validation | `C08`, `Finalist` | Staged validation after primary search |

### Shared invariant across profiles

By `3x` and `5x`, every profile should include the full shared core:

- `C01_threads_batch`
- `C02_n_parallel`
- `C03_kv_cache_type`
- `C04_context_size`
- `C05_threads`
- `C06_ubatch`
- `C07_batch`

Reason:

- this is the cleanest way to stop planner policy from becoming a shadow gate/search system
- profiles may spend earlier budget differently, but they should converge on the same primary search body at stronger tiers

### Profile ordering and promotion policy

#### `Balanced`

Definition:

- explicit mixed practical policy
- must cover both responsiveness and throughput levers before spending much budget on runtime/platform refinements

Recommended early order:

1. `C04_context_size`
2. `C06_ubatch`
3. `C01_threads_batch`
4. `C05_threads`
5. `C07_batch`
6. `C02_n_parallel`
7. `C03_kv_cache_type`
8. `NGL_sweep` when applicable

Recommended optional-family promotion:

- promote `C13_defrag_thold` and `C15_threads_http` earlier than other extended families
- keep `C10_mmap`, `C12_mlock`, `C14_cont_batching` later
- keep `C09_tensor_placement` and `C11_cpu_affinity` late and conditional

#### `T/S`

Definition:

- explicit throughput-first acquisition policy
- must still preserve enough latency-sensitive core coverage to avoid one-dimensional search

Recommended early order:

1. `C05_threads`
2. `C01_threads_batch`
3. `C07_batch`
4. `C06_ubatch`
5. `C02_n_parallel`
6. `NGL_sweep` when applicable
7. `C04_context_size`
8. `C03_kv_cache_type`

Recommended optional-family promotion:

- promote `C10_mmap` and `C12_mlock` earlier
- promote `C09_tensor_placement` earlier when applicability allows it
- defer `C13_defrag_thold`, `C14_cont_batching`, and `C15_threads_http` unless tier budget is larger

#### `TTFT`

Definition:

- explicit responsiveness-first acquisition policy
- must still retain throughput-shaping core families by `3x`

Recommended early order:

1. `C04_context_size`
2. `C06_ubatch`
3. `C13_defrag_thold`
4. `C15_threads_http`
5. `C03_kv_cache_type`
6. `NGL_sweep` when applicable
7. `C01_threads_batch`
8. `C05_threads`
9. `C07_batch`
10. `C02_n_parallel`

Recommended optional-family promotion:

- promote `C13_defrag_thold` and `C15_threads_http` strongly
- promote `C14_cont_batching` ahead of `C10` and `C12`
- keep `C09_tensor_placement` and `C11_cpu_affinity` late and conditional

### Repeat-tier matrix

| Tier | Repo-depth meaning | Family policy | Value policy | Derived campaign policy |
|---|---|---|---|---|
| `1x` | quick-like, 1 cycle/config | starter core only, plus profile-promoted special/optional families when highly justified | full YAML values for selected 2-5 value families; only `NGL_sweep` may use a predeclared scaffold | no `C08`, no `Finalist` |
| `3x` | standard-like, 3 cycles/config | full shared core, plus profile-promoted optional families | full YAML values for all selected families | no `Finalist`; `C08` normally deferred in v1 |
| `5x` | full-like, 5 cycles/config | full shared core, conditional `NGL_sweep`, broader optional families | full YAML values for all selected families | `C08` eligible; `Finalist` eligible only after a stable `C08` leader exists |

## Profile-by-Tier v1 Matrix

### `Balanced`

| Tier | Always include | Promote if applicable | Defer unless surplus budget |
|---|---|---|---|
| `1x` | `C04`, `C06`, `C01`, `C05`, `C07` | `NGL_sweep`, `C13`, `C15` | `C02`, `C03`, `C10`, `C12`, `C14`, `C09`, `C11`, `C08`, `Finalist` |
| `3x` | full shared core | `NGL_sweep`, `C13`, `C15` | `C10`, `C12`, `C14`, `C09`, `C11`, `C08`, `Finalist` |
| `5x` | full shared core | `NGL_sweep`, `C13`, `C15`, `C10`, `C12`, `C14` | `C09`, `C11`; `C08` / `Finalist` only when recommendation flow warrants validation |

### `T/S`

| Tier | Always include | Promote if applicable | Defer unless surplus budget |
|---|---|---|---|
| `1x` | `C05`, `C01`, `C07`, `C06`, `C02` | `NGL_sweep`, `C10`, `C12`, `C09` | `C04`, `C03`, `C13`, `C14`, `C15`, `C11`, `C08`, `Finalist` |
| `3x` | full shared core | `NGL_sweep`, `C10`, `C12`, `C09` | `C13`, `C14`, `C15`, `C11`, `C08`, `Finalist` |
| `5x` | full shared core | `NGL_sweep`, `C10`, `C12`, `C09`, `C13` | `C14`, `C15`, `C11`; `C08` / `Finalist` only when recommendation flow warrants validation |

### `TTFT`

| Tier | Always include | Promote if applicable | Defer unless surplus budget |
|---|---|---|---|
| `1x` | `C04`, `C06`, `C13`, `C15`, `C03` | `NGL_sweep`, `C14` | `C01`, `C05`, `C07`, `C02`, `C10`, `C12`, `C09`, `C11`, `C08`, `Finalist` |
| `3x` | full shared core | `NGL_sweep`, `C13`, `C15`, `C14` | `C10`, `C12`, `C09`, `C11`, `C08`, `Finalist` |
| `5x` | full shared core | `NGL_sweep`, `C13`, `C15`, `C14`, `C10`, `C12` | `C09`, `C11`; `C08` / `Finalist` only when recommendation flow warrants validation |

## What `1x / 3x / 5x` Should Mean in Repo Terms

### `1x`

Meaning:

- quick-like exploratory pass
- planner should prove useful with the smallest safe family set
- recommendation status should remain naturally biased toward provisional language

What expands:

- very little family count
- no derived validation

What does not expand:

- inner values for selected ordinary families

### `3x`

Meaning:

- standard-like development-grade pass
- enough budget to cover the full shared primary family

What expands:

- family count to the full shared core
- repetition depth from `1x` to `3x`

What does not expand:

- derived validation path by default

### `5x`

Meaning:

- full-like strongest normal search tier
- broad family coverage and strongest ordinary measurement base

What expands:

- repetition depth to full
- optional-family reach
- validation eligibility

What this does not mean:

- that every campaign automatically becomes mandatory
- that planner policy may bypass existing validation prerequisites

## Value Scaffold Narrowing: Allowed vs Too Risky

### Allowed in v1

Only one family is safe enough for planner-budget value scaffolding in v1:

- `NGL_sweep` at `1x`

Why:

- it is a 10-value ordinal sweep
- its YAML already encodes ascending-order semantics and OOM-boundary logic
- the cost savings are materially larger than for the 2-5 value families

Required constraints:

- scaffold values must be predeclared from the committed YAML list
- no interpolation
- no guessed interior optimum
- `3x` and `5x` should use full `NGL_sweep` value coverage when selected

### Too risky for v1

Do not value-subset these when they are selected:

- `C01_threads_batch`
- `C02_n_parallel`
- `C03_kv_cache_type`
- `C04_context_size`
- `C05_threads`
- `C06_ubatch`
- `C07_batch`
- `C13_defrag_thold`
- `C15_threads_http`

Reason:

- these are small 2-5 value families where interior optima are plausible and full coverage is cheap enough once the family is selected

## What Must Remain Shared Across Profiles

- the applicability rule catalog
- the shared validity floor and elimination rules
- the meaning of recommendation status and caveats
- the execution path through the existing runner and `RunPlan`
- the requirement that selected small families use full YAML values
- the prerequisite chain for `C08` and `Finalist`
- the fact that profile policy changes acquisition order, not measured truth

This is the minimum shared spine that keeps planner policy from becoming a second hidden methodology.

## Risks of Getting This Wrong

### 1. “Balanced” becomes vague default behavior

If `Balanced` is not explicitly defined, it will collapse into “whatever the planner happened to do first.”

### 2. Profile preference becomes shadow gate behavior

If `T/S` or `TTFT` can erase too much of the shared core, profile policy will effectively redefine the problem rather than prioritize acquisition.

### 3. Repeat tiers lose their repo meaning

If `1x / 3x / 5x` stop mapping cleanly to current execution-depth semantics, the planner will collide with existing run-mode truth and report wording.

### 4. Value scaffolding drifts beyond the safe special case

If ordinary 2-5 value sweeps get scaffolded aggressively, ACPM will start pruning plausible interior winners without enough evidence.

### 5. Planner implementation tries to bypass the runner

If the matrix is interpreted as a second execution system, ACPM will cut across current `RunPlan` and report/export surfaces instead of compiling into them.

## Downstream Implementation Consequences

- ACPM should compile profile/tier decisions into ordinary staged campaign runs, not a second runner
- repeat tier should map onto current cycle-depth semantics first
- planner metadata should record:
  - profile ID
  - planner policy ID/version
  - repeat tier
  - family inclusion/defer reason codes
  - whether `NGL_sweep` used scaffold coverage at `1x`
- any scoped family run must remain compatible with the current `RunPlan` plus `scope_authority` direction rather than reusing user-directed `custom` semantics silently

## Questions Answered in This Pass

### 1. Which applicable campaign families should be core vs optional for each profile?

Use a shared base core across all profiles, then let profiles promote different optional families and conditional special families earlier.

### 2. Which families should be earlier vs later for each profile?

- `Balanced`: mixed TG/TTFT practical families first
- `T/S`: throughput and throughput-supporting runtime families first
- `TTFT`: latency and tail-latency families first

### 3. What should `1x / 3x / 5x` mean in repo terms?

They should mean execution-depth strength first, with family-count expansion layered on top:

- `1x` quick-like
- `3x` standard-like
- `5x` full-like

### 4. Do repeat tiers expand family count, repetition depth, value coverage, or some combination?

A combination, but in a strict order:

- repetition depth first
- family count second
- value coverage only in the narrow `NGL_sweep` `1x` special case

### 5. Where is value scaffold narrowing allowed later as planner-budget policy?

Only for `NGL_sweep` at `1x` in v1.

### 6. What must remain shared across profiles?

Applicability truth, gates, scoring authority boundaries, execution path, and the full shared primary core by `3x` and `5x`.

## Remaining Open Questions

- What exact predeclared `NGL_sweep` scaffold should `1x` use if that family is selected?
- Should `C08_interaction` ever become eligible at `3x`, or should v1 keep all derived validation behind `5x` only?
- Does `T/S` need one more bounded pass on whether `NGL_sweep` is promoted before or after `C02_n_parallel` for GPU-backed large-model runs?

## Recommended Next Investigations

- `ACPM-NGL-scaffold-subset-policy-TARGET-INVESTIGATION.md`
- `ACPM-derived-validation-entry-policy-TARGET-INVESTIGATION.md`
- `ACPM-shared-core-family-catalog-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`
- `.agent/policies/architecture.md`
