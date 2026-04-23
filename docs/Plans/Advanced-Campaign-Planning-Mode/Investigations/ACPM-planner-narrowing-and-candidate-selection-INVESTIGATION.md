# ACPM Planner Narrowing and Candidate Selection Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 planner narrowing and candidate-selection policy only

## Outcome

Recommended v1 planner model:

- use a staged, rule-based narrowing model
- start from the repo’s committed campaign catalog, not from open-ended heuristic search
- narrow in four steps:
  1. candidate-universe assembly
  2. machine/model applicability pruning
  3. profile-specific prioritization
  4. repeat-tier expansion and execution compilation
- keep pruning conservative:
  - prune campaign families aggressively only when they are structurally irrelevant, fixture-like, or lower-priority extended sweeps
  - prune values only through predeclared YAML-enumerated scaffold subsets, never through inferred interpolation or guessed optima
  - never let planner policy relax validity floors or replace methodology truth

Best v1 shape:

- core family bundles selected by rule
- profile-specific ordering and emphasis
- repeat-tier-specific scope expansion
- generated/scoped campaign definitions compiled into existing execution through `RunPlan`

In concrete repo-fit terms, ACPM v1 should behave like:

- a planner that chooses which existing campaign families matter for this machine/model/profile/tier
- a planner that may create bounded scoped variants of those campaigns using existing YAML value lists
- not a planner that invents novel numeric values, predicts winners from sparse heuristics, or silently rewrites QuantMap’s scientific floor

This is the best fit because the current repo is still campaign-file first, single-variable purity is a core assumption, `build_config_list()` materializes exact YAML values deterministically, and the only existing planning-like precedent (`generate_c08()` / `generate_finalist()`) already works by materializing explicit generated campaign definitions rather than by teaching the runner a second execution universe.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/run_plan.py`
- `src/runner.py`
- `src/score.py`
- `src/report.py`
- `src/run_context.py`
- `src/characterization.py`
- `src/telemetry.py`
- `src/telemetry_policy.py`
- `src/execution_environment.py`
- `src/trust_identity.py`
- `src/artifact_paths.py`
- `src/governance.py`

Campaign/config surfaces inspected:

- `configs/baseline.yaml`
- `configs/profiles/default_throughput_v1.yaml`
- `configs/campaigns/C01_threads_batch.yaml`
- `configs/campaigns/C02_n_parallel.yaml`
- `configs/campaigns/C03_kv_cache_type.yaml`
- `configs/campaigns/C04_context_size.yaml`
- `configs/campaigns/C05_threads.yaml`
- `configs/campaigns/C06_ubatch.yaml`
- `configs/campaigns/C07_batch.yaml`
- `configs/campaigns/C08_interaction.yaml`
- `configs/campaigns/C09_tensor_placement.yaml`
- `configs/campaigns/C10_mmap.yaml`
- `configs/campaigns/C11_cpu_affinity.yaml`
- `configs/campaigns/C12_mlock.yaml`
- `configs/campaigns/C13_defrag_thold.yaml`
- `configs/campaigns/C14_cont_batching.yaml`
- `configs/campaigns/C15_threads_http.yaml`
- `configs/campaigns/Finalist.yaml`
- `configs/campaigns/NGL_sweep.yaml`
- fixture-like campaign files `A_fatal.yaml`, `B_low_sample.yaml`, `C_all_fail.yaml`, `D_one_passes.yaml`

Supporting ACPM investigations inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-blast-radius-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-refactor-seams-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-plan-contract-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planning-metadata-schema-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-to-governance-mapping-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-weight-and-gate-spec-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-weight-values-TARGET-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/policies/boundaries.md`

Validation used:

- targeted source inspection only
- no product-code changes
- no broad validation theater; this pass is planner-shape and pruning-risk mapping

## Current Candidate-Generation / Campaign-Materialization Constraints

### 1. QuantMap is still campaign-file first

Current execution starts from:

- `configs/baseline.yaml`
- `configs/campaigns/<campaign_id>.yaml`

`runner.run_campaign()` loads a campaign YAML, validates purity, calls `build_config_list()`, resolves `RunPlan`, and then executes.

Implication:

- ACPM cannot assume an existing general in-memory campaign object seam
- the safest v1 planner output is generated/scoped campaign definitions plus the usual execution contract, not a second runner API

### 2. `build_config_list()` materializes exact YAML values deterministically

