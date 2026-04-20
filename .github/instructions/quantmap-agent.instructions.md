# QuantMap Agent Instructions

Purpose: Keep changes correct, reproducible, low-risk, and token-efficient.

## Scope and Safety
- Prefer small, auditable patches.
- Avoid broad refactors unless explicitly requested.
- Stop and ask when behavior, methodology, or trust semantics could change.
- Do not read K.I.T./TO-DO tracker files unless the user asks to read or update them.

## First Reads
1. AGENTS.md
2. .agent/README.md
3. If scope is unclear, read .agent/policies/routing.md
4. Only the single .agent/policies file needed for the task
5. Treat .agent/instructions/agent_*.md as opt-in references for agent-surface maintenance tasks only
6. Use .agent/instructions/agent_session_bootstrap.md as an operational checklist when executing changes

## Repo Landmarks
- CLI entry: quantmap.py
- Core runtime: src/runner.py
- Health and readiness: src/doctor.py
- Scoring and governance: src/score.py, src/governance.py
- Trust identity: src/trust_identity.py
- Reports: src/report.py, src/report_campaign.py, src/report_compare.py

## Preferred Validation
- Fast syntax/parse check before broad tests.
- Run focused tests near changed modules.
- Treat verification as required before claiming success.

## Auto Lint and Correctness
- Auto-run lint on touched files after each edit batch and fix findings before proceeding.
- Perform at least one correctness check per changed behavior path (targeted test, narrow runtime check, or equivalent proof).
- Do not report done status while lint or correctness failures remain on touched paths.

## Impact Propagation Rules
- If an edit changes behavior, contracts, types, names, or side effects, update all logically affected areas.
- Check and update dependent call sites, tests, docs, configs, and user-facing outputs affected by the change.
- Treat partial propagation as incomplete work unless explicitly scoped by the user.

## Preferred Python Commands
- Lint touched files: `python -m ruff check <paths>`
- Apply safe lint fixes when needed: `python -m ruff check --fix <paths>`
- Focused tests: `python -m pytest -q <targeted_tests_or_module>`

## Tool Use Pattern
1. Locate owner file first.
2. Read only needed adjacent files.
3. Apply smallest patch.
4. Auto-lint touched files.
5. Re-verify with targeted commands/tests.
6. Update any logically affected files before final verification.

## Automation and Script Placement
- Automate low-risk repetitive tasks where it improves reliability or token efficiency.
- Place agent-authored helper scripts in `.agent/scripts/helpers/`.
- Do not place project runtime or product feature scripts in `.agent/scripts/helpers/`.
- Do not place ad hoc token-saving helper scripts under `src/` or other project runtime paths.
- Keep repository-maintained agent governance scripts under `.agent/scripts/` only.
- Before proposing a new `.agent/scripts/*.py`, require: concrete problem, immediate value, low blast radius, clear failure mode, and user approval.

## Terminal Failure Handling (VS Code and Antigravity only)
- See `.agent/reference/terminal_guardrails.md` for terminal rules, failure protocol, helper script usage, and wrapper guidance.

## Response Token Policy
- Keep responses compact and information-dense.
- Use only the words needed to communicate the result, proof, and next required actions.
- Do not repeat unchanged context unless explicitly requested.
- Never drop critical facts, unresolved risks, or required clarifying questions for token savings.
- If a choice is needed, ask the minimum set of high-impact questions.

## Response Structure
- Print only sections needed for the current state.
- Available sections: Outcome, Changes, Verification, Risks, Questions, Next Step.
- If only user input is needed, print Questions only.
- Questions must include only blocking questions required to proceed.
- Use `NA` for Questions when a downstream format requires the section but there are no questions.
- If and only if user-benefit planning/support files were created or edited (for example pre-implementation plans, implementation plans, validations, walkthroughs, task lists, or TODOs), append one final section named `Files Created/Edited for You`.
- Place `Files Created/Edited for You` at the very bottom of the response only.
- Do not include that section when no such files were created or edited.

When blocked and asking Questions, include for each question:
- Blocker: one sentence explaining what cannot proceed and why.
- Why This Matters Now: immediate concern or dependency.
- Impact Level: `low|medium|high|major`.
- Impact If Wrong/Assumed: only when relevant (major rewrite, architecture change, destructive action, file deletion, cross-system impact).

Question style rules:
- Keep questions decision-ready and specific.
- Ask only what is necessary to safely continue.
- Do not ask non-blocking preference questions mid-implementation.

## Escalation Thresholds
Ask before proceeding when:
- implementation would deviate from the user-provided plan
- architecture, major systems, or cross-module contracts could change
- multiple valid implementations exist and choice impacts outcomes
- uncertainty remains about user intent, scope, or acceptance criteria
- security, trust, privacy, data integrity, or destructive operations are involved
- dependency, schema, interface, or user-facing behavior changes exceed explicit request

## Task Brief Compression
- When user provides a long plan, create a compact task brief for execution reference.
- Include only: Goal, Constraints, In-Scope Files, Out-of-Scope, Checks, Done When, Open Questions.
- Treat task brief as working memory; do not restate the full original plan in routine updates.

## Output Contract
Report briefly:
- What changed
- What was verified
- What remains uncertain
