# CLI UX 2: Campaign and Artifact Discovery — PRE Implementation Plan

Date: 2026-04-23
Status: PRE / planning only
Precondition: Bundle 1 validated (`docs/Plans/CLI-UX/CLI-UX-1-Guided-Run-Shell-Validation.md`)

---

## Context

Bundle 1 delivered shell coherence on the existing command tree:

- top-level and subcommand help with a clear workflow section
- consistent next-action hints across `status`, `doctor`, `self-test`, `run --validate`, `list`, and run completion
- `list` footer lines exposing exact campaign IDs and summary paths
- `self-test` wording scoped to tooling integrity
- command reference reconciled with parser

The remaining highest-value gap identified by CLI Audit 1 is **post-run discoverability**.

After a run completes, the operator has no compact CLI surface to answer:

- where did this campaign write its artifacts?
- which artifacts are present vs. missing?
- what is the right path to open the campaign summary?

`list` now exposes IDs well, but still conflates history browsing with path lookup. `explain` and `compare` do not surface paths. The campaign-summary report contains correct artifact index material, but it requires the operator to know where to look and to trust that the report's status projection is accurate — which the audit found it sometimes is not.

This is CLI Audit Sequence 2, executed as the second bounded bundle.

---

## 1. Exact Bundle 2 Scope

The following are in scope:

1. **`quantmap artifacts <campaign-id>`** — new dedicated artifact locator command.
   - Shows canonical paths for: campaign summary, run report, raw telemetry, metadata, latest log.
   - Shows file presence status (present / missing) for each, read from disk against `artifact_paths.py` logic.
   - Shows DB-recorded artifact status alongside disk status so operator can see if they agree.
   - On unknown campaign ID: emit a clear not-found message with a `quantmap list` hint.

2. **Post-run artifact path summary in `run` completion output** — additive, brief.
   - After a successful run completes, emit a compact block: "Artifacts written to: ..." with the same paths the new `artifacts` command would show.
   - Does not change run mechanics or reporting; display-only addition to the run completion path in `runner.py`.

3. **Artifact status projection accuracy fix in `report_campaign.py`.**
   - The audit found campaign-summary.md sometimes shows `not generated` for artifacts that exist on disk and are recorded in the DB.
   - Identify and fix the projection logic so DB status and disk presence are checked together correctly before writing the status column.

4. **Artifact status vocabulary normalization** — conservative, targeted.
   - The current status vocabulary mixes: `not generated`, `file_present`, `pending`, `failed`, `missing`.
   - Define a small canonical set (e.g., `present`, `missing`, `pending`, `failed`) and apply consistently across the new `artifacts` command and the `report_campaign.py` fix.
   - Do not touch vocabulary in surfaces not already being changed this bundle.

---

## 2. Dedicated Discovery Surface vs. Enriching Existing Commands

**Decision: add a dedicated `quantmap artifacts <campaign-id>` command.**

Rationale:

- Bundle 1 already improved discoverability *inside* existing outputs (`list` footer lines, next-action hints). That approach is exhausted: further enriching `list`, `explain`, or `compare` with path detail makes those outputs wider without solving the focused lookup problem.
- The audit explicitly proposed `quantmap artifacts <campaign-id>` by name (section 9 and target UX architecture). The design intent is pre-established.
- A dedicated command gives a stable, testable, linkable noun for path discovery. It is purely additive — zero impact on existing command behavior.
- It keeps `list` as history/browsing and `artifacts` as path/status lookup, which is cleaner than overloading either.
- It also creates the right foundation for Sequence 3 (ACPM), where per-ACPM-run artifact lookup will be needed.

**The new command does not replace or alter `list`, `explain`, `compare`, or `export`.**

---

## 3. Exact Files and Surfaces Likely Affected

### Primary changes

| File | Change |
|---|---|
| `quantmap.py` | Register new `artifacts` subcommand with positional `campaign-id` argument; route to handler |
| `src/artifact_paths.py` | Verify/extend path resolution API to support per-campaign lookup of all four canonical artifact families; this is the query foundation for the new command |
| `src/ui.py` | Add `render_artifact_table(campaign_id, paths, statuses)` renderer for the new command and post-run block |
| `src/runner.py` | Add compact artifact path summary block at run completion (display-only; no logic change) |
| `src/report_campaign.py` | Fix artifact status projection: reconcile DB-recorded status with disk presence before writing status column |

### Secondary changes

| File | Change |
|---|---|
| `.agent/reference/command_reference.md` | Add `artifacts` command entry; keep in sync with parser |

### New test file

| File | Purpose |
|---|---|
| `test_cli_ux_artifact_discovery.py` | Tests for `artifacts` command: known campaign, unknown campaign, path presence rendering, not-found hint |

---

## 4. Explicit Out-of-Scope Items

- **ACPM namespace** (`quantmap acpm ...`) — Sequence 3; not this bundle
- **compare/explain not-found remediation and nearest-ID suggestions** — Sequence 4
- **full command-tree reorganization or subcommand nesting** — high blast radius; deferred
- **DB/schema changes** — no new columns, tables, or migrations
- **truth-lane or recommendation ownership changes** — hard boundary; not touched
- **`export` or `audit` surface changes** — not in this scope
- **vocabulary normalization in surfaces not being changed this bundle** — do not touch `explain`, `compare`, `export`, or `runner.py` status strings beyond the post-run path summary block
- **logger/operator output separation** — already partially addressed in Bundle 1 (`run --validate`); full separation across all surfaces is a separate concern
- **ACPM planning metadata or `acpm_planning.py`** — not touched