`runner.build_config_list()`:

- iterates the campaign’s `values`
- merges each value into the baseline config
- handles a few campaign-specific cases:
  - interaction values
  - CPU affinity
  - mirrored KV cache types

Implication:

- current repo semantics strongly favor planning over explicit enumerated candidate values
- ACPM value narrowing should therefore choose from existing YAML values, not synthesize new intermediate numeric guesses in v1

### 3. Single-variable purity is still a load-bearing assumption

The repo validates that ordinary campaigns are single-variable sweeps against baseline, with only special-case campaign types for:

- interaction (`C08_interaction`)
- validation (`Finalist`)

Implication:

- v1 planner should think in campaign families and staged explicit sweeps, not in unconstrained multivariate search

### 4. The existing planning precedents are staged and explicit

Current planning-like behavior already exists in two narrow forms:

- `score.generate_c08()`:
  - combines upstream score winners into an interaction campaign YAML
- `score.generate_finalist()`:
  - materializes a validation campaign YAML from the interaction winner
- `NGL_sweep.yaml` plus `report._ngl_sweep_section()`:
  - supports a context-aware recommendation inside a special sweep

Implication:

- the repo already accepts staged planning and generated campaign materialization
- but it does so through explicit generated artifacts, not hidden heuristic mutation inside the runner

### 5. Current campaign catalog already falls into meaningful families

Repo-grounded family split:

- core primary sweeps:
  - `C01` through `C07`
- special hardware curve sweep:
  - `NGL_sweep`
- extended sweeps:
  - `C09` through `C15`
- derived validation:
  - `C08_interaction`
  - `Finalist`
- fixture / harness-like campaigns:
  - `A_fatal`
  - `B_low_sample`
  - `C_all_fail`
  - `D_one_passes`

Implication:

- ACPM v1 does not need to invent families from scratch
- it does need an explicit planner-owned family catalog over the existing campaign set

### 6. Planner-relevant machine/model facts already exist, but are scattered

Current repo-native inputs already available before or at run start include:

- baseline machine facts:
  - CPU, GPU, RAM, OS, model path root
- baseline model facts:
  - architecture
  - active/total params
  - quantization
  - model size
  - context limits
  - architecture parameters for context estimation
- live execution environment:
  - support tier
  - measurement-grade flag
  - degraded reasons
- provider readiness:
  - ready / warnings / degraded / blocked
- characterization capability availability:
  - CPU/GPU/RAM/model-size probes

Implication:

- v1 has enough inputs for coarse planning
- there is still no dedicated planner-input bundle seam yet

### 7. Current run-time scope narrowing is intentionally simple

Today, narrowing happens only through:

- `--values` filtering
- `--mode quick`
- `--mode standard`

Those are execution-scope semantics, not recommendation planning.

Implication:

- ACPM narrowing should not overload existing `run_mode` meaning
- it should compile down into ordinary execution shape after planning is done

## Candidate Narrowing Models Considered

### 1. Free-form heuristic planner over raw machine/model facts

Meaning:

- planner directly predicts promising numeric values or multivariate combinations from machine/model characteristics

Assessment:

- reject for v1

Why:

- too speculative under current repo evidence
- no prior-run history in v1
- current architecture is not built around latent heuristic score prediction

### 2. Fixed candidate bundle per profile only

Meaning:

- `Balanced`, `T/S`, and `TTFT` each always run a fixed hard-coded set of campaigns/values

Assessment:

- too rigid

Why:

- ignores machine/model relevance
- does not use available platform/model facts
- likely to carry wrong assumptions across machines

### 3. Family selection only, no staged value narrowing

Meaning:

- planner chooses campaign families, but every selected campaign always runs all YAML values immediately

Assessment:

- viable, but not the best v1 fit

Why:

- safe, but leaves too much usefulness on the table for `1x`
- does not exploit the existing difference between provisional and validated exploration depth

### 4. Staged rule-based family selection plus bounded value scaffolds

Meaning:

- build a conservative candidate universe
- prune only through explicit rules
- use scaffold subsets for larger ordinal sweeps at lower repeat tiers
- expand to fuller coverage as repeat strength rises

Assessment:

- best v1 fit

Why:

- aligns with current explicit campaign/value model
- gives ACPM real narrowing power without turning it into speculative search
- preserves scientific honesty by keeping value choice explicit and auditable

### 5. History-driven adaptive narrowing

