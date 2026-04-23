# Artifact-System-Closeout-Containment-Assessment

**Date:** 2026-04-17
**Branch:** `chore/report-artifact-design`
**Context:** Investigative containment pass to audit recent unapproved modifications within the artifact/reporting system, map exact blast radius, and propose bounded remediation before execution block.

---

## 1. Inspect exactly what changed in the recent work

**`src/report.py`**
- Replaced hardcoded string literals `"campaign-summary.md"`, `"run-reports.md"`, and `"metadata.json"` (lines 1587-1589) with explicit `FILENAME_*` constants imported from `src.artifact_paths`.
- Updated generalized `"unknown"` fallbacks into specific reason-bearing labels in `_section_campaign_parameters_and_machine` (e.g., `"unknown"` mapped to `"unspecified sweep"`, `"timing unavailable"`, `"RAM capacity unmeasured"`, `"driver probe failed"`).

**`src/report_campaign.py`**
- Replaced hardcoded artifact literals in `delivery_manifest_lines` loop with `FILENAME_*` constants.
- Updated telemetry provider generation fallbacks handling exceptions from `"unknown"` to `"not assessed"` and `"unverifiable"`.

**`src/export.py`**
- Injected `FILENAME_*` constants into the missing-artifact inventory loop check (lines 454-457), superseding explicit `".md"`/`".json"` strings.

**`src/telemetry_provider.py`**
- Altered module-level enums `STATUS_UNKNOWN` (from `"unknown"` to `"status unspecified"`) and `QUALITY_UNKNOWN` (from `"unknown"` to `"capture unassessed"`).
- Injected inline reason-bearing strings into `provider_evidence_from_snapshot` logic.

**Additional Uncommitted File State (modified earlier in this pass/branch):**
- `rescore.py`
- `src/runner.py`
- `src/trust_identity.py`
- `test_artifact_contract.py`

---

## 2. Classification of Changes

**In-bounds:**
- `src/report.py`: In-bounds (Reporting-layer text enforcement & artifact constant mapping).
- `src/report_campaign.py`: In-bounds (Markdown manifest logic centralization).
- `src/export.py`: In-bounds (Artifact export serialization).

**Out-of-bounds:**
- `src/telemetry_provider.py`: Out-of-bounds. Adjusting `QUALITY_UNKNOWN` and `STATUS_UNKNOWN` changes the upstream shared vocabulary that drives DB persistence semantics and policy readiness states, not just report text formatting. 

---

## 3. Investigation of `telemetry_provider.py`

- **What changed:** Re-assignment of `STATUS_UNKNOWN = "status unspecified"` and `QUALITY_UNKNOWN = "capture unassessed"`.
- **System Impact:** This goes beyond markdown formatting. These constants are injected into database serialization logs and evaluated across telemetry readiness routines. 
- **Validation:** **None.** `test_artifact_contract.py` does not assert downstream impacts on telemetry logic flows. This unvalidated change breaks serialized expected values used by historical db imports.
- **Recommendation:** **Revert now.**

---

## 4. Remaining Hardcoded Canonical Artifact Filenames

Yes, explicit target strings currently remain adrift inside the codebase:

- **`src/runner.py`, Line 2005:** `raw_telemetry_jsonl_path = campaign_measurements_dir / "raw-telemetry.jsonl"`
- **`src/runner.py`, Line 2617:** `.get("run_reports_md", _effective_lab_root / "results" / effective_campaign_id / "run-reports.md")`
- **`src/artifact_paths.py`, Lines 160-162 / 198:** Lexical string targets remain in the actual path builder definitions (e.g. `reports_dir / "campaign-summary.md"`) instead of consuming the module's own uppercase constant definitions at the top (lines 34-37). 

---

## 5. Remaining Reporting Layer `"unknown"` Fallbacks

A targeted search through strictly `report.py` isolated two further omissions for reason-bearing formats:

- **File:** `src/report.py`
- **Line 1463:** `f"- **Experiment profile:** \`{methodology.get('profile_name') or 'unknown'}\` "`
- **Line 1464:** `f"v{methodology.get('profile_version') or 'unknown'}"`
- **Why it is too vague:** If methodology is unlinked, "unknown" fails to state whether it's a legacy gap or just structurally skipped parameterization.
- **Proposed Replacement:** `"unspecified profile"` and `"unspecified version"`.

---

## 6. Honest Test Coverage Validation

**What `test_artifact_contract.py` proves:**
- Proves that the trust identity component *strictly enforces* the 4-file array (specifically asserting `.jsonl` requirements against "complete" states).
- Proves that `artifact_paths` outputs correctly map canonical over deprecated items. 

**What it does NOT prove:**
- Does not validate that upstream modifications to `telemetry_provider.py` fail cleanly. 
- Does not validate that injected `runner.py` rendering strings correctly populate physical path checks when execution flags trigger.

**Conclusion on telemetry variation:** 
The telemetry changes completely lack meaningful validation constraints, reinforcing the decision to immediately revert.

---

## 7. Repo Cleanliness and Branch State

- **Current branch:** `chore/report-artifact-design`
- **Working Tree:** Dirty.
- **Modified (unstaged) files:** `rescore.py`, `src/export.py`, `src/report.py`, `src/report_campaign.py`, `src/runner.py`, `src/telemetry_provider.py`, `src/trust_identity.py`, `test_artifact_contract.py`.
- **Deleted (unstaged):** `docs/README.md`.
- **Untracked files:** `docs/playbooks/README.md`, `uv.lock`.
- **Action Requirement:** No action should be committed yet. State must be cleansed (via revert of out-of-bound documents and patching the remaining literal scopes) before pushing a unified bundle.

---

## 8. Bounded Implementation Recommendation

### A. Safe to keep now
The path restructuring and display fallback wording mapped across `src/report.py`, `src/report_campaign.py`, and `src/export.py`.

### B. Revert now
`git restore src/telemetry_provider.py` to scrub unauthorized generalized upstream alterations. 

### C. Defer to later pass
Scrubbing arbitrary text mappings inside system-level diagnostic routines (e.g. `src/explain.py` and `src/doctor.py`) which operate separate from user-facing report artifact renderers.

### D. Remaining bounded fixes still worth doing before a campaign
- Target and eliminate the dangling literals remaining inside `src/runner.py` (lines 2005 / 2617).
- Point the module path builders inside `src/artifact_paths.py` up to their corresponding `FILENAME_` global constants to truly create a single point of truth.
- Update lines 1463-1464 inside `src/report.py` to intercept `"unspecified profile"` constraints.

### E. Minimal validation steps needed before a campaign run
1. Execute `git restore src/telemetry_provider.py`.
2. Push bounded fix adjustments. 
3. Perform standard testing pass.
4. Run `uv run python src/runner.py configs/campaigns/B_low_sample.yaml --db-file lab.sqlite` to manually test output streams.
