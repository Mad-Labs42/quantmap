# Post-Run Review UX — Pre-Implementation Blast-Radius Audit

**Branch:** feat/post-run-review-ux
**Date:** 2026-04-26
**Scope:** Final campaign completion / post-run review screen for normal and ACPM runs.
**Hard constraints:** No YOLO persistence, no scoring changes, no DB schema changes, no telemetry changes, no trust-semantics changes.

---

## 1. Current Completion-Output Call Graph

### Entry Path A — `quantmap run --campaign <ID>`
```
quantmap.py: cmd_run(args)
  └─ runner.run_campaign(campaign_id, dry_run=False, ...)
       ├─ [dry_run=True]  → print dry-run summary block → return
       │                    (lines 1886–2010, runner.py)
       ├─ [measurement phase: _run_config loop]
       ├─ campaigns UPDATE status='complete'  (line 2562)
       ├─ console.print("Campaign {id} complete.")  (line 2569)
       ├─ [yolo_mode=True] → console.print YOLO banner  (lines 2572–2574)
       ├─ console.print("Running analysis and scoring...")  (line 2582)
       ├─ score_campaign()  ← src.score
       ├─ generate_report()  ← src.report  → console.print("Report written: ...")  (line 2709)
       ├─ generate_campaign_report()  ← src.report_campaign  → console.print("Run reports written: ...")  (line 2722)
       ├─ generate_metadata_json()  ← src.export  → console.print("Metadata written: ...")  (line 2774)
       ├─ [analysis failure] → console.print("Analysis failed ...")  (line 2804)
       └─ console.print(diagnostics path block)  (lines 2844–2848)
            └─ sys.exit(1) if not report_ok  (line 2853)
```

### Entry Path B — `quantmap acpm run --campaign <ID> --profile <P>`
```
quantmap.py: cmd_acpm_run(args)
  ├─ [dry_run=True] → ui.print_banner(...) + console.print(scope/values/cycles/scoring) → sys.exit(0)
  │                    (lines 667–676, quantmap.py)  — ACPM has its own dry-run block, does NOT call run_campaign
  ├─ console.print("Executing ACPM campaign...")  (line 678)
  └─ runner.run_campaign(campaign_id, dry_run=False, acpm_planning_metadata=..., scope_authority=...)
       └─ [identical path to Entry Path A above after this point]
```

### Key observations
- There are **two separate dry-run output blocks**:
  - `run_campaign(dry_run=True)` — handles `quantmap run --dry-run` (lines 1886–2010 in runner.py)
  - `cmd_acpm_run` inline block — handles `quantmap acpm run --dry-run` (lines 667–676 in quantmap.py)
- The **post-measurement final review block** in `run_campaign` (lines 2560–2853) is **100% shared** by both normal run and ACPM run. Both paths call `runner.run_campaign()` and land in the exact same code.
- The ACPM dry-run block in `quantmap.py` is entirely separate and not a candidate for the final-review improvement.

---

## 2. Files In Scope

### Primary change surface
| File | Role | Change type |
|------|------|-------------|
| `src/runner.py` | Contains the post-run output block (lines 2560–2853) | Move inline print statements into a dedicated render function |
| `src/ui.py` | Contains `render_artifact_block`, `print_next_actions`, `print_banner`, `format_status` | Add `render_post_run_review()` function here |

### Secondary surface (add/update tests only)
| File | Role |
|------|------|
| `test_cli_ux_yolo_review.py` | Update assertions to match new renderer, add normal+ACPM coverage |
| `test_cli_ux_acpm_run.py` | May need assertions about final output strings if they change |
| `test_cli_ux_guided_shell.py` | Depends on list/shell output, not final review — unlikely to change |
| `test_cli_ux_artifact_discovery.py` | Tests `render_artifact_block` — ensure not broken by ui.py additions |

---

## 3. Files Out of Scope

The following files **must not be modified** for this bundle. Any desired change touching these requires a separate design/risk pass.

| File | Reason |
|------|--------|
| `src/score.py` | Scoring — touching changes correctness/trust |
| `src/report.py` | Report generation — not display logic |
| `src/report_campaign.py` | Report generation — not display logic |
| `src/export.py` | Metadata export — not display logic |
| `src/trust_identity.py` | Trust semantics — changing this affects audit trail |
| `src/effective_filter_policy.py` | Policy authority — actively under review |
| `src/db.py` | Database schema and I/O — structural change |
| `src/telemetry.py` | Measurement infrastructure |
| `src/telemetry_policy.py` | Run readiness enforcement |

