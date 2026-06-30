from core.contracts.journey_contract import build_journey_contract
from core.contracts.models import (
    ApiCall,
    InteractionContract,
    JourneyCapture,
    LocatorCandidate,
    SuccessAssertion,
    SuccessObservation,
)


def test_contract_uses_real_interaction_contract_for_modal_submit_trigger():
    capture = JourneyCapture()
    capture.log_action(
        "inspect add modal",
        "Add User modal text='Add User'. Action controls visible: Cancel and Add.",
    )
    capture.log_action(
        "submit add user",
        "Clicked Add in the Add User modal. Backend call succeeded with "
        "POST /api/v1/adminuserservice/users returning 200.",
    )
    capture.api_calls.append(
        ApiCall("POST", "/api/v1/adminuserservice/users", status_code=200)
    )
    capture.interaction_contracts.append(
        InteractionContract.from_dict(
            {
                "surface_type": "web_ui",
                "container": {
                    "kind": "modal",
                    "selector": ".am-modal:visible",
                    "anchor_text": "Add User",
                },
                "fields": [
                    {
                        "semantic_name": "document_number",
                        "label": "Document Number",
                        "selector": "#add_user_document_num",
                        "tag": "input",
                        "input_type": "text",
                        "visible": True,
                        "editable": True,
                        "validated_locators": [
                            {
                                "strategy": "css",
                                "value": "#add_user_document_num",
                                "validated": True,
                                "executable": True,
                            }
                        ],
                    }
                ],
                "actions": [
                    {
                        "semantic_name": "submit_add_user",
                        "label": "Add",
                        "selector": ".am-modal:visible .am-modal-footer a:has-text('Add')",
                        "tag": "a",
                        "role": "",
                        "validated_locators": [
                            {
                                "strategy": "css",
                                "value": ".am-modal:visible .am-modal-footer a:has-text('Add')",
                                "validated": True,
                                "executable": True,
                            }
                        ],
                        "expected_service_calls": [
                            {
                                "method": "POST",
                                "path": "/api/v1/adminuserservice/users",
                                "status_code": 200,
                                "purpose": "business_state_change",
                            }
                        ],
                    }
                ],
            }
        )
    )

    contract = build_journey_contract(
        "Success criteria: the create action is submitted successfully; the new account appears.",
        capture,
    )

    assert contract.state_changing is True
    assert contract.complete is True
    assert contract.expected_service_calls[0].required is True
    assert contract.expected_service_calls[0].status_code == 200
    assert contract.expected_service_calls[0].purpose == "business_state_change"
    assert contract.expected_service_calls[0].trigger_action == "submit_add_user"
    assert (
        contract.expected_service_calls[0].trigger_selector_hint
        == "container=.am-modal:visible; action=css:.am-modal:visible .am-modal-footer a:has-text('Add')"
    )
    assert contract.interaction_contracts[0].surface_type == "web_modal"
    assert contract.interaction_contracts[0].fields[0].selector == "#add_user_document_num"


def test_state_changing_web_ui_contract_is_incomplete_without_real_interaction():
    capture = JourneyCapture()
    capture.log_action(
        "submit add user",
        "Clicked Add in the Add User modal. Backend call succeeded with "
        "POST /api/v1/adminuserservice/users returning 200.",
    )
    capture.api_calls.append(
        ApiCall("POST", "/api/v1/adminuserservice/users", status_code=200)
    )

    contract = build_journey_contract(
        "Success criteria: the create action is submitted successfully.",
        capture,
    )

    assert contract.state_changing is True
    assert contract.complete is False
    assert (
        "Missing structured interaction contract for state-changing web UI operation."
        in contract.completeness_issues
    )


def test_declared_business_effect_requires_observed_successful_api_call():
    capture = JourneyCapture()
    capture.log_action("submit add user", "Attempted Add but only a users GET refresh was observed.")
    capture.api_calls.append(ApiCall("GET", "/api/v1/adminuserservice/users", status_code=200))
    capture.interaction_contracts.append(
        InteractionContract.from_dict(
            {
                "surface_type": "page_form",
                "container": {"selector": "form#add-user"},
                "actions": [
                    {
                        "semantic_name": "submit_add_user",
                        "selector": "form#add-user a:has-text('Add')",
                        "expected_service_calls": [
                            {
                                "method": "POST",
                                "path": "/api/v1/adminuserservice/users",
                                "purpose": "business_state_change",
                            }
                        ],
                    }
                ],
            }
        )
    )

    contract = build_journey_contract(
        "Success criteria: the create action is submitted successfully.",
        capture,
    )

    assert contract.interaction_contracts[0].surface_type == "web_page"
    assert contract.interaction_contracts[0].container.kind == "page_form"
    assert contract.state_changing is True
    assert contract.complete is False
    assert (
        "Required service call POST /api/v1/adminuserservice/users was declared but not observed with a successful response."
        in contract.completeness_issues
    )