Meaning:

- use previous campaign results to skip directly to likely winners

Assessment:

- out of scope for v1

Why:

- no prior-run history in v1
- would require a different persistence and trust story

## Recommended v1 Planner Narrowing Model

### Recommendation

Use a staged, rule-based planner with explicit campaign-family cataloging and conservative value scaffolds.

Recommended stages:

1. Assemble the candidate universe from the current committed campaign catalog.
2. Remove fixture and structurally irrelevant campaigns.
3. Apply machine/model applicability rules.
4. Apply profile-specific prioritization.
5. Apply repeat-tier-specific expansion rules.
6. Compile selected stages into ordinary QuantMap campaign executions and `RunPlan`s.

### Stage 1: Candidate-universe assembly

Start from a planner-owned catalog built over the current campaign files:

- core primary family:
  - `C01_threads_batch`
  - `C02_n_parallel`
  - `C03_kv_cache_type`
  - `C04_context_size`
  - `C05_threads`
  - `C06_ubatch`
  - `C07_batch`
- special hardware-curve family:
  - `NGL_sweep`
- extended runtime/platform family:
  - `C09_tensor_placement`
  - `C10_mmap`
  - `C11_cpu_affinity`
  - `C12_mlock`
  - `C13_defrag_thold`
  - `C14_cont_batching`
  - `C15_threads_http`
- derived validation family:
  - `C08_interaction`
  - `Finalist`

Exclude from the v1 ACPM universe:

- `A_fatal`
- `B_low_sample`
- `C_all_fail`
- `D_one_passes`

Reasoning:

- these look harness-oriented and intentionally pathological, not normal ACPM tuning targets
- they should remain test/diagnostic surfaces, not planner candidates

This is an inference from current repo content and naming, not an explicit code contract today.

### Stage 2: Machine/model applicability pruning

Use only coarse, repo-native, low-speculation inputs:

- baseline machine facts
- baseline model facts
- execution environment support tier
- provider readiness
- characterization capability availability

Recommended v1 input bundle:

- machine:
  - CPU core topology counts if available
  - RAM total
  - GPU identity / compute / VRAM if available
  - OS/platform
- model:
  - architecture (`MoE` vs dense)
  - quantization
  - total/active params
  - model size
  - context operating / trained values
  - architecture parameters used by NGL/context estimation
- execution support:
  - support tier
  - measurement-grade flag
  - degraded reasons
- planner:
  - selected ACPM profile
  - selected repeat tier

Recommended applicability rules:

- keep `C01` through `C07` broadly eligible as the main portable core family
- treat `NGL_sweep` as eligible when GPU offload is a real decision surface for the current model/hardware
- treat `C09_tensor_placement` as eligible only when the model/hardware/runtime assumptions make `override_tensor` meaningfully variable
  - current repo evidence suggests this is especially tied to the `exps=CPU` MoE operating assumption
- treat `C11_cpu_affinity` as machine-class-specific
  - current YAML is explicitly Alder Lake / Windows shaped
  - planner should not blindly reuse it across unrelated CPU topologies without a machine-aware rule
- treat `C13_defrag_thold` and `C15_threads_http` as optional latency-sensitive extensions, not universal first-pass sweeps

### Stage 3: Profile-specific prioritization

Profiles should change:

- which campaign families are prioritized first
- which optional families are worth including at lower repeat tiers
- how quickly ACPM escalates from scaffold subset to fuller coverage

Profiles should not change:

- what counts as valid evidence
- what campaigns are physically possible
- what the final methodology means

Recommended profile behavior:

#### `Balanced`

- prioritize a mixed core bundle first
- start with:
  - `C01_threads_batch`
  - `C04_context_size`
  - `C05_threads`
  - `C06_ubatch`
  - `C07_batch`
- include `C02_n_parallel` and `C03_kv_cache_type` in the core path, but slightly later
- treat extended runtime/platform campaigns as secondary unless machine/model facts strongly suggest relevance

#### `T/S`

- prioritize throughput-shaping families first
- preferred early order:
  - `C05_threads`
  - `C01_threads_batch`
  - `C07_batch`
  - `C06_ubatch`
  - `C02_n_parallel`
- include `C09_tensor_placement`, `C10_mmap`, and `C12_mlock` earlier when the model is large, MoE-like, RAM-heavy, or obviously memory-pressure sensitive
- keep latency-sensitive families visible, but defer `C13_defrag_thold` and `C15_threads_http` unless there is room in the tier budget

