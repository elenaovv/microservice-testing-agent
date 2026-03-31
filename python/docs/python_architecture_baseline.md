# Python Architecture Baseline

This document captures the current Python-only runtime after the package split.
It reflects the actual flow that runs today, including the saved journey guide
that is produced before test generation and the first-pass coverage snapshot
that is persisted for later evaluation.

Scope:
- In scope: everything under `python/`
- In scope: `python/spec/msa.yaml` as the local MSA context
- Out of scope: everything under `java/`

## Current Runtime

```mermaid
flowchart LR
    CLI["main.py"]
    WF["workflow/workflow.py"]
    PROMPTS["prompts/generator.py"]
    AGENT["agent/agent.py"]
    TOOLS["agent/tools.py"]
    MODELS["core/models.py"]
    EXEC["core/executor.py"]
    REPORT["core/reporting.py"]
    SPEC["spec/msa.yaml"]
    GUIDE["test-results/*.journey.md + *.journey.json"]
    TEST["generated-tests/*.py"]
    RESULT["test-results/*.report.json"]

    CLI --> WF
    SPEC --> PROMPTS
    WF --> PROMPTS
    WF --> AGENT
    AGENT --> TOOLS
    TOOLS --> MODELS
    WF --> REPORT
    REPORT --> GUIDE
    WF --> TEST
    TOOLS --> EXEC
    EXEC --> REPORT
    REPORT --> RESULT
```

## Grouped Runtime View

This view keeps the same Python architecture, but groups the moving parts by
role so the `test` workflow reads more like an execution map than a waterfall.

