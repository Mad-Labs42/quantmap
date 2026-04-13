# Phase 3 Linux/NVIDIA Safety Decision Note

Status: decision required before measurement-grade native Linux/NVIDIA support  
Date: 2026-04-13  
Scope: Phase 3 telemetry provider policy only

Update: The WSL 2 decision in `Phase-3-WSL-Degraded-Support-Decision-Memo.md` supersedes the earlier blocked stance for WSL only. WSL is now allowed as `wsl_degraded` with measurement-grade false. This note remains active for future bare-metal `linux_native` support and must not be read as approval for measurement-grade native Linux/NVIDIA runs.

## 1. Decision Needing Approval

Phase 3 can continue hardening the provider boundary without deciding Linux/NVIDIA CPU thermal policy. However, QuantMap cannot honestly claim measurement-grade Linux/NVIDIA support until this question is resolved:

> If NVML GPU safety signals are available on Linux/NVIDIA but CPU package temperature is unavailable, should current measurement block, run only as explicitly degraded, or proceed under a Linux-specific provider policy?

## 2. Current Evidence

- Windows current-run policy still blocks when HWiNFO CPU thermal evidence is unavailable.
- The provider boundary now distinguishes `windows_native`, `wsl_degraded`, and reserved future `linux_native` support tiers.
- WSL 2 has been validated on the actual Windows/NVIDIA machine as a degraded Linux-like execution target:
  - Ubuntu 24.04.4 runs under WSL 2.
  - Docker Desktop is integrated with the Ubuntu distro.
  - Docker works from inside Ubuntu.
  - `docker run --rm hello-world` succeeds inside Ubuntu.
  - Direct Ubuntu `nvidia-smi` sees the RTX 3090.
  - CUDA container GPU passthrough works with `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`.
- WSL on this machine does not expose normal Linux CPU thermal interfaces:
  - `sensors` is unavailable.
  - `/sys/class/thermal` exposes only `cooling_device*`.
  - No `thermal_zone*` entries are present.
  - `/sys/class/hwmon` has no usable `temp*_input` files.
- WSL current-run readiness is therefore allowed only as `wsl_degraded`, with measurement-grade false and explicit degradation reasons including `wsl_hypervisor_boundary`, `not_linux_native`, and `missing_linux_cpu_thermal_interfaces`.
- Future bare-metal `linux_native` current-run readiness remains validation-pending. WSL evidence must not be treated as native Linux evidence.

## 3. Options

### Option A: Block

If CPU package temperature is unavailable, current measurement blocks even if NVML GPU safety signals exist.

Trust implication: strongest. QuantMap avoids making benchmark-grade claims without CPU thermal evidence.

Operator UX implication: strict and potentially frustrating on Linux hosts where CPU package thermals are not readily available.

Portability implication: Linux/NVIDIA measurement support may remain unavailable until an acceptable CPU thermal provider is added.

### Option B: Allow Only Explicitly Degraded Runs

If CPU package temperature is unavailable, current measurement may proceed only under an explicit degraded mode with clear labels and reduced evidence quality.

Trust implication: acceptable only if downstream reports, exports, compare, and recommendations visibly treat the run as degraded and not equivalent to fully instrumented Windows/HWiNFO runs.

Operator UX implication: useful for exploratory validation, but operators must not confuse degraded evidence with clinical-grade benchmarking.

Portability implication: allows Linux/NVIDIA experimentation while preserving honesty.

### Option C: Linux-Specific Provider Policy

Define a Linux/NVIDIA provider policy with a different required-signal set, justified by target evidence.

Trust implication: potentially strong, but only if the alternate required signals are explicitly justified and validated.

Operator UX implication: cleanest long-term behavior if Linux/NVIDIA has a real supported telemetry stack.

Portability implication: best long-term fit, but requires more evidence than is currently available.

## 4. Recommendation

Do not approve measurement-grade Linux/NVIDIA support yet.

Recommended next step:

1. Keep WSL as an explicit `wsl_degraded` tier, not `linux_native`.
2. Continue to mark WSL measurement-grade as false while CPU thermal evidence is unavailable.
3. Perform future bare-metal Linux/NVIDIA target validation before approving `linux_native`.
4. If a viable native Linux CPU thermal provider is identified, prefer Option C for `linux_native`.
5. If no viable native Linux CPU thermal provider is available but exploratory native Linux runs are still valuable, consider Option B only with explicit degraded-mode labeling and downstream trust treatment.

## 5. Current Implementation Stance

The current code preserves safety:

- Windows current-run behavior remains fail-loud when HWiNFO CPU thermal evidence is missing.
- WSL current-run behavior is allowed only as `wsl_degraded`, with persisted degraded execution evidence and measurement-grade false.
- Linux/NVIDIA boundary evidence can be represented.
- Measurement-grade `linux_native` support remains deferred until a future bare-metal Linux validation phase resolves CPU thermal safety policy.
