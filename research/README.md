# Research Utilities

This directory contains helper scripts for analysing saved experiment artifacts.
The scripts do not rerun the browser agent unless explicitly stated.

## Failure Mode Classification

`classify_failure_modes.py` reads existing evaluation artifacts and groups each
run into a small failure category for paper analysis.

Use it when you already have saved results such as:

- `evaluation-runs.jsonl`
- `*.report.json`
- `*.journey.json`

### Run On One Use Case Folder

```powershell
uv run python research\classify_failure_modes.py UC-ADM-007_runs\journey_jsons --output-dir UC-ADM-007_runs\failure-mode-summary
```

Expected console output:

```text
records: 10
markdown: UC-ADM-007_runs\failure-mode-summary\failure-modes.md
csv: UC-ADM-007_runs\failure-mode-summary\failure-modes.csv
```

Expected `failure-modes.md` shape:

```text
# Failure Mode Summary

## Category Summary

| Journey | Category | Count |
| --- | --- | ---: |
| UC-ADM-007 Update Train | passed | 8 |
| UC-ADM-007 Update Train | selector-not-found | 2 |
```

### Run On A Larger Results Directory

```powershell
uv run python research\classify_failure_modes.py results\study-2026\openai-gpt-5.4 --output-dir results\study-2026\failure-mode-summary
```

The script writes:

- `failure-modes.md`: readable summary for the paper
- `failure-modes.csv`: per-run labels for spreadsheet checks

### Current Categories

- `passed`: generated test passed.
- `browse-blocked`: browsing did not complete, so no valid generated test was produced.
- `syntax/collection`: generated test could not be parsed or collected.
- `timeout`: replay timed out during generated-test execution.
- `selector-ambiguity`: locator matched more than one element.
- `selector-not-found`: locator did not resolve to a visible element.
- `state/side-effect`: expected backend side effect was missing.
- `state/data-mismatch`: assertion appears tied to changed application data.
- `assertion-failure`: assertion failed but no more specific category was inferred.
- `infrastructure/other`: browser, MCP, process, or uncategorised runtime issue.

### Interpretation

The classification is a post-hoc analysis of existing run artifacts. It should
be reported as failure-mode analysis of the same experiment, not as a new test
execution campaign.
