# Current Code Flow (as implemented)

> How the root-level Python runtime actually works today.

```mermaid
flowchart LR
    subgraph CLI ["main.py CLI"]
        CMD_RUN["'run' command"]
        CMD_TEST["'test' command"]
    end

    USER_INPUT["User\n(free-text journey\nvia CLI argument)"]

    subgraph AGENT ["agent.py — Single LLM Agent"]
        direction TB
        LLM["OpenAI LLM API\n(pydantic-ai Agent)"]
        TOOLS["Agent Tools"]
        LOG["log_action()"]
        TIMER["start/stop_timer()"]
        CREATE["create_test_file()"]
        RUN_TEST["run_test_file()"]
        TOOLS --- LOG
        TOOLS --- TIMER
        TOOLS --- CREATE
        TOOLS --- RUN_TEST
    end

    subgraph PHASE1 ["Phase 1 — Browse Journey"]
        BROWSE["Agent browses\nlive app via\nPlaywright MCP"]
        ACTIONS["Logged actions\n+ timings"]
    end

    subgraph PHASE2 ["Phase 2 — Generate Test"]
        GEN["Agent writes\npytest-playwright\ntest from actions"]
        FILE["Single .py\ntest file"]
    end

    subgraph PHASE3 ["Phase 3 — Execute & Retry"]
        EXEC["pytest subprocess\n(run_test_file)"]
        OUTPUT["Raw stdout/stderr\n+ failure screenshot"]
        RETRY{"Pass?"}
    end

    subgraph DOCKER ["External — Hosted in Docker"]
        MSA["MSA Under Test\nlocalhost:8080"]
    end

    USER_INPUT -->|journey string| CMD_TEST
    CMD_TEST --> PHASE1
    BROWSE -->|calls| LLM
    LLM -->|browser actions via MCP| BROWSE
    BROWSE --> ACTIONS
    ACTIONS --> PHASE2
    GEN -->|calls| LLM
    LLM -->|test code| GEN
    GEN -->|create_test_file| FILE
    FILE --> PHASE3
    EXEC --> OUTPUT
    OUTPUT --> RETRY
    RETRY -->|No — retry up to N times| GEN
    RETRY -->|Yes| DONE["Done\n(console print)"]
    EXEC -->|HTTP requests| MSA
    MSA -->|responses| EXEC

    CMD_RUN -->|ad-hoc task| LLM

    style CLI fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    style AGENT fill:#ede9fe,stroke:#7c3aed,color:#3b0764
    style PHASE1 fill:#dcfce7,stroke:#16a34a,color:#14532d
    style PHASE2 fill:#fef9c3,stroke:#ca8a04,color:#713f12
    style PHASE3 fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    style MSA fill:#e0f0ff,stroke:#1D63ED,color:#003f7f
    style DOCKER fill:#eaf4ff,stroke:#1D63ED,color:#003f7f
```

## Key Differences from the Target Architecture

| Target Architecture | Current Code |
|---|---|
| **User Journey Extractor** takes use-case + MSA-spec documents and calls LLM to produce journeys | Journey is a **raw CLI string** typed by the user |
| **GUI description** document is fed into the Test Suite Generator | Agent **discovers the GUI live** by browsing via Playwright MCP |
| Generator and Executor are **separate components** | Both live inside **one monolithic agent** with a retry loop |
| A structured **Test Report** is produced and fed back | Only **raw console output** + optional failure screenshots |
