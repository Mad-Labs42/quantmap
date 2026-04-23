# Artifact-System-Upgrade

## Objective
A pre-implementation investigative pass verifying the exact source of truth, classification, fallback behavior, math soundness, and blast radius of proposed local-LLM hardware constraints before integration into the QuantMap reporting layer.

## Project Directives & Constraints
- **Canonical Artifacts:** Strictly 4 (Summary, Run-Reports, Telemetry JSONL, Metadata JSON). No 5th artifact.
- **Classification:** Strictly distinguish between `measured`, `OS-reported metadata`, `inferred from hardware metadata`, and unavailable states.
- **Reporting Rigor:** Do not present speculative "AI-friendly" derivations as facts. Graceful, explicit failure strings are required when data cannot be natively probed.
- **Scope Limits:** Support tuning without bloating the summary.

---

## 1. Targeted Field Investigation

### A. PCIe Generation & B. PCIe Lane Width
- **Source of Truth:** `pynvml.nvmlDeviceGetCurrPcieLinkGeneration()` and `nvmlDeviceGetCurrPcieLinkWidth()`. Highly reliable for NVIDIA hardware.
- **Classification:** `OS-reported metadata` (driver level).
- **Missing-Value Behavior:** `"not exposed by active driver/api"` (Catch-all for non-NVML setups).
- **Derived Math Soundness:** Deriving theoretical PCIe throughput (e.g., Gen4 x16 -> ~31.5 GB/s) is **sound but conditional**. It must be explicitly labeled as `theoretical_interconnect_throughput_gbs_inferred` because it represents the spec limit, not a live-measured bandwidth test.

### C. Usable VRAM Headroom
- **Source of Truth:** `pynvml.nvmlDeviceGetMemoryInfo(handle).free` (captured exactly *after* OS/Desktop bloat stabilization, but *before* the LLM server node allocates memory).
- **Classification:** `direct measurement`.
- **Missing-Value Behavior:** `"probe failed"` (if NVML throws during measurement phase).
- **Derived Math Soundness:** Sound. Total VRAM minus Free VRAM = exact OS overhead. No brittle derivations required. 

### D. Affinity Mask (Process-Level Capture)
- **Source of Truth:** `psutil.Process(pid).cpu_affinity()`. Cross-platform compatible. Provides precise indices of cores mapped to the backend executing the LLM.
- **Classification:** `direct OS-reported metadata`.
- **Missing-Value Behavior:** `"unavailable_permission_denied"` (if OS denies inspection rights) or `"unavailable_process_not_found"`.
- **Derived Math Soundness:** No derivations needed. The output is a literal array of logical thread integers indicating the scheduler bounds.

### E. RAM Configured Speed
- **Source of Truth:** Subprocess to `Win32_PhysicalMemory` (via PowerShell or WMI) on Windows, or `dmidecode -t memory` on Linux.
- **Classification:** `direct OS-reported metadata`.
- **Missing-Value Behavior:** `"not supported on this platform"` (if MacOS) or `"unavailable_requires_root"` (Linux `dmidecode` without sudo) or `"probe failed"`.
- **Derived Math Soundness:** No math required for speed MT/s reporting. 

### F. RAM Channel Topology
- **Source of Truth:** Not natively available without heavy diagnostic dependencies mimicking CPU-Z behavior or advanced kernel interrogation.
- **Classification:** `unavailable on this platform / inferred`.
- **Missing-Value Behavior:** `"not collected by current methodology"`.
- **Derived Math Soundness:** Calculating Theoretical System RAM Throughput requires multiplying configured speed by active channel count topology. Because channel count cannot be reliably probed without unacceptable bloat, deriving full system architecture RAM bandwidth is **too brittle** and therefore rejected from automated calculation.

### G. Theoretical VRAM Bandwidth Context (Memory Subsystem Context)
- **Source of Truth:** Offline Hardware Dictionary mapping (e.g., `"NVIDIA RTX 3090": 936.0`).
- **Classification:** `inferred from hardware metadata`.
- **Missing-Value Behavior:** If the GPU is unmapped in the dictionary: `"insufficient inputs for trustworthy derivation"`.
- **Derived Math Soundness:** While `pynvml` *can* report memory clocks and bus widths, deriving final GB/s is highly brittle due to undocumented GDDR vs HBM memory multipliers across architectures. The math is **unsound**. Utilizing an explicitly hardcoded offline dictionary mapping the hardware ID to spec throughput is the only safe, defensible way to provide this tuning context to AIs.

---

## 2. Blast Radius & Affected Files

| Component Layer | Likely File Touches | Action Required | Rescore/Runner Scope |
|---|---|---|---|
| **Telemetry / Characterization** | `src/telemetry.py` <br> `src/server.py` | Add safe, wrapped accessors for `psutil.affinity()` and `pynvml` PCIe calls. Safe `get_ram_speed()` subprocessing. | **Runner Only** |
| **Run Context / DB** | `src/runner.py` <br> `src/db.py` | Call probes during initialization block. Record these variables safely into the existing snapshot/environment SQL payload or `_stream: marker` JSONL. | **Runner Only** |
| **Artifact / Report Gen** | `src/report.py` <br> `src/report_campaign.py` | In `run-reports.md`, add an explicit sub-table or list characterizing hardware constraints with precision labeling (e.g. `(OS-Reported)`, `(Inferred)`). | **Both (Rescore & Runner)** |
| **Export / Metadata** | `src/export.py` | Add a `system_topology` constraints block in `metadata.json` capturing the new namespace arrays explicitly. | **Both** |

---

## 3. Rescore & Compatibility Demands (Parity Risks)

- **Strict Probe Isolation:** The runner (`src/runner.py`) is the *only* component allowed to probe the hardware realistically. All constraints must be locked as static JSON dicts in the database environment block when the run starts.
- **Rescore Determinism:** `rescore.py` must purely deserialize the snapshot. It must **never** execute `psutil` or `nvml` calls when regenerating reports. Rescoring cross-machine must produce identical topology constraints derived from the original SQL file footprint.
- **Legacy Parity:** If `rescore.py` encounters a historic legacy database generated prior to this Phase 6 investigation, the entire `system_topology` node defaults fields to explicitly emit `"not collected by current methodology"`, preventing runtime crash logic and fulfilling explicit string requirements.

---

## 4. Artifact Placement Constraints

1. **`campaign-summary.md`**: Do NOT add detailed PCIe or bandwidth tables here. Maintain as a lightweight executive summary. Only raise an alert block if something disastrous is detected (e.g., PCIe Gen1 mode).
2. **`run-reports.md`**: Embed a dense `### Hardware Topology & Constraints` mapping immediately adjacent to the `## Target Environment` definitions inside the detailed report.
3. **`metadata.json`**: Create a formal node (e.g., `environment.hardware_constraints`) categorizing these elements into standard types: `"pcie_gen": {"source": "OS_REPORTED", "value": 4}` for robust AI parsing limits.
4. **`raw-telemetry.jsonl`**: The environment layout captures all snapshot properties immediately prior to metric generation natively.

---

## 5. Pre-Implementation Checklist / Unanswered Gates

Before transitioning to Implementation, these gates must close:
1. Are we comfortable absorbing the technical debt of a static "Offline Hardware Dictionary" within QuantMap source to safely declare Theoretical VRAM boundaries, or should we completely abandon GPU output bandwidth references to ensure extreme minimalism?
2. Are OS-level subprocessing calls to `wmic` / `Get-CimInstance` considered acceptable attack surface additions for an analysis tool, or should RAM speed be designated as User-Supplied YAML only?