#### `TTFT`

- prioritize latency-shaping families first
- preferred early order:
  - `C04_context_size`
  - `C06_ubatch`
  - `C15_threads_http`
  - `C13_defrag_thold`
  - `C03_kv_cache_type`
- include `NGL_sweep` earlier when context-capacity tradeoffs matter for the selected workload framing
- keep throughput-oriented families present, but de-prioritize `C07_batch` and `C09_tensor_placement` relative to the other profiles unless machine/model facts make them obviously important

### Stage 4: Repeat-tier-specific expansion

Repeat tier should control both:

- execution depth
- how much of the candidate universe must be expanded beyond scaffolds

Recommended v1 interpretation:

- `1x`:
  - exploratory / provisional
  - narrow campaign family set
  - allow scaffold subsets for larger ordinal sweeps
- `3x`:
  - development-grade intermediate pass
  - full values for selected core campaigns
  - extended families only when structurally relevant
- `5x`:
  - validation-grade planning budget
  - broadest selected family coverage
  - minimal value pruning within selected campaigns
  - eligible to include derived validation stages

### Stage 5: Execution compilation

After narrowing, ACPM should compile its decision into:

- explicit selected campaign/value scope
- explicit execution schedule strength
- explicit execution identity via normal `RunPlan` semantics

Planner identity, reason codes, and narrowing provenance should remain beside `RunPlan`, not inside it.

## What ACPM May Prune vs Must Not Prune in v1

### ACPM may prune in v1

#### Entire campaigns

Allowed only when one of these is true:

- the campaign is a fixture / harness surface, not a product tuning surface
- the campaign is an extended family that is structurally irrelevant to the current machine/model assumptions
- the repeat tier is intentionally too small to include all optional families

Recommended safe examples:

- exclude fixture campaigns entirely
- exclude `C11_cpu_affinity` on machines where the current CPU-affinity assumptions clearly do not transfer
- defer `C09_tensor_placement` unless the MoE/tensor-placement assumption is in play

#### Values within campaigns

Allowed only under conservative rules:

- choose only from the campaign’s committed YAML value list
- no invented values
- no interpolation
- no "predicted optimum" math

Recommended v1 subsetting rules:

- binary campaigns:
  - test all values even at `1x`
- small categorical or tri-state campaigns:
  - usually test all values
- 4-5 value ordinal sweeps:
  - `1x` may use a scaffold subset that preserves:
    - baseline anchor if present
    - low edge
    - high edge
  - `3x` and `5x` should generally use full YAML coverage once the campaign is selected
- larger ordinal sweeps such as `NGL_sweep`:
  - `1x` may use a sparse scaffold plus sentinel/high-boundary structure
  - `3x` may use a wider scaffold or bounded expansion around the best provisional region
  - `5x` should move toward full selected-family coverage

#### Repeat depth

Yes.

This is one of the safest planner-controlled pruning levers because it is already aligned with current execution-depth semantics.

### ACPM must not prune or infer in v1

#### Global validity and gate semantics

Must not change or simulate:

- elimination thresholds
- validity floors
- confidence honesty rules
- methodology meaning

#### Novel numeric values

Must not:

- invent new sweep values not already present in campaign definitions
- interpolate between YAML values
- estimate interior optima and skip directly there

#### Cross-variable winner inference before measurement

Must not:

- guess the final multivariate best config from machine/model facts alone
- skip directly to interaction-style combined configs without upstream measured winners

#### History-based winner prediction

Must not:

- use prior-run history in v1
- assume transferability from other machines or models

#### Transient environment noise as a planner fact

Must not let short-lived current load, thermal noise, or background process fluctuations drive candidate pruning.

Those are execution-quality and confidence inputs, not durable narrowing facts.

#### Profile-driven campaign erasure of core tradeoff space

Must not let profile choice imply:

- "throughput profile means skip latency-relevant campaigns entirely"
- "TTFT profile means throughput-relevant campaigns do not matter"

That would turn profile identity into hidden methodology drift.

## Profile-Specific Planner Behavior

### Shared rule

All three profiles should share:

- one candidate-universe model
- one validity floor
- one methodology shape

The planner differences should be:

- ordering
- optional-family inclusion priority
- how quickly value scaffolds expand

### `Balanced`

Recommended policy:

