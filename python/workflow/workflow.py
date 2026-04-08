import os
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from agent.agent import agent
from core.evaluation_utils import append_evaluation_history
from core.executor import run_generated_test
from core.models import Deps, EvaluationContext
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
    build_browse_prompt,
    build_test_generation_prompt,
    derive_python_test_filename,
    load_msa_spec,
    load_system_description,
    validate_python_test_filename,
)
from pydantic_ai.usage import UsageLimits

AGENT_USAGE_LIMITS = UsageLimits(request_limit=200)
GENERATED_TESTS_DIR = Path("generated-tests")


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
    msa_spec_path: str | None = None,
    system_description_path: str | None = None,
) -> str:
    filename = filename or derive_python_test_filename(journey)
    validate_python_test_filename(filename)

    evaluation = _build_evaluation_context(
        variant_label=variant_label,
        mutation_id=mutation_id,
        fault_service=fault_service,
        base_url=base_url,
        run_kind="generated",
    )
    deps = Deps(evaluation=evaluation)
    msa_spec = load_msa_spec(Path(msa_spec_path) if msa_spec_path else None)
    system_description = load_system_description(
        Path(system_description_path) if system_description_path else None
    )
    run_started_at = datetime.now(timezone.utc).timestamp()

    async with agent:
        nav = await agent.run(
            build_browse_prompt(
                journey=journey,
                msa_spec=msa_spec,
                base_url=evaluation.base_url,
                system_description=system_description,
                use_case_context=use_case_context,
            ),
            deps=deps,
            usage_limits=AGENT_USAGE_LIMITS,
        )
        browse_network_requests = _parse_browse_network_requests(
            str(nav.output)
        )
        journey_guide = build_journey_guide(
            test_filename=filename,
            requested_journey=journey,
            capture=deps.capture,
            msa_spec=msa_spec,
            browse_network_requests=browse_network_requests,
            msa_spec_path=str(Path(msa_spec_path).resolve()) if msa_spec_path else "",
        )
        write_journey_guide(journey_guide)

        result = await agent.run(
            build_test_generation_prompt(
                journey=journey,
                filename=filename,
                max_retries=max_retries,
                msa_spec=msa_spec,
                capture=deps.capture,
                browse_network_requests=browse_network_requests,
                base_url=evaluation.base_url,
                system_description=system_description,
                use_case_context=use_case_context,
            ),
            message_history=nav.all_messages(),
            deps=deps,
            usage_limits=AGENT_USAGE_LIMITS,
        )

    final_report = load_execution_report(filename)
    if (
        final_report is not None
        and final_report.report_path is not None
        and final_report.report_path.exists()
        and final_report.report_path.stat().st_mtime >= run_started_at
    ):
        append_evaluation_history(final_report)

    return "\n\n".join(
        [
            render_journey_guide_summary(journey_guide),
            str(result.output),
        ]
    )


async def retest_generated_test(
    filename: str,
    *,
    variant_label: str = "original",
    mutation_id: str = "",
    fault_service: str = "",
    base_url: str | None = None,
    msa_spec_path: str | None = None,
) -> str:
    validate_python_test_filename(filename)
    evaluation = _build_evaluation_context(
        variant_label=variant_label,
        mutation_id=mutation_id,
        fault_service=fault_service,
        base_url=base_url,
        run_kind="retest",
    )
    journey_guide = load_journey_guide(filename)
    result = run_generated_test(
        filename=filename,
        generated_tests_dir=GENERATED_TESTS_DIR,
        base_url=evaluation.base_url,
    )
    report = build_execution_report(
        result,
        journey_guide=journey_guide,
        generated_tests_dir=GENERATED_TESTS_DIR,
        evaluation=evaluation,
        msa_spec_path=msa_spec_path,
    )
    write_execution_report(report)
    append_evaluation_history(report)

    parts: list[str] = []
    if journey_guide is not None:
        parts.append(render_journey_guide_summary(journey_guide))
    parts.append(render_execution_report(report))
    return "\n\n".join(parts)


async def run_browser_task(url: str, task: str) -> str:
    async with agent:
        history = []
        if url != "about:blank":
            nav = await agent.run(f"Navigate to {url}")
            history = nav.all_messages()
        result = await agent.run(
            task,
            message_history=history,
            usage_limits=AGENT_USAGE_LIMITS,
        )

    return str(result.output)
