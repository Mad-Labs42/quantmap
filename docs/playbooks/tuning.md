# Tuning Playbook

QuantMap is highly configurable. This playbook explains how to adjust the benchmarking pipeline for specific research or evaluation goals.

## 1. Governance: Registry vs. Profiles

QuantMap uses a two-layer governance model to separate *what* a metric is from *how* it is used.

- **Metric Registry (`configs/metrics.yaml`)**: Defines the canonical units, direction (maximize/minimize), and absolute filters for every metric.
- **Experiment Profile (`configs/profiles/*.yaml`)**: Defines the weights and active sub-set of metrics for a specific run.

> [!NOTE]
> **Cardinal Rule**: Profiles can tighten elimination gates (e.g. require CV < 3% instead of 5%), but they can NEVER relax them below the Registry floor.

## 2. Creating custom Baselines

A Baseline YAML defines the hardware-specific "Control" for your environment.

```yaml
# configs/baselines/my_custom_rig.yaml
lab_root: "D:/MyLab"
model_path: "D:/Models/Llama-3-8B-Q4_K_M.gguf"
server_bin: "D:/Tools/llama-server.exe"

# Resource Limits
max_threads: 16
batch_size: 512
```

Use your custom baseline by passing the `--baseline` flag:
```powershell
quantmap run --campaign C01 --baseline configs/baselines/my_custom_rig.yaml
```

## 3. High-Precision Tuning

If your results show high variance (Caution confidence), adjust the following in your **Campaign YAML**:

- **`cycles_per_config`**: Increase this (e.g. 5 -> 10) to improve statistical power.
- **`requests_per_cycle`**: Increase this (e.g. 30 -> 100) to flatten bursty outliers.

## 4. Adjusting Scoring Weights

To prioritize **Latency** over **Throughput**, create a custom Profile:

```yaml
# configs/profiles/latency_first.yaml
name: "Latency Sensitivity v1"
weights:
  warm_tg_median: 0.10
  warm_ttft_median_ms: 0.50
  warm_ttft_p90_ms: 0.30
  pp_median: 0.10
```

> [!IMPORTANT]
> **Methodology Drift**: Changing weights will significantly shift the winning config. Always use `quantmap audit` to ensure you are comparing campaigns that used the same profile.
