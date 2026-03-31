from datetime import datetime, timezone

from agent.agent import agent
from core.models import Deps
from core.reporting import (
    append_phase1_history,
    build_journey_guide,
    load_execution_report,
    render_journey_guide_summary,
    write_journey_guide,
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


async def generate_test(
    filename: str | None,
    journey: str,
    max_retries: int = 5,
) -> str:
    filename = filename or derive_python_test_filename(journey)
    validate_python_test_filename(filename)

    deps = Deps()
    msa_spec = load_msa_spec()
    run_started_at = datetime.now(timezone.utc).timestamp()

    async with agent:
        nav = await agent.run(
            build_browse_prompt(journey=journey, msa_spec=msa_spec),
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
        append_phase1_history(final_report)

    return "\n\n".join(
        [
            render_journey_guide_summary(journey_guide),
            str(result.output),
        ]
    )


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
