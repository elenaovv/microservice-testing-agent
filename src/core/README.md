# Core Package

This package contains the shared runtime logic behind generation, execution, coverage, reporting, and evaluation.

Main subpackages:
- `contracts/`: shared `dataclass` models and journey-contract construction.
- `execution/`: generated-test execution, retry budgets, artifact paths, and subprocess environment defaults.
- `reporting/`: journey-guide and execution-report builders plus console and Markdown rendering.
- `evaluation/`: evaluation history, summary rendering, and run-level metric aggregation.
- `analysis/`: lightweight failure inference, mutation helpers, and generated-test action sequence extraction.
- `coverage/`: endpoint extraction and service-operation coverage mapping.
- `capture/`: prompt and run-input capture helpers.
- `text/`: shared text/token vocabulary used by prompt and coverage helpers.

This package is still research-oriented. Some analysis is heuristic by design, especially GUI counting and failure classification.
