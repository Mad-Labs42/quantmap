# Phase 2.1 Bridge Recommendation

Status: recommended bridge before Phase 3 activation  
Date: 2026-04-12  
Scope: settings/environment boundary only

## Recommendation

Create a narrow **Phase 2.1 Settings and Environment Boundary Bridge** before activating Phase 3 Platform Generalization.

This bridge is justified by the Phase 2 final closure pass. Phase 2 substantially fixed the brittle current-methodology shell, but provider work still lacks a safe common settings/environment foundation.

## Why A Bridge Is Needed

The Phase 3 sequencing rule is:

> Telemetry/provider abstraction follows settings/environment boundary hardening.

That boundary is not ready yet.

Evidence:

- `src.config` still defines `LAB_ROOT` as an import-time constant.
- `src.config` checks only for `None`, so an empty `QUANTMAP_LAB_ROOT` becomes `Path('.')`.
- `src.server` still defines backend runtime paths at import time.
- `quantmap.py` has newer command-local helpers that treat empty env values as missing, which now differs from `src.config`.
- `export --strip-env` still uses `src.config.LAB_ROOT` for redaction, so a bad lab-root value can affect redaction behavior even when export uses explicit `--db` and `--output`.
- K.I.T. QM-005 and TO-DO TODO-017 already identify settings/path decoupling as the bridge between Operational Robustness and Platform Generalization.

## What This Bridge Is

This is a small boundary-hardening pass.

It should make current settings/environment state explicit enough that Phase 3 provider work does not recreate local lab assumptions.

## What This Bridge Is Not

It is not:

- telemetry provider implementation
- Linux/NVIDIA telemetry support
- backend adapter implementation
- broad settings framework
- packaging overhaul
- runner decomposition
- report consolidation
- optimization/recommendation work

## Proposed Scope

### 1. Normalize Environment Value Semantics

Treat missing and empty required env vars consistently.

Minimum targets:

- `QUANTMAP_LAB_ROOT`
- `QUANTMAP_SERVER_BIN`
- `QUANTMAP_MODEL_PATH`

Desired behavior:

- missing and empty strings both mean unavailable
- no required path silently becomes `Path('.')`
- command messages say what is missing and how to fix it

### 2. Add A Small Settings/Path Load Boundary

Create the smallest useful shared boundary for current settings state.

This can be a few functions or a small dataclass, not a framework.

It should answer:

- lab root available?
- lab root path if valid
- runtime server path available?
- model path available?
- source of each value
- error/remediation message when unavailable

Do not add provider abstraction here.

### 3. Preserve Explicit-DB Historical Reader Behavior

Historical readers with explicit `--db` should avoid lab-root requirements unless they truly need lab-root behavior.

Priority commands:

- `explain --db`
- `audit --db`
- `compare --db --output`
- `export --db --output`

### 4. Fix Export Redaction Root Semantics

`export --strip-env` needs an explicit and trustworthy redaction root.

Acceptable options:

- use a validated lab-root setting
- allow an explicit redaction root
- if unavailable, mark redaction as incomplete or fail clearly

Disallowed:

- treating `Path('.')` as a hidden lab root
- silently redacting based on an empty or malformed env value

### 5. Define Phase 3 Provider Settings Inputs

Before Phase 3 starts provider design, document the settings inputs providers are allowed to depend on.

Minimum:

- provider discovery should not import `src.server`
- provider diagnostics should not require a backend path unless that provider needs it
- telemetry availability should be reported as evidence quality, not hidden setup state
- provider code should not add new hardcoded lab-root or Windows path assumptions

## File-Level Touch Points

Likely files for the bridge:

- `src/config.py`
- `src/server.py`
- `quantmap.py`
- `src/doctor.py`
- `src/export.py`
- `docs/system/known_issues_tracker.md`
- `docs/system/TO-DO.md`
- current roadmap docs

Files to avoid broad refactoring:

- `src/runner.py`
- `src/report_campaign.py`
- `src/telemetry.py`

Touch them only if a small call-site adaptation is necessary.

## Verification Gates

The bridge is done when:

- empty `QUANTMAP_LAB_ROOT` does not resolve to the repo/current directory
- empty `QUANTMAP_SERVER_BIN` and `QUANTMAP_MODEL_PATH` do not resolve to current directory
- `quantmap --help`, `status`, `doctor`, and `about` remain usable under missing/empty env
- explicit-DB historical readers remain usable under missing/empty lab env
- `export --strip-env` either uses a validated redaction root or fails/labels incomplete redaction clearly
- Phase 3 provider work has a documented settings/environment input contract

## Relationship To Phase 2 Closure

This bridge is **not** the tiny Phase 2 final patch.

The Phase 2 final patch should close dry-run/readiness messaging and final closure validation.

The Phase 2.1 bridge should happen after that and before Phase 3 provider implementation.

## Recommendation Summary

Proceed in this order:

1. Land the tiny Phase 2 final patch.
2. Produce the final Phase 2 closure validation memo.
3. Run this Phase 2.1 settings/environment bridge.
4. Activate Phase 3 only after the bridge passes.

