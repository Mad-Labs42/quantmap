# ACPM Applicability and Pruning Rule Catalog Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM v1 applicability/pruning rule catalog only

## Outcome

Recommended v1 policy:

- treat applicability pruning as a narrow truth-contract layer, not a general optimization layer
- allow ACPM to exclude only:
  - fixture / harness campaigns that are not product tuning surfaces
  - derived campaigns whose prerequisites do not yet exist
  - campaign families whose own YAML semantics clearly depend on machine/model assumptions that are not true on the current machine/model
- do not let v1 applicability pruning remove ordinary YAML values within an applicable campaign
- do not let ACPM use profile preference, live noise, or speculative interior-optimum guesses as applicability grounds

Recommended v1 rule shape:

- `applicable`
  - the campaign is a real ACPM candidate on this machine/model
- `not_applicable`
  - the campaign is outside the ACPM universe for explicit structural reasons
- `applicable_but_optional`
  - the campaign is structurally real, but whether it is included is a later budget / preference decision, not an applicability truth decision

Best v1 reading of the current repo:

- applicability pruning should happen mostly at the campaign-family level
- value-level pruning is not yet truth-safe enough to put inside the applicability layer
- if later ACPM work wants scaffold subsets, that must live in a separate planner-budget policy and be labeled as narrowing, not applicability

Strongest repo-grounded reason:

- the current engine is file-first and campaign values are explicit YAML truth. The repo has very few durable, explicit machine/model contracts that justify pruning inner value lists before execution. Most of the current evidence supports conservative family gating, not speculative value exclusion.

## Scope / What Was Inspected

Primary code surfaces inspected:

- `src/runner.py`
- `src/run_plan.py`
- `src/score.py`
- `src/report.py`
- `src/characterization.py`
- `src/telemetry.py`
- `src/trust_identity.py`

Config surfaces inspected:

- `configs/baseline.yaml`
- `configs/campaigns/*.yaml`
- selected campaign YAMLs:
  - `C01_threads_batch.yaml`
  - `C02_n_parallel.yaml`
  - `C03_kv_cache_type.yaml`
  - `C04_context_size.yaml`
  - `C05_threads.yaml`
  - `C06_ubatch.yaml`
  - `C07_batch.yaml`
  - `C08_interaction.yaml`
  - `C09_tensor_placement.yaml`
  - `C10_mmap.yaml`
  - `C11_cpu_affinity.yaml`
  - `C12_mlock.yaml`
  - `C13_defrag_thold.yaml`
  - `C14_cont_batching.yaml`
  - `C15_threads_http.yaml`
  - `Finalist.yaml`
  - `NGL_sweep.yaml`

Supporting ACPM investigations inspected:

- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-planner-narrowing-and-candidate-selection-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-profile-to-governance-mapping-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-plan-contract-TARGET-INVESTIGATION.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-blast-radius-INVESTIGATION.md`

Repo-governance surfaces inspected:

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`

Validation used:

- targeted source/doc inspection
- one light proportional verification pass that parsed the live `configs/campaigns/*.yaml` files into a compact campaign/type/variable/value-count table
- no product-code edits

## Current Campaign / Value / Characterization Constraints

### 1. The campaign universe is still explicit YAML, not an inferred search space

`runner.load_campaign()` reads `configs/campaigns/<id>.yaml` directly.  
`runner.build_config_list()` then materializes configs directly from the committed `values:` list.

Implication:

- campaign IDs and value lists are current repo truth
- ACPM does not have a safe basis in v1 for inventing new values or interpolating missing ones

### 2. `RunPlan` captures selected values after scope is already chosen

`RunPlan` records:

- `all_campaign_values`
- `selected_values`
- `selected_configs`
- `untested_values`
- `coverage_fraction`

Implication:

- ACPM can truthfully narrow scope, but only after deciding it explicitly
- the applicability layer should stay very conservative because any missing values become auditable omissions

### 3. The live campaign catalog is structured but uneven

The current campaign set contains:

- primary sweeps:
  - `C01` through `C07`
- a specialized GPU-curve sweep:
  - `NGL_sweep`
- extended/runtime-sensitive sweeps:
  - `C09` through `C15`
- derived campaigns:
  - `C08_interaction`
  - `Finalist`
- obvious harness/fixture surfaces:
  - `A_fatal`
  - `B_low_sample`
  - `C_all_fail`
  - `D_one_passes`

The verification pass also confirmed:

