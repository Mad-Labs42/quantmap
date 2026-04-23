# AGENTS.md

## Purpose

Maintain rigor, correctness, reproducibility, and low-risk change.
Never trade trustworthiness for convenience.

## Default Behavior

Read this file first.
Read `.agent/README.md` for agent-surface map and script-placement rules.
Read `.agent/policies/*` only when required by the task.

Read only:

- the source files directly relevant to the task
- the single `.agent/policies/*` file that matches the task, if needed

Do not preload README/docs/all policy files.
Do not read K.I.T./TO-DO trackers unless the user explicitly asks to read or update them.

## Automation Boundaries

- Automate low-risk, repetitive tasks when it improves reliability or token efficiency.
- Put agent-authored helper scripts under `.agent/scripts/helpers/`.
- Do not place project runtime or user-facing feature scripts under `.agent/scripts/helpers/`.
- Do not place ad hoc token-saving helper scripts under `src/`, root, or other project runtime paths.
- Keep repository-maintained agent governance scripts under `.agent/scripts/` only.
- Before creating a new `.agent/scripts/*.py`, require: concrete problem, immediate value, low blast radius, clear failure mode, and user approval.

## Terminal Guardrails (VS Code and Antigravity only)

- See `.agent/reference/terminal_guardrails.md` for terminal rules, failure protocol, helper script usage, and wrapper guidance.

## When to Stop and Ask

Stop and ask before proceeding if:

- instructions conflict in a load-bearing way
- the task may change methodology, scoring, reporting, trust semantics, or architecture
- the correct behavior is unclear
- the change may require broad refactoring not explicitly requested
- project docs and code disagree on an important behavior

Do not resolve major ambiguity unilaterally.

Escalate and ask when:

- a required step would deviate from the user plan or implementation contract
- a choice may impact architecture, trust semantics, cross-module behavior, or major systems
- the request is ambiguous enough that multiple materially different implementations are possible
- executing safely requires irreversible, destructive, or high-blast-radius actions
- dependencies, schema, interfaces, or public behavior would change beyond requested scope

## Conflict Handling

If instructions appear to conflict:

1. identify the conflict clearly
2. inspect only the most relevant source and policy file
3. if the conflict affects important project behavior, stop and ask

Do not invent policy.
Do not force a resolution silently.

## Code Style Expectations

Write the smallest code that preserves:

- correctness
- clarity
- maintainability
- stability

Required execution behavior:

- Auto-lint after each edit batch on touched files before continuing.
- Run a correctness check appropriate to each changed path before claiming success.
- Update logically affected call sites, tests, docs, and configuration when edits change behavior or interfaces.
- Do not leave known lint or correctness failures unaddressed without explicitly reporting them.

Avoid unnecessary abstraction, wrappers, indirection, and ceremony.

## Working Style

- Prefer narrow, targeted reads.
- Prefer small, auditable patches.
- Avoid cosmetic churn.
- Verify before claiming success.
- State uncertainty explicitly.
- Treat linting and correctness checks as required work, not optional follow-up.

## Response Token Discipline

- Use the fewest words that still preserve full meaning and required detail.
- Remove filler, repetition, and restatement.
- Never omit critical facts, risks, assumptions, blockers, or required user questions to save tokens.
- If brevity conflicts with completeness, keep completeness and be concise elsewhere.

## `.agent/policies` Dispatch

Read `.agent/policies/<file>` only when needed:

- `project.md` -> repo purpose, identity, and success criteria
- `architecture.md` -> major modules, concern ownership, dependency boundaries, cross-cutting systems
- `boundaries.md` -> scope limits, invariants, and trust/risk constraints
- `workflow.md` -> task flow, patch strategy, and stop-and-ask behavior
- `testing.md` -> test and verification policy
- `tooling.md` -> tool-use policy for IDE agent actions
- `adversarial.md` -> critique, audit, red-team, challenge mode only
- `routing.md` -> choose the minimum required `.agent/policies` file(s)

Do not read all `.agent/policies/*` files for a normal task.

## Output

Report briefly:

- what changed
- what was verified
- what remains uncertain

Use only needed sections from: Outcome, Changes, Verification, Risks, Questions, Next Step.
If blocked only by user input, respond with Questions only.
Include Questions whenever answers are required to proceed; use `NA` when no questions are needed but the section is required.

Optional footer rule:

- If and only if the agent created or edited user-benefit planning/support files (for example pre-implementation plans, implementation plans, validations, walkthroughs, task lists, or TODOs), append one final bottom-only section named `Files Created/Edited for You`.
- That section must appear at the very end of the response and nowhere else.
- Do not include that section when no such files were created or edited.

When blocked and asking Questions, include concise context for each question:

- what is blocked and why it blocks progress now
- immediate concerns the user should know
- impact level (`low|medium|high|major`) if the answer could change scope or implementation
- impact summary when relevant (major rewrite, architecture change, destructive action, file deletion, or cross-system effects)
