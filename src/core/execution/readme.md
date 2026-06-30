# Execution

Code that runs generated tests and manages execution-time limits and paths.

- `executor.py` runs generated pytest files in a subprocess and collects stdout, stderr, screenshots, network traces, and exit status.
- `retry_budget.py` tracks the repair and rerun budget enforced by agent tools.
- `run_artifacts.py` centralizes generated-test and result artifact paths.
- `runtime_env.py` sets local cache and subprocess environment defaults for reproducible runs.

Keep report formatting, metric aggregation, and prompt construction outside this package.
