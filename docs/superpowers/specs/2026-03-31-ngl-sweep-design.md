# NGL Sweep Campaign — Design Spec

**Date:** 2026-03-31
**Branch:** claude/distracted-joliot
**Status:** Approved (post-review revision)

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
| Sweet-spot recommendation | Replaced by `min_context_length`-based recommendation | No arbitrary percentage thresholds; user states their actual requirement |
| vram_headroom_pct_min | Removed | Replaced by explicit context-length requirement |
| Est. Max Context | KV cache formula from model architecture params | Directly actionable: tells users what context depth each layer count supports |
| Diminishing returns | Marginal gain annotation at 15% of peak, display-only | Observation on data curve, not a recommendation; 15% is a display heuristic |

---

## Files Changed

| File | Nature of change |
|------|-----------------|
| `configs/campaigns/NGL_sweep.yaml` | New file |
| `src/server.py` | `ServerOOMError`, `_classify_startup_failure()`, process-exit fast-path in `_wait_for_server()` and `_wait_for_completion_ready()` |
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
- `oom_boundary_sweep: true` — opts the runner into OOM-aware handling and ascending-sort validation
- `min_context_length: null` — optional; when set (e.g. `8192`), report adds a targeted recommendation for the fastest config able to sustain that context depth; when null/absent, no single recommendation is made
- No `type:` field — nothing reads it; omitting avoids a dead schema field
- No `vram_headroom_pct_min` field — removed; no arbitrary percentage thresholds

Commented VRAM tier block (guidance only — not parsed):
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
- `log_snippet: str` — matching lines plus up to 3 lines of context (≤500 chars, truncated at a whole-line boundary — never mid-line)
- `log_path: Path` — path to the server log file
- `exit_code: int | None` — process exit code at time of failure

Raised by `start_server()` after any startup failure where log scan confirms OOM. Non-OOM startup failures continue to raise plain `RuntimeError`. `ServerOOMError` is a subclass of `RuntimeError`, so existing `except RuntimeError` handlers in `_run_cycle` still catch it — the exception hierarchy is backward-compatible. The runner catches `ServerOOMError` specifically to apply OOM semantics only when the flag is active (see Section 4).

### `_classify_startup_failure(log_path: Path) -> tuple[bool, str]`
Reads the server log and scans for OOM strings. Returns `(is_oom, snippet)`. If the log file does not exist or cannot be read, returns `(False, "")`.

**High-confidence OOM strings** (any one match is sufficient to classify as OOM):
- `"CUDA error: out of memory"`
- `"cudaMalloc failed"`
- `"failed to allocate"`
- `"not enough memory"`

**Lower-confidence string** (only counts as OOM if at least one high-confidence string also appears anywhere in the log):
- `"GGML_ASSERT"` — too broad on its own; fires on non-memory assertion failures

Snippet assembly: collect the matching line(s) and up to 3 lines of preceding context for the first match. Assemble as complete lines. Truncate at 500 chars by dropping whole trailing lines until under the limit. Never truncate mid-line.

### Process-exit fast-path in `_wait_for_server()` and `_wait_for_completion_ready()`
Both functions gain an optional `process: subprocess.Popen | None = None` parameter (default `None` — backward-compatible; existing callers outside server.py require no changes). When `process` is provided, each poll iteration (every 0.5s) calls `process.poll()`. If non-None (process has exited), skip the remaining timeout and immediately scan the log. Without this, an OOM crash that happens in 3 seconds waits the full `bind_timeout_s` (300s default) before being detected.

### `start_server()` changes
- Passes `process=process` to both `_wait_for_server()` and `_wait_for_completion_ready()` in attempt 1 and attempt 2
- After any `RuntimeError` in the startup sequence (both attempt 1 and attempt 2), calls `_classify_startup_failure(log_file)` and re-raises as `ServerOOMError(log_snippet, log_file, exit_code)` if confirmed OOM, otherwise re-raises the original `RuntimeError`

---

## Section 3: Database — Schema v4