def test_login_post_is_auth_precondition_not_business_side_effect():
    capture = JourneyCapture()
    capture.api_calls.append(ApiCall("POST", "/api/v1/users/login", status_code=200))
    capture.api_calls.append(
        ApiCall("POST", "/api/v1/adminuserservice/users", status_code=200)
    )
    capture.interaction_contracts.append(
        InteractionContract.from_dict(
            {
                "surface_type": "web_ui",
                "container": {"kind": "page_form", "selector": "form#add-user"},
                "actions": [
                    {
                        "semantic_name": "submit_add_user",
                        "selector": "form#add-user button[type=submit]",
                        "expected_service_calls": [
                            {
                                "method": "POST",
                                "path": "/api/v1/adminuserservice/users",
                                "purpose": "business_state_change",
                            }
                        ],
                    }
                ],
            }
        )
    )

    contract = build_journey_contract(
        "Admin use case UC-ADM-001: Add User. Preconditions: authenticated as ROLE_ADMIN.",
        capture,
    )

    login_call = next(
        call for call in contract.expected_service_calls if call.path.endswith("/login")
    )
    create_call = next(
        call
        for call in contract.expected_service_calls
        if call.path.endswith("/adminuserservice/users")
    )
    assert login_call.required is False
    assert login_call.purpose == "auth_precondition"
    assert create_call.required is True


def test_contract_allows_read_only_microservice_journey_without_auth_or_mutation():
    capture = JourneyCapture()
    capture.log_action("open catalog", "Opened catalog page for a read-only product list.")
    capture.log_action("verify items", "Verified multiple products are visible.")
    capture.api_calls.append(ApiCall("GET", "/api/v1/catalog/products", status_code=200))

    contract = build_journey_contract(
        "Success criteria: products are visible.",
        capture,
    )

    assert contract.state_changing is False
    assert contract.complete is True
    assert contract.service_interfaces == ["rest"]
    assert contract.expected_service_calls[0].required is False


def test_contract_allows_no_login_create_flow_with_generic_web_page_surface():
    capture = JourneyCapture()
    capture.log_action("open checkout", "Opened checkout page without authentication.")
    capture.log_action(
        "submit order",
        "Submitted checkout and observed POST /api/orders 201.",
    )
    capture.api_calls.append(ApiCall("POST", "/api/orders", status_code=201))
    capture.interaction_contracts.append(
        InteractionContract.from_dict(
            {
                "surface_type": "web_page",
                "container": {"kind": "page_form", "selector": "form#checkout"},
                "fields": [
                    {
                        "label": "Email",
                        "selector": "input[name='email']",
                        "input_type": "email",
                        "validated_locators": [
                            {
                                "strategy": "css",
                                "value": "input[name='email']",
                                "validated": True,
                                "executable": True,
                            }
                        ],
                    }
                ],
                "actions": [
                    {
                        "semantic_name": "submit_order",
                        "selector": "form#checkout button[type=submit]",
                        "validated_locators": [
                            {
                                "strategy": "css",
                                "value": "form#checkout button[type=submit]",
                                "validated": True,
                                "executable": True,
                            }
                        ],
                        "side_effects": [
                            {
                                "method": "POST",
                                "path": "/api/orders",
                                "status_code": 201,
                                "purpose": "business_state_change",
                            }
                        ],
                    }
                ],
            }
        )
    )

    contract = build_journey_contract(
        "Guest checkout. Success criteria: the order is created.",
        capture,
    )

    assert contract.state_changing is True
    assert contract.complete is True
    assert contract.interaction_contracts[0].surface_type == "web_page"
    assert contract.expected_service_calls[0].trigger_action == "submit_order"


