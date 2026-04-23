# Agent Maintenance Guide

This guide defines repository-level maintenance for AI coding agents.

## Objectives

- Improve context quality
- Reduce token waste
- Increase tool-use reliability
- Prevent configuration drift

## Core Controls

### Instruction Sources

- .github/instructions/quantmap-agent.instructions.md
- .copilot/instructions/quantmap-agent.instructions.md (pointer-only mirror)
- AGENTS.md and .agent/policies/* policy files

### Workspace Noise Reduction

- Exclude caches and generated outputs from search/watch.
- Keep Python formatter/lint setup stable and explicit.

### Validation Discipline

- Prefer targeted verification over broad test runs.
- Require evidence before marking work complete.
- Auto-lint touched files after each edit batch.
- Require correctness checks for each changed behavior path.
- Require propagation updates to dependent call sites, tests, docs, and config when behavior or interfaces change.

### Escalation Discipline

- Require questions before any deviation from user plan.
- Require questions before architecture, major-system, or cross-module behavior decisions.
- Require questions whenever intent, scope, or acceptance criteria are unclear.
- Require questions for destructive or irreversible operations.

### Response Structure Discipline

- Use only needed sections: Outcome, Changes, Verification, Risks, Questions, Next Step.
- If only user input is blocking progress, respond with Questions only.
- Questions should be minimal and strictly blocking.
- Each blocking question should include blocker context, immediate concern, and impact level.
- Use `major` impact for architecture shifts, major rewrites, destructive actions, file deletions, or cross-system impact.

## Agent Prompt Recipe

Use this template to reduce retries and context bloat:

- Goal: one sentence
- Constraints: bullets
- Files: exact paths
- Checks: exact commands/tests
- Done when: objective completion rules

## Drift Risks and Mitigation

Risk: Extensions/settings flip-flop from profile/sync.
Mitigation:

- Keep repo-level instruction files versioned.
- Keep workspace settings minimal and deterministic.
- Run `.\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py --strict` regularly.

## Agent Automation Commands

- Agent surface audit: `.\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py --strict`
- Changed-path verification: `.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py`
- Handoff generation: `.\.venv\Scripts\python.exe .agent\scripts\generate_agent_handoff.py`
- Workflow chain smoke check: `.\.venv\Scripts\python.exe .agent\scripts\agent_workflow_smokecheck.py`

Terminal command guardrails and failure tooling are centralized in `.agent/reference/terminal_guardrails.md`.

See full command definitions in .agent/instructions/agent_command_catalog.md.

### Surface Audit List Maintenance

- When policy/instruction docs are intentionally edited, update related audit constants in the same change:
	- `REQUIRED_SECTIONS` for load-bearing headers
	- `MIN_SIZE_CHARS` for expected minimum content volume
	- `REQUIRED_POLICY_PHRASES` for irreversible or unique behavioral constraints
- If routing dispatch changes, keep `routing.md` targets aligned with `.agent/policies/*.md` on disk (excluding `routing.md`).
- Keep `REQUIRED_SECTION_MIN_BULLETS` aligned with intentional section restructures.
	- Current checks enforce minimum bullets for:
		- `AGENTS.md` -> `## When to Stop and Ask`
		- `.agent/reference/terminal_guardrails.md` -> `## Failure Handling Protocol`
- After updates, run:
	- `.\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py --strict`
	- `.\.venv\Scripts\python.exe .agent\scripts\agent_workflow_smokecheck.py`
- If a threshold or phrase changes intentionally, include a one-line rationale in task or PR notes.

## New Session Lock-In

- Use .agent/instructions/agent_session_bootstrap.md as the first prompt payload in a new session.
- This bootstrap enforces instruction chain, escalation behavior, response structure, and command workflow in one compact artifact.

## Maintenance Cadence

- On every PR: run agent surface audit in CI.
- On implementation tasks: run changed-path verification before final response.
- On agent policy/doc/script edits: run workflow chain smoke check.
- On handoff requests or task completion: generate agent handoff artifact.
- Weekly: review instruction files for stale references.
- Monthly: remove dead prompts or duplicated policies.
