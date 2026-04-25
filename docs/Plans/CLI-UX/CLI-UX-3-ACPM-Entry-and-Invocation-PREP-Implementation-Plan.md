# CLI UX 3: ACPM Entry and Invocation Ergonomics — PRE Implementation Plan

Date: 2026-04-23
Status: PRE / planning only
Precondition: Bundles 1 and 2 validated

---

## Context

Bundle 1 delivered guided-shell coherence on the existing command tree.
Bundle 2 delivered post-run artifact discovery via `quantmap artifacts`.

CLI Audit 1 explicitly deferred ACPM ergonomics to Sequence 3 (section 10, "ACPM Entry/Invocation Ergonomics"). The audit found:

> "ACPM v1 is implemented structurally, but not yet ergonomically — governed profiles exist, planner metadata exists, recommendation authority exists, projection surfaces exist — there is no first-class ACPM CLI noun."

The audit also warned: "Invocation ergonomics must not collapse truth lanes." ACPM command surfaces may improve input vocabulary, preview flow, validation flow, and output language. They must not reassign authority for execution truth, planning provenance, methodology truth, filter-policy truth, or recommendation claim truth.

This plan defines the smallest safe next bundle for ACPM entry and invocation ergonomics.

---

## 1. Current Repo Truth After Bundles 1 and 2

### Parser surface (live check, `quantmap --help`)

Current subcommands: `run`, `doctor`, `init`, `self-test`, `status`, `rescore`, `audit`, `list`, `about`, `compare`, `explain`, `explain-compare`, `export`, `artifacts`.

**No `acpm` namespace exists.** The current CLI has no entry point for ACPM planner workflows.

### `run` mode surface

`quantmap run` accepts `--mode {full,standard,quick}` and `--values <comma-separated>`. No `--profile`, `--tier`, or `--acpm` flag. No subcommands.

### ACPM structural truth (runtime check, `src/acpm_planning.py`)

- `V1_ACPM_PROFILE_IDS = {"Balanced", "T/S", "TTFT"}`
- Repeat tiers: `1x` → `quick`, `3x` → `standard`, `5x` → `full`
- Profiles map to scoring profile names: `acpm_balanced_v1`, `acpm_ts_v1`, `acpm_ttft_v1`
- Scaffold values for NGL: `[10, 30, 50, 70, 90, 999]`
- Coverage classes: `scaffolded_1x`, `full`
- ACPM planning metadata is persisted at campaign start; `RunPlan` is execution truth

### Existing ACPM surfaces

- ACPM recommendation projections appear inside `run-reports.md` (`_section_recommendation`)
- ACPM recommendation record is written to DB (`_persist_acpm_recommendation_record`)
- `acpm_recommendation.py` evaluates recommendation authority
- Governance profiles exist at `configs/profiles/acpm_balanced_v1.yaml`, `acpm_ts_v1.yaml`, `acpm_ttft_v1.yaml`

### Known gaps (from audit)

- No `quantmap acpm` entry surface
- No `quantmap run --profile <name>` or `--tier <n>x` flag
- No preview/validate flow for an ACPM plan before execution
- No compact `quantmap run acpm ...` alias to show the effective run plan
- `artifacts` command at end of run completion points to manual run artifacts, not ACPM-specific surfaces

---

## 2. Exact Bundle 3 Scope

The following are in scope:

1. **`quantmap acpm` namespace** — new top-level subcommand with sub-verbs.
   - `quantmap acpm --help` shows the family overview and entry points.
   - Sub-verbs: `plan`, `validate`, `info`.

2. **`quantmap acpm plan --campaign <ID> --profile <name> [--tier <n>x]`** — preview flow.
   - Shows the effective run plan without executing: selected scope, coverage class, profile, repeat tier, effective run ID, scope authority, expected coverage class.
   - Does not mutate DB or write any artifacts.
   - Compiles against existing `acpm_planning.py` contracts; does not invent new truth.

3. **`quantmap acpm validate --campaign <ID> --profile <name> [--tier <n>x]`** — preflight check.
   - Validates campaign purity, profile existence, repeat tier validity, and scaffolding applicability.
   - Mirrors the validate pattern used by `run --validate` but scoped to ACPM inputs.
   - Prints pass/fail per check with remediation hints.

