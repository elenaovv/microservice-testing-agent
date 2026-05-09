# Browse Pass vs Generated Test Pass

This note explains why a run can complete the browser journey successfully but
still produce a generated test that fails during replay.

## Meaning Of The Metrics

`Browse Fail` and `Pass` measure different stages of the pipeline.

`Browse Fail` counts runs where the agent could not complete the requested user
journey during live GUI exploration. A browse pass means the agent reached the
intended outcome once through the live application and recorded the journey.

`Gen.` counts runs that produced syntactically valid test code after browsing.
This means the agent could convert the observed journey into an executable test
file.

`Pass` counts generated tests that passed when executed by pytest. This is a
stricter result than browsing because the generated test must replay the journey
as deterministic code without the adaptive reasoning used during exploration.

## Why Browse Can Pass But The Test Can Fail

The browser agent can adapt during exploration: it can inspect the current page,
retry actions, dismiss dialogs, choose visible elements, and recover from
unexpected UI states. The generated test is different. It replays one concrete
path and can fail if timing, selectors, table rows, dialogs, or application data
change between exploration and execution.

This does not automatically mean the tool is wrong. It shows the core research
challenge: transforming adaptive GUI exploration into stable regression tests.
The gap between `Gen.` and `Pass` is therefore an important result, not just an
implementation defect.

Typical causes include dynamic table ordering, generated order IDs, modal timing,
login/session state, strict selectors, repeated state-changing actions, and
assertions that are too closely tied to one observed screen state.

## Journey Evidence Used By The Generator

The live in-memory browse capture is the source of the journey evidence. After
browsing, the system saves that evidence as a `*.journey.json` artifact. The
saved JSON records the same browse evidence used for test generation, plus
derived metadata such as coverage, use-case details, paths, and the structured
journey contract.

The generator does not receive the full raw `*.journey.json` file as prompt
input during initial generation. Instead, it receives a prompt-rendered subset:
the replay plan, recorded timings, observed backend requests, and structured
journey contract derived from the live capture.

This distinction matters when interpreting failures. A failed generated test is
not usually caused by a mismatch between memory and the saved JSON. The more
important issue is the abstraction gap between adaptive browsing evidence and
deterministic replay code. If the browse phase records a weak, stale, ambiguous,
or non-executable locator, then both the prompt-rendered replay plan and the
saved JSON can preserve that weakness. The failure is therefore better described
as an observation/contract/replay-stability issue, not simply a JSON mismatch.

## How To Interpret The Table

The table is useful because it separates three outcomes:

- whether the agent can understand and complete the task in the GUI
- whether the agent can generate runnable test code from that journey
- whether the generated code is stable enough to pass as an automated test

For a research presentation, this distinction is valuable. For example, a use
case such as booking can have a lower pass rate not because the agent cannot
understand booking, but because booking mutates backend state and requires robust
selection, confirmation, and order-verification logic.

## Research Position

The current result is credible as a research finding if it is presented with the
right framing and limitations. It should not be claimed as a fully solved test
generation system. It can be claimed as evidence that an LLM browser agent can
explore realistic microservice GUI workflows, generate executable tests, and
expose where replay stability breaks down.

For a conference paper, the table is a useful starting point, especially because
it uses repeated runs and reports repair attempts, pass rate, API calls, code
size, and browse time. To make the evidence stronger, the paper should also
explain the failure categories and give examples of why failed generated tests
failed, such as selector ambiguity, timeout, changed backend state, or unmet
interaction contracts.

## Failure Category Extraction

Saved run artifacts can be classified without rerunning the browser experiment.
Use:

```bash
uv run python research/classify_failure_modes.py path/to/result-folder --output-dir path/to/failure-mode-summary
```

The script reads `evaluation-runs.jsonl` and `*.report.json` artifacts, then
writes:

- `failure-modes.md`: paper-readable counts and failed-run details
- `failure-modes.csv`: spreadsheet-friendly per-run labels

The current categories are `passed`, `browse-blocked`, `syntax/collection`,
`timeout`, `selector-ambiguity`, `selector-not-found`, `state/side-effect`,
`state/data-mismatch`, `assertion-failure`, and `infrastructure/other`.