| `src/acpm_recommendation.py` | Recommendation authority |
| `src/governance.py` | Governance contracts |
| `src/run_plan.py` | Run plan data model |
| `quantmap.py` | CLI dispatch — do not change command structure or ACPM dry-run behavior |
| `src/server.py` | Server lifecycle |
| `src/measure.py` | Measurement execution |
| `src/analyze.py` | Analysis pipelines |

---

## 4. Reusable UI / Report / Artifact Helpers

These already exist in `src/ui.py` and should be used (not duplicated) in any new renderer:

| Helper | Location | Purpose |
|--------|----------|---------|
| `render_artifact_block(campaign_id, artifacts, target_console)` | `ui.py:316–348` | Renders canonical 4-artifact status block with ✓/✗/⚠ and paths |
| `print_next_actions(actions, title, target_console)` | `ui.py:300–313` | Renders a consistent "Next actions" block with `SYM_INFO` bullets |
| `print_banner(text, style, target_console)` | `ui.py:279–288` | Consistent section header with divider |
| `format_status(label, passed, detail)` | `ui.py:290–297` | Formats a single ✓/✗ status line with dim detail |
| `get_console()` | `ui.py:243–277` | Returns the global capability-aware console instance |
| `SYM_OK`, `SYM_WARN`, `SYM_FAIL`, `SYM_INFO` | `ui.py:48–53` | Symbol constants (UTF-8 vs ASCII fallback) |
| `get_campaign_artifact_paths(lab_root, campaign_id, db_path)` | `artifact_paths.py:286–330` | Returns enriched 4-artifact list from DB + filesystem — the correct data source for `render_artifact_block` |

**Critical:** `render_artifact_block` already exists and is already tested in `test_cli_ux_artifact_discovery.py`. The post-run review should use it directly rather than repeating inline artifact path prints.

**Currently not used in post-run review:** `render_artifact_block` and `print_next_actions` are tested standalone but are not called from within `run_campaign`'s final block. This is the primary gap.

---

## 5. Current Test Coverage Found

| Test file | What it covers | Relevance |
|-----------|---------------|-----------|
| `test_cli_ux_yolo_review.py` | Final review YOLO output; internal diagnostics text; artifact log path | **Directly relevant** — will require updates if render is centralized |
| `test_cli_ux_artifact_discovery.py` | `render_artifact_block` output for complete/missing/present states; `quantmap artifacts` CLI | **Directly relevant** — tests the helper we will call |
| `test_cli_ux_acpm_run.py` | ACPM run dry-run, validate, error paths — subprocess-based | **Relevant** — tests show ACPM dry-run is in `quantmap.py`, not runner |
| `test_cli_ux_guided_shell.py` | `list_campaigns` output, `--help` structure, logging setup | Peripheral |
| `test_artifact_contract.py` | Canonical 4-artifact constants, path resolution | Out of scope for UX — indirectly confirms contract stability |
| `test_acpm_slice*.py` | ACPM planning/compilation | Not UX-layer coverage |

---

## 6. Test Coverage Missing (Should Be Added With This Bundle)

### Must-have
1. **Normal run → post-run output structure** — A mocked `run_campaign` test (like `test_cli_ux_yolo_review.py`) that asserts:
   - "Campaign X complete." is present
   - "Running analysis and scoring..." is present  
   - "Report written:" is present
   - "Run reports written:" is present
   - "Metadata written:" is present
   - Diagnostics path block is present
   - No YOLO text present
2. **ACPM run → same final block shared** — verify that calling `run_campaign` with `acpm_planning_metadata` set produces the same post-run structure (the ACPM path does not diverge after measurement)
3. **Analysis failure branch** — assert that "Analysis failed (raw data is safe...)" text appears when scoring raises an exception
4. **dry-run output structure (normal run)** — assert that the dry-run summary block contains required sections: "DRY RUN —", "Mode:", "Configs to test:", "Cycles per config:", etc.

### Nice-to-have
5. `print_next_actions` renders correctly in final-review context (once added)
6. `render_artifact_block` is called and output contains canonical artifact labels in final review
7. Report-failure vs analysis-failure distinction (different DB status paths)

---

## 7. Risk Areas and Recommended Guardrails

