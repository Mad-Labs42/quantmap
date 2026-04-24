# ACPM v1 End-State Validation

Date: 2026-04-23
Status: PASS
Scope: ACPM v1 closeout synthesis

---

## 1. Completed Slices

Completed and validated:

- Slice 1: structural truth prep
- Slice 2: effective filter-policy persistence and projection
- Slice 3: governed profiles and methodology labeling
- Slice 4: execution wiring, applicability, repeat tiers, and fixed `1x` NGL scaffold
- Slice 5: recommendation authority and caveat contract
- Slice 6: projections and consumer surfaces

Result:

- ACPM v1’s planned implementation slices are complete.

---

## 2. Final Architecture / Truth-Lane Summary

ACPM v1 now has five distinct truth lanes with bounded ownership:

- Execution truth:
  `RunPlan` plus generic `scope_authority`

- Planner provenance:
  adjacent ACPM planning metadata and planner compilation outputs

- Methodology truth:
  governed profiles and methodology snapshots

- Effective filter-policy truth:
  `campaign_start_snapshot.effective_filter_policy_json`

- Recommendation claim truth:
  `campaigns.recommendation_record_json`

Consumer surfaces now read and project these lanes; they do not own ACPM policy:

- `report.py`
- `report_campaign.py`
- `export.py`
- `compare.py` / `report_compare.py`
- `explain.py`

---

## 3. Validation Summary

Across the six slice validations:

- all slices ended in PASS
- focused slice tests and slice-to-slice regressions passed
- repo `.venv` / dev-contract checks passed where run
- changed-path verification passed on the implementation slices
- no implemented slice required reopening the locked baseline architecture

Known non-blocking validation noise remained consistent:

- pytest Windows temp-cleanup `WinError 5` warnings at process exit

These warnings did not invalidate the recorded PASS results.

---

## 4. Remaining Watch-Outs / Deferred Items

Still deferred or optional:

- exact CLI entry / ACPM invocation ergonomics
- optional formal machine-handoff artifact family or serializer
- exact compact list / compare wording refinements
- future profile-specific gates
- future dynamic or topology-specific NGL scaffold policies
- any broader report/export/compare UX redesign

Watch-outs that still matter:

- keep consumers projection-only; do not let them re-derive recommendation policy
- keep `leading_config_id` distinct from `recommended_config_id`
- keep execution truth, methodology truth, filter-policy truth, and recommendation truth separate
- complete the deeper reconciliation behind the stale `min_valid_warm_count` wording issue before any future relaxation-policy work
- some owner files were already dirty during later slices, so regression evidence matters more than raw git-status attribution

---

## 5. Readiness Judgment

Readiness judgment: **ready for normal ACPM v1 feature use and future hardening**.

Why:

- the planned v1 slices are complete
- core ownership boundaries now exist and are validated
- projections are wired onto existing authority rather than inventing new truth
- remaining items are hardening, ergonomics, or future-version expansion, not blockers for normal v1 use

Boundary on that judgment:

- this is readiness for the locked ACPM v1 baseline, not a claim that all future ACPM enhancements are complete

---

## 6. .agent Files Used This Turn

- `AGENTS.md`
- `.agent/README.md`
