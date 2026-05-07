import asyncio
import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

from agent.agent import SYSTEM_PROMPT_TEXT, agent
from core.evaluation_utils import append_evaluation_history
from core.executor import run_generated_test
from core.models import (
    ApiCall,
    Deps,
    EvaluationContext,
    ExecutionReport,
    JourneyContract,
    UseCaseMetadata,
)
from core.prompt_capture import (
    resolve_prompt_capture_output_path,
    write_prompt_capture,
    write_prompt_capture_entries,
)
from core.reporting import (
    build_execution_report,
    build_journey_guide,
    load_journey_guide,
    load_execution_report,
    write_execution_report,
    write_journey_guide,
)
from core.report_rendering import (
    render_execution_report,
    render_journey_guide_summary,
)
from prompts.generator import (
    MSA_SPEC_PATH,
    build_browse_prompt,
    build_test_generation_prompt,
    derive_python_test_filename,
    load_msa_spec,
    load_system_description,
    validate_python_test_filename,
)
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.usage import UsageLimits

AGENT_USAGE_LIMITS = UsageLimits(request_limit=200)
GENERATED_TESTS_DIR = Path("generated-tests")


def _required_contract_calls_observed(
    contract: JourneyContract,
    api_calls: list[ApiCall],
) -> bool:
    required_calls = [call for call in contract.expected_service_calls if call.required]
    if not required_calls:
        return False
    actually_observed = {(c.method.upper(), c.path) for c in api_calls}
    observed_successful_calls = {
        (call.method.upper(), call.path)
        for call in api_calls
        if call.status_code == 0 or 200 <= call.status_code < 300
    }
    return all(
        (call.method.upper(), call.path) in observed_successful_calls
        or (
            # Spuriously declared from MSA spec reading but never actually observed:
            # a different required call was successfully observed instead.
            (call.method.upper(), call.path) not in actually_observed
            and any(
                (sc.method.upper(), sc.path) in observed_successful_calls
                for sc in required_calls
                if sc.path != call.path
            )
        )
        for call in required_calls
    )


def _incomplete_state_changing_contract_can_continue(
    contract: JourneyContract,
    api_calls: list[ApiCall],
    *,
    journey_succeeded: bool | None,
) -> bool:
    return journey_succeeded is True and _required_contract_calls_observed(
        contract,
        api_calls,
    )


def _missing_state_changing_trigger_locator(contract: JourneyContract) -> bool:
    has_missing_trigger_issue = any(
        issue.startswith("Missing validated executable locator for state-changing action ")
        for issue in contract.completeness_issues
    )
    if not has_missing_trigger_issue:
        return False
    return not _has_stable_state_changing_trigger_hint(contract)


def _has_stable_state_changing_trigger_hint(contract: JourneyContract) -> bool:
    required_calls = [call for call in contract.expected_service_calls if call.required]
    if not required_calls:
        return False
    return all(_looks_like_stable_trigger_hint(call.trigger_selector_hint) for call in required_calls)


def _looks_like_stable_trigger_hint(hint: str) -> bool:
    normalized = hint.strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if "[ref=" in lowered or "generic[ref=" in lowered:
        return False
    return bool(
        re.search(r"#[A-Za-z][\w:-]*\s+\[data-[A-Za-z0-9_:\-]+(?:=[^\]]+)?\]", normalized)
        or re.search(r"\[data-[A-Za-z0-9_:\-]+(?:=[^\]]+)?\]", normalized)
        or re.search(r"\btest[_-]?id\b", lowered)
    )


def _build_evaluation_context(
    variant_label: str,
    mutation_id: str,
    fault_service: str,
    base_url: str | None,
    run_kind: str,
) -> EvaluationContext:
    resolved_base_url = (
        (base_url or os.environ.get("BASE_URL") or "http://localhost:8080").strip()
    )
    return EvaluationContext(
        variant_label=variant_label.strip() or "original",
        mutation_id=mutation_id.strip(),
        fault_service=fault_service.strip(),
        base_url=resolved_base_url,
        run_kind=run_kind,
    )


