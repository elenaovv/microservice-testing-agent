from core.contracts.models import JourneyCapture, JourneyContract, SuccessAssertion, SuccessObservation
from prompts.generator import _render_replay_plan


def test_replay_plan_renders_baseline_separately_from_success():
    contract = JourneyContract(
        baseline_observations=[
            SuccessObservation(
                label="target before update",
                surface_type="web_page",
                observation_kind="record",
                assertion="baseline-visible",
                scope_locator='page.get_by_role("row", name=target_name)',
                assertions=[
                    SuccessAssertion(
                        field_name="status",
                        assertion="to_have_text",
                        locator='scope.locator("td").nth(2)',
                        expected_value_source="old_status",
                    )
                ],
            )
        ],
        success_observations=[
            SuccessObservation(
                label="target after update",
                surface_type="web_page",
                observation_kind="record",
                assertion="visible",
                scope_locator='page.get_by_role("row", name=target_name)',
                assertions=[
                    SuccessAssertion(
                        field_name="status",
                        assertion="to_have_text",
                        locator='scope.locator("td").nth(2)',
                        expected_value_source="new_status",
                    )
                ],
            )
        ],
    )

    rendered = _render_replay_plan(capture=JourneyCapture(), contract=contract)

    assert "Baseline observations for setup/original values:" in rendered
    assert "remember status" in rendered
    assert "Success observations:" in rendered
    assert "assert status" in rendered
