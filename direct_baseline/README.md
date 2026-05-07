# Direct Generation Baseline

This folder contains an isolated baseline runner for the QUATIC study.

The baseline is **direct generation**, not exploration-grounded generation:

- It uses the same structured use cases, frozen `spec/msa.yaml`, model, and repair budget.
- Its prompt includes the same generic test-authoring, locator, modal-scoping,
  UI-only interaction, and repair guidance used by the main workflow where that
  guidance does not require browsing logs or exploration tools.
- It does not expose Playwright MCP/browser exploration tools to the model.
- It exposes only two model tools: `create_python_test_file` and `run_test_file`.
- The generated pytest-playwright test may open the browser during normal test execution.
- Repairs may use only `run_test_file` output and artifacts.
- Frontend API calls are captured by the repository-level pytest `conftest.py`, the
  same mechanism used by the main workflow.
- Additional failure-state capture is disabled by default. Use
  `--capture-failure-state` only for debugging, not for final comparison runs.

## Run

From the repository root:

```powershell
$env:OPENAI_MODEL="openai:gpt-5.4"
$env:BASE_URL="http://localhost:8080"

uv run python direct_baseline\runner.py `
  --output-dir results\direct-baseline-2026 `
  --runs 10 `
  --max-retries 5 `
  --base-url http://localhost:8080
```

To smoke-test one use case:

```powershell
uv run python direct_baseline\runner.py `
  --output-dir results\direct-baseline-smoke `
  --use-case-id UC-VIS-001 `
  --runs 1 `
  --max-retries 1 `
  --base-url http://localhost:8080
```

## Outputs

The output layout mirrors the main experiment layout:

```text
results/direct-baseline-2026/<model>/<use-case-id>/run-NN/
  generated-tests/
  test-results/
  runtime-results/
  prompt-captures/
  baseline-audit.json
```

Each run writes `baseline-audit.json`, recording that no MCP servers were exposed and listing the allowed tool calls made during the run.

By default, the baseline does not write a run-local `generated-tests/conftest.py`.
That keeps the pytest execution environment aligned with the main workflow. If
`--capture-failure-state` is enabled for debugging, the runner writes a temporary
run-local `conftest.py` that records visible page text and API responses after
failed tests.

## Paper Wording

Use wording like:

> The direct-generation baseline used the same structured use cases, MSA specification, model, repair budget, pytest-playwright execution harness, and generic test-authoring guidance as the exploration-grounded workflow. Browser exploration tools and exploration-derived artifacts were not exposed to the baseline agent; it could only save generated test files and execute them through the same pytest-playwright runner, using execution failures for repair.
