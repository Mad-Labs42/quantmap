# Environment Hardening Guide

Measurement jitter is the enemy of statistical significance. To achieve "Clinical-Grade" benchmarks, your environment must be a silent, stable stage. 

---

## 1. Failure Signatures: What "Bad" Looks Like

As an operator, you must learn to recognize the telemetry signatures of an invalid environment.

| Signature | What it looks like in Telemetry | Cause |
|---|---|---|
| **CPU Saturation** | 95%+ CPU Util, high variance in TTFT. | Background indexing or Windows Update. |
| **Thermal Wall** | GPU Temp plateaus; `thermal_events` > 0. | Cooling failure or aggressive GGUF splitting. |
| **I/O Drag** | Long "Idle" times between requests; low TG rate. | Antivirus scanning the `.gguf` file or Disk compression active. |
| **Context Jitter** | High CV (> 5%) with no high CPU usage. | Power Plan set to "Balanced" or "Power Saver." |

---

## 2. Hardware Monitoring (HWiNFO)

QuantMap relies on HWiNFO64 to capture the "Pulse" of the hardware.

1.  **Install HWiNFO64**.
2.  **Enable Shared Memory Support**: 
    - Settings -> General -> Check "Shared Memory Support."
    - *Note*: This version requires manual re-activation every 12 hours on the Free version.
3.  **Sensor Selection**: QuantMap reads CPU Temp, GPU Temp, and Thermal Throttling Status. Ensure these sensors are visible and reporting in the HWiNFO Sensors-Only window.

---

## 3. Windows Noise Suppression

### Windows Defender
Real-time scanning causes massive I/O jitter. 
- **The Golden Rule**: Add your **Lab Root**, **Binary Path**, and **Model Directory** to Defender Exclusions. 
- **Verify**: Use `quantmap doctor` to check if exclusions are active.

### Windows Search & Indexing
- **Action**: Disable indexing on the model drive.
- **Why**: The indexer often triggers during large file reads (server startup), causing cold-start latency spikes.

### Power Management
- **The "High Performance" Rule**: Ensure your machine is in High or Ultra High Performance mode.
- **Why**: "Balanced" mode parks cores and downclocks frequency during short idles, adding significant TTFT jitter.

---

## 4. Common Pitfalls

- **Relying on `doctor --fix` for system-level hardening**: QuantMap's auto-fixer only handles filesystem staging. It will **not** change your Security settings or Power Plan. These must be performed manually.
- **Ambient Temperature Spikes**: Don't run benchmarks while the AC is cycling or sun is hitting the rig.
- **Memory Saturation**: Ensure you have at least 2GB of headroom above your VRAM/RAM allocation. Swap file activity is fatal to throughput.

> [!CAUTION]
> **When NOT to use `doctor`**: Do not treat a `READY WITH WARNINGS` state as a "Pass" if you are performing a thermal-soak test. Without HWiNFO, the tool cannot see if the GPU is throttling, which is a fatal lack of evidence for that specific use case.
