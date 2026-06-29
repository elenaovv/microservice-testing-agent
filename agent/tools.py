"""Agent tools: registered via @agent.tool decorators.

This module is imported by agent.agent after the agent is constructed so that
all decorators run against the live agent instance.
"""
import hashlib
import py_compile
import re
import sys
import time
from pathlib import Path
from typing import Any

from pydantic_ai import BinaryContent, RunContext

from agent.agent import agent
from core.executor import run_generated_test
from core.models import ApiCall, Deps, ExecutionResult, InteractionContract, SuccessObservation
from core.run_artifacts import (
    GENERATED_TESTS_DIR,
    RUNTIME_RESULTS_DIR,
    RunArtifactPaths,
    TEST_RESULTS_DIR,
)
from core.reporting import (
    build_execution_report,
    load_journey_guide,
    write_execution_report,
)
from core.report_rendering import render_execution_report
from core.retry_budget import (
    render_repair_budget,
    repair_budget_exhausted,
)


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


def _syntax_check(path: Path) -> str | None:
    if not path.exists():
        return f"File not found: {path}"
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        return str(exc)
    return None


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
    path: URL path only, e.g. /api/v1/catalog/items/some-id
    status_code: HTTP response status code (0 if not visible)"""
    call = ApiCall(method=method.upper(), path=path, status_code=status_code)
    ctx.deps.capture.api_calls.append(call)
    _log(f"API: {method.upper()} {path} → {status_code or '?'}")
    return f"Logged: {method.upper()} {path} ({status_code or 'status unknown'})"


@agent.tool
def log_interaction_contract(
    ctx: RunContext[Deps],
    surface_type: str,
    container: dict[str, Any],
    fields: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    notes: str = "",
) -> str:
    """Record a structured contract for the actual interaction surface used.

    Use this after inspecting a form/modal/page/API/gRPC interaction that is
    required to complete the microservice use case. Surface_type may be web_page, web_modal, web_drawer, rest_endpoint,
    graphql_operation, grpc_method, cli_command, message_event, etc.

    For web UI fields, include actual DOM facts observed live:
    selector, label, id/element_id, tag, input_type, role, visible, editable,
    and select options as [{"label": "...", "value": "..."}].

    For actions, include the actual selector/tag/text/role and validated_locators
    when known. If one action opens another surface, set opens_surface. For the
    action that performs the business operation, include expected_service_calls
    or side_effects, e.g. [{"method": "POST", "path": "/api/...",
    "status_code": 200, "purpose": "business_state_change"}].
    """
    payload = {
        "surface_type": surface_type,
        "container": container or {},
        "fields": fields or [],
        "actions": actions or [],
        "notes": notes,
    }
    interaction = InteractionContract.from_dict(payload)
    existing_index = _find_existing_interaction_contract_index(
        ctx.deps.capture.interaction_contracts,
        interaction,
    )
    if existing_index is None:
        ctx.deps.capture.interaction_contracts.append(interaction)
    else:
        ctx.deps.capture.interaction_contracts[existing_index] = interaction
    container_kind = interaction.container.kind or "interaction"
    field_count = len(interaction.fields)
    action_count = len(interaction.actions)
    _log(
        "interaction contract — "
        f"{surface_type}/{container_kind}; fields={field_count}; actions={action_count}"
    )
    return (
        f"Logged interaction contract: {surface_type}/{container_kind} "
        f"with {field_count} field(s), {action_count} action(s)"
    )


def _find_existing_interaction_contract_index(
    interactions: list[InteractionContract],
    candidate: InteractionContract,
) -> int | None:
    candidate_key = _interaction_contract_key(candidate)
    if candidate_key is None:
        return None
    for index, interaction in enumerate(interactions):
        if _interaction_contract_key(interaction) == candidate_key:
            return index
    return None


def _interaction_contract_key(
    interaction: InteractionContract,
) -> tuple[str, str, str, str, str] | None:
    container = interaction.container
    surface_type = interaction.surface_type.strip().lower()
    kind = container.kind.strip().lower()
    anchor_text = re.sub(r"\s+", " ", container.anchor_text.strip().lower())
    selector = container.selector.strip()
    element_id = container.element_id.strip()
    url = container.url.strip()
    if not any((anchor_text, selector, element_id, url)):
        return None
    if anchor_text:
        return (surface_type, kind, anchor_text, url, "")
    return (surface_type, kind, selector or element_id, "", url)


@agent.tool
def log_success_observation(
    ctx: RunContext[Deps],
    label: str,
    surface_type: str,
    assertion: str,
    observation_kind: str = "",
    locator: str = "",
    scope_locator: str = "",
    scope_validated_locators: list[dict[str, Any]] | None = None,
    target_value: str = "",
    target_value_source: str = "",
    validated_locators: list[dict[str, Any]] | None = None,
    assertions: list[dict[str, Any]] | None = None,
    refresh_strategy: dict[str, Any] | None = None,
    observed_at_step: int | None = None,
    reason: str = "",
) -> str:
    """Record the exact observed proof that the use case success criteria were met.

    This is system-agnostic evidence. Use it
    for any interface type: web UI, REST endpoint, GraphQL operation, gRPC method,
    CLI command, or message event. For web UI evidence, include executable locator
    candidates that were verified live, such as a scoped role locator, CSS selector,
    test id, or XPath fallback. Do not record browser snapshot refs as executable
    locators. For repeated records such as table rows, list items, cards, or detail
    panels, record a scope_locator for the record/container and one assertion per
    important field, using structural locators inside that scope when visible text
    is duplicated.
    """
    payload = {
        "label": label,
        "surface_type": surface_type,
        "observation_kind": observation_kind,
        "assertion": assertion,
        "locator": locator,
        "scope_locator": scope_locator,
        "scope_validated_locators": scope_validated_locators or [],
        "target_value": target_value,
        "target_value_source": target_value_source,
        "validated_locators": validated_locators or [],
        "assertions": assertions or [],
        "refresh_strategy": refresh_strategy or {},
        "observed_at_step": observed_at_step,
        "reason": reason,
    }
    observation = SuccessObservation.from_dict(payload)
    ctx.deps.capture.success_observations.append(observation)
    locator_count = (
        len(observation.validated_locators)
        + len(observation.scope_validated_locators)
        + sum(len(assertion.validated_locators) for assertion in observation.assertions)
    )
    _log(
        "success observation - "
        f"{observation.surface_type or 'surface'}:{observation.label or observation.assertion}; "
        f"assertions={len(observation.assertions)}; locators={locator_count}"
    )
    return (
        f"Logged success observation: {observation.label or observation.assertion} "
        f"with {len(observation.assertions)} assertion(s), "
        f"{locator_count} locator candidate(s)"
    )


@agent.tool
def log_baseline_observation(
    ctx: RunContext[Deps],
    label: str,
    surface_type: str,
    assertion: str,
    observation_kind: str = "",
    locator: str = "",
    scope_locator: str = "",
    scope_validated_locators: list[dict[str, Any]] | None = None,
    target_value: str = "",
    target_value_source: str = "",
    validated_locators: list[dict[str, Any]] | None = None,
    assertions: list[dict[str, Any]] | None = None,
    refresh_strategy: dict[str, Any] | None = None,
    observed_at_step: int | None = None,
    reason: str = "",
) -> str:
    """Record structured pre-action state needed to perform or verify the journey.

    Baseline observations are not success criteria. Use this for original values,
    selected target records, preconditions, or source data that the generated test
    should preserve or compare against after an action. Use log_success_observation
    only after the requested success criteria have actually been verified.
    """
    payload = {
        "label": label,
        "surface_type": surface_type,
        "observation_kind": observation_kind,
        "assertion": assertion,
        "locator": locator,
        "scope_locator": scope_locator,
        "scope_validated_locators": scope_validated_locators or [],
        "target_value": target_value,
        "target_value_source": target_value_source,
        "validated_locators": validated_locators or [],
        "assertions": assertions or [],
        "refresh_strategy": refresh_strategy or {},
        "observed_at_step": observed_at_step,
        "reason": reason,
    }
    observation = SuccessObservation.from_dict(payload)
    ctx.deps.capture.baseline_observations.append(observation)
    locator_count = (
        len(observation.validated_locators)
        + len(observation.scope_validated_locators)
        + sum(len(assertion.validated_locators) for assertion in observation.assertions)
    )
    _log(
        "baseline observation - "
        f"{observation.surface_type or 'surface'}:{observation.label or observation.assertion}; "
        f"assertions={len(observation.assertions)}; locators={locator_count}"
    )
    return (
        f"Logged baseline observation: {observation.label or observation.assertion} "
        f"with {len(observation.assertions)} assertion(s), "
        f"{locator_count} locator candidate(s)"
    )


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
    if repair_budget_exhausted(ctx.deps.max_retries, ctx.deps.test_attempts):
        return (
            "Rejected: generated-test repair budget is exhausted. "
            f"{render_repair_budget(ctx.deps.max_retries, ctx.deps.test_attempts)}. "
            "Stop repairing and report the final failure from the latest execution report."
        )
    current_hash = hashlib.md5(code.encode()).hexdigest()[:12]
    if current_hash == ctx.deps.last_test_hash:
        return (
            f"Rejected: this code is identical to your previous attempt (hash {current_hash}). "
            "Running it again will produce the same failure. "
            "You must take a meaningfully different approach — change the locator strategy, "
            "restructure the flow, or reconsider which elements you are targeting."
        )
    ctx.deps.last_test_hash = current_hash
    ctx.deps.generation_attempts += 1
    generated_tests_dir = ctx.deps.generated_tests_dir or GENERATED_TESTS_DIR
    generated_tests_dir.mkdir(parents=True, exist_ok=True)
    path = generated_tests_dir / filename
    path.write_text(code, encoding="utf-8")
    _log(f"{path} ({len(code.splitlines())} lines)")

    # Archive every generated attempt under test-results/test-attempts/<test_stem>/.
    archive_dir = RunArtifactPaths(output_dir=ctx.deps.output_dir or TEST_RESULTS_DIR).test_attempts_dir(filename)
    archive_dir.mkdir(parents=True, exist_ok=True)
    attempt_name = f"attempt-{ctx.deps.generation_attempts:03d}-{current_hash}.py"
    archive_path = archive_dir / attempt_name
    archive_path.write_text(code, encoding="utf-8")
    _log(f"Archived {archive_path}")
    return f"Created {path}"


@agent.tool
def run_test_file(ctx: RunContext[Deps], filename: str) -> str | list:
    """Run a pytest file from generated-tests/. Returns output and a screenshot if the test failed."""
    if repair_budget_exhausted(ctx.deps.max_retries, ctx.deps.test_attempts):
        message = (
            "Repair budget exhausted before running another test execution. "
            f"{render_repair_budget(ctx.deps.max_retries, ctx.deps.test_attempts)}. "
            "Do not generate or run more repair attempts."
        )
        _log(message)
        return message
    _log(f"Running {filename} ...")
    ctx.deps.test_attempts += 1
    evaluation = ctx.deps.evaluation
    _output_dir = ctx.deps.output_dir or TEST_RESULTS_DIR
    generated_tests_dir = ctx.deps.generated_tests_dir or GENERATED_TESTS_DIR
    runtime_results_dir = ctx.deps.runtime_results_dir or RUNTIME_RESULTS_DIR
    test_path = generated_tests_dir / filename
    syntax_error = _syntax_check(test_path)
    if syntax_error:
        result = ExecutionResult(
            filename=filename,
            exit_code=2,
            stderr=f"Syntax check failed:\n{syntax_error}",
        )
    else:
        result = run_generated_test(
            filename=filename,
            generated_tests_dir=generated_tests_dir,
            base_url=evaluation.base_url if evaluation else None,
            network_results_dir=_output_dir,
            runtime_results_dir=runtime_results_dir,
        )
    if result.failed:
        ctx.deps.failed_test_attempts += 1
    journey_guide = load_journey_guide(filename, output_dir=_output_dir)
    report = build_execution_report(
        result,
        journey_guide=journey_guide,
        generated_tests_dir=generated_tests_dir,
        test_results_dir=_output_dir,
        evaluation=evaluation,
        max_retries=ctx.deps.max_retries,
        test_attempts=ctx.deps.test_attempts,
        failed_test_attempts=ctx.deps.failed_test_attempts,
    )
    write_execution_report(report, output_dir=_output_dir)
    report_text = render_execution_report(report)
    report_text = (
        f"{report_text}\n"
        f"- phase1.repair_budget: "
        f"{render_repair_budget(ctx.deps.max_retries, ctx.deps.test_attempts)}"
    )
    if report.phase1 and report.phase1.failure_diagnosis:
        diagnosis = report.phase1.failure_diagnosis
        repair_lines = [
            "",
            "TARGETED REPAIR GUIDANCE",
            "------------------------",
            f"First failing operation: {diagnosis.kind or report.phase1.failure_kind}",
        ]
        if diagnosis.failing_line:
            repair_lines.append(f"- failing_line: {diagnosis.failing_line}")
        if diagnosis.failing_locator:
            repair_lines.append(f"- failing_locator: {diagnosis.failing_locator}")
        if diagnosis.suggested_contract_surface:
            repair_lines.append(
                f"- relevant_contract_surface: {diagnosis.suggested_contract_surface}"
            )
        if diagnosis.suggested_repair_strategy:
            repair_lines.append(
                f"- suggested_repair_strategy: {diagnosis.suggested_repair_strategy}"
            )
        if diagnosis.repair_candidates:
            repair_lines.append("- repair_candidates:")
            for candidate in diagnosis.repair_candidates[:5]:
                scope = f"; scope={candidate.scope}" if candidate.scope else ""
                state = "validated" if candidate.validated else "suggested"
                executable = "executable" if candidate.executable else "non-executable"
                repair_lines.append(
                    f"  - {state}/{executable}: {candidate.strategy}={candidate.value}{scope}"
                )
        if (
            diagnosis.blocked_before_required_call
            and report.phase1.missing_expected_service_calls
        ):
            repair_lines.append(
                "The required service call is missing because the test failed before "
                "the trigger action. Repair only the failing locator/action first."
            )
        elif report.phase1.missing_expected_service_calls:
            repair_lines.append(
                "The generated run reached the flow but did not emit required "
                "service-side effect(s). Repair the trigger action below."
            )
            for call in report.phase1.missing_expected_service_calls:
                trigger = str(call.get("trigger_action", "")).strip() or "unknown trigger action"
                selector = str(call.get("trigger_selector_hint", "")).strip() or "no selector hint captured"
                repair_lines.append(
                    f"- Missing {call.get('method', '')} {call.get('path', '')}; "
                    f"trigger={trigger}; selector_hint={selector}"
                )
        repair_lines.append(
            "Allowed edit scope: keep successful setup/navigation/data entry stable; "
            "change only the failing locator/action unless the report proves that earlier "
            "steps did not execute."
        )
        report_text = f"{report_text}\n" + "\n".join(repair_lines)
    if result.failed:
        test_path = generated_tests_dir / filename
        try:
            test_source = test_path.read_text(encoding="utf-8")
        except Exception as exc:
            test_source = f"<could not read {test_path}: {exc}>"
        report_text = (
            f"{report_text}\n\n"
            "GENERATED TEST SOURCE\n"
            "-----------------------\n"
            f"{test_source}\n"
        )
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