- `C08_interaction` and `Finalist` are `auto_generated: true`
- `NGL_sweep` exposes a 10-value ordinal list
- most primary and extended sweeps expose only 2-5 committed values

Implication:

- fixture exclusion is repo-grounded
- derived-campaign gating is repo-grounded
- aggressive inner-list pruning is not repo-grounded

### 4. Characterization is richer for machine facts than for model semantics

`characterize_environment()` captures:

- CPU brand/architecture/core counts
- RAM and swap
- GPU name/VRAM/utilization/power/clocks
- OS/system/runtime facts
- model path and model file size

But live characterization does not capture rich model semantics such as:

- MoE vs dense
- quantization family
- active params
- context operating/trained

Those richer model facts currently live in `baseline.yaml` and campaign/baseline snapshots, not in `src/characterization.py`.

Implication:

- machine applicability rules can rely on live characterization facts
- model applicability rules should rely primarily on baseline/snapshot model metadata

### 5. Existing “planning-like” precedents are narrow and explicit

Current repo precedents are:

- `score.generate_c08()` and `generate_finalist()` derive later campaigns from measured winners
- `report._ngl_sweep_section()` can make a targeted context recommendation from explicit model fields and measured VRAM data

Implication:

- the repo already accepts explicit, bounded, evidence-based narrowing
- it does not support speculative pre-execution winner prediction

## Candidate Rule Models Considered

### 1. Broad heuristic pruning

Meaning:

- use machine/model intuition to skip many families and values before execution

Assessment:

- reject

Why:

- highest hidden-heuristic risk
- would let profile preference masquerade as applicability
- not supported by the current explicit YAML/value model

### 2. No applicability pruning at all

Meaning:

- everything committed is always in scope; ACPM only changes order

Assessment:

- too weak

Why:

- the repo clearly contains fixture campaigns and topology-specific campaigns
- derived campaigns clearly depend on prerequisites
- refusing all applicability logic would ignore explicit repo structure

### 3. Conservative campaign-family applicability plus no value pruning

Meaning:

- use only explicit machine/model grounds to gate whole campaign families
- keep inner value lists intact for any campaign deemed applicable

Assessment:

- best v1 fit

Why:

- matches the current explicit campaign catalog
- avoids false-pruning interiors
- keeps applicability separate from later budget and preference logic

### 4. Applicability plus scaffold value pruning

Meaning:

- use applicability and budget together to pre-prune larger value lists

Assessment:

- not for this rule-catalog layer

Why:

- may still be useful later as planner-budget policy
- but that is a separate narrowing policy, not applicability truth

## Recommended v1 Applicability / Pruning Rule Catalog

### Core policy

Use this ordering:

1. Determine whether a campaign is in the ACPM universe at all.
2. Apply explicit machine/model applicability rules to campaign families.
3. Keep all committed YAML values for any campaign that survives applicability.
4. Let later planner-budget policy decide ordering or optional-family deferral.
5. Let scoring and recommendation status decide post-execution claims.

### Campaign-family catalog

#### 1. Exclude from the ACPM universe in v1

These are not product-tuning candidates:

- `A_fatal`
- `B_low_sample`
- `C_all_fail`
- `D_one_passes`

Reason:

- naming, shape, and value counts mark them as pathological or harness-oriented surfaces rather than ordinary tuning campaigns

#### 2. Always structurally applicable core campaigns

Treat these as the default ACPM tuning core:

- `C01_threads_batch`
- `C02_n_parallel`
- `C03_kv_cache_type`
- `C04_context_size`
- `C05_threads`
- `C06_ubatch`
- `C07_batch`

Reason:

- they are committed primary sweeps over baseline config fields
- their own YAMLs present them as ordinary tuning surfaces rather than machine-specific exceptions
- profile preference may reorder them later, but should not erase them as “not applicable”

#### 3. Conditionally applicable specialized campaign

`NGL_sweep`

Treat as applicable only when all of the following are true:

- GPU offload is a real execution surface for the current runtime/model
- `n_gpu_layers` is a live config field in the current baseline
- ACPM has explicit GPU/offload facts rather than guessing from profile alone

Treat as not applicable when:

- execution is effectively CPU-only
- GPU offload is unavailable or not part of the real configuration surface

Important v1 boundary:

- do not prune individual NGL values on VRAM guesswork
- the campaign already has explicit ascending values and runtime OOM-boundary behavior

