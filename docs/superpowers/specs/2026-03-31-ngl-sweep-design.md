# NGL Sweep Campaign — Design Spec

**Date:** 2026-03-31
**Branch:** claude/distracted-joliot
**Status:** Approved

---

## Overview

Adds a portable `n_gpu_layers` sweep campaign to QuantMap. The campaign establishes a throughput-vs-VRAM curve for any model/GPU combination. On hardware where all layers fit in VRAM (DEEP THOUGHT: RTX 3090 24GB + `-ot exps=CPU`), the full curve is measured with no OOM. On smaller GPUs (12GB, 8GB), the runner detects the OOM boundary, records it as data, and terminates the sweep early. The same YAML runs on any hardware; the runner adapts.

---

## Design Decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Hardware portability | Single YAML, runner adapts | Full curve on 24GB; partial curve + OOM boundary on smaller GPUs |
| OOM detection | Early exit fast-path + log scan | Log scan is ground truth; exit fast-path avoids 300s timeout waits |
| OOM data treatment | Excluded from scoring; reported as boundary markers | OOM configs never ran inference — scoring them is meaningless |
| OOM log snippet | Stored in `configs.failure_detail` | Shows "how close" the allocation failure was |
| Sweep direction | Low-to-high | All viable data collected before boundary; failed startups are cheap |
| Early termination | 2 consecutive OOMs = confirmed ceiling | 1 OOM may be transient VRAM fragmentation; 2 = monotonicity confirmed |
| Values format | Explicit `values:` list | Consistent with all existing campaigns; all existing infrastructure works |
| GGML_ASSERT | Lower-confidence OOM signal | Too broad — only matched when co-occurring with allocation context |
| gpu_vram_total_mb | Same pynvml device handle as telemetry | Ensures single-GPU capture, not sum of all GPUs |
| Values sort validation | Validate ascending in `--validate`; auto-sort with warning at runtime | Monotonicity assumption for early termination requires ascending order |

---

## Files Changed

| File | Nature of change |
|------|-----------------|
| `configs/campaigns/NGL_sweep.yaml` | New file |
| `src/server.py` | `ServerOOMError`, `_classify_startup_failure()`, process-exit fast-path in `_wait_for_server()` |
| `src/db.py` | Schema v4: `configs.failure_detail`, `campaign_start_snapshot.gpu_vram_total_mb`, migration |
| `src/runner.py` | OOM handling in `_run_config()`, early termination + sort validation in `run_campaign()` / `_validate_campaign()` |
| `src/analyze.py` | `get_vram_per_config()` |
| `src/report.py` | NGL sweep section in `generate_report()` |

Core scoring and elimination pipeline (`score.py`) is **untouched**.

---

## Section 1: Campaign YAML

**File:** `configs/campaigns/NGL_sweep.yaml`

Fields:
- `campaign_id: "NGL_sweep"`
- `variable: "n_gpu_layers"` — matches the baseline.yaml config key
- `values: [10, 20, 30, 40, 50, 60, 70, 80, 90, 999]` — DEEP THOUGHT defaults (step 10, plus 999 for "all layers")
- `oom_boundary_sweep: true` — opts the runner into OOM-aware handling
- `vram_headroom_pct_min: 20` — sweet-spot recommendation threshold (configs using ≤80% VRAM)
- No `type:` field — nothing reads it; omitting avoids dead schema

Commented VRAM tier block:
```yaml
# Common starting points by GPU VRAM tier (999 = all layers, no OOM expected):
# 24GB (RTX 3090/4090): values: [10, 20, 30, 40, 50, 60, 70, 80, 90, 999]
# 12GB (RTX 3060/4070): values: [5, 10, 15, 20, 25, 30, 35, 40, 999]
#  8GB (RTX 3060 8GB):  values: [5, 10, 15, 20, 25, 999]
# 999 = all layers in llama.cpp convention. If the model fits entirely in VRAM
# at 999, no OOM will occur and the full curve is measured without interruption.
```

---

## Section 2: OOM Detection (server.py)

### `ServerOOMError(RuntimeError)`
New exception. Fields:
- `log_snippet: str` — matching lines plus up to 3 lines of context (≤500 chars)
- `log_path: Path` — path to the server log file
- `exit_code: int | None` — process exit code at time of failure

Raised by `start_server()` after any startup failure where log scan confirms OOM. Non-OOM failures continue to raise plain `RuntimeError`. `ServerOOMError` is a subclass of `RuntimeError`, so existing `except RuntimeError` handlers still catch it.

### `_classify_startup_failure(log_path: Path) -> tuple[bool, str]`
Reads the server log and scans for OOM strings. Returns `(is_oom, snippet)`.

**High-confidence OOM strings** (any one match is sufficient):
- `"CUDA error: out of memory"`
- `"cudaMalloc failed"`
- `"failed to allocate"`
- `"not enough memory"`

**Lower-confidence string** (only counts if a high-confidence string also appears nearby):
- `"GGML_ASSERT"` — too broad on its own; fires on non-memory assertion failures

Snippet: the matching line + up to 3 lines of context, truncated to 500 chars.

### Process-exit fast-path in `_wait_for_server()`
Add `process: subprocess.Popen` parameter. Each poll iteration (every 0.5s) calls `process.poll()`. If non-None (process has exited), immediately call `_classify_startup_failure()` and raise `ServerOOMError` or `RuntimeError` accordingly. Without this, an OOM crash that happens in 3 seconds waits the full `bind_timeout_s` (300s) before being detected.

`_wait_for_completion_ready()` gets the same fast-path for the same reason.

