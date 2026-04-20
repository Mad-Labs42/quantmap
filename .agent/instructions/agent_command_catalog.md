# Agent Command Catalog

Purpose: Standardized, token-efficient command workflows for coding agents.

## Core Commands

### Dev Contract Preflight

- Command: `.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick`
- Use when: starting implementation work or checking whether the active shell is using the repo development contract.
- Full check: `.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --full`
- CI check: `python .agent/scripts/helpers/verify_dev_contract.py --full --ci`
- Local failure semantics:
  - fails when the active interpreter is not the repo `.venv`
  - fails when the repo `.venv` is not anchored to `D:\.store\mise\data\installs\python\3.13.13`
  - fails when the active Python minor is not 3.13
  - fails when required dev tools are not importable
- Remediation: recreate `.venv` with `& D:\.store\mise\data\installs\python\3.13.13\python.exe -m venv .venv`, run `.\.venv\Scripts\python.exe -m pip install --no-user -e '.[dev]'`, then rerun the contract check with `.\.venv\Scripts\python.exe`.

### Agent Surface Audit

- Command: `.\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py --strict`
- Use when: validating instruction/policy drift controls (missing sections, size erosion, routing drift, pointer drift, and critical policy invariants).
- Output: `.agent/artifacts/agent_surface_audit.json` with `status`/`failures`/`warnings` plus structured category entries.
- Failure semantics: non-zero exit on strict failures.

### Changed-Path Verification

- Command: `.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py`
- Use when: verifying edits before claiming completion.
- Default behavior:
  - discovers changed and untracked files
  - runs lint + syntax checks for changed Python paths
  - runs focused pytest on changed test files and inferred test targets
  - writes artifact to `.agent/artifacts/changed_path_verify.json`
- Common flags:
  - `--base-ref <ref>` compare to specific git ref
  - `--paths <path...>` verify explicit files/directories only
  - `--no-untracked` exclude untracked files
  - `--max-test-files <n>` cap test fan-out
  - `--require-tests` fail when no test targets are found
  - `--dry-run` show selected checks without executing
  - Use `--paths` when unrelated dirty files would otherwise contaminate verification

### Agent Handoff Generator

- Command: `.\.venv\Scripts\python.exe .agent\scripts\generate_agent_handoff.py`
- Use when: finalizing work or preparing continuity handoff.
- Default behavior:
  - summarizes branch, changed files, and diff stats
  - includes available verification artifacts
  - produces sequential A2A JSON handoff outputs
  - writes to `.agent/handoffs` using sequential names: `agent-HO-1.json`, `agent-HO-2.json`, ...
- Outputs:
  - `.agent/handoffs/agent-HO-<n>.json`
  - optional markdown only when `--output-md <path>` is explicitly provided

### Workflow Chain Smoke Check

- Command: `.\.venv\Scripts\python.exe .agent\scripts\agent_workflow_smokecheck.py`
- Use when: validating instruction chaining and anti-over-ingestion safeguards.
- Default behavior:
  - checks key policy files for required minimal-read and escalation phrases
  - validates canonical instruction-root configuration
  - writes artifact to `.agent/artifacts/agent_workflow_smokecheck.json`

### BUG-GATE List Refresh

- Command: `.\.venv\Scripts\python.exe .agent\scripts\refresh_bug_gate_list.py --prefer-artifacts` (or `.\.venv\Scripts\python.exe .agent\scripts\refresh_bug_gate_list.py --local-only`)
- Use when: refreshing the manual BUG-GATE advisory tracker from digest artifacts and/or local digest runs.
- Outputs:
  - `docs/K.I.T.-&-ToDo/BUG-GATE-HIT-LIST.json` (canonical source)
  - `docs/K.I.T.-&-ToDo/BUG-GATE-HIT-LIST.md` (rendered view)
- Recommended cadence: daily and after merges.

### SonarCloud Digest

