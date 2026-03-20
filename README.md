# Browsing Agent

AI agent that controls a real browser via Playwright MCP, generates tests, and runs them.
Available in two flavours — same interface, same ideas, different output:

| | Python agent | Java agent |
|---|---|---|
| **Runtime** | uv / Python 3.12 | Maven / Java 21 |
| **AI framework** | pydantic-ai | LangChain4j |
| **Produces** | `pytest-playwright` tests → `python/generated-tests/` | Playwright-Java tests → `java/generated-tests/` |

---

## Python agent

```bash
cd python

uv run python main.py test "go to vr.fi, search Helsinki to Turku, verify results show price and time"
uv run python main.py test "go to vr.fi, search Helsinki to Turku" --filename test_vr.py
uv run python main.py test "..." --filename test_vr.py --max-retries 5
```

**Requirements:** Python 3.12+, `uv`, `OPENAI_API_KEY`

---

## Java agent

```bash
cd java

mvn exec:java -Dexec.args='test "go to vr.fi, search Helsinki to Turku, verify results show price and time"'
mvn exec:java -Dexec.args='test "go to vr.fi, search Helsinki to Turku" --filename TestVr.java'
mvn exec:java -Dexec.args='test "..." --filename TestVr.java --max-retries 5'
```

**Requirements:** Java 21+, Maven, `npx`, `OPENAI_API_KEY`

---

## How it works

1. The agent starts a `@playwright/mcp` stdio server and browses the journey step by step
2. Every action is noted — including cookie banners, popups, and overlays
3. A test is written that reproduces every step exactly
4. The test is run; if it fails the agent reads the error, fixes it, and retries up to `--max-retries` times
