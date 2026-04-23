# ACPM Blast Radius Investigation

Status: investigation-only  
Date: 2026-04-22  
Scope: Adaptive Campaign Planning Mode (ACPM) v1 blast-radius mapping only

## Outcome

ACPM can reuse the existing QuantMap execution and artifact engine, but the repo does not currently have a clean planner/orchestrator seam. The real blast radius is not just `runner.py`; it spans CLI dispatch, campaign/config shaping, pre-run environment evidence, runner orchestration, scoring/profile selection, report/export output, artifact-path contract, and a thin test surface around most of those areas.

The strongest current assets are:

- the existing `quantmap -> runner.run_campaign -> score_campaign -> report/export` path for actual execution and human-facing artifacts
- persisted run identity in `campaign_start_snapshot`, `methodology_snapshots`, and `artifacts`
- `RunPlan` for execution-shape truth once a run has already been decided
- provider/readiness seams in `telemetry_policy.py` and `telemetry_provider.py`

The highest-risk concern is architectural, not algorithmic: if ACPM is bolted into `run --mode`, `runner.py`, `score.py`, or the report modules directly, it will mix planning intent, execution-depth semantics, recommendation semantics, and artifact rendering in the wrong places.

## Scope / What Was Inspected

Code inspected:

- `quantmap.py`
- `src/runner.py`
- `src/run_plan.py`
- `src/score.py`
- `src/governance.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/export.py`
- `src/trust_identity.py`
- `src/artifact_paths.py`
- `src/compare.py`
- `src/explain.py`
- `src/doctor.py`
- `src/telemetry.py`
- `src/telemetry_policy.py`
- `src/telemetry_provider.py`
- `src/run_context.py`
- `src/characterization.py`
- `src/db.py`
- `configs/baseline.yaml`
- `configs/campaigns/C01_threads_batch.yaml`
- `configs/campaigns/NGL_sweep.yaml`

Tests inspected:

- `test_artifact_contract.py`
- `test_determinism.py`
- `test_governance.py`

Repo-native helper/tooling used:

- `.agent/scripts/helpers/signature_dump.py`

Validation run:

- `.\.venv\Scripts\python.exe -m pytest -q test_artifact_contract.py` -> passed
- `.\.venv\Scripts\python.exe -m pytest -q test_determinism.py` -> test assertions passed, but pytest ended with a coverage-file lock internal error while saving coverage output

## Likely ACPM Touchpoints

### 1. CLI / mode-entry / dispatch

- `quantmap.py` is the top-level dispatch surface. `cmd_run()` forwards directly to `runner.validate_campaign()` or `runner.run_campaign()`.
- The current `run` command already treats `--mode` as execution depth only: `full`, `standard`, `quick`. Those values are normalized into `RunPlan.run_mode`, DB identity, filter overrides, and report wording.
- `runner.py` enforces `--mode` and `--values` as mutually exclusive because `--mode` means full-campaign execution shape and `--values` means custom subset isolation.

Implication:

- ACPM should not be introduced by overloading the current `run --mode` surface. That flag already means “execution depth over an existing campaign,” not “planning strategy.”
- A new top-level ACPM command or command family is the safer seam.

### 2. Planning / config-shaping / campaign-building

- `src/run_plan.py` is not a planner. It captures resolved execution truth after scope has already been chosen.
- `runner.load_campaign()`, `validate_campaign_purity()`, and `build_config_list()` are the main existing config-shaping surfaces.
- The campaign model is still file-first: baseline YAML plus `configs/campaigns/<id>.yaml`.
- `score.generate_c08()` and `score.generate_finalist()` are the only existing “planning-like” generators. They auto-build new campaign YAMLs from prior winners.
- `configs/campaigns/NGL_sweep.yaml` plus `report._ngl_sweep_section()` show a second narrow planning/recommendation pattern: specialized targeted recommendation using `min_context_length`.

Implication:

- QuantMap already tolerates generated campaign definitions, but the reusable pattern is fragmented and not generalized.
- The repo is missing a first-class planning module that owns “what should we run next?” and “how do we materialize that into existing campaign execution inputs?”

