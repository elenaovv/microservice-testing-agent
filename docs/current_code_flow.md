# Current Code Flow

This document summarizes the Python runtime after the `src/` layout and `core/`
subpackage split.

```mermaid
flowchart LR
    subgraph CLI ["CLI"]
        MAIN["main.py"]
        RUN["run"]
        TEST["test"]
    end

    subgraph INPUTS ["Inputs"]
        JOURNEY["Free-text journey"]
        USECASE["Structured use case"]
        SPEC["spec/msa.yaml"]
        SYSTEM["spec/system_description.md"]
    end

    subgraph WORKFLOW ["Workflow"]
        WF["src/workflow/workflow.py"]
        BROWSE["Browse phase"]
        CONTRACT["Journey evidence and contract"]
        GENERATE["Test generation and repair"]
    end

    subgraph AGENT ["Agent Runtime"]
        AGENT_CORE["src/agent/agent.py"]
        TOOLS["src/agent/tools.py"]
        MCP["Playwright MCP"]
    end

    subgraph OUTPUTS ["Artifacts"]
        TEST_FILE["generated-tests/*.py"]
        JOURNEY_MD["test-results/*.journey.md"]
        JOURNEY_JSON["test-results/*.journey.json"]
        REPORT["test-results/*.report.json"]
        HISTORY["test-results/evaluation-runs.jsonl"]
    end

    subgraph SUT ["System Under Test"]
        UI["UI gateway"]
        API["MSA endpoints"]
    end

    MAIN --> RUN
    MAIN --> TEST
    JOURNEY --> WF
    USECASE --> WF
    SPEC --> WF
    SYSTEM --> WF
    TEST --> WF
    WF --> BROWSE
    BROWSE --> AGENT_CORE
    AGENT_CORE --> TOOLS
    AGENT_CORE --> MCP
    MCP --> UI
    UI --> API
    BROWSE --> CONTRACT
    CONTRACT --> JOURNEY_MD
    CONTRACT --> JOURNEY_JSON
    CONTRACT --> GENERATE
    GENERATE --> TEST_FILE
    GENERATE --> REPORT
    REPORT --> HISTORY
```

## Run Sequence

1. `main.py` parses the CLI arguments and calls the workflow layer.
2. `src/workflow/workflow.py` loads the selected use case, MSA specification, and system description.
3. The browse phase drives the deployed UI through Playwright MCP.
4. Agent tools record actions, timings, API calls, interaction contracts, baseline observations, and success observations.
5. The workflow builds and saves the journey guide before generating code.
6. The generation phase writes a `pytest-playwright` file to `generated-tests/`.
7. The generated test runs through the pytest subprocess runner.
8. Reports and evaluation history are written under `test-results/`.

## Runtime Boundaries

| Area | Current behavior |
| --- | --- |
| Use-case input | Free-text journey, use-case ID, or use-case file |
| GUI model | Discovered through live browsing, not loaded from a static GUI description |
| Test output | One generated Python test file per run |
| Execution | pytest subprocess through `src/core/execution/executor.py` |
| Reporting | Journey Markdown/JSON, report JSON, network data, evaluation history |
| Backend evidence | Browser-visible HTTP requests matched to `spec/msa.yaml` |