def test_contract_allows_api_only_service_interaction_surface():
    capture = JourneyCapture()
    capture.log_action("call API", "Called inventory reserve API directly.")
    capture.api_calls.append(ApiCall("POST", "/api/inventory/reservations", status_code=200))
    capture.interaction_contracts.append(
        InteractionContract.from_dict(
            {
                "surface_type": "rest_endpoint",
                "container": {
                    "kind": "rest_endpoint",
                    "selector": "POST /api/inventory/reservations",
                },
                "actions": [
                    {
                        "semantic_name": "reserve_inventory",
                        "side_effects": [
                            {
                                "method": "POST",
                                "path": "/api/inventory/reservations",
                                "status_code": 200,
                                "purpose": "business_state_change",
                            }
                        ],
                    }
                ],
            }
        )
    )

    contract = build_journey_contract(
        "Reserve inventory. Success criteria: reservation is accepted.",
        capture,
        interaction_surface="rest_endpoint",
    )

    assert contract.state_changing is True
    assert contract.complete is True
    assert contract.interaction_contracts[0].surface_type == "rest_endpoint"


def test_success_observation_survives_capture_contract_round_trip():
    capture = JourneyCapture()
    capture.success_observations.append(
        SuccessObservation(
            label="created entity appears",
            surface_type="web_page",
            observation_kind="record",
            assertion="visible",
            scope_locator='page.get_by_role("row", name=entity_name)',
            scope_validated_locators=[
                LocatorCandidate(
                    strategy="playwright",
                    value='page.get_by_role("row", name=entity_name)',
                    validated=True,
                    executable=True,
                    note="verified record scope",
                )
            ],
            target_value_source="generated_runtime_value",
            validated_locators=[
                LocatorCandidate(
                    strategy="playwright",
                    value='page.get_by_role("cell", name=entity_name, exact=True)',
                    validated=True,
                    executable=True,
                    note="verified after refreshed list",
                )
            ],
            assertions=[
                SuccessAssertion(
                    field_name="name",
                    assertion="to_have_text",
                    locator='scope.locator("td").nth(0)',
                    expected_value_source="entity_name",
                    validated_locators=[
                        LocatorCandidate(
                            strategy="playwright",
                            value='scope.locator("td").nth(0)',
                            scope='page.get_by_role("row", name=entity_name)',
                            validated=True,
                            executable=True,
                        )
                    ],
                )
            ],
            refresh_strategy={"type": "navigate", "url": "/entities"},
        )
    )

    contract = build_journey_contract(
        "Create entity. Success criteria: the new entity appears.",
        capture,
    )
    restored = JourneyCapture.from_dict(capture.to_dict())
    restored_contract = type(contract).from_dict(contract.to_dict())

    assert restored.success_observations[0].label == "created entity appears"
    assert contract.success_observations[0].validated_locators[0].validated is True
    assert contract.success_observations[0].observation_kind == "record"
    assert contract.success_observations[0].scope_validated_locators[0].validated is True
    assert (
        restored_contract.success_observations[0].validated_locators[0].value
        == 'page.get_by_role("cell", name=entity_name, exact=True)'
    )
    assert (
        restored_contract.success_observations[0].assertions[0].locator
        == 'scope.locator("td").nth(0)'
    )
    assert restored_contract.success_observations[0].refresh_strategy["url"] == "/entities"


def test_baseline_observation_is_separate_from_success_observation():
    capture = JourneyCapture()
    capture.baseline_observations.append(
        SuccessObservation(
            label="target record before update",
            surface_type="web_page",
            observation_kind="record",
            assertion="baseline-visible",
            scope_locator='page.get_by_role("row", name=target_name)',
            assertions=[
                SuccessAssertion(
                    field_name="original_status",
                    assertion="to_have_text",
                    locator='scope.locator("td").nth(2)',
                    expected_value_source="original_status",
                )
            ],
            reason="Capture original values that must be preserved after update.",
        )
    )

    contract = build_journey_contract(
        "Update entity. Success criteria: the changed status appears after submit.",
        capture,
    )
    restored_capture = JourneyCapture.from_dict(capture.to_dict())
    restored_contract = type(contract).from_dict(contract.to_dict())

    assert len(contract.baseline_observations) == 1
    assert contract.baseline_observations[0].label == "target record before update"
    assert contract.success_observations == []
    assert restored_capture.baseline_observations[0].assertions[0].field_name == "original_status"
    assert restored_contract.baseline_observations[0].assertions[0].locator == 'scope.locator("td").nth(2)'


