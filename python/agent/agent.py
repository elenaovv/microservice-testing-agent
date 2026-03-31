from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

from core.models import Deps

load_dotenv()

mcp = MCPServerStdio(
    "npx",
    ["-y", "@playwright/mcp@latest"],
    timeout=60,
)

agent = Agent(
    "openai:gpt-5.4",
    deps_type=Deps,
    mcp_servers=[mcp],
    retries=5,
    system_prompt=(
        "You are a browser automation agent. Use browser tools to complete tasks step by step. "
        "After each action, assess the result and decide what to do next — don't stop until the task is done. "
        "When asked to find a link or element 'like X', match by text content or semantic meaning. "
        "If something unexpected happens (login wall, cookie banner, CAPTCHA), handle it before continuing. "
        "Call log_action after every meaningful browser interaction — record what you did and why. "
        "Use start_timer / stop_timer around slow steps (page load, search results, navigation). "
        "When writing pytest-playwright tests: always use the `page` fixture, never manage the browser yourself. "
        "Always call `page.set_default_timeout(8000)` at the start of the test so failures are fast. "
        "If a cookie consent banner appeared, dismissing it must be the FIRST step after navigation. "
        "When MSA specification text is provided in the prompt, use it as domain context, but verify the actual UI live. "
        "Use the logged actions and measured timings to write the test — include every step, nothing skipped. "
        "Use `expect(locator).to_be_visible()` before interacting with elements so failures are clear. "
        "Set per-step timeouts to 2-3x the observed duration from your timers. "
        "Always add an `if __name__ == '__main__':` block at the bottom that launches Playwright directly "
        "and calls the test function, so the file can also be run with `python test_foo.py`."
    ),
)

# Import tools so that @agent.tool decorators are registered when this module loads
import agent.tools  # noqa: E402, F401