#### 4. Conditionally applicable MoE-placement campaign

`C09_tensor_placement`

Treat as applicable only when all of the following are true:

- the model semantics actually match the `exps=CPU`-style expert-placement assumption
- the baseline config includes `override_tensor` as a meaningful operating lever
- the current model/runtime still makes expert routing a real decision surface

Treat as not applicable when:

- the model is not MoE-like in the way the campaign assumes
- the `exps=CPU` operating assumption is absent
- tensor-placement strings would no longer describe the real architecture

Reason:

- the YAML rationale is explicitly tied to the current expert-placement assumption

#### 5. Conditionally applicable topology-specific campaign

`C11_cpu_affinity`

Treat as applicable only when all of the following are true:

- the OS/process-affinity semantics match the campaign’s implementation assumptions
- the machine topology matches an explicit affinity mapping that ACPM can name and defend
- the campaign’s `cpu_affinity_details` are meaningful on the current machine

Treat as not applicable when:

- ACPM cannot map the current CPU topology to the campaign’s hard-coded affinity policy
- the current machine is not meaningfully comparable to the Alder Lake style mapping encoded in the YAML

Reason:

- this YAML is explicitly machine-topology-specific, not a general optimization law

#### 6. Structurally applicable but optional extended campaigns

Treat these as real campaigns whose inclusion is a later budget/preference decision, not applicability truth:

- `C10_mmap`
- `C12_mlock`
- `C13_defrag_thold`
- `C14_cont_batching`
- `C15_threads_http`

Reason:

- each is a committed runtime/config surface with explicit YAML values
- current repo evidence does not provide a clean, general, machine/model impossibility rule that would justify hard exclusion in v1
- profile preference may defer them, but should not label them “not applicable” by default

#### 7. Derived campaigns with prerequisite gating

- `C08_interaction`
- `Finalist`

Treat as not applicable until their prerequisites exist.

Rules:

- `C08_interaction` is not applicable until its upstream winner set exists
- `Finalist` is not applicable until `C08_interaction` has produced a winner

Reason:

- this is explicit in the current YAMLs and `score.py` generators

## What Machine Facts Are Allowed to Drive Pruning

Allowed machine facts in v1:

- OS/platform class, but only when the campaign’s own semantics are OS-sensitive
- CPU topology facts, but only when the campaign itself encodes topology-specific policy
- presence or absence of a usable GPU/offload surface
- GPU VRAM presence/class, but only to establish whether GPU-offload campaigns are meaningful at all
- explicit characterization-capability availability, but only as a guard on whether ACPM may trust a fact class

Important limitation:

- if a required fact is missing, ACPM should become more conservative
- missing fact availability is not permission for more speculative pruning

## What Model Facts Are Allowed to Drive Pruning

Allowed model facts in v1:

- architecture class where the campaign semantics explicitly depend on it
- whether the current baseline config exposes the variable as a real surface
- explicit baseline model metadata already recorded in `baseline.yaml` or snapshots

Examples of allowed use:

- MoE-style architecture plus `override_tensor: exps=CPU` can justify `C09` applicability
- lack of a real GPU/offload surface can justify excluding `NGL_sweep`

Important limitation:

- live characterization only knows model path and size, not rich model semantics
- richer model applicability facts must come from baseline/snapshot metadata, not guessed from filename or profile choice

## Forbidden Pruning in v1

Do not allow ACPM applicability rules to:

- invent or interpolate campaign values
- prune interior numeric values from committed YAML lists
- use transient load, temperature, or background processes as scope-pruning facts
- use profile choice to erase core tradeoff families
- infer multivariate best configs before measurement
- skip straight to C08-style combined configs without measured winners
- treat expected neutrality as non-applicability
- guess unsupportedness from missing telemetry detail alone

Specific v1 prohibitions:

- do not use `gpu_vram_total` to pre-prune high `NGL_sweep` values
- do not use `total_ram` alone to prune `C10_mmap` or `C12_mlock`
- do not use `TTFT` or `T/S` profile choice to declare a core primary sweep “not applicable”
- do not use missing `n_layers` / `n_kv_heads` / `d_model` to prune `NGL_sweep`; it only blocks context estimation/report logic

## Applicability vs Preference vs Later-Stage Ranking / Narrowing

### Applicability

Applicability means:

- this campaign family is structurally real and defensible for the current machine/model
- or it is explicitly not real because a stated machine/model assumption is false

Applicability does not mean:

