# Python Runtime

This `python/` directory contains the research prototype runtime for the browsing-based test generator.

Current entry point:
- `main.py` exposes the CLI commands `run`, `test`, and `retest`.

Current package split:
- `agent/` builds the `pydantic-ai` agent and registers its tools.
- `workflow/` orchestrates browse, generate, execute, retest, and evaluation persistence.
- `prompts/` loads input specs and builds the browse and test-generation prompts.
- `core/` holds typed models, test execution, coverage inference, reporting, and evaluation summaries.
- `spec/` stores the local MSA spec, system description, and structured use-case files.
- `docs/` stores architecture notes and audits.

The code is aimed at showing the research flow clearly:
1. Explore the UI and log actions.
2. Generate a Python end-to-end test from the captured journey.
3. Execute it, repair it if needed, and persist evaluation artifacts.
