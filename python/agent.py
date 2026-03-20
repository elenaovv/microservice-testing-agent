import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import Agent, BinaryContent, RunContext
from pydantic_ai.mcp import MCPServerStdio

GENERATED_TESTS_DIR = Path("generated-tests")


@dataclass
class Deps:
    action_log: list[dict] = field(default_factory=list)
    timers: dict[str, float] = field(default_factory=dict)


mcp = MCPServerStdio("npx", ["-y", "@playwright/mcp@latest"])

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
        "Use the logged actions and measured timings to write the test — include every step, nothing skipped. "
        "Use `expect(locator).to_be_visible()` before interacting with elements so failures are clear. "
        "Set per-step timeouts to 2-3x the observed duration from your timers."
    ),
)


def _log(msg: str) -> None:
    print(f"\033[90m{msg}\033[0m", flush=True)


@agent.tool
def log_action(ctx: RunContext[Deps], action: str, note: str) -> str:
    """Log a browser action and the reason it was taken. Call after every meaningful interaction."""
    ctx.deps.action_log.append({"action": action, "note": note})
    _log(f"📝 {action} — {note}")
    return f"Logged: {action}"


@agent.tool
def start_timer(ctx: RunContext[Deps], name: str) -> str:
    """Start a named timer to measure how long a step takes."""
    ctx.deps.timers[name] = time.time()
    return f"Timer '{name}' started"


@agent.tool
def stop_timer(ctx: RunContext[Deps], name: str) -> str:
    """Stop a named timer and return elapsed seconds."""
    if name not in ctx.deps.timers:
        return f"No timer named '{name}'"
    elapsed = time.time() - ctx.deps.timers.pop(name)
    _log(f"⏱ {name}: {elapsed:.1f}s")
    return f"'{name}' took {elapsed:.1f}s"


@agent.tool
def create_test_file(ctx: RunContext[Deps], filename: str, code: str) -> str:
    """Create a pytest-playwright test file in generated-tests/. Filename must start with test_ and end with .py."""
    GENERATED_TESTS_DIR.mkdir(exist_ok=True)
    path = GENERATED_TESTS_DIR / filename
    path.write_text(code)
    _log(f"📄 {path} ({len(code.splitlines())} lines)")
    return f"Created {path}"


@agent.tool
def run_test_file(ctx: RunContext[Deps], filename: str) -> str | list:
    """Run a pytest file from generated-tests/. Returns output and a screenshot if the test failed."""
    path = GENERATED_TESTS_DIR / filename
    if not path.exists():
        return f"File not found: {path}"

    _log(f"🧪 Running {filename} ...")
    result = subprocess.run(
        [
            "uv", "run", "pytest", str(path), "-v", "--tb=short",
            "--headed", "--timeout=30",
            "--screenshot=only-on-failure",
            "--output=test-results",
        ],
        capture_output=True, text=True,
    )
    output = result.stdout + result.stderr
    for line in output.splitlines():
        _log(f"  {line}")

    if result.returncode != 0:
        screenshots = sorted(Path("test-results").rglob("*.png"), key=lambda p: p.stat().st_mtime)
        if screenshots:
            latest = screenshots[-1]
            _log(f"📸 Attaching screenshot: {latest}")
            return [output, BinaryContent(data=latest.read_bytes(), media_type="image/png")]

    return output