- it is the highest priority now
- it is likely to win
- it deserves fewer values

### Preference

Preference means:

- profile-specific ordering or inclusion priority among campaigns that are still structurally valid

Examples:

- `TTFT` can prioritize `C04`, `C13`, and `C15`
- `T/S` can prioritize `C05`, `C01`, and `C07`

But preference must not redefine applicability truth.

### Later-stage narrowing

Later-stage narrowing means:

- budgeting, ordering, or scaffold selection among already-applicable surfaces

That is where any future repeat-tier-specific value scaffolds belong.

It should not be mixed into the applicability catalog in v1.

### Ranking / recommendation

Ranking happens only after execution and scoring.

It must not leak backward into applicability.

## What Must Remain Fully Covered Even in ACPM

These must remain fully covered at the applicability layer:

- shared validity/gate semantics
- the committed value list for any campaign that survives applicability
- the core primary family as a class of structurally applicable tuning surfaces
- the distinction between:
  - structurally inapplicable
  - applicable but deferred
  - executed and later recommended

Bottom line:

- v1 ACPM may decide not to include some optional families yet
- but it should not silently hollow out the inner search space of selected campaigns under the name of applicability

## Biggest Interior-Optimum / False-Pruning Risks

### 1. Interior numeric winners

This is the biggest v1 false-pruning risk.

Campaigns like:

- `C01_threads_batch`
- `C05_threads`
- `C06_ubatch`
- `C07_batch`
- `C13_defrag_thold`

all have plausible interior optima.

If ACPM prunes inner values before measurement, it can easily remove the true best setting.

### 2. Treating topology-specific campaigns as portable

`C11_cpu_affinity` is the clearest example.

If ACPM reuses it as a generic CPU rule, it will silently turn machine-specific lore into fake universality.

### 3. Treating MoE-specific placement as a general rule

`C09_tensor_placement` is tied to the current expert-placement assumption.

If ACPM generalizes it to dense or differently routed models, it will be pruning on the wrong ontology.

### 4. Treating optional latency/runtime campaigns as “not applicable” because of profile

That would let planner preference masquerade as physical truth.

## Downstream Implementation Consequences

- ACPM needs a planner-owned campaign-family catalog with explicit applicability classes
- campaign-family rules should read baseline/snapshot machine/model facts, not ad hoc report prose
- any future value-scaffold logic must live in a separate layer from applicability
- planning metadata should record campaign-family applicability reasons, not pretend value-pruning was structural truth
- compare/audit surfaces will need to distinguish:
  - not applicable
  - applicable but deferred
  - executed

## Questions Answered in This Pass

### 1. What machine facts are allowed to drive pruning?

Only explicit, durable machine facts tied to campaign semantics:

- OS/platform
- CPU topology where the campaign itself is topology-specific
- presence of GPU/offload as a real execution surface
- availability of the fact class itself

### 2. What model facts are allowed to drive pruning?

Only explicit model facts tied to campaign semantics:

- architecture class
- whether the swept variable is a real config surface
- baseline/snapshot model metadata already committed in repo truth

### 3. What pruning is forbidden in v1?

- inner-value pruning on applicability grounds
- speculative winner prediction
- profile-driven erasure of core tradeoff space
- transient-environment-driven pruning

### 4. What counts as applicability vs preference vs later narrowing?

- applicability: structural yes/no for a campaign family
- preference: order/priority among structurally valid campaigns
- later narrowing: budget/scaffold decisions after applicability
- ranking: post-measurement selection only

### 5. What must remain fully covered?

- the committed YAML value list for any selected campaign
- the shared validity floor
- the distinction between non-applicable and merely deferred

## Remaining Open Questions

- Should v1 include an explicit planner-owned metadata field that labels each campaign family as `core`, `conditional`, `optional`, `derived`, or `fixture`, or is that better deferred until ACPM implementation prep begins?
- Does ACPM need a small explicit machine-topology compatibility table for `C11_cpu_affinity`, or should that campaign simply remain excluded outside the current known topology in v1?
- Should `NGL_sweep` be treated as always optional but applicable when GPU offload exists, or should it become core for large-model GPU-backed deployments?

## Recommended Next Investigations

- `ACPM-campaign-family-catalog-TARGET-INVESTIGATION.md`
- `ACPM-topology-specific-campaign-portability-TARGET-INVESTIGATION.md`
- `ACPM-optional-family-budget-policy-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/boundaries.md`
