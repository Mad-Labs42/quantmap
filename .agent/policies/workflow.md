# workflow.md

## Task Approach

- Start narrow.
- Read only the files needed for the current task.
- Use `routing.md` if the correct file is unclear.
- Do not preload `.agent/policies/*` files without a reason.

## Research vs Implementation

- Research first when behavior, scope, or risk is unclear.
- Implement first when the requested change is narrow and well-defined.
- Do not mix broad exploration with immediate patching.
- Do not code before identifying the affected area.

## Stop-and-Ask Rules

Stop and ask if:

- instructions conflict on a load-bearing issue
- the task may change methodology, scoring, trust, or reporting behavior
- the correct behavior is unclear
- the change requires broader refactoring than requested
- code, docs, and task intent do not align

Do not resolve major ambiguity silently.

Always ask before proceeding when:

- the required action would deviate from the user's stated plan
- a decision may alter architecture, major systems, or cross-module behavior
- doubt remains about requested scope, intent, or completion criteria
- destructive or irreversible actions are required
- dependency, schema, interface, or external behavior changes exceed request
- code and documentation disagree on expected behavior

## Patch Strategy

- Prefer the smallest safe change.
- Keep changes local.
- Avoid cosmetic churn.
- Do not rewrite working code without need.
- Do not add abstraction unless it clearly pays for itself.
- Keep code concise, clear, and stable.
- After each edit batch, auto-lint touched files before continuing.
- Run at least one correctness check suited to the changed behavior before claiming completion.
- When edits change interfaces or behavior, update logically affected call sites, tests, docs, and configuration in the same task.
- Do not leave known lint or correctness failures unresolved on touched paths.

## Reporting Back

Report:

- what changed
- what was checked
- what was verified
- what remains uncertain

Response quality rules:

- Keep wording lean and direct.
- Remove filler and repeated context.
- Preserve all load-bearing facts and required user questions.
- Do not compress away risks, blockers, or unresolved decisions.

Section rules:

- Use only needed sections: Outcome, Changes, Verification, Risks, Questions, Next Step.
- If blocked only by user input, print Questions only.
- Keep Questions limited to items that block safe progress.
- Use `NA` when Questions is required by format but there are none.
- If and only if user-benefit planning/support files were created or edited (for example pre-implementation plans, implementation plans, validations, walkthroughs, task lists, or TODOs), append one final section named `Files Created/Edited for You`.
- `Files Created/Edited for You` must appear only at the very bottom of the response.
- Do not include `Files Created/Edited for You` when no such files were created or edited.

Blocked-question detail rules:

- For each blocking question include: Blocker, Why This Matters Now, Impact Level, and Impact If Wrong/Assumed (when relevant).
- Use impact levels: `low|medium|high|major`.
- Mark `major` when answer may trigger architecture changes, broad rewrites, destructive operations, file deletions, or cross-system effects.
- Keep this context short but complete; do not omit risk details to save tokens.

Do not claim success without verification.
Do not hide limits or uncertainty.
