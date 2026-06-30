import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

from core.execution.runtime_env import (
    PROJECT_ROOT,
    build_subprocess_env,
    configure_local_runtime_environment,
)
from core.contracts.models import Deps

load_dotenv()
configure_local_runtime_environment()

MODEL_NAME = os.environ.get("OPENAI_MODEL", "openai:gpt-5.4").strip() or "openai:gpt-5.4"
INTERNAL_AGENT_RETRIES = int(os.environ.get("AGENT_INTERNAL_RETRIES", "2"))

_SUPPRESS_DIALOGS = str(Path(__file__).resolve().parent.parent.parent / "suppress_dialogs.js")
_NPM_CACHE_DIR = str(PROJECT_ROOT / ".tmp" / "npm-cache")
_PLAYWRIGHT_MCP_VERSION = "0.0.77"


def _playwright_mcp_stdio() -> tuple[str, list[str]]:
    local_binary = PROJECT_ROOT / "node_modules" / ".bin" / (
        "playwright-mcp.cmd" if os.name == "nt" else "playwright-mcp"
    )
    base_args = ["--timeout-action", "30000", "--init-script", _SUPPRESS_DIALOGS]
    if local_binary.exists():
        return str(local_binary), base_args
    return (
        "npx",
        [
            "--cache",
            _NPM_CACHE_DIR,
            "--prefer-offline",
            "-y",
            f"@playwright/mcp@{_PLAYWRIGHT_MCP_VERSION}",
            *base_args,
        ],
    )


_MCP_COMMAND, _MCP_ARGS = _playwright_mcp_stdio()

mcp = MCPServerStdio(
    _MCP_COMMAND,
    _MCP_ARGS,
    env=build_subprocess_env(),
    cwd=PROJECT_ROOT,
    timeout=120,
)


def _load_system_prompt() -> str:
    return (Path(__file__).resolve().parent / "prompts" / "system.md").read_text(
        encoding="utf-8"
    ).strip()


SYSTEM_PROMPT_TEXT = _load_system_prompt()

agent = Agent(
    MODEL_NAME,
    deps_type=Deps,
    toolsets=[mcp],
    retries=INTERNAL_AGENT_RETRIES,
    system_prompt=SYSTEM_PROMPT_TEXT,
)

# Import tools so that @agent.tool decorators are registered when this module loads
from . import tools as _tools  # noqa: E402, F401
