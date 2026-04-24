# CLI UX 1: Guided Run Shell PREP Implementation Plan

Date: 2026-04-23

## Executive Summary

The best first CLI/UX bundle is to make the existing QuantMap shell more legible without adding a new command family yet.

Recommendation: implement a bounded "guided run shell" pass across existing surfaces only:

- clearer top-level and subcommand help
- consistent next-action hints on the key operator path
- better campaign ID and artifact discoverability inside existing outputs
- command-reference alignment with the actual parser

Do **not** add `quantmap acpm` yet. Do **not** add `quantmap artifacts` yet. Both are plausible follow-ons, but neither is the smallest safe first move. The first bundle should prove that QuantMap can feel more coherent as an operator shell using the current command tree and ownership seams.

## 1. Exact First-Bundle Scope

### In scope

1. **Help readability on the existing command tree**
   - Improve `quantmap --help`.
   - Improve help text for the key operator commands:
     - `run`
     - `doctor`
     - `status`
     - `self-test`
     - `list`
   - Add workflow-oriented guidance and examples without changing command topology.

2. **Consistent next-action hints on the core operator path**
   - Standardize short "next actions" guidance for:
     - `status`
     - `doctor`
     - `self-test`
     - `run --validate`
     - `run` completion path
     - `list`
   - The point is not broad UX redesign; it is to reduce operator guesswork at the end of each command.

3. **Better campaign and artifact discoverability inside existing outputs**
   - Make `list` stop obscuring effective campaign IDs.
   - Make `list` more useful as the handoff surface into `explain`, `compare`, and `export`.
   - Add compact artifact pointers in existing outputs where they already fit naturally:
     - validation/run completion
     - history/listing
   - Favor compact canonical artifact cues over long path dumps.

4. **Readability/wording corrections on readiness surfaces**
   - Tighten terminology so tool integrity does not read like measurement readiness.
   - Reduce misleading or overly broad readiness wording on `self-test`.
   - Keep the environment/tooling/run-readiness distinction explicit.

5. **Parser/doc contract alignment**
   - Reconcile `.agent/reference/command_reference.md` with the actual current parser/help.
   - Ensure the first-bundle help/documentation changes do not immediately drift again.

### Explicit first-bundle decision

For this bundle, **artifact discoverability should be improved through existing outputs, not through a new `artifacts` command**.

Reason:

- adding a new top-level noun increases command-surface width immediately
- the audit’s strongest problem is shell coherence, not missing noun count
- the lower-blast-radius first move is to make `list`, `run`, `status`, and help output do more of the navigation work

## 2. Exact Files / Surfaces Likely Affected

### Primary implementation surfaces

- `quantmap.py`
  - top-level help text
  - subcommand help text
  - command descriptions/examples
  - any top-level next-step wording owned here

- `src/runner.py`
  - `list_campaigns()` readability and discoverability
  - `validate_campaign()` closing guidance
  - `run_campaign()` completion guidance and compact artifact pointers

- `src/doctor.py`
  - doctor closing guidance if current report-level rendering needs command-specific next steps

- `src/diagnostics.py`
  - shared readiness/result wording if the implementation chooses to centralize short end-state messaging

- `src/selftest.py`
  - wording correction so integrity validation is not presented as full environment readiness
  - next-action guidance back into the main operator flow

- `src/ui.py`
  - only if a very small shared helper is justified for consistent next-action blocks or compact command footers

### Documentation surface

- `.agent/reference/command_reference.md`

### Likely unaffected in this bundle

- `src/acpm_planning.py`
- `src/acpm_recommendation.py`
- `src/trust_identity.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/report_compare.py`
- `src/export.py`
- `src/explain.py`
- `src/compare.py`
- `src/db.py`
- `src/run_plan.py`

If implementation discovers that one of the "likely unaffected" files is required, pause and justify it explicitly before widening scope.

## 3. What Stays Explicitly Out Of Scope

1. **No parser/tree redesign**
   - no nested command families
   - no broad subcommand regrouping
   - no new command hierarchy

2. **No ACPM namespace in this bundle**
   - no `quantmap acpm ...`
   - no planner-oriented ACPM entrypoint
   - no ACPM-specific CLI nouns beyond wording guidance on future direction

3. **No new top-level `artifacts` command in this bundle**
   - improve discoverability through existing surfaces first
   - revisit a dedicated artifact locator only after the shell-coherence pass lands

4. **No truth-lane or authority changes**
   - no changes to `RunPlan` ownership
   - no changes to `scope_authority`
   - no changes to ACPM planning metadata ownership
   - no changes to methodology, effective filter-policy, or recommendation authority lanes

5. **No report/export/consumer redesign**
   - do not rework report content
   - do not fix broader artifact-status projection/reporting issues in this pass
   - do not widen into compare/explain family redesign yet

