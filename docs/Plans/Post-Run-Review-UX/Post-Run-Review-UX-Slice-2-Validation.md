# Post-Run Review UX Slice 2 — Validation Note

**Date:** 2026-04-26
**Branch:** feat/post-run-review-ux-slice-2
**Bundle:** Cleanup final-output duplication and add explicit outcome language.

---

## Files Changed

| File | Change type |
|------|-------------|
| `src/runner.py` | Wrapped generation phase in `console.status`; removed inline "Report written" prints; passed `failure_cause` and `failure_remediation` to renderer on failure. Updated `failure_cause` to "Post-campaign analysis failed." and simplified remediation to "Run 'quantmap rescore' to retry analysis." |
| `src/ui.py` | Added explicit outcome string blocks for success, failure with known cause, and failure with unknown cause; consolidated diagnostics message. Updated remediation string to use "Suggested fix:". |
| `test_cli_ux_post_run_review.py` | Added unit tests asserting correct outcome text, missing/present remediation advice, and diagnostics printing on failure. |

---

## Exact UX Behavior Changed

1. **Removed Output Duplication:** The inline `[green]Report written: ...` sequential prints have been removed from `runner.py`.
2. **Added Live Generation Spinner:** The report and artifact generation phase is now wrapped in `with console.status("Generating artifacts..."):`, preserving live feedback without leaving clutter in the final scrollback.
3. **Explicit Outcome Language:** `render_post_run_review` now prints the exact required success/failure phrasing.

### Exact Wording Contract Validated

**Success:**

```text
All requested campaigns ran successfully.
```

**Known failure:**

```text
Error: QuantMap could not execute the requested campaigns.

We identified the following blocker(s):

- Cause: <known cause>.
  Suggested fix: <specific remediation advice>.
```

*(Followed by diagnostics path)*

**Unknown failure:**

```text
Error: QuantMap could not execute the requested campaigns.

Cause: Unknown.
Internal diagnostics may help diagnose the issue: <path>
```

---

## Deferred Features & Limitations

**Partial/Mixed Campaign Outcome:** 
Currently, QuantMap's `runner.py` boundary executes only a single `campaign_id` per run. The runner state does not expose a trustworthy per-requested-campaign success/failure list. Therefore, we do not fake multi-campaign aggregation. The mixed campaign outcome text is explicitly **deferred** until a future bundle when the runner boundary is extended to natively support and distinguish results for multiple requested campaigns simultaneously.

---

## Exact Behavior Intentionally Not Changed

- **Exception handling:** Did not change `try`/`except` boundaries or swallow exceptions inside the `console.status` block.
- **Process Exit (`sys.exit`):** Exit logic remains untouched in `runner.py`.
- **Artifact Generation / Scoring:** Did not change the logic, metrics, schema, DB writes, or trust mechanics.
- **YOLO Behavior:** Preserved dormant YOLO logic. Output only changes if `yolo_mode=True` is explicitly passed. Normal runs remain silent regarding YOLO.
- **ACPM Paths:** Left untouched.

---

## Final String Scan

A case-insensitive regex scan across `src/runner.py`, `src/ui.py`, and `test_cli_ux_post_run_review.py` for:
`Quantmap|Report written:|Run reports written:|Metadata written:|Analysis failed|Failure reason unavailable|Raw data is safe`
returned 0 instances of improper product capitalization, and 0 matches for legacy wording strings that were requested to be removed. The only match for `Analysis failed` was the valid, intentional logging context `"Post-campaign analysis failed: %s"`.

---

## Validation Commands and Results

```powershell
# Targeted checks
.\.venv\Scripts\python.exe -m ruff check src/ui.py src/runner.py test_cli_ux_yolo_review.py test_cli_ux_post_run_review.py
→ All checks passed!

.\.venv\Scripts\python.exe -m mypy quantmap.py
→ Success: no issues found in 1 source file

# Targeted tests
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_post_run_review.py test_cli_ux_yolo_review.py test_cli_ux_artifact_discovery.py
→ 24 passed in 1.26s

# Full test suite
.\.venv\Scripts\python.exe -m pytest -q
→ 149 passed in ~16s

# Git Working Tree Status
git diff --check
→ Clean
```

---

## Agent Files Used

- `.agent/policies/project.md`
- `.agent/policies/testing.md`

