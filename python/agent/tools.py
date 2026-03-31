"""Agent tools: registered via @agent.tool decorators.

This module is imported by agent.agent after the agent is constructed so that
all decorators run against the live agent instance.
"""
import sys
import time
from pathlib import Path

from pydantic_ai import BinaryContent, RunContext

from agent.agent import agent
from core.executor import run_generated_test
from core.models import Deps
from core.reporting import (
    build_execution_report,
    load_journey_guide,
    render_execution_report,
    write_execution_report,
)

GENERATED_TESTS_DIR = Path("generated-tests")


def _log(msg: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe_msg = msg.encode(encoding, errors="replace").decode(encoding)
    print(f"\033[90m{safe_msg}\033[0m", flush=True)


@agent.tool
def log_action(ctx: RunContext[Deps], action: str, note: str) -> str:
    """Log a browser action and the reason it was taken. Call after every meaningful interaction."""
    ctx.deps.capture.log_action(action, note)
    _log(f"{action} — {note}")
    return f"Logged: {action}"


@agent.tool
def start_timer(ctx: RunContext[Deps], name: str) -> str:
    """Start a named timer to measure how long a step takes."""
    ctx.deps.active_timers[name] = time.time()
    return f"Timer '{name}' started"


@agent.tool
def stop_timer(ctx: RunContext[Deps], name: str) -> str:
    """Stop a named timer and return elapsed seconds."""
    if name not in ctx.deps.active_timers:
        return f"No timer named '{name}'"
    elapsed = time.time() - ctx.deps.active_timers.pop(name)
    ctx.deps.capture.record_timing(name, elapsed)
    _log(f"{name}: {elapsed:.1f}s")
    return f"'{name}' took {elapsed:.1f}s"


@agent.tool
def create_python_test_file(ctx: RunContext[Deps], filename: str, code: str) -> str:
    """
    Create a pytest-playwright test file in generated-tests/. Filename must end with .py.
    Make sure the test is an executable python file. So that it can be run using `uv run python test_generated.py`
    """
    GENERATED_TESTS_DIR.mkdir(exist_ok=True)
    path = GENERATED_TESTS_DIR / filename
    path.write_text(code)
    _log(f"{path} ({len(code.splitlines())} lines)")
    return f"Created {path}"


@agent.tool
def run_test_file(ctx: RunContext[Deps], filename: str) -> str | list:
    """Run a pytest file from generated-tests/. Returns output and a screenshot if the test failed."""
    _log(f"Running {filename} ...")
    evaluation = ctx.deps.evaluation
    result = run_generated_test(
        filename=filename,
        generated_tests_dir=GENERATED_TESTS_DIR,
        base_url=evaluation.base_url if evaluation else None,
    )
    journey_guide = load_journey_guide(filename)
    report = build_execution_report(
        result,
        journey_guide=journey_guide,
        evaluation=evaluation,
    )
    write_execution_report(report)
    report_text = render_execution_report(report)
    for line in report_text.splitlines():
        _log(f"  {line}")

    if result.failed:
        screenshot = result.latest_artifact("screenshot")
        if screenshot is not None:
            _log(f"Attaching screenshot: {screenshot.path}")
            return [
                report_text,
                BinaryContent(
                    data=screenshot.path.read_bytes(),
                    media_type="image/png",
                ),
            ]

    return report_text
