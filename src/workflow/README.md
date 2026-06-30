# Workflow Package

This package orchestrates the end-to-end runtime flow.

Files:
- `workflow.py` contains the real implementations.
- `__init__.py` re-exports the public functions so `main.py` can keep importing from `workflow`.

Current public workflow functions:
- `run_browser_task`: ad-hoc browser task execution.
- `generate_test`: Phase 1 browse and capture, then Phase 2 prompt-driven test generation.
- `retest_generated_test`: rerun an existing generated test against a selected variant or base URL.

This package is the bridge between the CLI, the agent layer, prompt construction, and the reporting/evaluation layer.