## PR Review Fixes (Post-Run Review UX Slice 2 Cleanup)

**Exact Files Changed:**

- `docs/AUDITS/Post-Run-Review-UX/Post-Run-Review-UX-Slice-2-Blast-Radius-Audit.md`
- `src/runner.py`
- `src/ui.py`
- `test_cli_ux_post_run_review.py`

**Exact Review Findings Fixed:**

1. **Audit Doc Staleness:** Added a prominent disclaimer to the top of the blast-radius audit, explicitly marking it as historical and superseded by this validation note, and warning that the inline prints and winner-line discussions are stale.
2. **Docstring Update:** Added missing `Args` entries for `failure_cause` and `failure_remediation` to the `render_post_run_review` docstring in `src/ui.py`.
3. **Punctuation Normalization:** Implemented a `_norm` helper in `src/ui.py` to deterministically handle terminal punctuation for causes and fixes, ensuring no doubled periods and appending one if missing. Also updated "Suggested next step:" to "Suggested fix:".
4. **Wording Contract:** Removed "Raw data is safe." from `src/runner.py` and changed the failure cause string to "Post-campaign analysis failed." to match the exact wording contract. Updated tests to expect the new strings.
5. **Whitespace-only Failure Cause:** Updated `src/ui.py` to treat whitespace-only `failure_cause` as an unknown failure, computing a stripped value early in the renderer.

**Sonar New Issue Disposition:**

The SonarCloud new issue was addressed by correctly documenting the new parameters in the docstring and ensuring clean logic flow for the punctuation normalizer.

**Validation Commands & Results:**

- `ruff check`: All checks passed.
- `mypy quantmap.py`: Success, no issues found.
- Targeted `pytest`: 24 passed in 1.26s.
- Full `pytest`: 149 passed cleanly.
- `git diff --check`: Clean.

**Final String Scan:**

A regex scan for `Quantmap|Report written:|Run reports written:|Metadata written:|Failure reason unavailable|Raw data is safe` returned only valid, properly cased usages (`QuantMap`, `quantmap`) and 0 instances of the banned legacy strings.

**Agent Files Used:**

- `.agent/policies/project.md`
- `.agent/policies/testing.md`

**Remaining Risks:**

Mixed/partial multi-campaign post-run outcome aggregation is intentionally deferred.
`runner.py` currently processes one `campaign_id` per invocation and does not expose a
trustworthy per-requested-campaign success/failure list. This has no impact on current
single-campaign Slice 2 behavior, but any future bundle that introduces multi-campaign
execution will need explicit aggregation semantics before the partial-outcome wording
contract can be implemented.

---

## Final Blocker Cleanup Pass

**Exact Files Changed:**

- `src/ui.py`
- `docs/Plans/Post-Run-Review-UX/Post-Run-Review-UX-Slice-2-Validation.md`

**Exact Blockers Fixed:**

1. **Rich Markup Escaping:** Added `from rich.markup import escape as _escape` inside the
   `failure_cause_stripped` branch of `render_post_run_review`. Dynamic `failure_cause`
   and `failure_remediation` text is now escaped before interpolation, preventing any
   brackets in caller-supplied strings from being interpreted as Rich markup tags. Static
   markup strings (`[bold red]`, `[dim]`) are unchanged.
2. **Validation doc — fenced block language:** Changed bare fences to ` ```text ` and
   added blank lines before and after each block (MD031/MD022).
3. **Validation doc — Known failure period:** Added the missing trailing period to the
   `Suggested fix: <specific remediation advice>.` example line.
4. **Validation doc — Remaining Risks:** Replaced "None" with a factual note that
   multi-campaign outcome aggregation is intentionally deferred.

**Validation Commands & Results:**

- `ruff check src/ui.py test_cli_ux_post_run_review.py`: All checks passed.
- `mypy quantmap.py`: Success, no issues found in 1 source file.
- Targeted `pytest` (post-run review + yolo): 18 passed in 1.45s.
- Full `pytest`: 149 passed in 17.28s.
- `git diff --check`: Clean.

**Final String Scan:**

Scan for `Quantmap|Report written:|Run reports written:|Metadata written:|Failure reason unavailable|Raw data is safe` returned 0 banned-string matches.

**Agent Files Used:**

- `.agent/policies/project.md`
- `.agent/policies/testing.md`
