# architecture.md

## Major modules

- **Entry / orchestration**: starts commands and coordinates flow.

- **Execution**: runs campaign cycles and collects raw results.

- **Context**: captures machine state, telemetry, probe results, and confidence inputs.

- **Scoring**: normalizes metrics, ranks configs, applies filters, and selects winners.

- **Reporting**: builds reports, warnings, summaries, and artifacts.

- **Governance**: defines methodology, defaults, and compatibility behavior.

- **Diagnostics**: handles audits, readiness checks, and degraded-state inspection.

## Where key concerns live

- Measurement and run execution: execution.
- Environment/telemetry capture: context.
- Scoring and ranking outcomes: scoring.
- Report generation and artifact output: reporting.
- Methodology and policy behavior: governance.
- Readiness and health investigation: diagnostics.

## Important dependency boundaries

- Execution depends on governance constraints and emits measurement data.
- Context collection is separate from scoring interpretation.
- Scoring consumes execution/context outputs and should not be coupled to report presentation.
- Reporting consumes scored results and context but should not mutate measurement/scoring semantics.
- Diagnostics can inspect all layers but should not silently alter core behavior.

## Cross-cutting systems

- Governance rules apply across execution, scoring, and reporting.
- Trust/confidence semantics span context capture, scoring, and reporting.
- Artifact freshness and reporting integrity span execution outputs and report/export surfaces.
