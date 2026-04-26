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
```
All requested campaigns ran successfully.
```

**Known failure:**
```
Error: QuantMap could not execute the requested campaigns.

We identified the following blocker(s):

- Cause: <known cause>.
  Suggested fix: <specific remediation advice>
```
*(Followed by diagnostics path)*

**Unknown failure:**
```
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
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_post_run_review.py test_cli_ux_yolo_review.py
→ 18 passed in ~1s

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