### Risk 1 — Changing text strings that tests assert on
**Severity: HIGH**
`test_cli_ux_yolo_review.py` has hard string assertions on:
- `"Internal diagnostic files were retained for debugging."`
- `"By default, they are not included in the user-facing artifact list."`
- `"If you would like to view them, you may do so at:"`
- The log path containing `logs\test_model\test_camp`

If the render is centralized into `ui.py`, these strings must be preserved verbatim **or** tests updated atomically with the rename.

**Guardrail:** Run `pytest -q test_cli_ux_yolo_review.py` after every refactor step.

### Risk 2 — `artifact_dir` call in the diagnostics block raises an exception
**Severity: MEDIUM**
The current diagnostics path block (runner.py lines 2836–2851) is wrapped in `try/except`. It calls `artifact_dir(lab_root, "logs", model_identity, effective_campaign_id, create=False)`. If `model_identity` is `None` or path construction fails, it silently swallows the exception and skips the print.

Any refactoring that moves this call must preserve the `try/except` wrapper. If the wrapper is removed or the exception surface broadens, the diagnostics block could crash the final review.

**Guardrail:** Keep `try/except` around the diagnostics path call; log the exception if it fires.

### Risk 3 — `sys.exit(1)` after `not report_ok` must survive any refactor
**Severity: HIGH**
Line 2853: `if not report_ok: sys.exit(1)`. This is the contract that CI and automation detect a failed analysis/report pipeline. If the post-run block is refactored and this exit is accidentally moved inside the new renderer (which would not be reachable from the runner), CI could silently exit 0 after a failed report.

**Guardrail:** The `sys.exit(1)` must remain **in `runner.py`**, not inside the UI renderer. The renderer should return values or raise, never call `sys.exit`.

### Risk 4 — Double-rendering if both the old inline prints and the new renderer fire
**Severity: HIGH**
If the existing `console.print("Report written: ...")` calls are not removed when the new renderer is added, the final screen will duplicate those lines.

**Guardrail:** Remove every `console.print` from the post-run block that will be replaced by the renderer, atomically in the same commit.

### Risk 5 — `report_ok`/`v2_ok` state flags consumed by renderer but defined in runner
**Severity: MEDIUM**
The renderer needs to know whether report/run-reports/metadata succeeded or failed. These flags (`report_ok`, `v2_ok`) are currently local variables inside `run_campaign`. If the renderer function is in `ui.py`, the runner must pass this state explicitly.

**Guardrail:** Define a small `PostRunSummary` dataclass or a plain dict with the required fields and pass it to the renderer. Do not let the renderer query the DB — let the runner resolve state and hand it off.

### Risk 6 — ACPM vs normal run final output divergence
**Severity: LOW**
The ACPM run calls `runner.run_campaign(acpm_planning_metadata=...)` with extra metadata. The final review block is currently identical for both. If the redesign adds ACPM-specific context (e.g., showing the ACPM profile used) it needs to decide whether that context comes from `acpm_planning_metadata` or from the post-scoring DB state.

**Guardrail:** For this bundle, the final review block should remain identical for normal and ACPM paths. ACPM-specific augmentation is a separate, future feature.

### Risk 7 — Artifact block relies on filesystem state at render time
**Severity: LOW**
`get_campaign_artifact_paths` does filesystem discovery and DB lookups at call time. If called at the end of `run_campaign` before files are fully flushed, it may show "not found" for files that were just written. This is a pre-existing condition.

**Guardrail:** This is acceptable for now. The YOLO review tests already mock artifact paths rather than real filesystem state, so tests will be stable regardless.

### Risk 8 — Rich markup tag escaping
**Severity: LOW**
The existing diagnostics path block uses f-string interpolation with `[dim]...[/dim]` tags. Paths containing `[` or `]` characters could corrupt Rich markup. This is a pre-existing risk in the current code.

**Guardrail:** Use `rich.markup.escape()` on any user-supplied path strings when embedding them in Rich markup strings. This is a net improvement — not a regression risk.

---

## 8. What Is UI-Only vs. What Requires a Separate Pass

### ✅ Safe as UI-only changes (this bundle)
- Centralizing the post-run print block into `ui.render_post_run_review()`
- Calling `render_artifact_block` to replace the individual "Report written: / Run reports written: / Metadata written:" prints
- Calling `print_next_actions` with suggested follow-up commands (`quantmap explain`, `quantmap artifacts`, `quantmap list`)
- Improving the internal diagnostics wording/path presentation
- Adding section headers (e.g., "Campaign Summary" for the artifact block)
- Making the completion line more prominent
- Adding missing test coverage for normal-run and failure-path output

