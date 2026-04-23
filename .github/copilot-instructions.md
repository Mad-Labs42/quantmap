# Copilot PR Review Instructions

**Scope**: GitHub pull request reviews only. This file does not apply to coding-agent interactions, autocomplete suggestions, or workspace guidance.

## Posture

Copilot is authorized to comment on PRs to identify issues that CodeRabbit and SonarCloud may not catch or that complement their analysis.

## What Copilot Should Focus On

- **Logical correctness** that goes beyond static analysis: temporal issues, race conditions, state machine violations, protocol mismatches.
- **Missing error handling**: paths that could fail silently or with confusing messages.
- **Performance concerns**: algorithmic inefficiencies, unnecessary allocations, or I/O patterns that impact benchmarking integrity.
- **Cross-cutting semantics**: changes that affect governance, telemetry, methodology stability, or trust surface.
- **Documentation accuracy**: where comments or docstrings contradict the implementation.
- **API contract stability**: changes to public or internal interfaces that affect downstream call sites.

## What Copilot Should NOT Duplicate

Do **not** comment on:
- Style, formatting, or naming conventions (CodeRabbit covers these).
- Security hotspots flagged by CodeQL (overlap is noise).
- Code smell or complexity metrics (SonarCloud is the authority).
- Lint/type issues that ruff/mypy will catch in CI.
- Pre-commit hook enforcement (not in scope for PR review).

## Conflict Resolution

If CodeRabbit, SonarCloud, or mypy has already commented on an issue:
- Reference the existing comment if adding a different perspective.
- Do not repeat the same finding unless your angle is materially different.
- Prioritize blocking review comments over suggestions.

## Example Good Comments

✓ "This change removes the locking pattern from `_domain_coverage()` but keeps the cached result assignment. That's a use-after-free risk in concurrent scenarios."

✓ "The telemetry context is not passed to the new helper; downstream reports will show degraded confidence without notifying operators."

✓ "This `await` only wraps the first coroutine, not the retry loop. The retry will block the event loop on network timeouts."

## Example Comments to Skip

✗ "Consider renaming `cfg` to `config` for clarity." (CodeRabbit)

✗ "Avoid using `exec()` — this is a security risk." (CodeQL)

✗ "This function is too complex." (SonarCloud complexity metric)
