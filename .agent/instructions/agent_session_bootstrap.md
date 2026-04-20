# Agent Session Bootstrap

Use this as the first-message payload in a new coding-agent session.

## Mission

Execute the user request with minimal risk, high correctness, and strict token discipline.
Use this file as an execution checklist, not a duplicate policy source.

## Mandatory Instruction Chain

1. Read AGENTS.md.
2. Read .agent/README.md.
3. Read .github/instructions/quantmap-agent.instructions.md.
4. Read .agent/policies/routing.md only if scope is unclear.
5. Read only the single additional .agent/policies/* file required by the task.
6. Do not preload docs, README, or all policy files.
7. Do not read K.I.T./TO-DO tracker files unless user explicitly asks.

## Automation and Token Efficiency

- Look for safe automation opportunities before manual repetitive work.
- Prefer existing repository scripts and standard command workflows for repeated tasks first.
- Use automation to reduce token usage in both execution and reporting.
- If a repeated task is not automated and can be safely scripted with low blast radius, create a small helper script in `.agent/scripts/helpers/`.
- Do not automate destructive, high-risk, or ambiguous operations without explicit user approval.
- Do not place project runtime or product feature scripts in `.agent/scripts/helpers/`.
- Do not place ad hoc token-saving helper scripts under `src/`, root, or other project runtime paths.
- Keep repository-maintained governance scripts under `.agent/scripts/` only.
- Before creating a new `.agent/scripts/*.py`, require: concrete problem, immediate value, low blast radius, clear failure mode, and user approval.

## Terminal Failure Protocol (VS Code and Antigravity only)

- See `.agent/reference/terminal_guardrails.md` for terminal rules, failure protocol, helper script usage, and wrapper guidance.

## Escalation Rules (Ask Before Proceeding)

- Required step would deviate from user plan.
- Decision may alter architecture, major systems, or cross-module behavior.
- Scope, intent, or acceptance criteria are unclear.
- Action is destructive, irreversible, or high blast radius.
- Dependency/schema/interface/public behavior changes exceed request.
- Code and docs disagree on expected behavior.

## Investigation-Only Mode

- If the user says investigate/propose/plan/do not implement/wait for approval, stop after findings and proposals.
- Permission to install dependencies or run read-only investigation commands is not permission to implement changes.
- Before the first file-modifying action in investigation-only mode, ask for explicit go-ahead in one sentence.

## Response Rules

- Use only needed sections: Outcome, Changes, Verification, Risks, Questions, Next Step.
- If blocked only by user input, respond with Questions only.
- Keep output concise but do not omit load-bearing facts or intricate details the user should be aware of.

## Blocking Question Format

For each blocking question include:

- Question: decision needed from user.
- Blocker: what is blocked and why.
- Why This Matters Now: immediate concern/dependency.
- Impact Level: low|medium|high|major.
- Impact If Wrong/Assumed: include when relevant.

Use impact level `major` for architecture changes, major rewrites, destructive operations, file deletions, or cross-system effects.

## Standard Command Workflow

1. `.\.venv\Scripts\python.exe .agent\scripts\helpers\verify_dev_contract.py --quick`
2. `.\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py --strict`
3. implement scoped changes
4. `.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py`
5. fix findings and re-run verification
6. if agent policy/docs/scripts changed, run `.\.venv\Scripts\python.exe .agent\scripts\agent_workflow_smokecheck.py`
7. `.\.venv\Scripts\python.exe .agent\scripts\generate_agent_handoff.py` when completing or handing off

If step 1 fails because `.venv` is missing or anchored to the wrong Python, recreate it with `& D:\.store\mise\data\installs\python\3.13.13\python.exe -m venv .venv`, then run `.\.venv\Scripts\python.exe -m pip install --no-user -e '.[dev]'`.

## Script Intent (When to Use)

- `agent_surface_audit.py`: enforce required policy files/settings and guardrails.
- `helpers/verify_dev_contract.py --quick`: verify active local dev interpreter and required tools before implementation work.
- `changed_path_verify.py`: default verification for changed code paths.
- `changed_path_verify.py --paths <path...>`: scoped verification when repo has unrelated dirty files.
- `agent_workflow_smokecheck.py`: verify doc chain and minimal-ingestion rules after policy/doc/script edits.
- `generate_agent_handoff.py`: produce continuity artifact at completion or handoff.

## Session Task Brief

When user provides a long implementation plan, compress into this working brief and use it as execution memory:

- Goal
- Constraints
- In-Scope Files
- Out-of-Scope
- Checks
- Done When
- Open Questions

Do not repeatedly restate the full user plan unless asked.
