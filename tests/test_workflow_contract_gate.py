from core.models import ApiCall, JourneyContract, ServiceCallRequirement
from workflow.workflow import (
    _incomplete_state_changing_contract_can_continue,
    _missing_state_changing_trigger_locator,
    _required_contract_calls_observed,
)


def test_successful_browse_with_observed_required_call_can_continue_despite_missing_trigger_locator():
    contract = JourneyContract(
        expected_service_calls=[
            ServiceCallRequirement(
                method="PUT",
                path="/api/v1/entities",
                required=True,
                purpose="business_state_change",
            )
        ],
        state_changing=True,
        complete=False,
        completeness_issues=[
            "Missing validated executable locator for state-changing action Submit."
        ],
    )
    api_calls = [ApiCall("PUT", "/api/v1/entities", status_code=200)]

    assert _required_contract_calls_observed(contract, api_calls) is True
    assert _missing_state_changing_trigger_locator(contract) is True
    assert (
        _incomplete_state_changing_contract_can_continue(
            contract,
            api_calls,
            journey_succeeded=True,
        )
        is True
    )


def test_incomplete_contract_without_observed_required_call_must_not_continue():
    contract = JourneyContract(
        expected_service_calls=[
            ServiceCallRequirement(
                method="PUT",
                path="/api/v1/entities",
                required=True,
                purpose="business_state_change",
            )
        ],
        state_changing=True,
        complete=False,
        completeness_issues=[
            "Missing validated executable locator for state-changing action Submit."
        ],
    )

    assert (
        _incomplete_state_changing_contract_can_continue(
            contract,
            [ApiCall("GET", "/api/v1/entities", status_code=200)],
            journey_succeeded=True,
        )
        is False
    )


def test_incomplete_contract_with_stable_trigger_hint_can_continue_with_warning():
    contract = JourneyContract(
        expected_service_calls=[
            ServiceCallRequirement(
                method="PUT",
                path="/api/v1/entities",
                required=True,
                purpose="business_state_change",
                trigger_selector_hint="action=#active-modal [data-confirm]",
            )
        ],
        state_changing=True,
        complete=False,
        completeness_issues=[
            "Missing validated executable locator for state-changing action Submit."
        ],
    )
    api_calls = [ApiCall("PUT", "/api/v1/entities", status_code=200)]

    assert _required_contract_calls_observed(contract, api_calls) is True
    assert _missing_state_changing_trigger_locator(contract) is False


def test_incomplete_contract_without_missing_trigger_locator_can_continue_with_warning():
    contract = JourneyContract(
        expected_service_calls=[
            ServiceCallRequirement(
                method="PUT",
                path="/api/v1/entities",
                required=True,
                purpose="business_state_change",
            )
        ],
        state_changing=True,
        complete=False,
        completeness_issues=[
            "Missing validated executable locator for visible editable field Name."
        ],
    )
    api_calls = [ApiCall("PUT", "/api/v1/entities", status_code=200)]

    assert _required_contract_calls_observed(contract, api_calls) is True
    assert _missing_state_changing_trigger_locator(contract) is False