### 3. Characterization / telemetry / run-context

- `run_context.create_run_context()` captures a structured environment/context bundle by orchestrating `characterization.py`.
- `runner._run_config()` already captures one run-context JSON file per cycle before execution starts.
- `telemetry_policy.probe_provider_readiness()` and `doctor.check_telemetry_provider_readiness()` are the cleanest pre-run readiness surfaces.
- `telemetry.collect_campaign_start_snapshot()` persists run-level telemetry provider evidence, execution-environment evidence, baseline identity, QuantMap identity, and `run_plan_json`.

Implication:

- ACPM can reuse current characterization and readiness evidence, but there is no dedicated “planner input bundle” API yet.
- Existing run-context capture is execution-time and sidecar-file based, not planner-owned and not first-class in the DB.

### 4. Runner / execution / orchestration

- `runner.run_campaign()` is the existing end-to-end engine: scope resolution, telemetry readiness, DB registration, snapshot capture, cycle execution, analysis, scoring, reporting, metadata export, and status updates.
- `runner.validate_campaign()` is the existing structural preflight.
- `RunPlan` is already the single authoritative execution description for dry-run, validate, execution, and primary reporting.

Implication:

- ACPM should reuse `runner.run_campaign()` for actual execution rather than bypassing it.
- ACPM’s own job should be planning/staging/orchestration above the runner, not re-implementing campaign execution.

### 5. Result selection / scoring / recommendation-adjacent surfaces

- `score.score_campaign()` is the main scoring entry point.
- `score.compute_scores()` separates rankable recommendation set from wider evidence set.
- `governance.py` already supports experiment profiles and metric registries.
- `report.py` contains specialized recommendation logic for `NGL_sweep` and generalized “Production Command” output for winners.
- `explain.py` and `compare.py` are winner/result interpretation layers, not planning layers.

Implication:

- ACPM can likely reuse the current scoring engine.
- ACPM may require targeted prep if Balanced / T/S / TTFT need to map to distinct experiment profiles or scoring views.
- Recommendation logic is currently split between scoring and reports instead of being owned by a dedicated recommendation/planner layer.

### 6. Report / artifact / output surfaces

- Human-facing artifacts already exist and are strongly structured:
  - `report.py` -> `campaign-summary.md`
  - `report_campaign.py` -> `run-reports.md`
  - `export.generate_metadata_json()` -> `metadata.json`
  - measurement stream -> `raw-telemetry.jsonl`
- `artifact_paths.py` and `test_artifact_contract.py` enforce a strict 4-artifact formal contract.
- `trust_identity.py` and `export.py` already consume persisted `run_plan`, methodology, telemetry provider evidence, and artifact statuses.
- Current machine-usable recommendation output does not exist as a dedicated serializer. The nearest surfaces are:
  - `configs.config_values_json`
  - `configs.resolved_command`
  - winner extraction in `score.py`
  - command appendices in `report.py` and `report_campaign.py`

Implication:

- Human-facing ACPM output can likely stay inside the existing artifact/report system cleanly if ACPM still runs through normal campaigns.
- The machine-facing handoff file does not yet have a clear output seam. It should not be sourced by scraping report markdown.

## Reuse Candidates

### Reusable As-Is

- `runner.run_campaign()` for actual execution
- `runner.validate_campaign()` for structural preflight on generated/scoped campaigns
- `RunPlan` for execution-shape truth after ACPM decides scope
- `score.score_campaign()` and `compute_scores()` for winner/ranking generation
- `governance.ExperimentProfile` / `MetricRegistry` as the scoring-policy substrate
- `doctor.check_telemetry_provider_readiness()` and `telemetry_policy.probe_provider_readiness()` for pre-run readiness input
- `trust_identity.load_run_identity()` plus `export.generate_metadata_json()` for persisted provenance and structured output
- `artifact_paths.py` for current human-artifact layout

### Reusable Only After Targeted Prep