### Existing `campaigns.failure_reason` (unchanged)
The `campaigns` table already has a `failure_reason TEXT` column that records why a campaign-level failure occurred (e.g. a fatal exception in the runner). This column is **not modified** by this feature. It operates at campaign granularity.

### New column: `configs.failure_detail TEXT NULL`
A distinct column at **config granularity**. Populated when `status = 'oom'`; NULL for all other statuses. Stores the OOM log snippet (≤500 chars). Note: no CHECK constraint exists on `configs.status` in the current schema (v3); the new status values `oom` and `skipped_oom` can be inserted without altering a constraint.

New status values for `configs.status` (documented in schema comment alongside existing values):
- `pending` — not yet started
- `running` — cycles in progress
- `complete` — all cycles complete
- `oom` — server startup failed with confirmed OOM; no inference ran
- `skipped_oom` — not attempted; preceding consecutive OOMs confirmed the VRAM ceiling

### New column: `campaign_start_snapshot.gpu_vram_total_mb REAL NULL`
- Populated at campaign start via `pynvml.nvmlDeviceGetMemoryInfo(handle).total / (1024 * 1024)`
- Uses the **same device handle** as the one used to collect `telemetry.gpu_vram_used_mb` — critical on multi-GPU systems to capture the specific inference GPU, not the sum of all devices
- Represents physical GPU memory capacity (constant for the device, not a per-config allocated ceiling)
- NULL if pynvml is unavailable (non-ABORT; report shows "N/A" for VRAM %)

### Migration
Schema version bumps from v3 to v4. Two `ALTER TABLE ... ADD COLUMN` statements:
```sql
ALTER TABLE configs ADD COLUMN failure_detail TEXT NULL;
ALTER TABLE campaign_start_snapshot ADD COLUMN gpu_vram_total_mb REAL NULL;
```
Both are safe and backward-compatible — existing rows get NULL.

---

## Section 4: Runner Changes

All OOM-aware logic is guarded by `campaign.get("oom_boundary_sweep", False)`. Standard campaigns (all existing C01–C15, Finalist) are **unaffected** — the guard is never entered and `_run_config()` continues to return `True`/`False` as before.

### `_validate_campaign()` — values sort check
When `campaign.get("oom_boundary_sweep")` is True, add a validation check:
- Verify `values` list is in strictly ascending order
- **FAIL** with guidance: "oom_boundary_sweep requires values in ascending order (low-to-high) for early termination to be correct. Got: [999, 80, 60] — sort ascending or set oom_boundary_sweep: false."

### `_run_config()` — OOM handling
Signature and return type are unchanged for standard campaigns. When `oom_boundary_sweep` is active, the OOM-handling block is wrapped in the guard:

```python
if campaign.get("oom_boundary_sweep", False):
    try:
        # run all cycles as normal; ServerOOMError may fire on any cycle's
        # start_server() call, not only cycle 1
        ... # existing cycle loop
    except ServerOOMError as exc:
        # mark config oom, store snippet, skip cooldown, return sentinel
        ...
        return "oom"
```

The `ServerOOMError` guard covers **all cycles**, not only cycle 1. If cycle 1 succeeds but cycle 2 OOMs (rare — could happen if another process grabbed VRAM between cycles), the config is marked `oom` and the boundary logic fires in the campaign loop. This is more conservative than treating it as a generic crash, which would discard the data and continue.

When `oom_boundary_sweep` is False, `ServerOOMError` propagates unchanged up through `_run_cycle()` to the existing `except Exception` handler in `_run_config()`, which marks the cycle invalid and logs a crash — same as today.

### `run_campaign()` — early termination (entire block inside guard)

The `oom_boundary_sweep` flag controls both initialisation and per-config logic. Both live inside a single outer guard so `consecutive_ooms` is never referenced in a scope where it wasn't initialised:

```python
oom_boundary_sweep = campaign.get("oom_boundary_sweep", False)
if oom_boundary_sweep:
    values = campaign.get("values", [])
    if values != sorted(values):  # runtime belt-and-suspenders after --validate
        logger.warning("oom_boundary_sweep: values not sorted ascending — auto-sorting")
        # (build_config_list already consumed the values; log the warning for the audit trail)
    consecutive_ooms = 0

for i, config in enumerate(configs):
    result = _run_config(...)

    if oom_boundary_sweep:
        if result == "oom":
            consecutive_ooms += 1
            if consecutive_ooms == 1:
                logger.warning("OOM on %s — continuing to confirm boundary", config_id)
            elif consecutive_ooms >= 2:
                logger.error("OOM confirmed on %s — VRAM ceiling established; terminating sweep", config_id)
                # Mark ALL remaining configs skipped_oom in DB BEFORE break.
                # This ensures crash recovery sees them as already done and
                # does not re-attempt them on resume.
                for remaining_config in configs[i + 1:]:
                    ... # INSERT or UPDATE status='skipped_oom', failure_detail='boundary confirmed by 2 consecutive OOM failures'
                break
        else:
            consecutive_ooms = 0  # reset — prior OOM was transient
```

`break` exits the config loop and falls through to the existing campaign-complete block (DB status update, `_clear_progress()`, analysis+report). This is the normal completion path — `run_campaign()` exits 0.

**Crash recovery after partial `skipped_oom` batch:** All remaining configs are written to the DB as `skipped_oom` *before* `break` executes. If the runner crashes between the DB write and `_clear_progress()`, a resume will see those configs already in the DB with a non-`pending`/non-`running` status and skip them. The `consecutive_ooms` counter is not persisted — it is re-derived from the campaign loop. On resume, if all remaining configs are already `skipped_oom`, the loop body is never entered for them and the campaign completes cleanly.

### `--dry-run` output for OOM-boundary campaigns
When `oom_boundary_sweep` is True, the dry-run summary includes a dedicated line after the standard config/cycle/request counts:
```
OOM boundary detection: enabled (early termination after 2 consecutive OOMs)
```
Purpose: the user confirms OOM-aware behavior is active before committing to a multi-hour run.

---

## Section 5: Analysis and Report

### `get_vram_per_config(campaign_id, db_path) -> dict[str, dict]`
New function in `analyze.py`. Queries:
```sql
SELECT config_id, MAX(gpu_vram_used_mb) AS peak_mb, AVG(gpu_vram_used_mb) AS avg_mb
FROM telemetry
WHERE campaign_id = ?
GROUP BY config_id
```
Also reads `gpu_vram_total_mb` from `campaign_start_snapshot` in a separate query.

Returns `{config_id: {"peak_mb": float, "avg_mb": float, "total_mb": float | None}}`.

**Important:** OOM and skipped configs produce zero telemetry rows. Their `config_id`s are absent from the returned dict. All callers must use `.get(config_id)` and handle `None` — never `dict[config_id]` directly. The report renders `—` for absent entries.

### KV cache estimation
Used to compute **Est. Max Context** for each config. Formula:

```
est_max_context_tokens = vram_free_bytes / kv_cache_bytes_per_token
```

Where:
- `vram_free_bytes = (total_mb - peak_mb) * 1024 * 1024`
- `kv_cache_bytes_per_token = n_kv_layers_on_gpu * 2 * n_kv_heads * head_dim * bytes_per_element`
  - `n_kv_layers_on_gpu` = number of transformer layers on GPU (= min(n_gpu_layers, total_layers))
  - `n_kv_heads` = number of KV heads (GQA: n_heads / gqa_factor)
  - `head_dim` = d_model / n_heads
  - `bytes_per_element` = 2 for f16 (default), 1 for q8_0, 0.5 for q4_0 (from `kv_cache_type_k` in baseline config)

**Source of architecture parameters:** baseline.yaml `model:` section. Currently it records `total_params_b`, `architecture`, `experts_total`, etc. — but does NOT record `n_layers`, `n_kv_heads`, or `d_model`. If these fields are absent, Est. Max Context is shown as "N/A" throughout the report, with a note: "Context estimation unavailable — add n_layers, n_kv_heads, d_model to baseline.yaml model section."

**This feature therefore requires a one-time addition** of those three fields to `baseline.yaml` before the NGL sweep report can show estimates. The implementation must not crash or skip the column silently — it must show "N/A" with an explanatory note.