- Command: `.\.venv\Scripts\python.exe .agent\scripts\helpers\sonar_digest.py --json`
- Use when: collecting current SonarCloud issues, hotspots, and quality-gate signal into canonical BUG-GATE findings schema.
- Common flags:
  - `--project-key <key>` SonarCloud project key (default: `Mad-Labs42_quantmap`)
  - `--organization <org>` SonarCloud org key (default: `mad-labs42`)
  - `--max-findings <n>` cap findings in output
- Failure semantics:
  - returns `auth_missing` with `no_data` findings when `SONAR_TOKEN` is absent/invalid
  - returns `no_data` on network/rate-limit/API failures

### CodeQL Digest

- Command: `.\.venv\Scripts\python.exe .agent\scripts\helpers\codeql_digest.py --repo <owner/repo> --json`
- Use when: collecting GitHub code-scanning (CodeQL) alerts into canonical BUG-GATE findings schema.
- Common flags:
  - `--repo <owner/repo>` repository selector (default: `Mad-Labs42/quantmap`)
  - `--state <open|closed|dismissed|fixed>` alert state filter (default: `open`)
  - `--max-findings <n>` cap findings in output
- Failure semantics:
  - returns `scope_missing` with `no_data` findings when code-scanning scope/permissions are insufficient
  - returns `auth_missing` when GitHub auth is unavailable
  - returns `no_data` on network/rate-limit/API failures

### pip-audit Digest

- Command: `.\.venv\Scripts\python.exe .agent\scripts\helpers\pip_audit_digest.py --json`
- Use when: collecting dependency vulnerability signals from pip-audit into canonical BUG-GATE findings schema.
- Common flags:
  - `--requirements <path>` optional requirements file input for pip-audit
  - `--max-findings <n>` cap findings in output
- Failure semantics:
  - returns `tool_missing` with `no_data` findings when `pip-audit` is not installed
  - returns `tool_unavailable` with `no_data` findings on index/network/tooling failures

### mypy Digest

- Command: `.\.venv\Scripts\python.exe .agent\scripts\helpers\mypy_digest.py --json`
- Use when: collecting mypy static typing diagnostics into canonical BUG-GATE findings schema.
- Common flags:
  - `--paths <path...>` optional mypy path targets; when omitted, mypy default config behavior is used
  - `--max-findings <n>` cap findings in output
- Failure semantics:
  - returns `tool_missing` with `no_data` findings when `mypy` is not installed
  - returns `no_data` with captured note on crashes/config failures that produce no parseable diagnostics

### Terminal Guardrails and Failure Commands

- See `.agent/reference/terminal_guardrails.md` for terminal guardrails and the optional PowerShell wrapper.
- Preflight command checker: `.\.venv\Scripts\python.exe .agent\scripts\helpers\terminal_preflight_check.py --shell powershell --command "<command>"`
- Guardrail self-test proof: `.\.venv\Scripts\python.exe .agent\scripts\helpers\terminal_guardrail_selftest.py`

## Lightweight Utility Commands

### Targeted Lint

- `.\.venv\Scripts\python.exe -m ruff check <paths>`
- `.\.venv\Scripts\python.exe -m ruff check --fix <paths>`

### Targeted Tests

- `.\.venv\Scripts\python.exe -m pytest -q <test_paths_or_nodeids>`

### Syntax Check

- `.\.venv\Scripts\python.exe -m compileall -q <paths>`

## Recommended Agent Workflow

1. Run dev contract preflight.
2. Implement minimal patch.
3. Run changed-path verification.
4. Fix findings and re-run verification.
5. Run workflow chain smoke check when policy/docs are edited.
6. Generate handoff when completing task.

## Escalation Triggers

Ask user before proceeding when command outcomes imply:

- required deviation from provided plan
- architecture or cross-system impact
- ambiguous scope or acceptance criteria
- destructive or irreversible operations
- dependency/interface/schema/public behavior expansion beyond request