- `score.generate_c08()` / `generate_finalist()` as proof that QuantMap accepts auto-generated campaign YAMLs, but not as ACPM’s long-term home
- `report._ngl_sweep_section()` as proof that specialized recommendation logic already exists, but only after extracting the planning/recommendation decision logic out of the report layer
- `run_context.create_run_context()` if ACPM needs machine-aware planning before execution; today it is execution-time and file-based, not planner-owned
- `governance.py` and `score.py` if ACPM user profiles are mapped to explicit experiment profiles; current runner/CLI flow does not expose profile selection for normal runs
- `report_campaign.generate_campaign_report()` if ACPM needs richer plan/scope reporting; the function supports `run_plan`, but runner currently does not pass it through

### Should Not Be Built On Directly

- `run --mode` as the ACPM UX surface
- `runner.py` as the home for planning logic
- `score.py` as the home for generalized campaign planning/orchestration
- `report.py` or `report_campaign.py` as the source of machine-facing handoff data
- `telemetry.py` as the place to embed ACPM-specific readiness or planning policy

## Structural Risks / Bad Seams

### Missing planner seam

There is no clear module that owns:

- user intent -> planning strategy
- planning strategy -> generated campaign stages
- planning result -> execution handoff
- recommendation result -> machine-facing variable-only handoff

`RunPlan` is execution metadata, not planning logic. Existing planning-like behavior is split between `score.py` campaign generators and report-specific recommendation logic.

### `run --mode` is already semantically occupied

Current modes are not user-optimization profiles. They are execution-depth contracts with downstream effects on:

- effective campaign IDs
- scoring filter overrides
- report confidence language
- scope/coverage metadata

Using that surface for Balanced / T/S / TTFT would collide with existing meanings.

### God objects / high-blast-radius modules

The main ACPM-adjacent risk centers are:

- `src/runner.py` (~133 KB)
- `src/report_campaign.py` (~119 KB)
- `src/report.py` (~84 KB)
- `src/telemetry.py` (~73 KB)
- `src/score.py` (~66 KB)
- `src/characterization.py` (~64 KB)
- `src/db.py` (~40 KB)

ACPM should touch these as consumers/integration points, not as its primary implementation home.

### Output contract is intentionally rigid

The current report/measurement contract is explicitly 4 formal artifacts. `test_artifact_contract.py` guards this. Adding the ACPM machine handoff file casually to `report_paths()` would cut across an intentionally narrow contract.

The existing clean pattern is:

- formal artifacts for core campaign truth
- supporting files for additional evidence or operational sidecars

That decision needs to be explicit for ACPM.

### Report detail path does not fully consume persisted run-plan truth

`report_campaign.generate_campaign_report()` accepts `run_plan`, and several sections use `selected_values`, `untested_values`, and `coverage_fraction`, but `runner.run_campaign()` currently does not pass `run_plan` into that call. The detailed report still has campaign/run-mode information via DB rows, but richer scope detail is not reliably wired through there.

This is a warning sign for ACPM: persisted execution/planning truth exists, but not every output surface currently consumes it cleanly.

### Planning logic is currently entangled with scoring/reporting special cases

Two existing patterns are useful but structurally risky if copied:

- auto-generated campaign sequencing lives in `score.py`
- targeted recommendation logic lives inside `report.py`

Those are workable precedents, but bad long-term homes for ACPM.

### Current campaign model is still campaign-file first

`runner.run_campaign()` loads `configs/campaigns/<campaign_id>.yaml`. There is no in-memory campaign object seam at the runner boundary. ACPM therefore cannot currently hand a fully planned run directly into the engine without materializing a file or adding a new execution seam.

### Test coverage is thin exactly where ACPM will stress the repo

What is covered:

- governance basics
- artifact contract and one narrow runner early-exit behavior
- score determinism tie-breaking

What is largely uncovered:

- CLI dispatch for new command surfaces
- `RunPlan`
- campaign-generation flows
- `runner.run_campaign()` happy-path orchestration
- `report.py` and `report_campaign.py`
- `export.generate_metadata_json()`
- `run_context.py` and `characterization.py`
- generalized recommendation serialization

## Prep Work Implied by Findings

Minimum prep work before ACPM implementation:

1. Define a dedicated ACPM entry surface and owner module.
   Recommendation: new planner/orchestrator module plus a new top-level CLI command, not `run --mode`.