### ⛔ Requires a separate design/risk pass (out of scope)
| Desired improvement | Why out of scope |
|--------------------|-----------------|
| Show YOLO mode context in final review | Requires YOLO persistence to DB — trust semantics |
| Show ACPM profile/tier used in final review | Would require reading `acpm_planning_metadata` from DB post-run, or changing the run_plan snapshot — schema change |
| Interactive post-run menu (explain / compare / artifacts) | Requires stdin interaction in a non-interactive-safe way — needs separate UX design |
| Showing scores/ranking in the final screen | Requires exposing score data from `score_campaign()` result — risk of misleading display if analysis failed partially |
| Showing run quality tier (quick/standard/full) in review | Run plan data is available, so this is borderline — but changing the footer wording risks breaking test assertions; do as a targeted follow-on |
| Changing artifact labels/blurbs | Would break `test_cli_ux_artifact_discovery.py` assertions unless updated atomically; acceptable but must be a deliberate, coordinated change |

---

## 9. Recommendation

**Proceed with implementation.** This bundle is safe as a UI-only change.

### Smallest safe implementation slice

**Step 1 — Create `ui.render_post_run_review()`**
- Accept: `campaign_id`, `report_ok`, `v2_ok`, `diagnostics_path`, `yolo_mode`, `target_console`
- Render: completion banner, artifact block (via `render_artifact_block`), diagnostics path, YOLO notice if active, (optionally) next-actions block
- No `sys.exit` — return nothing, let caller handle exit
- Live in `src/ui.py`

**Step 2 — Refactor `run_campaign` post-run block**
- Build `PostRunSummary` data (or plain dict) from existing `report_ok`, `v2_ok`, `_eff_diagnostics_folder` locals
- Call `ui.render_post_run_review(...)` in place of the existing inline prints
- Remove inline `console.print("Report written: ...")`, `console.print("Run reports written: ...")`, `console.print("Metadata written: ...")` prints
- **Preserve** `sys.exit(1) if not report_ok` in runner.py
- **Preserve** the `try/except` around the diagnostics path resolution

**Step 3 — Add/update tests**
- Update `test_cli_ux_yolo_review.py` assertions to match the new renderer output
- Add `test_cli_ux_post_run_review.py` with:
  - normal run (no YOLO) — asserts complete text, diagnostics block, no YOLO text
  - failed analysis — asserts "Analysis failed" text, no artifact block
  - (optional) ACPM run produces same output structure

### Watch-outs
1. `sys.exit(1)` must remain in runner.py, not in the UI renderer.
2. Remove every old inline print that the new renderer replaces — no duplication.
3. Preserve `try/except` around the `artifact_dir` call for the diagnostics path.
4. All four canonical artifact labels/blurbs must remain unchanged in their string values if any test asserts on them.
5. Run the full test suite after the refactor — 133 tests must pass.

---

## Appendix A — Commands Run During Audit

```powershell
Select-String -Path quantmap.py -Pattern "run_campaign" | Select-Object LineNumber, Line
Select-String -Path src/effective_filter_policy.py -Pattern "scoring_confirmation" | Select-Object LineNumber, Line
New-Item -ItemType Directory -Force -Path "docs\Plans\Post-Run-Review-UX"
```

## Appendix B — Agent Files Used

- `.agent/policies/project.md` — repo purpose and success criteria
- `.agent/policies/testing.md` — validation depth and narrow-first order

---

## Appendix C — Files Directly Read During Audit

| File | Lines reviewed | Purpose |
|------|---------------|---------|
| `src/runner.py` | 1660–2010, 2540–2870 | Complete post-run output flow |
| `src/ui.py` | 1–349 (full) | All existing UI helpers |
| `src/artifact_paths.py` | 1–331 (full) | Artifact constants and `get_campaign_artifact_paths` |
| `quantmap.py` | 180–260, 620–692 | `cmd_run` and `cmd_acpm_run` entry points |
| `test_cli_ux_yolo_review.py` | 1–99 (full) | Current final review test coverage |
| `test_cli_ux_acpm_run.py` | 1–125 (full) | ACPM run test coverage |
| `test_cli_ux_guided_shell.py` | 1–159 (full) | Guided shell test coverage |
| `test_cli_ux_artifact_discovery.py` | 1–151 (full) | Artifact discovery and render_artifact_block coverage |
