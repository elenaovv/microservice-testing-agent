# Browse Pass vs Generated-Test Pass

Successful browsing and successful replay measure different things. A journey
can complete in the live browser and still produce a test that fails later.

## Metric Definitions

| Metric | Meaning |
| --- | --- |
| `Browse Fail` | The browse phase did not complete the requested journey or did not validate the required interaction contract. |
| `Gen.` | The run produced a syntactically valid Python test file. |
| `Pass` | The generated test passed when executed by pytest after zero or more repair attempts. |

The metrics describe different stages. A browse pass means the live UI journey
was completed once. A generated-test pass means the same workflow survived as
deterministic replay code.

## Replay Failure Causes

The browse phase can adapt to the current UI state. It can inspect pages, retry
actions, dismiss dialogs, and choose visible controls. The generated test does
not have that adaptive context. It replays one fixed path and can fail if any of
the following change between browsing and replay:

- selector stability
- modal timing
- table ordering
- generated identifiers
- login/session state
- repeated state-changing actions
- expected backend state
- assertions tied too closely to one screen state

The gap between `Gen.` and `Pass` is therefore a replay-stability result. It is
not the same as a browse failure.

## Journey Evidence Used During Generation

The live in-memory browse capture is the source of the generation evidence. The
workflow also saves that evidence as a `*.journey.json` artifact after browsing.

The generator does not receive the raw saved JSON file. It receives a rendered
subset that includes:

- replay plan
- recorded timings
- observed backend requests
- structured journey contract
- selected use-case and MSA context

If a generated test fails, the usual cause is not a mismatch between memory and
the saved JSON. The more relevant cause is loss or weakening of evidence while
turning adaptive browser observations into fixed replay code.

## Failure Categories

Saved run artifacts can be classified without rerunning the experiment:

```bash
uv run python research/classify_failure_modes.py path/to/result-folder --output-dir path/to/failure-mode-summary
```

The script reads `evaluation-runs.jsonl` and `*.report.json` files, then writes:

- `failure-modes.md`
- `failure-modes.csv`

Current categories:

- `passed`
- `browse-blocked`
- `syntax/collection`
- `timeout`
- `selector-ambiguity`
- `selector-not-found`
- `state/side-effect`
- `state/data-mismatch`
- `assertion-failure`
- `infrastructure/other`

## Paper Use

Use the result to describe the conversion problem:

> The workflow can often complete a live GUI journey and generate executable
> test code, but deterministic replay remains sensitive to selectors, timing,
> state, and oracle strength.

Avoid framing the table as proof that GUI test generation is solved. The result
is more precise when paired with failure categories and concrete examples from
the saved reports.

## Figure Labels

For the MAESTRO architecture figure:

- label the arrow from Phase 1 to Phase 2 as `Journey evidence + contract`;
- keep the phase label as `Test Generation and Repair`;
- label the browser-control path as `Playwright MCP browser control`;
- label HTTP evidence as browser-visible gateway traffic;
- show `test-results/` reports as an output from Phase 2.