6. **No fuzzy matching / search subsystem**
   - not-found remediation for later read commands can be considered later
   - the first bundle should start with clearer IDs and handoff surfaces, not string-matching behavior

7. **No database or schema changes**

## 4. Blast Radius And Risks

### Expected blast radius

Low to moderate.

This bundle should primarily affect:

- CLI help text
- terminal wording
- terminal table layout
- compact operator guidance

It should not alter:

- scoring behavior
- run identity semantics
- artifact ownership
- ACPM planning behavior

### Main risks

1. **Output drift risk**
   - Existing screenshots, habits, or any light parsing expectations may depend on current terminal wording or table columns.

2. **Over-abstraction risk**
   - A small shared helper in `src/ui.py` is acceptable only if it stays tiny.
   - Do not turn "consistent next actions" into a large shell framework.

3. **Accidental command-scope widening**
   - It will be tempting to fold in `explain`, `compare`, or a new `artifacts` command.
   - Resist that in this first bundle.

4. **Readiness-term confusion**
   - Renaming or tightening end-state wording must preserve the real distinction between:
     - tool integrity
     - environment readiness
     - run preflight readiness

5. **ACPM watch-out**
   - Do not let workflow/help wording imply new ACPM authority.
   - Future ACPM invocation ergonomics remain deferred; this bundle only makes the current shell more coherent.

## 5. Smallest Strong Validation Plan

### Required verification

1. **Repo preflight**

```powershell
.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick
```

2. **CLI help smoke**

```powershell
.\.venv\Scripts\python.exe quantmap.py --help
.\.venv\Scripts\python.exe quantmap.py run --help
.\.venv\Scripts\python.exe quantmap.py doctor --help
.\.venv\Scripts\python.exe quantmap.py status --help
.\.venv\Scripts\python.exe quantmap.py self-test --help
.\.venv\Scripts\python.exe quantmap.py list --help
```

3. **Core operator-flow smoke**

```powershell
.\.venv\Scripts\python.exe quantmap.py status
.\.venv\Scripts\python.exe quantmap.py doctor
.\.venv\Scripts\python.exe quantmap.py self-test
.\.venv\Scripts\python.exe quantmap.py run --campaign B_low_sample --validate
.\.venv\Scripts\python.exe quantmap.py list
```

4. **Changed-path verification**

```powershell
.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py --paths quantmap.py src\runner.py src\doctor.py src\diagnostics.py src\selftest.py src\ui.py .agent\reference\command_reference.md
```

### Validation standard for this bundle

- Help output must clearly teach the intended first workflow.
- `status`, `doctor`, `self-test`, `run --validate`, and `list` must each end with concise next-step guidance.
- `list` must expose effective campaign IDs clearly enough to be used directly in follow-up commands.
- No new command tree or ACPM surface should appear.

## 6. Recommended Implementation Order

1. **Define the bundle’s shared wording contract first**
   - settle the exact short-form vocabulary for:
     - purpose
     - readiness/result state
     - next actions
   - keep this tiny and explicit before editing multiple outputs

2. **Update top-level and subcommand help in `quantmap.py`**
   - improve the first-run/operator guidance while keeping the current tree intact
   - add examples only where they materially reduce ambiguity

3. **Fix readiness wording split**
   - tighten `self-test`
   - align `status` / `doctor` / `run --validate` around clearer scope boundaries

4. **Improve `run --validate` and run-completion guidance in `src/runner.py`**
   - standardize next actions
   - add compact artifact/campaign handoff cues
   - do not widen into report redesign

5. **Improve `list` discoverability in `src/runner.py`**
   - make effective campaign IDs usable
   - make follow-up commands more obvious
   - keep terminal width in mind; prefer compact artifact cues over long raw paths

6. **Update `.agent/reference/command_reference.md` last**
   - sync docs to the actual shipped parser/help behavior after CLI wording settles

7. **Run the full bounded validation pass**

## 7. Implementation Guardrails

1. Prefer editing existing surfaces over adding new abstractions.
2. If a helper is added, keep it very small and presentation-only.
3. Do not move shell coherence work into report consumers.
4. Do not touch ACPM authority-bearing files unless unexpectedly required.
5. If implementation pressure pushes toward a new `artifacts` or `acpm` command, stop and split that into the next bundle instead of expanding this one.

## 8. Recommendation For The Next Bundle After This One

If this bundle lands cleanly, the next most likely bounded follow-on is:

- either a dedicated artifact locator surface
- or narrow ACPM invocation ergonomics

Those should remain separate decisions. This first bundle should prove the operator shell can become more coherent without adding new top-level nouns first.

## 9. .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/policies/routing.md`
- `.agent/policies/workflow.md`
- `.agent/reference/command_reference.md`
