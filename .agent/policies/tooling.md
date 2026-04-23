# tooling.md

## Purpose

Use tools to improve accuracy, remove guesswork, and verify facts.
Use the smallest reliable action.

## Tool Use Standard

Good tool use is targeted, evidence-seeking, and risk-proportionate.
Stop once the next safe step is clear.

## Use Tools Early When They Help

Use tools early when they quickly clarify:

- file ownership
- code location
- dependency impact
- command behavior
- runtime state
- whether a claim is actually true

Do not guess when a cheap check can answer.

## Escalate Gradually

Preferred pattern:

1. inspect the most likely file or signal
2. search if location or ownership is unclear
3. run focused commands when behavior must be verified
4. expand scope only if the task requires it

Start narrow; widen only as needed.

## Read Strategy

- Prefer likely owner files first.
- Follow dependency paths only when needed.
- Read adjacent files only when they affect the task.
- Stop once understanding is sufficient to act safely.
- Treat K.I.T./TO-DO tracker files as opt-in context only.

Do not read broadly without reason.
Do not read K.I.T./TO-DO tracker files unless the user asks to read or update them.

## Command Strategy

- Use commands when direct evidence matters.
- Prefer project scripts and known workflows.
- Inspect failures before replacing a working path.
- Verify outcomes before concluding a tool is broken.
- Auto-lint touched files after each edit batch, then continue implementation.
- Use targeted correctness checks before declaring completion.

Preferred Python checks:

- `.\.venv\Scripts\python.exe -m ruff check <touched_paths>`
- `.\.venv\Scripts\python.exe -m ruff check --fix <touched_paths>` when safe auto-fixes are needed
- `.\.venv\Scripts\python.exe -m pytest -q <targeted_tests_or_module>`

Terminal safety and failure command guidance:

- `.agent/reference/terminal_guardrails.md`

Agent automation commands:

- `.\.venv\Scripts\python.exe .agent\scripts\agent_surface_audit.py --strict`
- `.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py`
- `.\.venv\Scripts\python.exe .agent\scripts\generate_agent_handoff.py`
- `.\.venv\Scripts\python.exe .agent\scripts\agent_workflow_smokecheck.py`

Prefer these scripts over ad hoc command chains when applicable.
Run `.\.venv\Scripts\python.exe .agent\scripts\agent_workflow_smokecheck.py` when editing agent instructions, policy docs, or workflow scripts.

## IDE / Extension Strategy

- Use IDE features as helpers, not authority.
- Verify important claims with source or command evidence.
- Do not let convenience features decide scope or correctness.

## Context Pruning Safety

- Do not auto-apply context-pruning exclusions beyond known safe caches/artifacts without user approval.
- Review pruning candidates manually before changing workspace exclusions.
- Ask before excluding docs, configs, source, tests, or any path with decision-critical context.

## Common Failure Modes

Avoid:

- guessing instead of checking
- editing before locating the true owner file
- reading broadly when a focused search would do
- trusting summaries without source confirmation
- stopping investigation too early
- over-investigating after the answer is already clear

## Rule

Be efficient, not hesitant.
Be thorough, not sprawling.
Use the cheapest reliable move that keeps work safe.