4. **`quantmap acpm info --profile <name>`** — profile discoverability.
   - Shows profile display name, lens description, scoring profile name.
   - Lists all available profiles if no `--profile` given.
   - Helps operator choose a profile without reading YAML files.

5. **Top-level help update** — additive entry point reference.
   - `quantmap --help` epilog or subcommand list gains `quantmap acpm` entry pointing to the new namespace.
   - Does not change `run` help or `Start here:` workflow.

6. **Post-run guidance update in `runner.py`** — when an ACPM run completes.
   - After run completion, `artifacts` block is followed by a compact note on how to invoke `quantmap acpm plan` to preview the next planned run.
   - Display-only; does not change run semantics.

---

## 3. Exact Files and Surfaces Likely Affected

### Primary changes

| File | Change |
|---|---|
| `quantmap.py` | Register `acpm` subparser with `plan`, `validate`, `info` sub-verbs; wire handlers |
| `src/acpm_planning.py` | Export existing helpers as a stable callable surface for CLI (already exists; ensure clean call interface) |
| `src/ui.py` | Add `render_acpm_plan_preview()` for the plan subcommand output |
| `src/runner.py` | Extend run completion guidance with ACPM next-action hint (display-only) |

### Secondary changes

| File | Change |
|---|---|
| `.agent/reference/command_reference.md` | Add `acpm` namespace entries for `plan`, `validate`, `info` |

### New test file

| File | Purpose |
|---|---|
| `test_cli_ux_acpm_entry.py` | Tests for `acpm` namespace: help smoke, plan preview, validate flow, info subcommand, unknown profile handling |

---

## 4. Explicit Out-of-Scope Items

- **`quantmap acpm run`** — execution wired to existing `RunPlan`/runner flow; not this bundle. The plan is to expose ACPM entry before wiring the execution path.
- **New `run --profile` or `run --tier` flags** — defer until ACPM namespace is stable.
- **Changing `run --mode` semantics** — `quick/standard/full` remain the operator execution modes. Repeat tiers map internally but are not exposed as new mode names.
- **ACPM truth-lane changes** — hard boundary. CLI surfaces only consume and display existing truth; they do not create, modify, or reassign authority.
- **DB/schema changes** — no new columns, tables, or migrations.
- **Report or consumer surface changes** — `run-reports.md`, `campaign-summary.md`, `explain`, `compare`, `export` not touched this bundle.
- **ACPM recommendation projection surfaces** — recommendation display inside reports is already present; not changed.
- **`acpm_planning.py` internal logic** — not modified; CLI calls existing public functions.
- **Broad command-tree redesign** — flat topology preserved; no nesting introduced.
- **`list` or `explain` not-found remediation** — Sequence 4; deferred.

---

## 5. Blast Radius and Risks

### Low blast radius

- New `acpm` subparser: purely additive; no existing command behavior changes.
- `command_reference.md` update: documentation only.
- `runner.py` completion hint update: display-only append; does not change run flow or exit codes.
- `ui.py` renderer: additive function; existing renderers untouched.

### Moderate blast radius