2. Define the ACPM planner output contract.
   It needs to state what ACPM hands to the existing engine:
   - generated/scoped campaign definitions
   - chosen scoring profile or recommendation lens
   - planned execution stages
   - final recommended variable set

3. Define the machine-facing handoff output seam.
   Recommendation: derive it from scored config data plus a dedicated serializer, not from report markdown.

4. Decide whether the handoff file is:
   - a supporting file outside the 4-artifact formal contract, or
   - a new formal artifact with an explicit contract expansion

5. Decide how Balanced / T/S / TTFT map into QuantMap’s scoring architecture.
   This is the most important semantic prep item because it determines whether ACPM mainly reuses `governance.py` or requires a separate recommendation layer above scoring.

6. Extract or isolate campaign-generation utilities from `score.py` if ACPM will generate campaign definitions.

7. Add focused tests for:
   - ACPM CLI dispatch
   - planner output contract
   - generated campaign/materialization logic
   - handoff serialization
   - profile-selection/recommendation semantics

High-value but not necessarily first:

- thread persisted `run_plan` truth more consistently into `report_campaign.py`
- add a dedicated pre-run planner-input helper around `run_context` / provider readiness if ACPM needs machine-aware planning before the first run starts

## Open Questions / Major Concerns

### Major concern: user profiles vs scoring profiles

Balanced, T/S, and TTFT could mean at least three materially different things:

- direct mappings to distinct `ExperimentProfile`s
- one scoring profile plus planner-side weighting/selection heuristics
- a hybrid where scoring stays stable but ACPM changes campaign ordering and stop conditions

That choice changes the blast radius across `governance.py`, `score.py`, reports, and historical methodology trust semantics.

### Major concern: file-first runner boundary

If ACPM is meant to plan multiple stages dynamically, the current runner boundary forces a choice:

- materialize planned campaigns as YAML files and reuse current execution exactly
- or introduce a new non-file execution seam into the runner

That is an important implementation-order decision because it changes how much prep work is needed before any ACPM logic lands.

### Major concern: artifact contract expansion

The machine-facing handoff file is easy to want and easy to place badly. If it is treated as a normal report artifact without an explicit contract decision, ACPM will cut across a currently well-guarded output model.

### Major concern: planning evidence / provenance

The repo already persists execution truth and methodology truth. ACPM will introduce another truth layer: planning intent. There is not yet a defined place for “why ACPM chose this campaign set / stopping rule / recommendation path.”

## Recommended Next Investigations

Recommended targeted follow-ups before implementation:

- `ACPM-profile-to-governance-mapping-TARGET-INVESTIGATION.md`
- `ACPM-planner-entry-and-execution-contract-TARGET-INVESTIGATION.md`
- `ACPM-machine-handoff-output-contract-TARGET-INVESTIGATION.md`
- `ACPM-generated-campaign-materialization-TARGET-INVESTIGATION.md`

The first two are the most important. They decide whether ACPM can stay as a thin planner over existing surfaces or whether it forces broader structural change.

## Recommended Implementation-Order Implications

Recommended order:

1. Decide ACPM profile semantics first.
   Do not start with CLI wiring or report wording before deciding what Balanced / T/S / TTFT actually mean in scoring/planning terms.

2. Define the planner/orchestrator seam next.
   ACPM needs its own owner module before any logic is added to runner, score, or reports.

3. Decide campaign materialization strategy.
   If ACPM will generate YAML-backed stages, settle that early so execution reuse is straightforward.

4. Define the machine-facing handoff contract before report changes.
   That output should come from structured data, not a report appendix retrofit.

5. Integrate with existing execution/report surfaces after the above contracts are fixed.
   The current runner/report/export stack is strong once ACPM knows what it is handing off.

6. Leave compare/audit/explain/history expansion out of ACPM v1 unless a later requirement forces them in.
   v1 explicitly does not need prior-run history, so those surfaces are not on the critical path.

## .agent Files Used This Turn

- `.agent/policies/workflow.md`
- `.agent/policies/architecture.md`
- `.agent/scripts/helpers/signature_dump.py`