```mermaid
flowchart LR
    subgraph CLI ["CLI Layer"]
        CMD_RUN["`run` command"]
        CMD_TEST["`test` command"]
        MAIN["`main.py`"]
    end

    USER_INPUT["User journey or task"]

    subgraph WF ["Workflow Layer"]
        WORKFLOW["`workflow/workflow.py`"]
        BROWSE_PROMPT["Browse prompt"]
        TEST_PROMPT["Test-generation prompt"]
    end

    subgraph CONTEXT ["Domain Context"]
        SPEC["`spec/msa.yaml`"]
    end

    subgraph AGENT ["Agent Runtime"]
        AGENT_CORE["`agent/agent.py`<br/>PydanticAI agent + Playwright MCP"]
        TOOLS["`agent/tools.py`<br/>log_action / timers / file write / test run"]
    end

    subgraph CAPTURE ["Journey Capture"]
        CAPTURE_MODEL["`JourneyCapture`"]
        GUIDE["`JourneyGuide`"]
        COVERAGE["`CoverageSnapshot`"]
    end

    subgraph ARTIFACTS ["Generated Artifacts"]
        TEST_FILE["`generated-tests/*.py`"]
        JOURNEY_MD["`test-results/*.journey.md`"]
        JOURNEY_JSON["`test-results/*.journey.json`"]
        REPORT_JSON["`test-results/*.report.json`"]
    end

    subgraph EXECUTION ["Execution Layer"]
        EXECUTOR["`core/executor.py`<br/>pytest subprocess"]
        REPORTING["`core/reporting.py`<br/>journey + execution reporting"]
    end

    subgraph SYSTEM ["System Under Test"]
        UI["Docker app UI<br/>`localhost:8080`"]
        API["MSA endpoints behind UI gateway"]
    end

    USER_INPUT --> MAIN
    MAIN --> CMD_RUN
    MAIN --> CMD_TEST

    CMD_TEST --> WORKFLOW
    SPEC --> BROWSE_PROMPT
    SPEC --> TEST_PROMPT
    WORKFLOW --> BROWSE_PROMPT
    WORKFLOW --> TEST_PROMPT
    WORKFLOW --> AGENT_CORE

    BROWSE_PROMPT --> AGENT_CORE
    AGENT_CORE --> TOOLS
    TOOLS --> CAPTURE_MODEL
    CAPTURE_MODEL --> REPORTING
    REPORTING --> GUIDE
    GUIDE --> COVERAGE
    REPORTING --> JOURNEY_MD
    REPORTING --> JOURNEY_JSON

    TEST_PROMPT --> AGENT_CORE
    CAPTURE_MODEL --> TEST_PROMPT
    GUIDE --> TEST_PROMPT
    AGENT_CORE --> TEST_FILE

    TEST_FILE --> TOOLS
    TOOLS --> EXECUTOR
    EXECUTOR --> UI
    UI --> API
    EXECUTOR --> REPORTING
    GUIDE --> REPORTING
    REPORTING --> REPORT_JSON

    CMD_RUN --> AGENT_CORE

    style CLI fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    style WF fill:#f3e8ff,stroke:#7c3aed,color:#4c1d95
    style CONTEXT fill:#fef3c7,stroke:#d97706,color:#78350f
    style AGENT fill:#ede9fe,stroke:#7c3aed,color:#3b0764
    style CAPTURE fill:#dcfce7,stroke:#16a34a,color:#14532d
    style ARTIFACTS fill:#ecfeff,stroke:#0891b2,color:#164e63
    style EXECUTION fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    style SYSTEM fill:#e0f0ff,stroke:#1d63ed,color:#003f7f
```

## Package Responsibilities

- `main.py`
  - CLI parsing
  - command dispatch only
- `workflow/`
  - owns the `run` and `test` orchestration
  - keeps `main.py` unchanged via `workflow/__init__.py`
- `prompts/`
  - loads `spec/msa.yaml`
  - builds browse and test-generation prompts
  - validates generated test filenames
- `agent/`
  - constructs the PydanticAI agent and Playwright MCP server
  - registers all `@agent.tool` functions
- `core/models.py`
  - typed journey, coverage, execution, and reporting models
- `core/executor.py`
  - runs pytest in a subprocess
  - collects stdout, stderr, exit code, and artifacts
- `core/reporting.py`
  - builds journey guides before code generation
  - builds execution reports after test execution
  - persists markdown and JSON artifacts under `test-results/`

## Current Test Flow

For `uv run python main.py test "<journey>" --filename test_foo.py --max-retries 5`:

1. `main.py` dispatches to `workflow.generate_test(...)`.
2. `prompts/generator.py` loads `spec/msa.yaml`.
3. The agent browses the live UI with Playwright MCP.
4. The browse phase logs actions and timings through `agent/tools.py`.
5. `core/reporting.py` converts that capture into a saved journey guide before any test file is generated.
6. The journey guide is written to:
   - `test-results/<test_name>.journey.md`
   - `test-results/<test_name>.journey.json`
7. The test-generation prompt uses the requested journey, the MSA spec, and the captured browse steps.
8. The agent writes `generated-tests/<test_name>.py`.
9. The agent runs the generated test through `core/executor.py`.
10. `core/reporting.py` writes `test-results/<test_name>.report.json`.
11. The execution report includes the saved journey artifacts plus a first-pass coverage snapshot.

## Persisted Artifacts

For each generated test name `test_foo.py`, the runtime now persists:

- `generated-tests/test_foo.py`
  - generated Playwright pytest file
- `test-results/test_foo.journey.md`
  - human-readable UI journey guide
- `test-results/test_foo.journey.json`
  - machine-readable journey and coverage data
- `test-results/test_foo.report.json`
  - execution result plus artifact references

## Typed Contracts In Use

The current Python flow already uses these core contracts:

- `ActionStep`
  - one logged UI action and why it was taken
- `TimingSample`
  - elapsed time for a named step
- `JourneyCapture`
  - ordered browse-phase actions and timings
- `CoverageSnapshot`
  - UI-step count
  - unique-action count
  - timed-step count
  - endpoint candidate count
  - service candidate count
  - candidate endpoint and service labels
  - caveat notes about heuristic coverage
- `JourneyGuide`
  - requested journey
  - cloned `JourneyCapture`
  - persisted paths for markdown and JSON guide artifacts
  - `CoverageSnapshot`
- `ExecutionResult`
  - subprocess result and collected artifacts
- `ExecutionReport`
  - pass/fail status
  - summary and raw output
  - saved report path
  - related artifacts
  - optional `CoverageSnapshot`

## Coverage Model Today

Coverage is intentionally conservative at this stage.

- UI coverage is based on logged browser actions and timers.
- Endpoint coverage is heuristic: journey text plus logged actions are matched against endpoints declared in `spec/msa.yaml`.
- Service coverage is derived from the matched endpoint set and acts as a first-pass node or microservice coverage estimate.
- DOM-node coverage is not implemented yet.

This is enough to support later evaluation work without pretending that true backend or UI instrumentation already exists.

## Current Gaps

The architecture is cleaner than before, but a few gaps remain:

1. Coverage is still heuristic and spec-driven, not instrumented from network traffic or DOM traversal.
2. Reporting is persisted as JSON and markdown, but not yet as JUnit or another external test-report format.
3. The workflow still relies on one agent runtime across browse, synthesize, and execute phases.

## Near-Term Direction

The next reasonable additions are:

1. Capture actual request or route usage from the browser to replace heuristic endpoint matching.
2. Add explicit UI-node coverage if later evaluation needs DOM-level evidence instead of action logs.
3. Persist a portable test report format alongside the existing JSON artifacts.
4. Optionally split browse and synthesize into separately invokable workflow stages.