def test_contract_prefers_modal_submit_over_page_opener_for_same_service_call():
    capture = JourneyCapture()
    capture.log_action("open add user form", "Clicked page Add to open Add User modal.")
    capture.log_action(
        "submit add user",
        "Clicked modal confirm Add and observed POST /api/v1/adminuserservice/users 200.",
    )
    capture.api_calls.append(
        ApiCall("POST", "/api/v1/adminuserservice/users", status_code=200)
    )
    capture.interaction_contracts.extend(
        [
            InteractionContract.from_dict(
                {
                    "surface_type": "web_page",
                    "container": {"kind": "page_form", "selector": "admin_user.html"},
                    "actions": [
                        {
                            "semantic_name": "open_add_user",
                            "text": "Add",
                            "selector": "button:has-text('Add')",
                            "opens_surface": "web_modal:Add User",
                            # Legacy bad capture: this should lose to the modal action.
                            "expected_service_calls": [
                                {
                                    "method": "POST",
                                    "path": "/api/v1/adminuserservice/users",
                                    "purpose": "business_state_change",
                                }
                            ],
                        }
                    ],
                }
            ),
            InteractionContract.from_dict(
                {
                    "surface_type": "web_modal",
                    "container": {
                        "kind": "modal",
                        "selector": "div.am-modal-dialog:has-text('Add User')",
                        "anchor_text": "Add User",
                    },
                    "actions": [
                        {
                            "semantic_name": "submit_add_user",
                            "text": "Add",
                            "selector": "[data-am-modal-confirm]",
                            "side_effects": [
                                {
                                    "method": "POST",
                                    "path": "/api/v1/adminuserservice/users",
                                    "status_code": 200,
                                    "purpose": "business_state_change",
                                }
                            ],
                        }
                    ],
                }
            ),
        ]
    )

    contract = build_journey_contract(
        "Success criteria: the create action is submitted successfully.",
        capture,
    )

    call = contract.expected_service_calls[0]
    assert call.required is True
    assert call.trigger_action == "submit_add_user"
    assert (
        call.trigger_selector_hint
        == "container=div.am-modal-dialog:has-text('Add User'); action=[data-am-modal-confirm]"
    )


def test_snapshot_selectors_are_preserved_as_non_executable_candidates_only():
    interaction = InteractionContract.from_dict(
        {
            "surface_type": "web_modal",
            "container": {"kind": "modal", "anchor_text": "Add User"},
            "fields": [
                {
                    "label": "Name",
                    "selector": "textbox[aria-label='Name:']",
                    "role": "textbox",
                    "visible": True,
                    "editable": True,
                }
            ],
            "actions": [
                {
                    "text": "Add",
                    "selector": "button/text=Add",
                    "tag": "generic/button",
                }
            ],
        }
    )

    assert interaction.fields[0].selector == ""
    assert interaction.fields[0].validated_locators[0].strategy == "snapshot"
    assert interaction.fields[0].validated_locators[0].executable is False
    assert interaction.actions[0].selector == ""
    assert interaction.actions[0].validated_locators[0].strategy == "snapshot"
    assert interaction.actions[0].validated_locators[0].executable is False


def test_state_changing_web_modal_requires_validated_replay_locators():
    capture = JourneyCapture()
    capture.api_calls.append(
        ApiCall("POST", "/api/v1/entities", status_code=200)
    )
    capture.interaction_contracts.append(
        InteractionContract.from_dict(
            {
                "surface_type": "web_modal",
                "container": {
                    "kind": "modal",
                    "selector": ".modal, .overlay",
                    "anchor_text": "Create Entity",
                },
                "fields": [
                    {
                        "label": "Name",
                        "selector": "input[placeholder='Name']",
                        "tag": "input",
                        "visible": True,
                        "editable": True,
                    }
                ],
                "actions": [
                    {
                        "semantic_name": "submit_entity",
                        "text": "Submit",
                        "selector": "button:has-text('Submit')",
                        "tag": "div",
                        "role": "button",
                        "expected_service_calls": [
                            {
                                "method": "POST",
                                "path": "/api/v1/entities",
                                "status_code": 200,
                                "purpose": "business_state_change",
                            }
                        ],
                    }
                ],
            }
        )
    )

    contract = build_journey_contract(
        "Create entity. Success criteria: the new entity appears.",
        capture,
    )

    assert contract.complete is False
    assert any(
        "Missing validated executable locator for visible editable field Name"
        in issue
        for issue in contract.completeness_issues
    )
    assert any(
        "Missing validated executable locator for state-changing action submit_entity"
        in issue
        for issue in contract.completeness_issues
    )
    assert any(
        "Selector/tag mismatch for action submit_entity"
        in issue
        for issue in contract.completeness_issues
    )
    assert (
        contract.expected_service_calls[0].trigger_selector_hint
        == "container=.modal, .overlay; action=role:button|Submit"
    )


