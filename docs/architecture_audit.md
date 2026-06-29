# Architecture Audit

This audit compares the current Python runtime with the intended two-phase
testing workflow.

## Runtime Flow

```mermaid
flowchart LR
    subgraph INPUTS ["Inputs"]
        UC["Use case"]
        SPEC["MSA specification"]
        SYS["System description"]
    end

    subgraph WF ["Workflow Orchestration"]
        CLI["main.py"]
        WORKFLOW["workflow/workflow.py"]
        BROWSE["Phase 1: browse journey"]
        CONTRACT["Journey evidence and contract"]
        REPLAY["Phase 2: generate, execute, repair"]
    end

    subgraph AGENT ["Agent Runtime"]
        CORE["agent/agent.py"]
        TOOLS["agent/tools.py"]
        MCP["Playwright MCP"]
    end

    subgraph CORE ["Core Services"]
        MODELS["core/models.py"]
        EXEC["core/executor.py"]
        REPORT["core/reporting.py"]
        COVERAGE["core/coverage_utils.py"]
    end

    subgraph ARTIFACTS ["Artifacts"]
        TESTS["generated-tests/*.py"]
        JOURNEY["test-results/*.journey.*"]
        RUN_REPORT["test-results/*.report.json"]
        HISTORY["test-results/evaluation-runs.jsonl"]
    end

    subgraph SUT ["System Under Test"]
        UI["UI gateway"]
        API["MSA services"]
    end

    UC --> CLI
    SPEC --> WORKFLOW
    SYS --> WORKFLOW
    CLI --> WORKFLOW
    WORKFLOW --> BROWSE
    BROWSE --> CORE
    CORE --> TOOLS
    TOOLS --> MCP
    MCP --> UI
    UI --> API
    BROWSE --> CONTRACT
    CONTRACT --> JOURNEY
    CONTRACT --> REPLAY
    REPLAY --> TESTS
    REPLAY --> EXEC
    EXEC --> REPORT
    REPORT --> RUN_REPORT
    RUN_REPORT --> HISTORY
```

## Component Status

| Component | Status | Notes |
| --- | --- | --- |
| CLI | Implemented | `main.py` supports `run`, `test`, repeated runs, use-case IDs, use-case files, and runtime paths. |
| Workflow orchestration | Implemented | `workflow/workflow.py` controls browsing, journey capture, generation, execution, repair, and reporting. |
| Structured use cases | Implemented | Loaded from `spec/use_cases/index.yaml` and the referenced YAML files. |
| MSA specification | Implemented | `spec/msa.yaml` is loaded, sliced for prompts, and parsed for coverage mapping. |
| System description | Implemented | Loaded from `spec/system_description.md` when supplied or defaulted. |
| Browser interaction | Implemented | Uses Playwright MCP through the Pydantic AI agent runtime. |
| Journey guide | Implemented | Saved as Markdown and JSON before test generation. |
| Journey contract | Implemented | Built from captured actions, interaction contracts, observed calls, baseline observations, and success observations. |
| Test generation | Implemented | Produces one `pytest-playwright` file per run. |
| Test execution | Implemented | Runs pytest through `core/executor.py`. |
| Repair loop | Implemented | Bounded by the configured retry budget. |
| Reporting | Implemented | Writes report JSON, evaluation history, summary tables, screenshots, and network artifacts. |
| Backend tracing | Not implemented | Current evidence is limited to frontend-visible HTTP requests. |

## Known Gaps

1. Generated output is one candidate test per run, not an assembled suite.
2. Backend coverage is based on gateway-visible HTTP traffic, not distributed tracing.
3. The same model-backed runtime handles browse and generation phases.
4. External report formats such as JUnit XML are not part of the current reporting path.
5. Main-study state reset is not enforced by the Python workflow.

## Scope

The implemented architecture supports the current research workflow: use a
structured task, browse the live system, save journey evidence, generate a
test, execute it, repair it, and report the result. It does not provide full
backend coverage or complete automated suite construction.