- `src/acpm_planning.py` call interface: the module already has clean public functions. CLI calls must use only documented interfaces and not depend on internal state. **Constraint: verify CLI calls pass the same inputs as existing callers (e.g., runner.py's ACPM path).**
- `src/ui.py` style consistency: new renderer must match existing `render_artifact_block` style.

### Highest risk in this bundle

- **Introducing a new command family with ACPM branding** before execution is wired: the plan/validate/info commands exist but have no run path. This is not wrong if scoped correctly, but creates an expectation that `acpm run` will follow. **Constraint: explicitly note in epilog/description that `acpm run` execution is the next bundle, and that current execution uses `quantmap run --mode quick` (or equivalent).**
- **Profile name mismatch with actual governance files**: if `configs/profiles/acpm_*.yaml` profile names do not match `_ACPM_PROFILE_REGISTRY` values, the plan subcommand will fail to load profiles. **Constraint: verify the mapping before wiring.**

### Not a risk for this bundle

- RunPlan execution semantics — unchanged
- Methodology snapshots — unchanged
- Recommendation authority — unchanged
- Filter policy truth — unchanged

---

## 6. Smallest Strong Validation Plan

### Repo and changed-path checks (run in this order)

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths quantmap.py src\acpm_planning.py src\ui.py src\runner.py .agent\reference\command_reference.md test_cli_ux_acpm_entry.py
.\.venv\Scripts\python.exe -m ruff check quantmap.py src\acpm_planning.py src\ui.py src\runner.py test_cli_ux_acpm_entry.py
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_acpm_entry.py
```

### Help smoke

```powershell
.\.venv\Scripts\python.exe quantmap.py --help
.\.venv\Scripts\python.exe quantmap.py acpm --help
.\.venv\Scripts\python.exe quantmap.py acpm plan --help
.\.venv\Scripts\python.exe quantmap.py acpm validate --help
.\.venv\Scripts\python.exe quantmap.py acpm info --help
```

Verify: `acpm` appears in top-level help with a clear one-line description; `acpm plan` shows `--campaign`, `--profile`, `--tier` flags; `acpm validate` shows same flags; `acpm info` shows `--profile` flag and lists profiles.

### Functional smoke

```powershell
# Profile listing
.\.venv\Scripts\python.exe quantmap.py acpm info

# Single profile info
.\.venv\Scripts\python.exe quantmap.py acpm info --profile Balanced

# Plan preview for a valid campaign
.\.venv\Scripts\python.exe quantmap.py acpm plan --campaign B_low_sample --profile Balanced --tier 1x

# Validate for a valid campaign
.\.venv\Scripts\python.exe quantmap.py acpm validate --campaign B_low_sample --profile Balanced --tier 1x

# Unknown profile — expect error with valid profile list
.\.venv\Scripts\python.exe quantmap.py acpm info --profile BadProfile

# Unknown campaign (plan/validate) — expect not-found hint
.\.venv\Scripts\python.exe quantmap.py acpm plan --campaign does_not_exist_999 --profile Balanced
```

### Acceptance criteria

| Check | Must Pass |
|---|---|
| `verify_dev_contract --quick` | yes |
| `changed_path_verify` on all touched paths | yes |
| `ruff check` on all touched Python | yes |
| `pytest -q test_cli_ux_acpm_entry.py` | yes |
| `acpm` appears in top-level help | yes |
| `acpm --help` shows plan/validate/info family | yes |
| `acpm info` lists all 3 profiles with descriptions | yes |
| `acpm info --profile Balanced` shows lens description | yes |
| `acpm plan --campaign B_low_sample --profile Balanced` shows preview block | yes |
| `acpm plan --profile BadProfile` exits 1 with valid options | yes |
| `acpm plan --campaign unknown_id` exits 1 with hint | yes |
| No `acpm run` execution path wired | yes |
| `command_reference.md` includes all 3 acpm subcommands | yes |
| No existing subcommand behavior changed | yes |

---

## 7. Recommended Implementation Order

1. **`src/acpm_planning.py`** — audit the existing public API (`get_acpm_profile_info`, `load_acpm_scoring_profile`, `compile_acpm_plan`, etc.); ensure all needed helpers are importable at module level with clean call signatures. No logic changes.

2. **`src/ui.py`** — add `render_acpm_plan_preview()` renderer matching existing artifact-block style. Define canonical labels for profile/repeat-tier/coverage-class display.

3. **`quantmap.py`** — wire the `acpm` subparser with `plan`, `validate`, `info` sub-verbs. Keep execution unwired (handlers call plan/validate logic only). Add `acpm` to top-level help.

4. **`src/runner.py`** — add ACPM next-action hint at run completion after the artifact block (brief: "Run `quantmap acpm plan` to preview the next planned scope.").

5. **`test_cli_ux_acpm_entry.py`** — write targeted tests: help smoke, profile listing, plan preview content, validate pass/fail, unknown profile error, unknown campaign error.

6. **`.agent/reference/command_reference.md`** — add `acpm` entries for `plan`, `validate`, `info`.

7. **Run full validation suite** — as per section 6.

Steps 1–3 are the primary value path and can be verified independently. Step 4 (runner hint) is display-only and safe to add at end. Step 5 (tests) must pass before claiming completion.

**Post-bundle note (not implementation scope):** The next bundle after this one should wire `quantmap acpm run` by calling `runner.run_campaign()` with ACPM-compiled parameters. That bundle must verify that ACPM-compiled execution and manual `run` execution produce identical results, confirming no truth-lane divergence.

---

## `.agent` Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/reference/terminal_guardrails.md`
- `.agent/scripts/helpers/verify_dev_contract.py`