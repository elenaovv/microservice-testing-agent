from agent.agent import agent
from core.models import Deps
from prompts.generator import (
    build_browse_prompt,
    build_test_generation_prompt,
    load_msa_spec,
    validate_python_test_filename,
)
from pydantic_ai.usage import UsageLimits

AGENT_USAGE_LIMITS = UsageLimits(request_limit=200)


async def generate_test(
    filename: str,
    journey: str,
    max_retries: int = 5,
) -> str:
    validate_python_test_filename(filename)

    deps = Deps()
    msa_spec = load_msa_spec()

    async with agent:
        nav = await agent.run(
            build_browse_prompt(journey=journey, msa_spec=msa_spec),
            deps=deps,
            usage_limits=AGENT_USAGE_LIMITS,
        )

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

    return str(result.output)


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