### Report NGL sweep section
Condition: `campaign.get("variable") == "n_gpu_layers"` (checked in `generate_report()`).

Title: **"GPU Layer Sweep — Throughput vs. VRAM"**

Table columns (sorted by NGL ascending):

| NGL | TG (t/s) | TG P10 | VRAM Used | VRAM Free | Est. Max Context | Score | Notes |
|-----|----------|--------|-----------|-----------|-----------------|-------|-------|
| 10  | 5.43     | 5.12   | 4,821 MB  | 19,555 MB | 163K tokens     | 0.312 | —     |
| …   | …        | …      | …         | …         | …               | …     | —     |
| 60  | 9.10     | 8.87   | 16,400 MB | 8,576 MB  | 16K tokens      | 0.741 | ← diminishing returns beyond this point |
| 80  | 10.97    | 10.41  | 22,100 MB | 2,276 MB  | 3.8K tokens     | 0.911 | ★ score winner |
| 90  | —        | —      | —         | —         | —               | —     | OOM: CUDA error: out of memory |
| 999 | —        | —      | —         | —         | —               | —     | skipped (boundary confirmed) |

**VRAM Free** = `total_mb - peak_mb`. Shows "N/A" if `total_mb` is NULL.

**Est. Max Context** = computed from KV cache formula above. Shows "N/A" if model architecture params absent or VRAM free is N/A.

**Diminishing returns annotation:** Compute marginal throughput gain per layer step for each consecutive pair of viable (non-OOM) configs:
```
marginal_gain(i) = (tg_i - tg_{i-1}) / (ngl_i - ngl_{i-1})
```
Find `peak_marginal = max(marginal_gain)`. Annotate the first row where `marginal_gain` drops below `0.15 * peak_marginal` with "← diminishing returns beyond this point". This annotation is display-only — it never affects scoring, elimination, or recommendations. If fewer than 3 viable configs exist, skip the annotation (not enough data for a meaningful trend).

### Below-table text
**If `min_context_length` is set** (e.g. `min_context_length: 8192`):

Find the viable configs (non-OOM, non-skipped) with `est_max_context >= min_context_length`, sorted by TG median descending. Take the first (fastest):
> "For your stated minimum of 8K context: NGL=60 (TG median 9.1 t/s, est. max context 16K, 6.7 GB VRAM free). This is the fastest config that meets your context requirement."

If no config meets the requirement:
> "No config in this sweep can sustain 8K context — consider a smaller quantization or fewer layers on GPU."

If Est. Max Context is N/A (model params absent), skip this recommendation entirely and note:
> "Context-based recommendation unavailable — add n_layers, n_kv_heads, d_model to baseline.yaml model section."

**If `min_context_length` is null or absent:**
> "No context requirement specified. Set min_context_length in your campaign YAML to get a targeted recommendation, or choose from the table above based on your workload."

**Score winner** (always present, independent of context recommendation): rendered by the existing report infrastructure, unchanged.

### Scoring exclusion
OOM and skipped configs have `status != 'complete'`. The existing `WHERE status = 'complete'` filter in `score_campaign()` excludes them automatically. **No changes to score.py.**

---

## Invariants Preserved

- Campaign purity check: `n_gpu_layers` is a baseline config field; purity check passes unchanged
- One variable per campaign: all other config fields remain at baseline values
- Raw data immutability: `raw.jsonl` append-only; OOM configs produce no request records (nothing to append)
- Crash recovery: `progress.json` updated after each config completes. Configs with `status='oom'` and `status='skipped_oom'` are both treated as complete on resume — they are skipped in the same way as `status='complete'` configs (checked against `completed_config_ids` set)
- Exit code integrity: early termination via `break` flows into the existing campaign-complete block; `run_campaign()` exits 0. Report generation failure still exits 1
- Backward compatibility: `ServerOOMError` is a `RuntimeError` subclass; `process` parameter on `_wait_for_server()` defaults to `None`; OOM logic in `_run_config()` and `run_campaign()` is guarded by `oom_boundary_sweep`; standard campaigns are unaffected
