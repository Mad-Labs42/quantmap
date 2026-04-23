# Phase 3 WSL Degraded Support Follow-Up Validation Memo

Status: bounded follow-up complete  
Date: 2026-04-13  
Scope: WSL degraded support cleanup, WSL Python setup, and first real WSL QuantMap campaign-start validation

## 1. Purpose

This memo records the bounded follow-up after accepting WSL 2 as an explicit degraded Linux-like execution target.

This pass did not attempt to complete native Linux support, add a Windows-host telemetry bridge, introduce backend abstraction, or redesign packaging. Its purpose was narrower:

- correct stale Linux/NVIDIA safety-note wording
- set up a usable WSL Python environment for QuantMap
- run the first real QuantMap path inside WSL
- verify that WSL degraded truth is persisted and visible downstream
- preserve the distinction between WSL degraded support and future bare-metal `linux_native`

## 2. WSL Python Environment Setup

Ubuntu had Python 3.12.3 available, which satisfies QuantMap's `requires-python = ">=3.12"`.

Initial `python3 -m venv` failed because Ubuntu did not have `python3.12-venv` / `ensurepip` installed, and passwordless `sudo` was unavailable. The setup therefore used a user-local bootstrap path:

```bash
curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
python3 /tmp/get-pip.py --user --break-system-packages
python3 -m pip install --user --break-system-packages virtualenv
python3 -m virtualenv "$HOME/.venvs/quantmap-phase3-wsl"
. "$HOME/.venvs/quantmap-phase3-wsl/bin/activate"
python -m pip install --upgrade pip setuptools wheel
cd /mnt/d/Workspaces/QuantMap_agent
python -m pip install -e .
```

Dependency import verification passed for:

- `psutil`
- `yaml`
- `httpx`
- `pandas`
- `numpy`
- `pynvml`
- `rich`
- `dotenv`
- `pydantic`

No project packaging model was changed.

## 3. Real WSL Validation Performed

Validation ran inside the WSL Ubuntu distro using:

- repo path: `/mnt/d/Workspaces/QuantMap_agent`
- venv: `/home/hitchhiker/.venvs/quantmap-phase3-wsl`
- lab root: `/home/hitchhiker/work/quantmap-wsl-lab`
- server binary for this validation attempt: `/mnt/d/.store/tools/llama.cpp/build-B/bin/llama-server.exe`
- model path: `/mnt/d/.store/models/Devstral-Small-2507/Q5_K_M/Devstral-Small-2507-Q5_K_M.gguf`

The key commands were:

```bash
python quantmap.py status
python quantmap.py doctor --fix
python quantmap.py run --campaign C01_threads_batch --mode quick --values 4 --cycles 1 --requests-per-cycle 1 --dry-run
python quantmap.py run --campaign C01_threads_batch --mode quick --values 4 --cycles 1 --requests-per-cycle 1
python quantmap.py explain --db /home/hitchhiker/work/quantmap-wsl-lab/db/lab.sqlite C01_threads_batch__quick --evidence
python quantmap.py compare --db /home/hitchhiker/work/quantmap-wsl-lab/db/lab.sqlite C01_threads_batch__quick C01_threads_batch__quick --force --output /home/hitchhiker/work/quantmap-wsl-lab/results/C01_threads_batch__quick/self_compare.md
python quantmap.py export --db /home/hitchhiker/work/quantmap-wsl-lab/db/lab.sqlite C01_threads_batch__quick --output /home/hitchhiker/work/quantmap-wsl-lab/C01_threads_batch__quick_wsl_degraded.qmap --lite
```

## 4. Validation Results

| Area | Result | Evidence |
|---|---|---|
| WSL detection | passed | `execution_platform=linux`, `support_tier=wsl_degraded`, `boundary_type=wsl2_hypervisor_boundary` |
| Measurement-grade classification | passed | `measurement_grade=false` persisted in `execution_environment_json` |
| Degraded reasons | passed | persisted reasons include `wsl_hypervisor_boundary`, `not_linux_native`, and `missing_linux_cpu_thermal_interfaces` |
| CPU thermal fail-honest behavior | passed | `cpu_temp_c` persisted as `unsupported`; startup logs warned that WSL CPU package temperature is unavailable and the run is not measurement-grade |
| GPU/NVML visibility | passed | NVML provider persisted as `available` with RTX 3090 and driver `591.86`; `nvidia_smi_available=true` persisted in execution evidence |
| WSL readiness policy | passed | provider readiness returned `degraded`, not `blocked`; current-run readiness did not block solely because Linux CPU thermal interfaces were missing |
| Report propagation | passed | `report.md` and `report_v2.md` show `Execution support tier = wsl_degraded`, `Measurement-grade platform = False`, degradation reasons, and degraded provider evidence |
| Export propagation | passed | `.qmap` export is a SQLite case file and includes the campaign start snapshot with persisted WSL degraded execution/provider evidence |
| Explicit-DB historical reader independence | passed for explain/compare/export | commands succeeded using explicit `--db` and literal output paths while current env values were empty |
| Real measurement validity | not passed | the campaign control path ran, but the measurement cycle crashed because the current backend path launches a Windows `llama-server.exe` through WSL interop and exited before HTTP readiness |

## 5. Persisted Run Evidence

The WSL run-start snapshot persisted:

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

Telemetry provider evidence persisted:

- HWiNFO shared memory: `unsupported`
- NVML: `available`
- telemetry capture quality: `degraded`
- `cpu_temp_c`: `unsupported`
- `gpu_vram_used_mb`: `available`
- `power_limit_throttling`: `available`
- `gpu_temp_c`: `available`

## 6. Important Caveat

The first real WSL run did not produce a valid measurement sample. It proved the WSL degraded QuantMap startup, readiness, persistence, report, export, and explicit-DB historical reader paths. It did not prove a successful WSL measurement workload.

The measurement cycle failed because the current backend/server path is still a Windows `llama-server.exe` path launched through WSL interop and exited before the HTTP layer was ready. That is a bounded backend-execution/platform follow-up, not a reason to weaken WSL degraded telemetry semantics and not evidence for native Linux support.

## 7. Future Bare-Metal Linux Work

Still future work:

- measurement-grade `linux_native` support
- bare-metal Linux CPU thermal provider validation
- native Linux backend/server execution validation
- any Linux-specific provider policy that would claim measurement-grade safety
- optional future `wsl_host_bridged` design

WSL degraded support remains separate from all of the above.

## 8. Current-State Sentence

QuantMap now has real WSL 2 degraded-path validation: it can classify WSL explicitly, persist non-measurement-grade degraded evidence, surface GPU/NVML visibility and missing CPU thermal truth downstream, and run historical readers from persisted evidence, while successful WSL measurement execution and measurement-grade bare-metal `linux_native` support remain future work.
