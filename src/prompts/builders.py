from core.contracts.models import JourneyCapture, JourneyContract
from prompts.journey_rendering import (
    render_journey_contract_for_prompt,
    render_replay_plan,
)
from prompts.spec_context import build_execution_brief
from prompts.template_loader import render_template


def build_browse_prompt(
    journey: str,
    msa_spec: str,
    base_url: str,
    *,
    system_description: str = "",
    use_case_context: str = "",
    msa_spec_path: str = "",
) -> str:
    execution_brief = build_execution_brief(
        journey=journey,
        msa_spec=msa_spec,
        system_description=system_description,
        use_case_context=use_case_context,
    )
    return render_template(
        "browse_prompt.md",
        {
            "base_url": base_url,
            "execution_brief": execution_brief,
            "msa_spec_instruction": _browse_msa_spec_instruction(msa_spec_path),
        },
    )


def build_test_generation_prompt(
    journey: str,
    filename: str,
    max_retries: int,
    msa_spec: str,
    capture: JourneyCapture,
    browse_network_requests: list[dict[str, str]],
    base_url: str,
    msa_spec_path: str = "",
    journey_contract: JourneyContract | None = None,
    *,
    system_description: str = "",
    use_case_context: str = "",
) -> str:
    observed_requests = [
        f"{str(item.get('method', '')).upper():<5} {str(item.get('path', ''))}"
        for item in browse_network_requests
        if str(item.get("method", "")).strip() and str(item.get("path", "")).strip()
    ]
    observed_requests_block = (
        "\n".join(observed_requests)
        if observed_requests
        else "No backend API requests were captured during exploration."
    )
    execution_brief = build_execution_brief(
        journey=journey,
        msa_spec=msa_spec,
        system_description=system_description,
        use_case_context=use_case_context,
    )
    return render_template(
        "test_generation_prompt.md",
        {
            "base_url": base_url,
            "execution_brief": execution_brief,
            "replay_plan": render_replay_plan(capture, journey_contract),
            "timing_summary": capture.timing_summary(),
            "observed_requests_block": observed_requests_block,
            "journey_contract_block": render_journey_contract_for_prompt(journey_contract),
            "filename": filename,
            "max_retries": max_retries,
            "msa_spec_instruction": _generation_msa_spec_instruction(msa_spec_path),
        },
    )


def _browse_msa_spec_instruction(msa_spec_path: str) -> str:
    if not msa_spec_path:
        return ""
    return (
        f"Before filling any form that requires account credentials or test data, "
        f"you must call read_spec_file('{msa_spec_path}') first to retrieve the correct "
        f"inputs from the MSA specification. Do not attempt to guess or infer credentials "
        f"from the live UI. This applies to login forms, registration forms, payment fields, "
        f"or any other form requiring specific test data. "
        f"After calling read_spec_file, call log_action to record the credentials and entry "
        f"point URLs you found, so they are available during test generation."
    )


def _generation_msa_spec_instruction(msa_spec_path: str) -> str:
    if not msa_spec_path:
        return ""
    return (
        f"If you need credentials or any other specification details not already "
        f"present above, call read_spec_file('{msa_spec_path}')."
    )