def _extract_json_payload(raw_output: str) -> object | None:
    text = raw_output.strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```" in text:
        parts = text.split("```")
        for index in range(1, len(parts), 2):
            candidate = parts[index].strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    decoder = json.JSONDecoder()
    for start_index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[start_index:])
            return payload
        except json.JSONDecodeError:
            continue

    return None


def _parse_browse_network_requests(raw_output: str) -> list[dict[str, str]]:
    payload = _extract_json_payload(raw_output)
    if payload is None:
        return []

    raw_requests: list[object]
    if isinstance(payload, list):
        raw_requests = payload
    elif isinstance(payload, dict):
        for key in ("requests", "network_requests", "result", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                raw_requests = value
                break
        else:
            raw_requests = []
    else:
        raw_requests = []

    parsed_requests: list[dict[str, str]] = []
    for item in raw_requests:
        if not isinstance(item, dict):
            continue
        method = str(item.get("method", "")).upper().strip()
        url = str(item.get("url", "")).strip()
        path = str(item.get("path", "")).strip()
        if not path and url:
            path = urlparse(url).path
        if not method or not path or "/api/" not in path:
            continue
        parsed_requests.append(
            {
                "method": method,
                "url": url,
                "path": path,
            }
        )

    return parsed_requests


async def generate_test(
    filename: str | None,
    journey: str,
    max_retries: int = 5,
    *,
    variant_label: str = "original",
    mutation_id: str = "",
    fault_service: str = "",
    base_url: str | None = None,
    use_case_context: str = "",
    use_case: UseCaseMetadata | None = None,
    msa_spec_path: str | None = None,
    system_description_path: str | None = None,
    prompt_capture_path: str | None = None,
    output_dir: Path | None = None,
    history_dir: Path | None = None,
    generated_tests_dir: Path | None = None,
    runtime_results_dir: Path | None = None,
    aggregate_history_dir: Path | None = None,
) -> str:
    filename = filename or derive_python_test_filename(journey)
    validate_python_test_filename(filename)

    _output_dir = output_dir or Path("test-results")
    _history_dir = history_dir or Path("test-results")
    _generated_tests_dir = generated_tests_dir or GENERATED_TESTS_DIR
    _runtime_results_dir = runtime_results_dir or Path("runtime-results")

    evaluation = _build_evaluation_context(
        variant_label=variant_label,
        mutation_id=mutation_id,
        fault_service=fault_service,
        base_url=base_url,
        run_kind="generated",
    )
    deps = Deps(evaluation=evaluation)
    deps.max_retries = max(max_retries, 0)
    deps.output_dir = _output_dir
    deps.history_dir = _history_dir
    deps.generated_tests_dir = _generated_tests_dir
    deps.runtime_results_dir = _runtime_results_dir
    selected_msa_spec_path = Path(msa_spec_path) if msa_spec_path else MSA_SPEC_PATH
    resolved_msa_spec_path = str(selected_msa_spec_path.resolve())
    msa_spec = load_msa_spec(selected_msa_spec_path)
    system_description = load_system_description(
        Path(system_description_path) if system_description_path else None
    )
    run_started = datetime.now(timezone.utc)
    run_started_at = run_started.timestamp()
    prompt_capture_run_id = run_started.strftime("%Y%m%dT%H%M%S%fZ")
    browse_prompt = build_browse_prompt(
        journey=journey,
        msa_spec=msa_spec,
        base_url=evaluation.base_url,
        system_description=system_description,
        use_case_context=use_case_context,
        msa_spec_path=resolved_msa_spec_path,
    )

    journey_guide = None
    result = None
    capture_messages: Sequence[object] = ()
    test_generation_prompt = "Test generation phase was not reached."
    run_exception: BaseException | None = None

    try:
        async with agent:
            browse_start = datetime.now(timezone.utc).timestamp()
            try:
                nav = await agent.run(
                    browse_prompt,
                    deps=deps,
                    usage_limits=AGENT_USAGE_LIMITS,
                )
                capture_messages = nav.all_messages()
            except (UnexpectedModelBehavior, Exception) as e:
                if not isinstance(e, UnexpectedModelBehavior) and "exceeded max retries" not in str(e):
                    raise
                browse_elapsed = datetime.now(timezone.utc).timestamp() - browse_start
                deps.capture.record_timing("browse_total", browse_elapsed)
                print(f"\033[90mbrowse_total: {browse_elapsed:.1f}s\033[0m", flush=True)
                return f"Browse phase failed: {e}\n\nPartial actions logged:\n{deps.capture.action_summary()}"
            browse_elapsed = datetime.now(timezone.utc).timestamp() - browse_start
            deps.capture.record_timing("browse_total", browse_elapsed)
            print(f"\033[90mbrowse_total: {browse_elapsed:.1f}s\033[0m", flush=True)
            browse_network_requests = [
                {"method": c.method, "url": "", "path": c.path, "status_code": c.status_code}
                for c in deps.capture.api_calls
            ]
            journey_guide = build_journey_guide(
                test_filename=filename,
                requested_journey=journey,
                capture=deps.capture,
                msa_spec=msa_spec,
                use_case=use_case,
                browse_network_requests=browse_network_requests,
                msa_spec_path=resolved_msa_spec_path,
            )
            write_journey_guide(journey_guide, output_dir=_output_dir)

            if (
                journey_guide.contract is not None
                and journey_guide.contract.state_changing
                and not journey_guide.contract.complete
            ):
                reason = (
                    "Browse phase completed the UI journey, but the structured "
                    "journey contract is incomplete for a state-changing microservice "
                    "operation: "
                    + "; ".join(journey_guide.contract.completeness_issues)
                )
                if (
                    _incomplete_state_changing_contract_can_continue(
                        journey_guide.contract,
                        deps.capture.api_calls,
                        journey_succeeded=deps.journey_succeeded,
                    )
                ):
                    print(
                        "\033[33mWarning: "
                        f"{reason} Continuing to test generation because the browse "
                        "journey reported success and all required state-changing "
                        "service calls were observed. Treat contract.complete=False "
                        "as a contract-quality issue for this run.\033[0m",
                        flush=True,
                    )
                else:
                    print(f"\033[33mSkipping test generation - {reason}\033[0m", flush=True)
                    deps.browse_failure_reason = f"contract_incomplete: {reason}"
                    return "\n\n".join(
                        [
                            render_journey_guide_summary(journey_guide),
                            f"Browse contract incomplete: {reason}\n\nNo test was generated.",
                        ]
                    )

            if deps.journey_succeeded is False:
                reason = deps.journey_outcome_reason or "Browse phase did not complete the journey successfully."
                # Note: HTTP status codes are not a reliable proxy for application-level
                # success — many systems return 200 for business-logic failures (e.g. wrong
                # credentials, constraint violations). We cannot programmatically distinguish
                # "agent failed to interact with the UI" from "system under test misbehaved"
                # without an external network observer. Both cases abort test generation here.
                print(f"\033[33mSkipping test generation — browse phase failed: {reason}\033[0m", flush=True)
                deps.browse_failure_reason = f"journey_failed: {reason}"
                if deps.capture.api_calls:
                    call_summary = ", ".join(
                        f"{c.method} {c.path} → {c.status_code or '?'}"
                        for c in deps.capture.api_calls
                    )
                    print(f"\033[90mAPI calls recorded during failed browse: {call_summary}\033[0m", flush=True)
                return "\n\n".join([
                    render_journey_guide_summary(journey_guide),
                    f"Browse phase failed: {reason}\n\nNo test was generated.",
                ])

            # Advisory check: agent claimed success but logged no API calls.
            # For state-changing journeys this is suspicious (modal may not have been handled),
            # but it is valid for read-only journeys or systems that do not use REST HTTP.
            # Emit a visible warning so the operator can judge, but do not abort.
            if deps.journey_succeeded is True and not deps.capture.api_calls:
                print(
                    "\033[33mWarning: browse phase reported success but no backend API calls "
                    "were recorded via log_api_call. If this journey involves a state change "
                    "(create/update/delete), the operation may not have reached the server "
                    "(e.g. a confirmation modal was skipped). Review the generated test carefully.\033[0m",
                    flush=True,
                )

            test_generation_prompt = build_test_generation_prompt(
                journey=journey,
                filename=filename,
                max_retries=max_retries,
                msa_spec=msa_spec,
                capture=deps.capture,
                browse_network_requests=browse_network_requests,
                base_url=evaluation.base_url,
                journey_contract=journey_guide.contract,
                system_description=system_description,
                use_case_context=use_case_context,
                msa_spec_path=resolved_msa_spec_path,
            )
            message_history = nav.all_messages()
            capture_messages = message_history
            result = await agent.run(
                test_generation_prompt,
                message_history=message_history,
                deps=deps,
                usage_limits=AGENT_USAGE_LIMITS,
            )
            capture_messages = result.all_messages()

        return "\n\n".join(
            [
                render_journey_guide_summary(journey_guide),
                str(result.output),
            ]
        )
    except BaseException as exc:
        run_exception = exc
        raise
    finally:
        if prompt_capture_path:
            try:
                capture_dir = Path(prompt_capture_path)
                if capture_dir.suffix.lower() == ".txt":
                    capture_dir = capture_dir.parent / capture_dir.stem
                write_prompt_capture_entries(
                    output_dir=capture_dir,
                    filename=filename,
                    requested_journey=journey,
                    system_prompt=SYSTEM_PROMPT_TEXT,
                    browse_prompt=browse_prompt,
                    test_generation_prompt=test_generation_prompt,
                    all_messages=capture_messages,
                    run_id=prompt_capture_run_id,
                )
                if Path(prompt_capture_path).suffix.lower() == ".txt":
                    capture_output_path = resolve_prompt_capture_output_path(
                        prompt_capture_path,
                        filename,
                    )
                else:
                    capture_output_path = (
                        Path(prompt_capture_path)
                        / Path(filename).stem
                        / prompt_capture_run_id
                        / f"{Path(filename).stem}.prompts.txt"
                    )
                write_prompt_capture(
                    output_path=capture_output_path,
                    filename=filename,
                    requested_journey=journey,
                    system_prompt=SYSTEM_PROMPT_TEXT,
                    browse_prompt=browse_prompt,
                    test_generation_prompt=test_generation_prompt,
                    all_messages=capture_messages,
                )
            except Exception as capture_error:
                print(
                    f"\033[33mPrompt capture write failed: {capture_error}\033[0m",
                    flush=True,
                )

        history_appended = False
        try:
            final_report = load_execution_report(filename, output_dir=_output_dir)
            if (
                final_report is not None
                and final_report.report_path is not None
                and final_report.report_path.exists()
                and final_report.report_path.stat().st_mtime >= run_started_at
            ):
                append_evaluation_history(final_report, history_dir=_history_dir)
                if aggregate_history_dir and Path(aggregate_history_dir) != _history_dir:
                    append_evaluation_history(final_report, history_dir=Path(aggregate_history_dir))
                history_appended = True
        except Exception as append_error:
            print(
                f"\033[33mEvaluation history append failed: {append_error}\033[0m",
                flush=True,
            )

        if not history_appended and run_exception is None and deps.browse_failure_reason:
            browse_fail_report = ExecutionReport(
                filename=filename,
                status="browse_failed",
                exit_code=1,
                summary=f"Test '{filename}' not generated — browse phase did not complete.",
                details=deps.browse_failure_reason,
                requested_journey=journey,
                use_case=use_case,
                evaluation=evaluation,
                coverage=journey_guide.coverage.clone() if journey_guide is not None else None,
            )
            try:
                write_execution_report(browse_fail_report, output_dir=_output_dir)
                append_evaluation_history(browse_fail_report, history_dir=_history_dir)
                if aggregate_history_dir and Path(aggregate_history_dir) != _history_dir:
                    append_evaluation_history(browse_fail_report, history_dir=Path(aggregate_history_dir))
            except Exception as browse_fail_error:
                print(
                    f"\033[33mBrowse-failed history append failed: {browse_fail_error}\033[0m",
                    flush=True,
                )

        if not history_appended and run_exception is not None:
            exc_name = type(run_exception).__name__
            exc_message = str(run_exception).strip()
            detail_suffix = f": {exc_message}" if exc_message else ""
            if isinstance(run_exception, (KeyboardInterrupt, asyncio.CancelledError)):
                fallback_status = "failed"
                fallback_exit_code = 130 if isinstance(run_exception, KeyboardInterrupt) else 1
                fallback_summary = f"Test '{filename}' interrupted before evaluation history append."
                fallback_details = (
                    "Run was interrupted and no fresh execution report could be appended "
                    f"to evaluation history. Interruption: {exc_name}{detail_suffix}"
                )
            else:
                fallback_status = "error"
                fallback_exit_code = 1
                fallback_summary = f"Test '{filename}' aborted due to {exc_name}."
                fallback_details = (
                    f"An unhandled exception prevented test execution from completing. "
                    f"{exc_name}{detail_suffix}"
                )
            fallback_report = ExecutionReport(
                filename=filename,
                status=fallback_status,
                exit_code=fallback_exit_code,
                summary=fallback_summary,
                details=fallback_details,
                requested_journey=journey,
                use_case=use_case,
                evaluation=evaluation,
                coverage=journey_guide.coverage.clone() if journey_guide is not None else None,
            )
            try:
                write_execution_report(fallback_report, output_dir=_output_dir)
                append_evaluation_history(fallback_report, history_dir=_history_dir)
                if aggregate_history_dir and Path(aggregate_history_dir) != _history_dir:
                    append_evaluation_history(fallback_report, history_dir=Path(aggregate_history_dir))
            except Exception as fallback_error:
                print(
                    f"\033[33mFallback history append failed: {fallback_error}\033[0m",
                    flush=True,
                )


async def retest_generated_test(
    filename: str,
    *,
    variant_label: str = "original",
    mutation_id: str = "",
    fault_service: str = "",
    base_url: str | None = None,
    msa_spec_path: str | None = None,
    output_dir: Path | None = None,
    history_dir: Path | None = None,
    source_dir: Path | None = None,
    generated_tests_dir: Path | None = None,
    runtime_results_dir: Path | None = None,
    aggregate_history_dir: Path | None = None,
) -> str:
    _output_dir = output_dir or Path("test-results")
    _history_dir = history_dir or Path("test-results")
    _generated_tests_dir = generated_tests_dir or GENERATED_TESTS_DIR
    _runtime_results_dir = runtime_results_dir or Path("runtime-results")
    # Journey guide was written during generation; look in source_dir (default: test-results/).
    _source_dir = source_dir or Path("test-results")
    validate_python_test_filename(filename)
    evaluation = _build_evaluation_context(
        variant_label=variant_label,
        mutation_id=mutation_id,
        fault_service=fault_service,
        base_url=base_url,
        run_kind="retest",
    )
    journey_guide = load_journey_guide(filename, output_dir=_source_dir)
    result = run_generated_test(
        filename=filename,
        generated_tests_dir=_generated_tests_dir,
        base_url=evaluation.base_url,
        network_results_dir=_output_dir,
        runtime_results_dir=_runtime_results_dir,
    )
    report = build_execution_report(
        result,
        journey_guide=journey_guide,
        generated_tests_dir=_generated_tests_dir,
        test_results_dir=_output_dir,
        evaluation=evaluation,
        msa_spec_path=msa_spec_path,
    )
    write_execution_report(report, output_dir=_output_dir)
    append_evaluation_history(report, history_dir=_history_dir)
    if aggregate_history_dir and Path(aggregate_history_dir) != _history_dir:
        append_evaluation_history(report, history_dir=Path(aggregate_history_dir))

    parts: list[str] = []
    if journey_guide is not None:
        parts.append(render_journey_guide_summary(journey_guide))
    parts.append(render_execution_report(report))
    return "\n\n".join(parts)


async def run_browser_task(url: str, task: str) -> str:
    deps = Deps()
    async with agent:
        history = []
        if url != "about:blank":
            nav = await agent.run(f"Navigate to {url}", deps=deps)
            history = nav.all_messages()
        result = await agent.run(
            task,
            message_history=history,
            deps=deps,
            usage_limits=AGENT_USAGE_LIMITS,
        )

    return str(result.output)
