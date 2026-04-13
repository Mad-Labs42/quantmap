# Phase 3 WSL Linux-Native Backend Smoke Validation Memo

Status: bounded WSL backend validation complete; appendix_b fix applied  
Date: 2026-04-13  
Scope: one real end-to-end WSL degraded QuantMap run using a Linux-native backend path

## 1. Purpose

This memo records the first successful real QuantMap measurement run from inside WSL 2 using a backend that is valid from WSL's point of view.

This pass did not attempt native bare-metal Linux support, backend abstraction, Windows-host telemetry bridging, interop support, packaging redesign, or performance tuning. Its purpose was narrower:

- choose the shortest valid Linux-native backend path
- prove the backend was reachable from WSL before QuantMap used it
- run a tiny real QuantMap campaign inside WSL
- verify persisted WSL degraded truth after the run
- verify downstream historical surfaces preserve that truth

## 2. Backend Path Chosen

Chosen backend:

```text
/home/hitchhiker/work/quantmap-wsl-native-backend/llama-server-wsl-native
```

This is a small WSL wrapper around the official llama.cpp Ubuntu x64 prebuilt:

```text
/home/hitchhiker/work/quantmap-wsl-native-backend/llama-b8779-bin-ubuntu-x64/llama-server
```

Version:

```text
llama.cpp b8779, commit 75f3bc94e, built for Linux x86_64
```

Model:

```text
/mnt/d/.store/models/Nemotron-Nano-4B/v2.1/Q4_K_M/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf
```

Why this path was chosen:

- QuantMap currently owns `llama-server` process launch through `src/server.py`.
- External Docker backend attachment is not currently a supported success path without backend adapter work.
- No Linux-native `llama-server` binary already existed locally.
- The official Ubuntu x64 prebuilt was faster and narrower than building llama.cpp in WSL.
- The backend executable is Linux-native from WSL's perspective and does not rely on Windows `.exe` interop.

## 3. Setup Steps

The Linux prebuilt needed two small WSL environment fixes:

```bash
ROOT=/home/hitchhiker/work/quantmap-wsl-native-backend
curl -L -o "$ROOT/llama-b8779-bin-ubuntu-x64.tar.gz" \
  https://github.com/ggml-org/llama.cpp/releases/download/b8779/llama-b8779-bin-ubuntu-x64.tar.gz
tar -xzf "$ROOT/llama-b8779-bin-ubuntu-x64.tar.gz" -C "$ROOT/llama-b8779-bin-ubuntu-x64"
```

The prebuilt package includes CPU backend variant libraries but no generic `libggml-cpu.so` symlink. The loader only found the RPC backend until this local symlink was added:

```bash
cd /home/hitchhiker/work/quantmap-wsl-native-backend/llama-b8779-bin-ubuntu-x64
ln -s libggml-cpu-x64.so libggml-cpu.so
```

The CPU plugin also required the OpenMP runtime:

```bash
wsl -d Ubuntu -u root -- bash -lc "apt-get update && apt-get install -y libgomp1"
```

Wrapper script:

```sh
#!/usr/bin/env sh
LLAMA_DIR=/home/hitchhiker/work/quantmap-wsl-native-backend/llama-b8779-bin-ubuntu-x64
export LD_LIBRARY_PATH="$LLAMA_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cd "$LLAMA_DIR" || exit 1
exec "$LLAMA_DIR/llama-server" "$@"
```

The WSL Python environment from the prior follow-up was reused:

```text
/home/hitchhiker/.venvs/quantmap-phase3-wsl
```

## 4. Backend Verification Before QuantMap

Manual server command:

```bash
/home/hitchhiker/work/quantmap-wsl-native-backend/llama-server-wsl-native \
  --host 127.0.0.1 \
  --port 18080 \
  --model /mnt/d/.store/models/Nemotron-Nano-4B/v2.1/Q4_K_M/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf \
  -c 512 -ngl 0 --threads 2 --threads-batch 2 --threads-http 1 -ub 128 -b 128
```

Validated before the QuantMap run:

- `/health` returned `{"status":"ok"}` after about 19 seconds.
- `/v1/models` listed `NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf`.
- `/v1/chat/completions` returned HTTP 200 with usage/timing fields.

This established that the backend itself was reachable from WSL and that QuantMap was not the first component discovering backend failure.

## 5. QuantMap Smoke Config

Temporary WSL-only config root:

```text
/home/hitchhiker/work/quantmap-wsl-smoke-configs
```

Temporary lab root:

