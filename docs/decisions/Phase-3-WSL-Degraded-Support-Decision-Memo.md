# Phase 3 WSL Degraded Support Decision Memo

Status: accepted implementation decision  
Date: 2026-04-13  
Scope: Phase 3 Platform Generalization, WSL degraded support only

## 1. Decision

QuantMap will support WSL 2 as an explicitly degraded Linux-like execution target now.

WSL 2 must not be treated as native Linux. It must not be described as measurement-grade Linux support.

The current support tiers are:

- `windows_native`
- `wsl_degraded`
- `linux_native` reserved for later validation

## 2. Target Evidence

Validated on the target Windows/NVIDIA machine:

- WSL 2 is installed and running.
- Ubuntu is installed under WSL 2.
- Docker Desktop is integrated with the Ubuntu distro.
- Docker works from Ubuntu.
- `docker run --rm hello-world` succeeds inside Ubuntu.
- GPU passthrough into Linux containers works.
- `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` sees the RTX 3090.
- `nvidia-smi` works directly inside Ubuntu.

Also validated:

- `command -v sensors` returns nothing.
- `/sys/class/thermal` contains only `cooling_device*`.
- `/sys/class/thermal` has no `thermal_zone*`.
- `/sys/class/hwmon` is empty.
- no normal Linux `temp*_input` thermal files are visible.

Conclusion: WSL is useful for Linux-like execution, Docker/container validation, GPU visibility, and bounded platform hardening. It does not expose normal Linux CPU thermal interfaces on this machine.

## 3. Support Semantics

### `windows_native`

- Measurement-grade can remain true when Windows current-run safety requirements are met.
- Windows HWiNFO/NVML fail-loud behavior is not weakened.

### `wsl_degraded`

- Current runs may proceed as degraded when the rest of the runtime is usable.
- Measurement-grade is false.
- Boundary type is WSL 2 / hypervisor boundary.
- CPU thermal telemetry remains unavailable/fail-honest.
- GPU visibility through `nvidia-smi` may be represented when available.
- Python NVML sampling support remains distinct from `nvidia-smi` visibility.

### `linux_native`

- Reserved for a later bare-metal Linux compatibility phase.
- Not claimed complete by this WSL work.
- Requires real native Linux validation and an approved CPU thermal policy.

## 4. Explicit Non-Goals

This decision does not implement:

- Windows-host telemetry bridge
- native Linux measurement-grade support
- backend abstraction
- plugin framework
- broad runner decomposition
- report consolidation
- universal hardware support

## 5. Trust Rule

WSL degraded evidence must be persisted and surfaced. Historical readers must use persisted evidence, not current live environment reconstruction.

Downstream artifacts should make these facts hard to miss:

- support tier is `wsl_degraded`
- measurement-grade is false
- CPU thermal interfaces are unavailable
- WSL is not native Linux

