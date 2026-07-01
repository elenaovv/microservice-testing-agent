# Microservice Testing Agent

This is the operator guide for running the browsing-driven test generation prototype.

## Repository Layout

- `src/agent/`: constructs the single Pydantic AI agent and registers its tools.
- `src/workflow/`: coordinates browse, journey-contract creation, test generation, execution, repair, and reporting.
- `src/core/`: shared contracts plus execution, reporting, evaluation, analysis, coverage, and capture helpers.
- `src/prompts/`: loads use cases, MSA specification, and system description, then builds agent prompts.
- `direct_baseline/`: static-input baseline that skips browser exploration.
- `spec/`: MSA specification, system description, research use cases, and fault catalog.
- `research/`: post-hoc analysis and preflight utilities used for the paper evaluation.
- `tests/`: unit tests for prompt loading, retry budgets, network diffing, and journey-contract gates.

## Runtime Behavior

The runtime takes a user journey or a structured use case, explores the live application in a browser, generates a Python end-to-end test, runs that test, and saves the results.

Outputs:
- generated tests go to `generated-tests/`
- journey guides, reports, and evaluation summaries go to `test-results/`

## Requirements

Install these first:
- Python 3.12
- `uv`
- Node.js with `npm`

The runtime also expects:
- a reachable application URL, usually passed with `--base-url`
- an API key for the model provider in `.env`

Minimum `.env` example:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=openai:gpt-5.4
BASE_URL=http://localhost:8080
```

The same values are shown in `.env.example`. Keep real API keys in `.env`; do not commit them.

`BASE_URL` can also be overridden on the command line.

## Setup

From the repository root:

```bash
uv sync
npm ci
```

If Playwright browsers are not installed yet:

```bash
uv run playwright install chromium
```

## Commands

Ad-hoc journey:

```bash
uv run python main.py test "book a ticket from point a to point b" --base-url http://localhost:8080
```

Ad-hoc journey with explicit filename:

```bash
uv run python main.py test "book a ticket from point a to point b" --filename booking_test.py --base-url http://localhost:8080
```

Structured use case by ID:

```bash
uv run python main.py test --use-case-id UC-VIS-004 --base-url http://localhost:8080
```

Structured use case by YAML file:

```bash
uv run python main.py test --use-case-file spec/use_cases/user/research_cases/UC-VIS-004-book-ticket.yaml --base-url http://localhost:8080
```

Before running structured use cases, check the YAML test data against the live deployment. TrainTicket dates, source stations, and destination stations must be valid for the current database and UI calendar. A past date or unavailable route can make the browse journey fail before test generation, or make replay fail after generation.

Run against another MSA or another local spec set:

```bash
uv run python main.py test --use-case-file path/to/use_case.yaml --msa-spec path/to/msa.yaml --system-description path/to/system_description.md --base-url http://localhost:8080
```

Rerun an existing generated test:

```bash
uv run python main.py retest booking_test.py --variant-label original --base-url http://localhost:8080
```

## Result Files

After a run:
- the generated Python test file is in `generated-tests/`
- the saved journey guide is in `test-results/<name>.journey.md`
- the execution report is in `test-results/<name>.report.json`
- the aggregated evaluation summary is in `test-results/evaluation-summary.md`

## Operational Notes

- If `--filename` is omitted, the runtime derives a test filename from the selected journey or use case.
- If `journey` is omitted entirely, the runtime falls back to the legacy `spec/use-cases.txt` list.
- The current browse phase uses Playwright MCP. Evaluation coverage is persisted, but true Python-side Phase 1 network listening is not implemented yet.
- Local run outputs such as `generated-tests/`, `test-results/`, `runtime-results/`, and `prompt-captures/` are ignored by default.
