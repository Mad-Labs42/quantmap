# Phase 1 Trust Bundle: Existing-State Inventory

**Status:** DRAFT | **Target:** Phase 1 Implementation Plan | **Date:** 2026-04-11

## 1. Objective
This inventory identifies the "truth" of the current QuantMap implementation for key trust mechanisms. It maps existing code components to the five Trust Bundle areas, identifying duplicated logic, misleading half-measures, and verified foundations to ensure Phase 1 is built on a clean, non-redundant architecture.

---

## 2. Area A: Verbatim Snapshotting
*Goal: Ensure the database is a fully self-contained forensic capsule.*

| Mechanism | File(s) | State | Recommendation |
|:---|:---|:---|:---|
| **Campaign YAML** | `telemetry.py`, `runner.py` | **VERIFIED** - Verbatim text is stored in `campaign_start_snapshot.campaign_yaml_content`. | Keep. |
| **Baseline YAML** | `telemetry.py` | **PARTIAL** - Only `baseline_yaml_sha256` is stored. Text is volatile on disk. | **EXTEND**: Add `baseline_yaml_content` to DB. |
| **Methodology Context** | N/A | **MISSING** - Scoring profiles (`configs/profiles/*.yaml`) and Metric Registry (`metrics.yaml`) are not snapshotted. | **NEW**: Snapshot effective methodology to DB. |
| **Prompt Identity** | `telemetry.py` | **PARTIAL** - `prompt_sha256_json` stores hashes of request payloads. Payloads themselves are volatile. | Keep hashes; consider verbatim snapshotting for "Small" payloads if portability is required. |

---

## 3. Area B: Code Identity (Proof of Backend & Runner)
*Goal: Cryptographically link the measurement to the specific code that took it.*

| Mechanism | File(s) | State | Recommendation |
|:---|:---|:---|:---|
| **Server Binary SHA256** | `telemetry.py` | **VERIFIED** - Authoritative hash of the `llama-server` executable is recorded. | Keep. |
| **Build Commit** | `runner.py`, `baseline.yaml` | **MISLEADING** - Sourced from a YAML string (user-provided). No verification against the binary. | **REPLACE**: Source from binary if possible, or mark as "Claimed Commit". |
| **QuantMap Identity** | N/A | **MISSING** - QuantMap's own git version/commit is not recorded. | **NEW**: Record `quantmap_version` and `quantmap_git_commit` in snapshot. |

---

## 4. Area C: Snapshot-First Report Identity
*Goal: Ensure reports are built FROM the database, not FROM volatile disk assumptions.*

| Mechanism | File(s) | State | Recommendation |
|:---|:---|:---|:---|
| **Header Sourcing** | `report_campaign.py` | **VERIFIED** - Sourced from `campaign_start_snapshot` table. | Keep. |
| **Model/Path Context** | `report_campaign.py` | **MIXED** - Uses DB for some fields, falls back to `baseline` object in memory. | **REPLACE**: Transition fallback to use snapshotted baseline in DB. |
| **Methodology Display** | `report_campaign.py` | **BRITTLE** - Hardcoded "v1.0" labels in report strings, not derived from snapshotted state. | **REPLACE**: Labels must be derived from snapshotted methodology. |

---

## 5. Area D: Layered State/Outcome Model
*Goal: Distinguish "The runner loop finished" from "The data is valid and the report generated".*

| Mechanism | File(s) | State | Recommendation |
|:---|:---|:---|:---|
| **Execution Status** | `db.py` (campaigns) | **PARTIAL** - `status` (pending/running/complete/failed/aborted). Only reflects code exit state. | Keep as "Execution Layer". |
| **Measurement Outcome** | `db.py` (requests) | **VERIFIED** - `outcome` (success/timeout/oom/etc.) correctly identifies data quality. | Keep as "Measurement Layer". |
| **Interpretation State** | N/A | **MISSING** - No record of whether scoring or ranking succeeded vs failed. | **NEW**: Add `interpretation_status` (unranked/scored/finalized). |
| **Presentation Success**| N/A | **MISSING** - No record of whether the final Report MD or CSV was actually written. | **NEW**: Add `presentation_status` to track artifact delivery. |

---

## 6. Area E: Environment-Aware Path Resolution
*Goal: Single source of truth for "where things live" across all deployment machines.*

| Mechanism | File(s) | State | Recommendation |
|:---|:---|:---|:---|
| **Lab Root Derivation** | `config.py`, `runner.py` | **VERIFIED** - `QUANTMAP_LAB_ROOT` is the authoritative anchor. | Keep. |
| **Profile Isolation** | `runner.py` | **VERIFIED** - `_derive_lab_root` separates profiles into distinct DB/Log namespaces. | Keep. |
| **Tool Inventory** | N/A | **SHADOWED** - `server.py` and `telemetry.py` both define paths to tools via env vars. | **CONSOLIDATE**: Move to a central `EnvironmentProvider` authority. |

---

## 7. Immediate Removal Candidates (Dead/Misleading Code)
- **Hardcoded Methodology Literals**: Any module-level strings like `METHODOLOGY_HEADER = ...` in `score.py` or `report_campaign.py` that describe versioning manually.
- **Duplicate Path Logic**: Remove ad-hoc `Path(os.getenv(...))` calls in favor of the `config.py` exports or the new `EnvironmentProvider`.

---

## 8. Next Steps
1. **Approve Inventory**: (Josh)
2. **Draft Phase 1 Implementation Plan**: Map these findings to specific code changes.