- use the broadest mixed early bundle
- avoid extreme family bias
- prefer campaigns that jointly expose throughput and latency tradeoffs

Expected behavior:

- more symmetric family coverage
- fewer optional-family prunes at `3x` than `T/S` or `TTFT`

### `T/S`

Recommended policy:

- bias early budget toward throughput, throughput-floor, and prompt-throughput shaping families
- include memory-placement/runtime families earlier when model size and hardware pressure suggest they could matter materially

Expected behavior:

- faster convergence on practical high-throughput candidates
- greater risk of missing latency-optimal families if over-pruned, so keep some latency-sensitive coverage in the core bundle

### `TTFT`

Recommended policy:

- bias early budget toward responsiveness, context cost, and tail-latency-sensitive families
- include families that plausibly change perceived first-token behavior earlier

Expected behavior:

- better early coverage of responsiveness levers
- must still keep throughput viability visible so the profile does not become one-dimensional

## Repeat-Tier-Specific Planner Behavior

### `1x`

Recommended planner behavior:

- narrowest safe family set
- allow scaffold subsetting on larger ordinal sweeps
- prefer discovery over validation
- do not include derived validation stages by default

Recommended product reading:

- useful first look
- strong provisional narrowing only

### `3x`

Recommended planner behavior:

- full values for selected core campaigns
- reduced pruning of medium-size sweeps
- optional extended families only when structurally justified
- derived validation only when the core path is sufficiently complete

Recommended product reading:

- development-grade candidate selection

### `5x`

Recommended planner behavior:

- broadest selected-family coverage
- minimal value pruning inside selected campaigns
- eligible to include:
  - `C08_interaction`
  - `Finalist`
- best fit for cases where ACPM is expected to produce the strongest recommendation claims

Recommended product reading:

- validation-focused narrowing with the smallest acceptable risk of accidental over-pruning

## What Narrowing Rationale Should Be Persisted

Persist only compact, audit-useful rationale that `RunPlan` itself cannot already show.

Recommended v1 persisted rationale:

- `narrowing.applied`
- compact `reason_codes`
- optionally:
  - `campaign_ids_considered`
  - `variable_families_considered`

Recommended v1 reason-code families:

- `fixture_campaigns_excluded`
- `core_family_only`
- `extended_family_deferred`
- `machine_class_pruning`
- `model_class_pruning`
- `profile_priority_throughput_first`
- `profile_priority_latency_first`
- `repeat_tier_limits_scope`
- `numeric_scaffold_subset`
- `binary_full_retained`
- `derived_validation_deferred`
- `derived_validation_enabled`

Recommended persistence rule:

- persist why ACPM narrowed
- do not persist duplicated copies of `selected_values` or `selected_configs`, because `RunPlan` already owns execution truth

## Risks of Getting This Wrong

### 1. Interior-optimum loss from over-aggressive value pruning

This is the biggest v1 pruning risk.

If ACPM chooses too sparse a subset for 4-5 value sweeps:

- the actual best config may be an interior value
- the planner may report a plausible but wrong provisional leader

Mitigation:

- use only conservative scaffold subsets
- expand to full values at `3x`/`5x`
- keep caveat/report semantics honest when scaffold pruning occurred

### 2. Reusing machine-specific campaigns on the wrong hardware

Examples:

- `C11_cpu_affinity` currently encodes Alder Lake-specific assumptions
- `C09_tensor_placement` is strongly tied to the repo’s current `exps=CPU` MoE operating assumption

If ACPM treats those as universal:

- planner behavior becomes architecture-hostile
- recommendations become less transferable and harder to trust

### 3. Treating profile as permission to erase tradeoff space

If `T/S` or `TTFT` prunes away too many families:

- profiles stop being honest lenses over one shared validity floor
- they start acting like hidden problem redefinitions

### 4. Letting transient environment state drive narrowing

If ACPM narrows because the machine is noisy right now:

- planning becomes nondeterministic
- execution-quality concerns leak into planner truth

### 5. Planner becoming a second hidden methodology

If family/value pruning becomes too opaque:

- recommendations may still look methodologically grounded
- but real outcome variance will come from hidden planner heuristics

That would violate current repo trust philosophy.

## Downstream Refactor / Prep Implications

### 1. ACPM needs a planner-owned campaign family catalog

This should live under the future `src/acpm/` boundary, not in `runner.py` or report modules.

