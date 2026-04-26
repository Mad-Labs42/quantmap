# Post-Run Review UX Slice 2 — Blast-Radius Audit

**Branch:** feat/post-run-review-ux-slice-2
**Date:** 2026-04-26
**Scope:** Determining the safest next UX improvement for the final post-run review screen without violating production constraints.

---

## 1. Current State

**Final Review Screen Behavior (`render_post_run_review`):**
Currently prints:
- YOLO warning (conditionally, if explicitly activated by caller).
- The Canonical Artifact Block (via `render_artifact_block`), showing presence and database status for the 4 core artifacts.
- A "Next actions" block with static, copy-pasteable CLI commands (only if `report_ok=True`).
- A Diagnostics path notice (if `diagnostics_path` is present).

**Inline Runner Output (`runner.py`):**
Before the final review screen appears, `runner.py` prints:
- `Campaign {id} complete.`
- `Running analysis and scoring...`
- `Report written: {path}`
- `Run reports written: {path}`
- `Metadata written: {path}`
- (On failure): `Analysis failed (raw data is safe...)`

**Output Duplication:**
There is distinct UX duplication. Artifact paths are printed inline sequentially as they generate, and then printed *again* in the final artifact block.

**User Experience:**
- **Success:** The user sees the sequential "written" prints, followed immediately by the structured artifact block and next actions.
- **Failure:** The user sees "Analysis failed", followed by the diagnostics block. Because of our Slice 1 fix, the artifact block will accurately reflect `failed`/`not found` for artifacts that the current run failed to generate.

## 2. Artifact UX Findings

- **Completeness & Determinism:** The artifact block is complete, canonical, and fully deterministic. It utilizes existing helper functions (`get_campaign_artifact_paths` and `render_artifact_block`).
- **Staleness:** Slice 1 explicitly eliminated stale artifact status by cross-referencing the `report_ok`/`v2_ok`/`meta_ok` flags before rendering.
- **Verdict:** The artifact presentation is technically sound. No new paths or generation semantics should be added.

## 3. Next-Actions UX Findings

- **Current UX:** Prints static string commands (`quantmap explain ...`, `quantmap artifacts ...`, `quantmap list`).
- **Assessment:** This is perfectly safe, non-interactive guidance. It is highly beneficial for operator onboarding.
- **Interactive Menu:** Proposing an interactive terminal menu (e.g., prompt-toolkit or `rich.prompt`) is **explicitly out of scope** for Slice 2. It introduces significant complexity regarding TTY handling, CI/CD compatibility, and dry-run boundaries.

## 4. Outcome Summary Findings

- **Current State:** The final screen currently reports *process success* (via artifact presence) but *not campaign outcome* (e.g., which config won).
- **Assessment:** Adding a lightweight "Outcome Summary" (e.g., "Winner: X" or "Winner: None (Baseline retained)") is theoretically safe because `runner.py` already receives the `scores` dictionary from `score_campaign()` (which contains the `winner` key).
- **Risk:** We must **not** introduce interpretation or trust claims. The runner should simply pass `scores.get("winner")` to the renderer. 
- **Verdict:** It is safe to add a single outcome line indicating the winner, provided we rely solely on the existing validated `scores` dictionary.

## 5. ACPM / Dry-Run Considerations

- **ACPM Path:** ACPM "real runs" funnel completely through `runner.run_campaign()` and thus receive the exact same final screen naturally. There is no divergence, and we should not invent ACPM-specific final screen behavior at this stage.
- **Dry-Run:** The dry-run output blocks (both in `runner.py` and `quantmap.py` for ACPM) exit early and are fully isolated from `render_post_run_review`.

## 6. Risk Surfaces / Do Not Touch

If we proceed with Slice 2, the following rules apply:
- **Presentation-Only:** `src/ui.py` and print statements in `src/runner.py`.
- **Test-Only:** `test_cli_ux_post_run_review.py`, `test_cli_ux_yolo_review.py`.
- **Do Not Touch (High Risk):** 
  - `src/score.py`
  - `src/db.py`
  - `src/telemetry.py`
  - `src/artifact_paths.py`
  - `src/report.py`
  - Any process-exit behavior (`sys.exit`).
  - YOLO semantics (must remain dormant).

## 7. Recommended Slice 2

I recommend the following "Smallest Safe Slice 2":

1. **Resolve Output Duplication (UX Polish):** 
   - Remove the sequential `console.print("Report written: ...")` statements in `runner.py`. 
   - *Optional but recommended:* Wrap the generation phase in a `with console.status("Generating artifacts..."):` block so the user still gets live feedback without polluting the final terminal scrollback.
2. **Add Lightweight Outcome Display:**
   - Pass the `winner_id` (from `scores.get("winner")`) to `render_post_run_review`.
   - Have the renderer print a single static line (e.g., "Outcome: Winner is {winner_id}" or "Outcome: Baseline retained").

**Explicit Non-Goals:**
- No interactive prompts.
- No YOLO activation/persistence.
- No ACPM profile display.

## 8. Required Tests & Validation

**Tests Needed:**
- Update `test_cli_ux_post_run_review.py` to assert the presence of the new Outcome string when a winner is passed.
- Update `test_cli_ux_yolo_review.py` to ensure the overall terminal output matches the new deduped flow (i.e., verifying the inline prints are gone).

**Validation Commands:**
```powershell
.\.venv\Scripts\python.exe -m ruff check src/ui.py src/runner.py
.\.venv\Scripts\python.exe -m mypy src/ui.py src/runner.py
.\.venv\Scripts\python.exe -m pytest -q test_cli_ux_post_run_review.py test_cli_ux_yolo_review.py
```

## 9. Open Decisions

Before implementation begins, the product owner must decide:
1. **Spinner vs Silence:** Are we comfortable using `rich.console.status` for the generation phase, or should we remain completely silent between `Running analysis...` and the final artifact block?
2. **Outcome Explicitness:** Is stating `Outcome: Winner is {X}` sufficient, or do we prefer strict minimalism ("nothing beyond success/failure and artifact status")?

## 10. Agent Files Used
- Implicitly relied on `.agent/policies/project.md` (for understanding constraints around trust and reporting).
- Implicitly relied on `.agent/policies/testing.md` (for framing the validation plan).