def test_later_contract_for_same_surface_supersedes_incomplete_locator_sketch():
    capture = JourneyCapture()
    capture.api_calls.append(ApiCall("POST", "/api/v1/entities", status_code=200))
    capture.interaction_contracts.append(
        InteractionContract.from_dict(
            {
                "surface_type": "web_modal",
                "container": {
                    "kind": "modal",
                    "selector": "generic",
                    "anchor_text": "Create Entity",
                },
                "fields": [
                    {
                        "label": "Name",
                        "selector": "input[aria-label='Name']",
                        "tag": "input",
                        "visible": True,
                        "editable": True,
                    }
                ],
                "actions": [
                    {
                        "semantic_name": "submit_entity",
                        "text": "Submit",
                        "selector": "button",
                        "tag": "button",
                        "expected_service_calls": [
                            {
                                "method": "POST",
                                "path": "/api/v1/entities",
                                "status_code": 200,
                                "purpose": "business_state_change",
                            }
                        ],
                    }
                ],
            }
        )
    )
    capture.interaction_contracts.append(
        InteractionContract.from_dict(
            {
                "surface_type": "web_modal",
                "container": {
                    "kind": "modal",
                    "selector": "#create_entity_modal",
                    "anchor_text": "Create Entity",
                },
                "fields": [
                    {
                        "label": "Name",
                        "selector": "#entity_name",
                        "tag": "input",
                        "visible": True,
                        "editable": True,
                        "validated_locators": [
                            {
                                "strategy": "css",
                                "value": "#entity_name",
                                "validated": True,
                                "executable": True,
                            }
                        ],
                    }
                ],
                "actions": [
                    {
                        "semantic_name": "submit_entity",
                        "text": "Submit",
                        "selector": "#create_entity_modal [data-confirm]",
                        "tag": "button",
                        "validated_locators": [
                            {
                                "strategy": "css",
                                "value": "#create_entity_modal [data-confirm]",
                                "validated": True,
                                "executable": True,
                            }
                        ],
                        "expected_service_calls": [
                            {
                                "method": "POST",
                                "path": "/api/v1/entities",
                                "status_code": 200,
                                "purpose": "business_state_change",
                            }
                        ],
                    }
                ],
            }
        )
    )

    contract = build_journey_contract(
        "Create entity. Success criteria: the create action is submitted successfully.",
        capture,
    )

    assert contract.complete is True
    assert len(contract.interaction_contracts) == 1
    assert contract.interaction_contracts[0].container.selector == "#create_entity_modal"
    assert contract.interaction_contracts[0].fields[0].selector == "#entity_name"
    assert (
        contract.expected_service_calls[0].trigger_selector_hint
        == "container=#create_entity_modal; action=css:#create_entity_modal [data-confirm]"
    )


def test_recent_action_note_promotes_stable_modal_trigger_hint():
    capture = JourneyCapture()
    capture.log_action(
        "modal scope resolution",
        "Update modal submit is a span with data-am-modal-confirm inside #update-entity-modal.",
    )
    capture.log_action("submit update", "Clicked scoped Submit control in the modal.")
    capture.api_calls.append(ApiCall("PUT", "/api/v1/entities", status_code=200))
    capture.interaction_contracts.append(
        InteractionContract.from_dict(
            {
                "surface_type": "web_modal",
                "container": {
                    "kind": "modal",
                    "selector": "div:has-text('Update Entity')",
                    "anchor_text": "Update Entity",
                },
                "actions": [
                    {
                        "semantic_name": "submit_entity",
                        "text": "Submit",
                        "selector": "div:has-text('Update Entity') button:has-text('Submit')",
                        "tag": "button",
                        "expected_service_calls": [
                            {
                                "method": "PUT",
                                "path": "/api/v1/entities",
                                "status_code": 200,
                                "purpose": "business_state_change",
                            }
                        ],
                    }
                ],
            }
        )
    )

    contract = build_journey_contract(
        "Update entity. Success criteria: the update action is submitted successfully.",
        capture,
    )

    assert (
        contract.expected_service_calls[0].trigger_selector_hint
        == "action=#update-entity-modal [data-am-modal-confirm]"
    )
    assert contract.complete is False


def test_unknown_container_kind_maps_to_generic_web_surface_without_taxonomy_edit():
    interaction = InteractionContract.from_dict(
        {
            "surface_type": "web_ui",
            "container": {
                "kind": "toast_notification",
                "anchor_text": "Saved",
            },
        }
    )

    assert interaction.surface_type == "web_toast_notification"
    assert interaction.container.kind == "toast_notification"