### 2. Config/candidate materialization needs a cleaner seam

`build_config_list()` is still the right reuse target, but the planner will need a way to materialize:

- full campaign definitions
- scoped value subsets
- stage-specific effective campaign IDs

without teaching `runner.py` ACPM policy directly.

### 3. Planner-input assembly needs a small dedicated bundle

The repo already has the facts, but not one clean planner input object.

v1 prep should likely gather:

- baseline machine/model/runtime identity
- execution-environment classification
- provider readiness state
- optional coarse characterization capabilities

into one planner-facing bundle.

### 4. Generated campaign handling should follow existing explicit patterns

The safest v1 shape is:

- planner creates explicit staged/scoped campaign definitions
- runner validates and executes them normally

rather than:

- runner learning ACPM-specific narrowing logic internally

## Questions Answered in This Pass

### 1. What planner inputs should ACPM use in v1?

Use only coarse, repo-native stable inputs:

- baseline machine facts
- baseline model facts
- execution support tier
- provider readiness
- characterization capability availability
- selected profile
- selected repeat tier
- current campaign catalog and YAML value lists

### 2. What should ACPM be allowed to prune in v1?

A bounded combination:

- fixture campaigns
- structurally irrelevant extended campaigns
- lower-priority families under smaller repeat tiers
- YAML-enumerated value subsets through conservative scaffolds
- repeat depth

### 3. What should ACPM definitely not prune or infer in v1?

- validity floors and gates
- novel numeric values
- unmeasured interaction winners
- history-driven predictions
- transient environment-load-driven candidate elimination

### 4. What is the best v1 narrowing model?

A staged rule-based hybrid:

- family catalog
- applicability pruning
- profile ordering
- repeat-tier expansion
- explicit execution compilation

### 5. One pass or staged?

Staged.

The repo already naturally supports staged explicit planning better than one-pass global inference.

### 6. What existing repo structures can ACPM reuse?

Best reuse candidates:

- campaign YAML catalog
- `build_config_list()`
- `RunPlan`
- generated campaign precedent from `generate_c08()` / `generate_finalist()`
- execution-environment classification
- provider readiness
- trust-identity reconstruction

### 7. How should ACPM balance usefulness against over-pruning?

By:

- pruning families mainly through explicit applicability rules
- pruning values only through conservative scaffolds
- expanding coverage as repeat tier rises

### 8. What narrowing rationale should be recorded?

Compact reason codes and considered-family summaries above what `RunPlan` already shows.

### 9. What planner decisions should stay internal?

- transient heuristic scores
- intermediate shortlist rankings
- raw characterization dumps
- low-level tie-break mechanics

### 10. How should the planner differ across profiles?

- by ordering, optional-family inclusion, and expansion emphasis
- not by validity floors

### 11. How should the planner differ across repeat tiers?

- `1x`: narrowest safe exploratory scope
- `3x`: fuller core-campaign coverage
- `5x`: broad selected-family coverage plus derived validation eligibility

### 12. What is the recommended v1 planner narrowing and candidate-selection model, and why?

Use a staged, rule-based campaign-family planner with conservative YAML-based value scaffolds.

Why:

- it gives ACPM real narrowing power while staying compatible with the repo’s file-first execution model and scientific honesty requirements.

## Remaining Open Questions

### 1. Exact campaign-family catalog for non-DEEP-THOUGHT machine classes

This pass can identify the safe model shape, but not every exact family rule for future machines.

### 2. Exact scaffold subsets for each ordinal sweep

This should be settled in a smaller follow-up rather than hidden inside first implementation.

### 3. Whether `NGL_sweep` belongs in the universal core family or a hardware-conditional special family

Current repo evidence points to "special but important," but the exact rule should be made explicit before implementation.

### 4. How much of the current extended family should become universally portable vs explicitly machine-specific

This especially affects:

- `C09_tensor_placement`
- `C11_cpu_affinity`
- `C12_mlock`

## Recommended Next Investigations

- `ACPM-campaign-family-catalog-TARGET-INVESTIGATION.md`
- `ACPM-value-scaffold-subset-policy-TARGET-INVESTIGATION.md`
- `ACPM-machine-and-model-classification-inputs-TARGET-INVESTIGATION.md`
- `ACPM-derived-validation-stage-policy-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/README.md`
- `.agent/policies/architecture.md`
- `.agent/policies/boundaries.md`