```text
/home/hitchhiker/work/quantmap-wsl-native-lab
```

Campaign:

```text
WSL_smoke_threads
```

Effective run ID:

```text
WSL_smoke_threads__v2
```

Shape:

- one config
- one cycle
- three streamed requests
- `threads=2`
- `n_gpu_layers=0`
- `context_size=512`
- not benchmark-quality and not intended for tuning conclusions

Environment:

```bash
export QUANTMAP_CONFIGS_DIR=/home/hitchhiker/work/quantmap-wsl-smoke-configs
export QUANTMAP_LAB_ROOT=/home/hitchhiker/work/quantmap-wsl-native-lab
export QUANTMAP_SERVER_BIN=/home/hitchhiker/work/quantmap-wsl-native-backend/llama-server-wsl-native
export QUANTMAP_MODEL_PATH=/mnt/d/.store/models/Nemotron-Nano-4B/v2.1/Q4_K_M/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf
export QUANTMAP_SERVER_READY_TIMEOUT=240
```

Command:

```bash
cd /mnt/d/Workspaces/QuantMap_agent
. /home/hitchhiker/.venvs/quantmap-phase3-wsl/bin/activate
python quantmap.py run \
  --campaign WSL_smoke_threads \
  --baseline /home/hitchhiker/work/quantmap-wsl-smoke-configs/baseline.yaml \
  --values 2 \
  --cycles 1 \
  --requests-per-cycle 3
```

## 6. Run Result

The run completed measurement, analysis, and report generation:

- campaign status: `complete`
- analysis status: `complete`
- report status: `partial`
- config rows: 1
- cycle rows: 1
- request rows: 3
- successful request rows: 3
- telemetry rows: 5
- background snapshot rows: 1

Request outcomes:

| Request | Type | Outcome | TTFT | TG |
|---|---|---|---:|---:|
| 1 | `speed_short` | `success` | 1232.1 ms | 9.23 t/s |
| 2 | `speed_short` | `success` | 1095.6 ms | 9.48 t/s |
| 3 | `speed_medium` | `success` | 1299.2 ms | 9.09 t/s |

The smoke run did not produce a winner because the intentionally tiny sample had only one warm `speed_short` observation for scoring and was eliminated as `cv_uncomputable`. That is acceptable for this validation because the goal was an end-to-end measurement proof, not a benchmark-quality comparison.

The report layer correctly remained honest:

- `report.md`: complete
- `report_v2.md`: partial at time of smoke run, with `appendix_b: name 'stats' is not defined` (see Section 13)
- `scores.csv`: failed/missing because no winner/passing score artifact was produced

The `report_v2.md` partial status was not a WSL backend failure. It was a localized NameError in `_appendix_eliminations` that was subsequently fixed. See Section 13.

## 7. Persisted Truth Validation

`campaign_start_snapshot.execution_environment_json` persisted:

```json
{
  "execution_platform": "linux",
  "support_tier": "wsl_degraded",
  "boundary_type": "wsl2_hypervisor_boundary",
  "measurement_grade": false,
  "degraded_reasons": [
    "wsl_hypervisor_boundary",
    "not_linux_native",
    "missing_linux_cpu_thermal_interfaces"
  ],
  "evidence": {
    "sys_platform": "linux",
    "osrelease": "6.6.87.2-microsoft-standard-WSL2",
    "proc_version_contains_wsl": true,
    "cpu_thermal_interfaces_available": false,
    "nvidia_smi_available": true
  }
}
```

Provider evidence persisted:

- HWiNFO shared memory: `unsupported`
- NVIDIA Management Library: `available`
- GPU: `NVIDIA GeForce RTX 3090`
- driver: `591.86`
- telemetry capture quality: `degraded`
- `cpu_temp_c`: `unsupported`
- `gpu_vram_used_mb`: `available`
- `power_limit_throttling`: `available`

Backend policy evidence:

- resolved command uses `/home/hitchhiker/work/quantmap-wsl-native-backend/llama-server-wsl-native`
- no Windows `.exe` backend appears in the resolved command
- backend target is Linux-native from WSL's perspective
- WSL backend boundary policy did not block

## 8. Downstream Surface Validation

Validated surfaces:

