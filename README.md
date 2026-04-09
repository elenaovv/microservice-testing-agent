# Browsing Agent

This repository contains the Python research prototype for browsing-driven end-to-end test generation for web systems and microservice-based applications.

If someone new wants to run the project, the operator guide is here:
- [python/README.md](python/README.md)

In short, the runtime does this:
1. Browse the live UI with an LLM agent through Playwright MCP.
2. Log the journey and generate a Python end-to-end test.
3. Run the generated test and save evaluation artifacts.

Main runtime entry point:
- [python/main.py](python/main.py)

Main output locations:
- generated tests: `python/generated-tests/`
- reports and evaluation artifacts: `python/test-results/`
