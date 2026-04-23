# Phase 2.1 Settings/Environment Bridge Implementation Validation Memo

Status: implementation pass complete  
Date: 2026-04-12  
Scope: Phase 2.1 settings/environment bridge only

## 1. What Changed

Phase 2.1 implemented the narrow settings/environment bridge approved after Phase 2 closure.

Core changes:

- Added `src/settings_env.py`, a small stdlib-only helper for environment path normalization.
- Treats `None`, `""`, whitespace-only values, and env values that point to the current directory as unavailable/invalid for required runtime paths.
- Updated `src.config.LAB_ROOT` so empty/missing/invalid lab root fails clearly instead of becoming `Path('.')`.
- Updated `src.server.SERVER_BIN` and `src.server.MODEL_PATH` so empty/missing/invalid runtime paths fail clearly instead of becoming `Path('.')`.
- Updated CLI path resolution in `quantmap.py` to use the shared semantics while preserving explicit `--db` / `--output` reader independence.
- Added clearer `doctor` diagnostics for lab root, inference server, and model path, including empty-env cases.
- Updated `export --strip-env` so normal CLI use hard-fails when no trustworthy redaction root exists. It no longer creates a bundle that appears redacted when redaction is incomplete.
- Updated export manifest/redaction internals to receive redaction root explicitly instead of importing `src.config.LAB_ROOT`.
- Contained report fallback behavior so empty `QUANTMAP_LAB_ROOT` no longer becomes report output root `Path('.')`.
- Updated characterization/report model-path reads to use the shared env semantics where relevant.

Out-of-scope work was intentionally not done:

- no telemetry provider implementation
- no backend adapter implementation
- no broad settings framework
- no runner decomposition
- no report consolidation
- no optimization/recommendation work

## 2. Files Touched

Code files:

- `src/settings_env.py`
- `src/config.py`
- `src/server.py`
- `quantmap.py`
- `src/doctor.py`
- `src/export.py`
- `src/report.py`
- `src/report_campaign.py`
- `src/characterization.py`

Documentation artifact:

- `docs/decisions/Phase-2.1-Settings-Environment-Bridge-Implementation-Validation-Memo.md`

## 3. Validation Run

### Compile / Syntax

Passed:

```powershell
.\.venv\Scripts\python.exe -m compileall src\settings_env.py src\config.py src\server.py quantmap.py src\doctor.py src\export.py src\report.py src\report_campaign.py src\characterization.py
```

### Required Path Semantics

Passed:

- Empty `QUANTMAP_LAB_ROOT` now raises `SettingsEnvError` instead of importing as `Path('.')`.
- Empty `QUANTMAP_SERVER_BIN` and `QUANTMAP_MODEL_PATH` now raise `SettingsEnvError` instead of importing as `Path('.')`.
- Env value `.` is classified as `invalid` by the shared helper.
- Empty `QUANTMAP_LAB_ROOT` no longer makes `src.report.LAB_ROOT` or `src.report_campaign.LAB_ROOT` equal to `Path('.')`; they fall back to the existing backward-compatible default.

Representative observed outputs:

- `config_error SettingsEnvError QUANTMAP_LAB_ROOT is empty...`
- `server_error SettingsEnvError QUANTMAP_SERVER_BIN is empty...`
- `QUANTMAP_SERVER_BIN invalid None QUANTMAP_SERVER_BIN points to the current directory`

### Shell Commands Under Empty Env

Passed with `QUANTMAP_LAB_ROOT=''`, `QUANTMAP_SERVER_BIN=''`, and `QUANTMAP_MODEL_PATH=''`:

```powershell
.\.venv\Scripts\python.exe quantmap.py --plain --help
.\.venv\Scripts\python.exe quantmap.py --plain status
.\.venv\Scripts\python.exe quantmap.py --plain doctor
.\.venv\Scripts\python.exe quantmap.py --plain about
```

Observed behavior:

- help works
- status works in degraded/blocked mode
- doctor reports lab root, server binary, and model path as empty
- about still reports software identity and marks lab/DB unavailable

### Explicit-DB Historical Reader Independence

Passed under empty env:

```powershell
.\.venv\Scripts\python.exe quantmap.py --plain explain TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite
.\.venv\Scripts\python.exe quantmap.py --plain audit TrustPilot_v1 TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite
.\.venv\Scripts\python.exe quantmap.py --plain compare TrustPilot_v1 TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite --output $env:TEMP\qmap-bridge-compare.md --force
.\.venv\Scripts\python.exe quantmap.py --plain export TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite --output $env:TEMP\qmap-bridge-export.qmap --lite
```

Observed behavior:

- explicit-DB explain, audit, compare, and non-redacted export work without lab-root env
- no lab-root default is required when explicit input/output paths are provided

### Export Redaction Root Semantics

Passed:

```powershell
$env:QUANTMAP_LAB_ROOT=''
.\.venv\Scripts\python.exe quantmap.py --plain export TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite --output $env:TEMP\qmap-bridge-export-redacted.qmap --lite --strip-env
```

Observed behavior:

- command exits with code `1`
- no bundle is created
- message says `--strip-env` requires a valid redaction root
- message states QuantMap will not create a bundle that appears redacted when redaction is incomplete

Passed with valid lab root:

```powershell
$env:QUANTMAP_LAB_ROOT='D:\Workspaces\QuantMap'
.\.venv\Scripts\python.exe quantmap.py --plain export TrustPilot_v1 --db D:\Workspaces\QuantMap\db\lab.sqlite --output $env:TEMP\qmap-bridge-export-redacted-ok.qmap --lite --strip-env
```

Observed behavior:

- export succeeds
- privacy label includes `Stripped/Redacted (schema_aware_applied:7)`

### Current-Run / Current-Input Fail-Loud Behavior

Passed under empty env:

```powershell
.\.venv\Scripts\python.exe quantmap.py --plain run --campaign C01_threads_batch --dry-run --mode quick
.\.venv\Scripts\python.exe quantmap.py --plain rescore TrustPilot_v1 --current-input
```

Observed behavior:

- both exit with code `1`
- both show a clear settings/path error
- neither silently writes into repo-root `db`, `logs`, `results`, or `state`

## 4. Remaining Concern Or Follow-Up

No Phase 2.1 implementation blocker remains from this pass.

Follow-up to track after review:

- Living trackers should be updated after acceptance to mark TODO-031 / QM-005 bridge progress or closure.
- Phase 3 should remain pending until this bridge is accepted and the living docs are aligned.
- Existing repo-root `results` was already present before this pass. An empty repo-root `logs` directory created during an earlier validation probe was removed after confirming it was empty.

## 5. Phase State Recommendation

Treat Phase 2.1 implementation pass as complete and ready for review.

Do not activate Phase 3 until:

- this memo is accepted
- living docs/K.I.T./TO-DO are aligned
- the project explicitly marks the settings/environment bridge as closed