| Surface | Result |
|---|---|
| `report.md` | Shows `Execution support tier = wsl_degraded`, `Measurement-grade platform = False`, degradation reasons, and provider evidence. |
| `report_v2.md` | Shows the same persisted execution/provider evidence and records partial artifact status honestly. |
| `.qmap` export | SQLite export includes `execution_environment_json`, `telemetry_provider_identity_json`, `telemetry_capabilities_json`, and `telemetry_capture_quality`. |
| `explain --evidence` | Updated to show persisted execution support, measurement-grade state, degradation reasons, providers, and capture quality. |
| `quantmap list` | Updated to show persisted execution support tier in the history table. |
| explicit-DB readers with empty current env | `explain --db` and `export --db` succeeded with empty current env values and still used persisted WSL degraded evidence. |

## 9. Code Changes From This Validation

Two small reader-surface changes were made because validation showed explain/history could operate but did not visibly surface the degraded platform truth:

- `src/explain.py`: `--evidence` now prints persisted execution support tier, execution boundary, measurement-grade state, platform degradation reasons, telemetry providers, and telemetry capture quality from the run snapshot.
- `src/runner.py`: `quantmap list` now includes a narrow `Support` column sourced from persisted `campaign_start_snapshot.execution_environment_json`.

No backend abstraction, WSL interop mode, Windows-host telemetry bridge, native Linux support, or report redesign was added.

## 10. What This Proves

This pass proves:

- QuantMap can complete a real end-to-end WSL 2 run when given a valid Linux-native backend path.
- The WSL run remains explicitly `wsl_degraded`.
- Measurement-grade remains `false`.
- Missing Linux CPU thermal interfaces remain persisted as degradation evidence.
- GPU/NVML visibility can be represented without making WSL measurement-grade.
- Report, export, explain, and history surfaces can preserve persisted degraded truth.
- Explicit-DB historical readers can read the run under empty current env values.

## 11. What This Does Not Prove

This pass does not prove:

- measurement-grade bare-metal `linux_native` support
- native Linux CPU thermal provider availability
- Linux/NVIDIA benchmarking parity with Windows/HWiNFO
- WSL host telemetry bridging
- backend abstraction readiness
- benchmark-quality performance conclusions for the Nemotron smoke run

## 12. Current-State Sentence

QuantMap can now complete a real end-to-end WSL 2 campaign when configured with a Linux-native backend, while correctly preserving `wsl_degraded`, non-measurement-grade execution evidence and keeping measurement-grade bare-metal `linux_native` support as future work. The `report_v2` Appendix B `NameError` identified during this smoke run has been fixed; `report_v2.md` now completes cleanly.

## 13. Post-Smoke-Run Fix: Appendix B NameError

**Date:** 2026-04-13  
**Scope:** one surgical fix to `src/report_campaign.py`

### Root Cause

`_appendix_eliminations` referenced the bare name `stats` on the line that derives the `degraded` dict:

```python
degraded = {cid: s.get("elimination_reason") for cid, s in stats.items() ...}
```

`stats` is a local variable in the caller (`generate_report_v2`) and was never passed as a parameter to `_appendix_eliminations`. The function signature accepts only `scores_result`, `config_variable_map`, and `variable_name`. Because `stats` is always available as `scores_result["stats"]`, this is the correct source.

### Fix

One line changed in `src/report_campaign.py:1540`:

```python
# before
degraded = {cid: s.get("elimination_reason") for cid, s in stats.items() if s.get("config_status") == "degraded"}

# after
degraded = {cid: s.get("elimination_reason") for cid, s in scores_result.get("stats", {}).items() if s.get("config_status") == "degraded"}
```

No other changes were made to `_appendix_eliminations` or any other report function.

### Why `scores_result.get("stats", {})` and not `scores_result["stats"]`

Defensive access is used because `_appendix_eliminations` does not control what is in `scores_result`. The `stats` key is always present in practice, but `get({})` keeps the function safe if called from an unusual rescore path. This is not a speculative fallback — it does not hide real scoring failures; it only guards the rendering function from a missing key in a data structure it receives.

### Validation

- Unit test: called `_appendix_eliminations` directly with a synthetic `scores_result` that includes a `stats` entry with `config_status == "degraded"` and `elimination_reason == "wsl_degraded"`. No NameError. Degraded config appeared in both the Eliminated table and the Forensic Exclusions sub-table.
- End-to-end test: `rescore.py TrustPilot_v1` (campaign with one eliminated config). `report_v2.md` written without any `appendix_b` failure. `report_v2_md` artifact recorded as `complete; error=None` in the DB.
- No regression in export, explain, or history surfaces — the fix touches only the rendering function.

### WSL degraded truth unchanged

The fix does not change WSL classification, measurement-grade state, degraded reasons, or any persistence behavior. The `wsl_degraded` evidence in the DB from the original smoke run remains correct.
