# ACPM Profile to Governance Mapping Target Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: ACPM profile semantics, governance fit, and downstream implications only

## Outcome

Balanced, T/S, and TTFT should be modeled in v1 as a methodology-primary hybrid:

- each ACPM profile must map to an explicit governed scoring profile that affects winner-selection semantics and is persisted in methodology/trust surfaces
- each ACPM profile may also carry paired planner heuristics that influence campaign ordering, escalation, and measurement efficiency
- planner heuristics must not replace, hide, or silently override the governed scoring semantics

This is the best fit for the current repo because QuantMap already treats profiles as methodology objects with trust and snapshot implications, while ACPM as a feature is explicitly a planner/orchestrator over the existing engine. Pure scoring profiles would under-specify planning behavior. Pure planner heuristics would hide user-intent semantics from the trust surface and make recommendation behavior look methodology-neutral when it is not.

Recommended v1 framing:

- `Balanced`: governed mixed recommendation profile, closest to current default throughput-plus-latency practicality
- `T/S`: governed throughput-biased recommendation profile with the same global validity floor
- `TTFT`: governed latency-biased recommendation profile with the same global validity floor

These should be recommendation profiles, not new measurement universes.

## Scope / What Was Inspected

Policies/docs inspected:

- `.agent/policies/project.md`
- `.agent/policies/boundaries.md`
- `docs/system/trust_surface.md`
- `docs/Plans/Advanced-Campaign-Planning-Mode/Investigations/ACPM-blast-radius-INVESTIGATION.md`

Methodology/config surfaces inspected:

- `configs/metrics.yaml`
- `configs/profiles/default_throughput_v1.yaml`
- `configs/baseline.yaml`
- `configs/campaigns/NGL_sweep.yaml`

Code inspected:

- `src/governance.py`
- `src/score.py`
- `src/trust_identity.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `quantmap.py`

Validation targeted for this pass:

- governance-oriented profile verification only

## Candidate Semantic Models Considered

### 1. Pure scoring profiles

Meaning in system terms:

- Balanced / T/S / TTFT are just `ExperimentProfile` selections
- they change weights, possibly some profile-governed thresholds, and possibly confidence policy
- ACPM planner behavior stays methodology-neutral and only gathers data efficiently
- final recommendation is fully determined by the selected scoring profile

Advantages:

- strong fit with existing trust/methodology snapshot machinery
- clear auditability because user intent is visible in `profile_name`, `profile_version`, weights, gates, and report/export surfaces
- winner-selection semantics are explicit and reviewable

Weaknesses:

- does not explain what ACPM as a planner should do differently before scoring
- pushes too much product meaning into methodology even when some profile behavior is really acquisition strategy
- risks overloading current `ExperimentProfile` schema beyond what runtime actually uses today

### 2. Pure planner heuristics

Meaning in system terms:

- QuantMap scoring stays on one global profile, effectively `default_throughput_v1`
- Balanced / T/S / TTFT only change what campaigns are run first, what variables are explored, or when more repetition is requested
- final recommendation is still judged under one shared scoring methodology

Advantages:

- keeps scoring and methodology stable
- easy to say ACPM is “just orchestration”

Weaknesses:

- poor fit for current trust model if user-facing recommendations differ by profile but methodology snapshots still show the same scoring profile
- hides important user-intent semantics from report/export/audit surfaces
- risks practical recommendation behavior that looks scientific but is actually heuristic and under-disclosed

### 3. Hybrid: governed scoring profile plus planner heuristics

Meaning in system terms:

- each ACPM profile has a governed methodology component and a planner-policy component
- methodology component decides how candidate configs are judged once measured
- planner component decides how ACPM spends budget to gather evidence for that profile efficiently
- both are explicit, but only the methodology component changes winner-selection semantics

Advantages:

- best fit with current architecture and product direction
- preserves snapshot/audit truth for conclusion semantics
- still lets ACPM behave differently as a planner without pretending every planning choice is methodology

Weaknesses:

- needs explicit boundary discipline so planner logic does not silently leak into scoring semantics
- requires a clear mapping contract between ACPM profile IDs and methodology profile IDs

### 4. Something else: recommendation lens separate from both governance and planning

Meaning in system terms:

- ACPM profile is its own recommendation layer after measurement and maybe after scoring
- neither `ExperimentProfile` nor planner heuristics fully own the semantics

Assessment:

- worst fit for the current repo
- creates a third semantic layer where QuantMap already distinguishes measurement, methodology, and interpretation
- highest risk of hidden recommendation logic

## Repo-grounded Findings

### 1. Profiles are already methodology objects, not just UI labels

`configs/profiles/default_throughput_v1.yaml` explicitly says changing it changes scoring behavior. `governance.py`, `score.py`, `trust_identity.py`, `report.py`, `report_campaign.py`, `export.py`, and `quantmap about/status` all already treat profile identity as part of the trust surface.

This strongly argues against pure planner-only semantics.

### 2. The current trust model expects conclusion-shaping logic to be snapshot-visible

`trust_surface.md` and `trust_identity.py` make methodology authority explicit and snapshot-first. Historical interpretation is supposed to come from persisted methodology evidence, not hidden current logic.

If ACPM profiles can materially change what config is recommended, that meaning should not live only in planner heuristics.

### 3. The repo already separates methodology truth from recommendation confidence language

`report.py` and `report_campaign.py` already vary wording by run mode:

- Custom -> “best among tested”
- Quick -> “broad but shallow”
- Standard -> “development-grade”
- Full -> “validated optimal”

This is important: the repo already has a clean pattern where practical recommendation caveats are expressed outside raw scoring semantics. ACPM should reuse this separation rather than collapsing everything into profile weights.

### 4. Current `ExperimentProfile` runtime use is narrower than the schema suggests

The schema includes:

- `experiment_family`
- `ranking_mode`
- `composite_basis`
- `report_emphasis`
- `diagnostic_metrics`

But current runtime meaning is concentrated mainly in:

- `weights`
- `gate_overrides`
- `confidence_policy`
- compatibility validation against registry family tags

This means ACPM should not assume the existing profile schema already solves planning semantics. It gives a methodology home, not a planner-policy home.

### 5. The default profile is already close to a “Balanced practical throughput” stance

`default_throughput_v1.yaml` is not raw-throughput-only. It already mixes:

- throughput median
- throughput floor
- warm TTFT median
- warm TTFT P90
- cold TTFT
- prompt processing

with hard viability gates for:

- CV
- thermal events
- outliers
- latency ceiling
- success rate
- warm TG floor
- sample count

That is much closer to a practical balanced recommendation profile than to a pure “maximize T/S at all costs” profile.

### 6. The registry draws a strong line between metric meaning and metric use

`configs/metrics.yaml` explicitly says:

- metrics.yaml defines what a metric means
- experiment profiles define how metrics are used

This is exactly the right place for ACPM profile conclusion semantics. It argues for profile-specific weighting/use while keeping metric definitions global.

### 7. The repo philosophy disfavors hidden recommendation semantics

Project and boundary policies require:

- scientific rigor
- determinism
- auditable behavior
- visible warnings
- evidence-bounded interpretation

Poorly defined profile semantics would violate those constraints by making recommendations depend on unstated preference logic.

### 8. NGL recommendation behavior proves planner/recommendation logic exists outside governance

`configs/campaigns/NGL_sweep.yaml` plus `report._ngl_sweep_section()` show an existing narrow recommendation layer driven by user need (`min_context_length`) rather than core scoring methodology.

This is evidence that planner/recommendation behavior and methodology behavior are not the same thing in QuantMap. ACPM needs both, but they should not be conflated.

### 9. Current methodology loading paths are already prepared for profile-specific scoring

`score.score_campaign()` can already take `profile_name`.
`trust_identity.load_methodology_for_historical_scoring()` already persists and rehydrates profile/registry evidence.

So the repo already has a real mechanism for “different recommendation semantics must be visible as methodology,” even though only one profile file currently exists.

## Recommended ACPM Profile Model for v1

### Recommendation

Use a hybrid model with a governed scoring core:

- ACPM profile = `governed recommendation lens` + `paired planner policy`

In more concrete repo terms:

- the governed recommendation lens should be implemented as an explicit `ExperimentProfile` selection or direct profile mapping that changes ranking intent visibly and audibly
- the paired planner policy should govern which campaigns or variables ACPM prioritizes first and when it escalates repetition
- the planner policy must never silently change what “winner” means after measurement; that must remain the job of the governed recommendation lens

### Why this is the best fit

It best matches four current realities:

1. QuantMap already has profile-aware trust machinery.
2. ACPM is explicitly a planner/orchestrator over the existing engine.
3. Current report language already distinguishes recommendation confidence from methodology.
4. The repo’s scientific posture requires conclusion-shaping logic to be explicit and auditable.

### What this means for the three v1 profiles

Recommended semantic reading:

- `Balanced`: the default practical single-user recommendation lens; closest descendant of current `default_throughput_v1`
- `T/S`: throughput-first recommendation lens, but still bounded by global viability and honesty constraints
- `TTFT`: latency-first recommendation lens, but still bounded by minimum throughput/stability viability and honesty constraints

Recommended governance stance:

- these are three different ways to judge “best practical config”
- they are not three different metric universes
- they are not three hidden recommendation heuristics layered on top of one unchanged methodology

## What Should Be Global vs Profile-specific

### Global across all ACPM profiles

- metric definitions in `configs/metrics.yaml`
- raw measurement pipeline and telemetry capture behavior
- eliminated vs unrankable semantics
- explicit missing/failed/unsupported distinctions
- trust/evidence labeling
- methodology snapshot persistence rules
- artifact honesty and freshness rules
- repeat-tier meaning for `1x / 3x / 5x` as execution-strength semantics
- hard minimum validity/safety constraints for:
  - thermal safety
  - request success reliability
  - minimum statistical viability
  - explicit uncertainty disclosure

Recommended v1 stance:

- do not let ACPM profile selection relax core validity gates below the repo’s current scientific floor

### Legitimately profile-specific in v1

- relative importance of throughput vs latency within ranked candidates
- planner ordering bias toward throughput-sensitive vs latency-sensitive variables/campaigns
- planner escalation priority when evidence is ambiguous for that profile’s lens
- report/explanation emphasis wording tied to the selected ACPM profile

### Probably not profile-specific in v1

- telemetry readiness standards
- thermal throttle disqualification
- success-rate floor
- artifact contract truthfulness
- whether historical methodology must be snapshot-visible
- deterministic tie-breaking

### Minimum viability/safety constraints regardless of profile

All ACPM profiles should still require:

- no thermal-throttle acceptance
- no silent acceptance of unreliable success behavior
- no recommendation from clearly insufficient evidence without explicit downgrade language
- no hidden switch from governed anchors to cohort-relative behavior without explicit labeling
- no profile-specific wording that overstates certainty

## Risks of Getting This Wrong

### 1. Hidden methodology drift

If profiles are treated as planner-only while changing recommendation behavior materially, the trust surface will say one thing and ACPM will do another.

### 2. False scientific neutrality

If one default scoring profile stays fixed while ACPM changes recommendations heuristically, the system may look evidence-bound while actually embedding untracked preference logic.

### 3. Overloading governance with planner behavior

If everything is pushed into `ExperimentProfile`, the repo may start encoding campaign ordering, repetition escalation, or exploration strategy inside methodology objects that should only describe how evidence is judged.

### 4. Broken audit/report semantics

If ACPM profile semantics are unclear, report language such as “validated optimal,” “best among tested,” or future ACPM-specific phrasing may become misleading because the system cannot clearly say whether a result reflects methodology, search coverage, or heuristic preference.

### 5. Brittle downstream implementation

If the semantic model is vague, later planner, scoring, artifact, and audit work will all invent their own meaning for the same profile names.

## Downstream Decisions Affected

This answer directly affects:

- whether ACPM requires new profile YAMLs under `configs/profiles/`
- whether planner code selects `profile_name` when invoking scoring
- whether ACPM reports and metadata must surface both profile ID and planner policy
- how repeat-strength tiers interact with recommendation certainty
- what fields the future machine handoff serializer should trust as the authoritative winner basis
- how audit/explain surfaces should describe ACPM recommendations
- whether profile-specific campaign ordering is allowed to differ without changing scoring semantics

It also constrains later work on:

- planner/orchestrator contract
- profile-to-campaign mapping
- repeat escalation policy
- report/audit labeling

## Questions Answered in This Pass

### What would pure scoring profiles mean?

They would make ACPM profiles explicit methodology choices, changing winner-selection semantics through governed profile fields only.

### What would pure planner heuristics mean?

They would leave methodology fixed while making ACPM profiles only affect search/order/escalation behavior.

### What would a hybrid mean?

It would separate:

- how evidence is collected efficiently
- from how measured candidates are judged

### Which interpretation best fits the current repo?

The hybrid, with methodology as the primary truth-bearing layer.

### Which interpretation best preserves QuantMap’s scientific character?

The hybrid, because conclusion semantics remain explicit and snapshot-visible while planner behavior remains bounded and non-hidden.

### What should remain fixed?

Metric meaning, validity/safety floors, trust semantics, artifact honesty, and uncertainty handling.

### What may vary by profile?

Ranking emphasis and planner priority, but not the basic truth contract.

## Remaining Open Questions

### 1. How much may profile-specific gates differ in v1?

The safest current recommendation is:

- keep hard validity/safety floors global
- allow profile-specific ranking weights first

But the exact rule should be frozen explicitly.

### 2. What is the exact intended meaning of `T/S`?

The repo supports a throughput-first interpretation, but the acronym expansion and user-facing definition should be frozen before implementation to prevent ambiguity in docs and reports.

### 3. Should ACPM profile identity be identical to methodology profile identity?

Recommended default: yes for v1 naming alignment, but the planner-policy layer still needs its own explicit ownership.

### 4. How should repeat-strength tiers interact with confidence and recommendation claims?

This depends on whether `1x / 3x / 5x` are only execution presets or also recommendation sufficiency tiers.

## Recommended Next Investigations

Recommended follow-ups:

- `ACPM-profile-weight-and-gate-spec-TARGET-INVESTIGATION.md`
- `ACPM-repeat-tier-sufficiency-policy-TARGET-INVESTIGATION.md`
- `ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`

Priority order:

1. `ACPM-profile-weight-and-gate-spec-TARGET-INVESTIGATION.md`
2. `ACPM-repeat-tier-sufficiency-policy-TARGET-INVESTIGATION.md`
3. `ACPM-profile-report-and-audit-labeling-TARGET-INVESTIGATION.md`

## .agent Files Used This Turn

- `.agent/policies/project.md`
- `.agent/policies/boundaries.md`
