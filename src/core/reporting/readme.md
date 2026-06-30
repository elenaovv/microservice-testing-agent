# Reporting

Builders and renderers for run outputs.

- `reporting.py` builds journey guides and execution reports from captured runtime evidence.
- `report_rendering.py` renders those reports for console and Markdown output.

This package should format and persist evidence that already exists. It should not drive the browser, run pytest directly, or decide repair strategy.