### `start_server()` changes
- Pass `process` to `_wait_for_server()` and `_wait_for_completion_ready()`
- After any `RuntimeError` in the startup sequence (both attempt 1 and attempt 2), call `_classify_startup_failure()` and re-raise as `ServerOOMError` if confirmed
- The `ServerOOMError` propagates up through `_run_cycle()` to `_run_config()`

---

## Section 3: Database — Schema v4

### New column: `configs.failure_detail TEXT NULL`
- Populated when `status = 'oom'`; NULL for all other statuses
- Stores the OOM log snippet (≤500 chars) from `_classify_startup_failure()`
- New status values documented in schema comment: `oom`, `skipped_oom`

### New column: `campaign_start_snapshot.gpu_vram_total_mb REAL NULL`
- Populated at campaign start via `pynvml.nvmlDeviceGetMemoryInfo(handle).total / (1024*1024)`
- Uses the **same device handle** as `telemetry.gpu_vram_used_mb` — critical on multi-GPU systems to ensure the specific inference GPU is captured, not the sum of all GPUs
- NULL if pynvml is unavailable (non-ABORT condition; report shows "N/A")

### Migration
Schema version bumps from v3 to v4. Both `ALTER TABLE ... ADD COLUMN` statements. Safe and backward-compatible — existing rows get NULL.

---

## Section 4: Runner Changes

### `_validate_campaign()` — values sort check
When `campaign.get("oom_boundary_sweep")` is True, add a validation check:
- Verify `values` list is in strictly ascending order
- **FAIL** with guidance: "oom_boundary_sweep requires values in ascending order (low-to-high) for early termination to be correct. Got: [999, 80, 60] — sort ascending or set oom_boundary_sweep: false."

### `_run_config()` — OOM handling
When `oom_boundary_sweep` is active on the campaign:
1. Attempt cycle 1. If `ServerOOMError` is raised during `start_server()`:
   - Mark config `status='oom'`, `failure_detail=exc.log_snippet` in DB
   - Skip cooldown (no inference ran)
   - Return `"oom"` sentinel
2. If cycle 1 succeeds, run remaining cycles normally and return `True`

### `run_campaign()` — early termination
New local variable `consecutive_ooms = 0`, active only when `campaign.get("oom_boundary_sweep")` is True.

```
config returns "oom":
  consecutive_ooms += 1
  if consecutive_ooms == 1:
    log WARNING: "OOM on {config_id} — continuing to confirm boundary"
  if consecutive_ooms >= 2:
    log ERROR: "OOM confirmed on {config_id} — boundary established"
    mark all remaining configs status='skipped_oom' in DB
    break campaign loop

config returns True (success):
  consecutive_ooms = 0   # reset — prior OOM was transient
```

Auto-sort with warning: if `oom_boundary_sweep` is True and values are not sorted at runtime (belt-and-suspenders after `--validate`), sort them ascending and log a WARNING. This prevents silent bad results if `--validate` was skipped.

---

## Section 5: Analysis and Report

### `get_vram_per_config(campaign_id, db_path) -> dict[str, dict]`
New function in `analyze.py`. Queries:
```sql
SELECT config_id, MAX(gpu_vram_used_mb) as peak_mb, AVG(gpu_vram_used_mb) as avg_mb
FROM telemetry
WHERE campaign_id = ?
GROUP BY config_id
```
Also reads `gpu_vram_total_mb` from `campaign_start_snapshot`.
Returns `{config_id: {"peak_mb": float, "avg_mb": float, "total_mb": float | None}}`.

### Report NGL sweep section
Condition: `campaign.get("variable") == "n_gpu_layers"` (checked in `generate_report()`).

Title: **"GPU Layer Sweep — Throughput vs. VRAM"**

One table covering every value in the sweep, sorted by NGL:

| NGL | VRAM Used | VRAM % | TG Median | TG P10 | Score | Notes |
|-----|-----------|--------|-----------|--------|-------|-------|
| 10  | 4,821 MB  | 20%    | 5.43      | 5.12   | 0.312 | —     |
| …   | …         | …      | …         | …      | …     | —     |
| 80  | 22,100 MB | 92%    | 10.97     | 10.41  | 0.911 | ★ score winner |
| 90  | —         | —      | —         | —      | —     | OOM: CUDA error: out of memory attempting to allocate 1.2 GB |
| 999 | —         | —      | —         | —      | —     | skipped (boundary confirmed) |

**Sweet-spot recommendation** (below table): highest-scoring config with VRAM usage ≤ `(100 - vram_headroom_pct_min)%`. Example output:
> "Sweet spot: NGL=70 — 83% VRAM (4.1 GB headroom), TG median 10.51 t/s. NGL=80 is 4% faster but leaves only 8% VRAM headroom — vulnerable to context growth or concurrent use."

If no OOM occurred (DEEP THOUGHT case), note: "No OOM boundary reached — all layer counts are viable on this GPU."

If VRAM total is unavailable (NULL), VRAM % column shows "N/A".

### Scoring exclusion
OOM and skipped configs have `status != 'complete'` in the DB. The existing `WHERE status = 'complete'` guard in `score_campaign()` excludes them automatically. **No changes to score.py.**

---

## Invariants Preserved

- Campaign purity check: `n_gpu_layers` is a baseline config field; purity check passes unchanged
- One variable per campaign: all other config fields remain at baseline values
- Raw data immutability: `raw.jsonl` append-only; OOM configs produce no request records
- Crash recovery: `progress.json` updated per config; OOM configs are recorded as complete (status=oom) and skipped on resume
- Exit code integrity: OOM early termination exits 0 (campaign ran to completion by design); report generation failure still exits 1