---

## 5. Blast Radius and Risks

### Low blast radius

- `quantmap artifacts` command: purely additive; no existing command behavior changes.
- `command_reference.md` update: documentation only.
- Post-run artifact path block in `runner.py`: display-only append at completion; does not change run flow, error handling, or exit codes.

### Moderate blast radius

- `src/artifact_paths.py` extension: if the existing API is extended rather than replaced, risk is low. Risk rises if the query logic for existing callers is altered. **Constraint: extend, do not refactor callers.**
- `src/ui.py` renderer addition: additive, but ui.py is shared. Verify no unintended style bleed to existing renderers.

### Highest risk in this bundle

- `src/report_campaign.py` artifact status projection fix: this touches report generation output. A wrong fix could make report content worse, not better. **Constraint: write a targeted test that exercises the projection path before and after the fix, and run `changed_path_verify.py` on this file.**
- Vocabulary normalization: applying a new set of status strings in `report_campaign.py` and `ui.py` while leaving other surfaces alone risks creating two valid vocabularies simultaneously. **Constraint: define the canonical set explicitly in a comment or constant block; apply only in changed surfaces this bundle.**

### Not a risk for this bundle

- ACPM truth lane — not touched
- RunPlan execution semantics — not touched
- Methodology snapshots — not touched

---

## 6. Smallest Strong Validation Plan

### Repo and changed-path checks (run in this order)

```powershell
.\\.venv\\Scripts\\python.exe .agent\\scripts\\helpers\\verify_dev_contract.py --quick
.\\.venv\\Scripts\\python.exe .agent\\scripts\\changed_path_verify.py --paths quantmap.py src\\artifact_paths.py src\\ui.py src\\runner.py src\\report_campaign.py .agent\\reference\\command_reference.md test_cli_ux_artifact_discovery.py
.\\.venv\\Scripts\\python.exe -m ruff check quantmap.py src\\artifact_paths.py src\\ui.py src\\runner.py src\\report_campaign.py test_cli_ux_artifact_discovery.py
.\\.venv\\Scripts\\python.exe -m pytest -q test_cli_ux_artifact_discovery.py
```

### Help smoke

```powershell
.\\.venv\\Scripts\\python.exe quantmap.py --help
.\\.venv\\Scripts\\python.exe quantmap.py artifacts --help
```

Verify: `artifacts` appears in top-level help with a clear one-line description; subcommand help shows `campaign-id` argument and expected output shape.

### Functional smoke

```powershell
# Known campaign — expect path table and presence status
.\\.venv\\Scripts\\python.exe quantmap.py artifacts B_low_sample__v512

# Unknown campaign — expect not-found message + list hint
.\\.venv\\Scripts\\python.exe quantmap.py artifacts does_not_exist_999

# Run completion path block — observe after a validate-only run
.\\.venv\\Scripts\\python.exe quantmap.py run --campaign B_low_sample --validate
```

### Report projection check

For a campaign where artifacts exist on disk and in DB, regenerate the campaign summary and confirm the artifact status table no longer shows `not generated` for present files.

```powershell
.\\.venv\\Scripts\\python.exe quantmap.py export --campaign B_low_sample__v512
```

Open generated `campaign-summary.md` and verify artifact status column matches disk presence.

### Acceptance criteria

| Check | Must Pass |
|---|---|
| `verify_dev_contract --quick` | yes |
| `changed_path_verify` on all touched paths | yes |
| `ruff check` on all touched Python | yes |
| `pytest -q test_cli_ux_artifact_discovery.py` | yes |
| `artifacts <known-id>` shows paths and presence | yes |
| `artifacts <bad-id>` shows not-found + list hint | yes |
| Post-run block appears at run completion | yes |
| Campaign summary artifact status no longer wrong for present files | yes |
| `command_reference.md` includes `artifacts` entry | yes |
| No existing subcommand behavior changed | yes |

---

## 7. Recommended Implementation Order

1. **`src/artifact_paths.py`** — audit the current API; extend or add a `get_artifact_paths(campaign_id, db)` function that returns a typed dict of path → disk-presence pairs for all four canonical artifact families. This is the data foundation everything else consumes.

2. **`src/ui.py`** — add `render_artifact_table(campaign_id, artifact_data)` that renders the path/status table in a format consistent with Bundle 1 UX conventions. Define canonical status constants here.

3. **`quantmap.py`** — wire the `artifacts` subcommand: parse `campaign-id`, call `artifact_paths.get_artifact_paths`, call `ui.render_artifact_table`, emit not-found hint if campaign not in DB.

4. **`src/runner.py`** — after run completion, call the same `artifact_paths` query and emit a compact path block using a brief version of the same renderer.

5. **`src/report_campaign.py`** — inspect the artifact status projection code; fix the reconciliation between DB-recorded status and disk presence. Apply canonical status strings defined in step 2.

6. **`test_cli_ux_artifact_discovery.py`** — write targeted tests: `artifacts` known/unknown ID, not-found hint text, projection fix regression test for `report_campaign.py`.

7. **`.agent/reference/command_reference.md`** — add `artifacts` entry.

8. **Run full validation suite** — as per section 6.

Steps 1–3 are the highest-value path and can be verified independently before steps 4–5 are added. Step 5 (projection fix) is the highest-risk step; do it after the additive steps are clean so any regression is isolated.

---

## `.agent` Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
- `.agent/reference/terminal_guardrails.md`
- `.agent/scripts/helpers/verify_dev_contract.py`
