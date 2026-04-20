# .agent Directory Map

This folder contains agent-facing policy, instruction, automation, and generated continuity artifacts.

## scripts

- scripts/agent_surface_audit.py: Validates required agent files, required sections, policy invariants, routing consistency, and workspace guardrail settings.
- scripts/agent_workflow_smokecheck.py: Verifies instruction-chain integrity and anti-over-ingestion constraints.
- scripts/changed_path_verify.py: Runs changed-path lint/syntax/test verification and writes a summary artifact.
- scripts/generate_agent_handoff.py: Generates sequential agent-to-agent JSON handoff snapshots for continuity (optional markdown via explicit output flag).
- scripts/helpers/_ast_utils.py: Shared AST parsing utilities for Python signature extraction (used by signature_dump.py and git_symbol_summary.py).
- scripts/helpers/signature_dump.py: CLI tool to extract and dump Python function/class signatures from source files (plain text or JSON output).
- scripts/helpers/git_symbol_summary.py: CLI tool to summarize changed Python symbols between Git refs (merge-base with main by default, fallback to HEAD~1).
- scripts/helpers/_gh_client.py: GitHub API client with GH_TOKEN env-var or `gh auth` fallback, paginated GET wrapper, and rate-limit-aware error handling.
- scripts/helpers/verify_dev_contract.py: Verifies the active development interpreter, required dev tools, pytest-cov support, and default pytest config.
- scripts/helpers/terminal_preflight_check.py: Blocks shell-mismatch command patterns before execution.
- scripts/helpers/terminal_guardrail_selftest.py: Runs repeatable guardrail checks and writes a proof artifact.

## instructions

- instructions/agent_command_catalog.md: Command catalog for agent automation scripts and expected outputs.
- instructions/agent_maintenance.md: Maintenance guidance for instruction drift control and operating cadence.
- instructions/agent_session_bootstrap.md: First-session lock-in payload for instruction chain and execution rules.

## policies

- policies/adversarial.md: Critique/red-team review posture and failure-focused auditing rules.
- policies/architecture.md: High-level module ownership and dependency boundaries.
- policies/boundaries.md: Scope and trust constraints that must not be changed casually.
- policies/project.md: Repo purpose and success criteria.
- policies/routing.md: Policy-file routing rules to minimize unnecessary reads.
- policies/testing.md: Validation standards and verified vs unverified expectations.
- policies/tooling.md: Tool-use strategy and command workflow discipline.
- policies/workflow.md: Task flow, stop-and-ask thresholds, and reporting format.

## reference

- reference/command_reference.md: User-facing command reference for CLI command behavior.
- reference/terminal_guardrails.md: Central terminal guardrails, failure protocol, and wrapper guidance.

## docs

- docs/dev-contract.md: Repo-native development contract for local setup, verification, and CI parity.

## artifacts

- artifacts/agent_surface_audit.json: Latest strict audit report from agent_surface_audit.py.
- artifacts/agent_workflow_smokecheck.json: Latest workflow chain smokecheck report.
- artifacts/changed_path_verify.json: Latest changed-path verification report.
- artifacts/terminal_guardrail_proof.json: Latest terminal guardrail self-test proof report.

## handoffs

- handoffs/agent-HO-<n>.json: Agent-to-agent sequential handoff snapshot.

## docs/CHECKPOINTS-HANDOFFS

- docs/CHECKPOINTS-HANDOFFS/agent-HO-<n>.json: Agent-to-human handoff snapshot (only when explicitly requested).

Notes:

- Files under artifacts are generated outputs and are expected to be overwritten by script runs.
- This README should be updated whenever files are added, removed, or renamed under .agent.

## Guardrail Modifications (2026-04-18)

- Added terminal guardrails in AGENTS, scoped to VS Code and Antigravity contexts only.
- Added onboarding instruction that repeated command-category failures must capture debug context before retry.
- Added explicit PowerShell-only command syntax expectation for PowerShell terminals.
- Added explicit pre-mutation path verification expectation (cwd + target paths).
- Added automation boundary clarification:
  - helper scripts for agent automation belong in `.agent/scripts/helpers/`
  - project runtime/user-facing scripts must not be placed in helper script location
  - ad hoc token-saving scripts must not be placed in runtime paths (`src/`, root, etc.)
- Consolidated terminal failure guidance and wrapper guidance in `.agent/reference/terminal_guardrails.md`.
- Extended agent surface audit to require preflight/self-test guardrail phrases.
- Removed deprecated `.agents` folder and corrected active onboarding references back to `.agent` paths.
- Removed low-value helper scripts from the active script set.

### Terminal Guardrail List (VS Code and Antigravity only)

- See `.agent/reference/terminal_guardrails.md` for the canonical terminal guardrail rules and command guidance.

