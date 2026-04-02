import os
from datetime import datetime, timezone
from pathlib import Path

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


async def generate_test(
    filename: str | None,
    journey: str,
    max_retries: int = 5,
    *,
    variant_label: str = "original",
    mutation_id: str = "",
    fault_service: str = "",
    base_url: str | None = None,
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
    msa_spec = load_msa_spec()
    run_started_at = datetime.now(timezone.utc).timestamp()

    async with agent:
        nav = await agent.run(
            build_browse_prompt(
                journey=journey,
                msa_spec=msa_spec,
                base_url=evaluation.base_url,
            ),
            deps=deps,
            usage_limits=AGENT_USAGE_LIMITS,
        )
        journey_guide = build_journey_guide(
            test_filename=filename,
            requested_journey=journey,
            capture=deps.capture,
            msa_spec=msa_spec,
        )
        write_journey_guide(journey_guide)

        result = await agent.run(
            build_test_generation_prompt(
                journey=journey,
                filename=filename,
                max_retries=max_retries,
                msa_spec=msa_spec,
                capture=deps.capture,
                base_url=evaluation.base_url,
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
