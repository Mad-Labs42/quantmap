# boundaries.md

## Scope Limits

- Do not expand task scope without user approval.
- Do not turn a narrow fix into a broad refactor.
- Do not reorganize files, names, or structure unless required by the task.
- Do not add abstractions/helpers/layers unless they clearly reduce risk or duplication.
- Do not replace existing project patterns casually.

## Non-Negotiable Constraints

- Preserve scientific rigor.
- Preserve reproducibility.
- Preserve determinism.
- Preserve auditable behavior.
- Preserve explicit failure semantics.
- Preserve visible warnings.
- Preserve evidence-bounded interpretation.

## Do Not Change Casually

- scoring semantics
- normalization behavior
- ranking logic
- winner selection
- confidence aggregation
- methodology loading
- report structure
- warning generation or suppression
- artifact overwrite / freshness behavior
- missing vs failed vs unsupported distinctions
- eliminated vs unrankable distinctions

## Scientific Boundaries

- Do not present interpretation as measurement.
- Do not present inference as fact.
- Do not claim causality without support.
- Do not overstate small or noisy differences.
- Do not collapse uncertainty.
- Do not hide limitations.

## Trust Boundaries

- Do not silently change load-bearing behavior.
- Do not silently alter defaults that affect conclusions.
- Do not silently weaken checks, audits, or safeguards.
- Do not silently remove diagnostic detail that affects trust.
- Do not trade correctness for convenience.

## Reporting Boundaries

- Keep data separate from interpretation.
- Keep warnings visible.
- Keep required sections explicit.
- Do not omit failed, missing, unsupported, or degraded conditions when they matter.
- Do not allow stale artifacts to appear current.
- Do not make reports sound more certain than the evidence allows.

## When to Stop and Ask

Stop and ask before proceeding if the task may change:

- methodology
- scoring intent
- ranking outcomes
- trust/confidence semantics
- reporting truthfulness
- repo structure beyond the immediate task
