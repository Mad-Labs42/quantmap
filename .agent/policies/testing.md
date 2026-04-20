# testing.md

## Validation Expectations

- Validate before claiming success.
- Match validation depth to change risk.
- Prefer direct proof over assumption.
- State clearly when something was not tested.
- Lint touched files after each edit batch; treat lint failures as blocking until addressed or explicitly reported.

## Narrow-First Order

Use the smallest useful check first:

1. targeted inspection
2. focused test
3. narrow runtime check
4. broader validation only if needed

Do not jump to broad testing when a narrow check can prove the change.

## Verified Means

Treat as verified only if:

- the relevant behavior was actually checked
- the result matched the intended outcome
- the check was appropriate to the change

## Not Verified Means

Say not verified when:

- no check was run
- the check was partial
- the environment prevented confirmation
- the result was inferred but not observed
- broader effects remain untested

## Testing Rules

- Test the changed path first.
- Avoid unrelated validation unless risk justifies it.
- Do not confuse static review with runtime proof.
- Do not report confidence beyond the evidence.
- If a change affects neighboring behavior, add or update tests for impacted paths.
- Re-check dependent call paths when contracts, names, signatures, or outputs change.
- Prefer `.\.venv\Scripts\python.exe .agent\scripts\changed_path_verify.py` for repeatable changed-path validation.
