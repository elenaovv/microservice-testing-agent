# Core Package

This package contains the shared runtime logic behind generation, execution, coverage, and evaluation.

Main modules:
- `models.py`: standard `dataclass` models for captures, reports, coverage snapshots, evaluation context, and saved use-case metadata.
- `executor.py`: runs generated pytest-playwright files and collects execution artifacts.
- `coverage_utils.py`: extracts endpoint definitions from the MSA spec and maps observed requests back to services and operations.
- `inference.py`: lightweight heuristics for blocked runs, failure kind, fault signature, GUI count, and related analysis.
- `reporting.py`: builds journey guides and execution reports and writes them to disk.
- `report_rendering.py`: renders saved journey and execution data into readable text and markdown.
- `evaluation_utils.py`: appends evaluation history and regenerates the summary markdown.
- `evaluation_rendering.py`: renders the evaluation summary tables.
- `mutation_utils.py`: Phase 3 helpers for mutation and variant comparisons.

This package is still research-oriented. Some analysis is heuristic by design, especially GUI counting and failure classification.
