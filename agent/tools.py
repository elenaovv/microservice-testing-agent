"""Agent tools: registered via @agent.tool decorators.

This module is imported by agent.agent after the agent is constructed so that
all decorators run against the live agent instance.
"""
import hashlib
import sys
import time
from pathlib import Path

from pydantic_ai import BinaryContent, RunContext

from agent.agent import agent
from core.executor import run_generated_test
from core.models import ApiCall, Deps
from core.reporting import (
    build_execution_report,
    load_journey_guide,
    write_execution_report,
)
from core.report_rendering import render_execution_report

GENERATED_TESTS_DIR = Path("generated-tests")


@agent.tool
def read_spec_file(ctx: RunContext[Deps], path: str) -> str:
    """Read a specification file by path and return its full contents.
    Use this to access credentials, gateway details, service descriptions,
    or any other information from the MSA spec or related files that is
    not already present in the prompt.
    Accepts paths relative to the project root or absolute paths."""
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    if not resolved.exists():
        return f"File not found: {path}"
    try:
        return resolved.read_text(encoding="utf-8")
    except Exception as exc:
        return f"Could not read {path}: {exc}"


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
def log_api_call(ctx: RunContext[Deps], method: str, path: str, status_code: int = 0) -> str:
    """Log a backend API call observed in the browser network activity.
    Call this for every significant backend request you observe, especially
    state-changing ones (POST, PUT, DELETE) and their responses.
    method: HTTP method (GET, POST, PUT, DELETE, etc.)
    path: URL path only, e.g. /api/v1/adminrouteservice/adminroute/some-id
    status_code: HTTP response status code (0 if not visible)"""
    call = ApiCall(method=method.upper(), path=path, status_code=status_code)
    ctx.deps.capture.api_calls.append(call)
    _log(f"API: {method.upper()} {path} → {status_code or '?'}")
    return f"Logged: {method.upper()} {path} ({status_code or 'status unknown'})"


@agent.tool
def report_journey_outcome(ctx: RunContext[Deps], success: bool, reason: str) -> str:
    """Report whether the browse phase successfully completed the use case journey.
    MUST be called at the end of every browse phase.
    success: True if all success criteria were met and verified, False otherwise.
    reason: brief explanation — what was achieved or what blocked completion."""
    ctx.deps.journey_succeeded = success
    ctx.deps.journey_outcome_reason = reason
    status = "SUCCEEDED" if success else "FAILED"
    _log(f"Journey outcome: {status} — {reason}")
    return f"Journey outcome recorded: {status}"


@agent.tool
def create_python_test_file(ctx: RunContext[Deps], filename: str, code: str) -> str:
    """
    Create a pytest-playwright test file in generated-tests/. Filename must end with .py.
    Make sure the test is an executable python file. So that it can be run using `uv run python test_generated.py`
    """
    current_hash = hashlib.md5(code.encode()).hexdigest()[:12]
    if current_hash == ctx.deps.last_test_hash:
        return (
            f"Rejected: this code is identical to your previous attempt (hash {current_hash}). "
            "Running it again will produce the same failure. "
            "You must take a meaningfully different approach — change the locator strategy, "
            "restructure the flow, or reconsider which elements you are targeting."
        )
    ctx.deps.last_test_hash = current_hash
    GENERATED_TESTS_DIR.mkdir(exist_ok=True)
    path = GENERATED_TESTS_DIR / filename
    path.write_text(code, encoding="utf-8")
    _log(f"{path} ({len(code.splitlines())} lines)")
    return f"Created {path}"


@agent.tool
def run_test_file(ctx: RunContext[Deps], filename: str) -> str | list:
    """Run a pytest file from generated-tests/. Returns output and a screenshot if the test failed."""
    _log(f"Running {filename} ...")
    ctx.deps.test_attempts += 1
    evaluation = ctx.deps.evaluation
    _output_dir = ctx.deps.output_dir or Path("test-results")
    result = run_generated_test(
        filename=filename,
        generated_tests_dir=GENERATED_TESTS_DIR,
        base_url=evaluation.base_url if evaluation else None,
        network_results_dir=_output_dir,
    )
    if result.failed:
        ctx.deps.failed_test_attempts += 1
    journey_guide = load_journey_guide(filename, output_dir=_output_dir)
    report = build_execution_report(
        result,
        journey_guide=journey_guide,
        test_results_dir=_output_dir,
        evaluation=evaluation,
        max_retries=ctx.deps.max_retries,
        test_attempts=ctx.deps.test_attempts,
        failed_test_attempts=ctx.deps.failed_test_attempts,
    )
    write_execution_report(report, output_dir=_output_dir)
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
