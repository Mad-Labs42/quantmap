# Post-Run Review UX — Validation Note (Cleanup Pass)

**Date:** 2026-04-26
**Branch:** feat/post-run-review-ux
**Bundle:** Cleanup pass — doc location corrections + artifact block population

---

## Files Changed

| File | Change type |
|------|-------------|
| `src/runner.py` | Added `get_campaign_artifact_paths` to imports; added artifact discovery + `artifacts=_artifact_list` arg to `render_post_run_review` call |
| `src/ui.py` | Added `render_post_run_review()` (from prior pass — unchanged in this pass) |
| `test_cli_ux_yolo_review.py` | Added `get_campaign_artifact_paths` monkeypatch; added `test_artifact_block_populated_in_post_run_review` |
| `test_cli_ux_post_run_review.py` | New (from prior pass — unchanged in this pass); 11 unit tests for the renderer in isolation |
| `docs/Plans/Post-Run-Review-UX/Post-Run-Review-UX-Validation.md` | This file — moved from incorrect location; replaces `docs/AUDITS/CLI-audit/post-run-review-ux-validation.md` |
| `docs/AUDITS/Post-Run-Review-UX/Post-Run-Review-UX-Blast-Radius-Audit.md` | Moved from `docs/Plans/Post-Run-Review-UX/Post-Run-Review-UX-PRE-Implementation-Blast-Radius.md` |

### Files deleted
- `docs/AUDITS/CLI-audit/post-run-review-ux-validation.md` (incorrect location — replaced by this file)
- `docs/Plans/Post-Run-Review-UX/Post-Run-Review-UX-PRE-Implementation-Blast-Radius.md` (incorrect location — moved to AUDITS)

---

## Exact Behavior Changed

### `src/runner.py`
- Added `get_campaign_artifact_paths` to the `src.artifact_paths` import block.
- After all artifact writers finish and before `render_post_run_review`, runner now calls:
  ```python
  _artifact_list = get_campaign_artifact_paths(
      _effective_lab_root, effective_campaign_id, db_path=_eff_db_path
  )
  ```
  This is a **read-only** DB + filesystem discovery call. No writes, no schema changes.
- `_artifact_list` (or `None` on exception) is passed as `artifacts=` to `render_post_run_review`.
- The artifact block now appears in the final review screen after a real run.

### `test_cli_ux_yolo_review.py`
- `_run_mocked_campaign` now also monkeypatches `runner.get_campaign_artifact_paths` to return a fixed single-artifact list.
- New test `test_artifact_block_populated_in_post_run_review` asserts `"campaign_summary_md"` and `"Artifacts"` appear in final review output.

---

## Exact Behavior Intentionally Not Changed

- `sys.exit(1)` on `not report_ok` — remains in `runner.py`, not in the renderer
- Progress prints (`"Report written:"`, `"Running analysis and scoring..."`, etc.) — unchanged in `runner.py`
- `"Campaign {id} complete."` — unchanged
- `"Analysis failed (raw data is safe..."` — unchanged
- Scoring, telemetry, DB writes, artifact generation, report generation — none touched
- ACPM dry-run and normal run dry-run paths — not touched
- YOLO: remains dormant unless `yolo_mode=True` is explicitly passed by caller
- Existing YOLO/no-YOLO test assertions — all pass unchanged
- `render_artifact_block` — not modified
- `get_campaign_artifact_paths` — not modified; called read-only after all writers finish

---

## Artifact Block Population

**Is the canonical artifact block now populated from real artifact discovery?**

Yes. `runner.py` calls `get_campaign_artifact_paths(_effective_lab_root, effective_campaign_id, db_path=_eff_db_path)` after all four artifact writers have finished (`generate_report`, `generate_campaign_report`, `generate_metadata_json`, raw telemetry). The function reads the DB `artifacts` table rows (written by each generator) and resolves filesystem presence. The result is passed to `render_post_run_review(artifacts=...)` which calls `render_artifact_block`. The discovery call is wrapped in `try/except` — on any failure, `_artifact_list=None` is passed and the artifact block is silently omitted.

---

## PR Review Fixes

- consolidated duplicate artifact-status override branches into an artifact-type/ok-flag map
- no behavior change intended

---

## Validation Commands and Results

```
# Targeted lint
.\.venv\Scripts\python.exe -m ruff check src/ui.py src/runner.py test_cli_ux_yolo_review.py test_cli_ux_post_run_review.py
→ All checks passed!

# Targeted tests
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_yolo_review.py test_cli_ux_post_run_review.py
→ 14 passed in 1.00s

# Full suite
.\.venv\Scripts\python.exe -m pytest -q
→ 145 passed in 13.57s   (133 original + 12 new: 11 post_run_review unit tests + 1 artifact block integration test)
```

---

## Agent Files Used

- `.agent/policies/project.md`
- `.agent/policies/testing.md`

---

## Remaining Risks / Follow-Up Bundles

### Not in scope for this bundle (by design)
1. **YOLO persistence** — `yolo_mode` is dormant plumbing. Persisting it touches trust metadata and campaign start snapshot. Requires a scoped bundle.
2. **Interactive post-run menu** — Not implemented. Future bundle.
3. **ACPM-specific final screen context** — ACPM real runs share the identical final review via `run_campaign()`. If the ACPM profile/tier should appear in the review, that requires passing `acpm_planning_metadata` through. Separate bundle.
4. **Artifact SHA / verification status display** — `render_artifact_block` shows path and DB status but not SHA. SHA is available from the artifact list. Enhancement for a future polish pass.
5. **Winner/best-config summary** — No scoring interpretation in the renderer. Explicitly deferred.
