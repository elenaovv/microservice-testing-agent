# Agent Package

This package defines the live AI agent layer.

Files:
- `agent.py` constructs the `pydantic-ai` `Agent`, selects the model, and connects to the Playwright MCP server.
- `tools.py` registers the tool functions available to the model during browsing and test generation.
- `prompts/system.md` contains the agent system prompt loaded by `agent.py`.

Current tool set:
- `log_action`
- `start_timer`
- `stop_timer`
- `create_python_test_file`
- `run_test_file`

This package is intentionally thin. It does not own reporting, evaluation, or prompt building logic; those stay in `core/` and `prompts/`.
