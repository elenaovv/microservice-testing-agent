from pathlib import Path

from core.evaluation_utils import build_phase1_metrics
from core.models import (
    ExecutionResult,
    InteractionContract,
    JourneyContract,
    ServiceCallRequirement,
)


def test_missing_required_service_call_classifies_side_effect_failure(tmp_path: Path):
    generated_dir = tmp_path / "generated-tests"
    results_dir = tmp_path / "test-results"
    generated_dir.mkdir()
    results_dir.mkdir()
    (generated_dir / "add_test.py").write_text(
        "def test_example(page):\n"
        "    page.goto('http://example.test')\n",
        encoding="utf-8",
    )
    (results_dir / "add_test.network.json").write_text(
        """
        {
          "filename": "add_test.py",
          "requests": [
            {"method": "GET", "path": "/api/v1/adminuserservice/users"}
          ]
        }
        """,
        encoding="utf-8",
    )
    contract = JourneyContract(
        expected_service_calls=[
            ServiceCallRequirement(
                method="POST",
                path="/api/v1/adminuserservice/users",
                required=True,
                trigger_action="submit add user",
                trigger_selector_hint="scope text=Add User; action text=Add",
            )
        ],
        state_changing=True,
    )

    metrics = build_phase1_metrics(
        result=ExecutionResult(
            filename="add_test.py",
            exit_code=1,
            stdout="Timeout",
        ),
        generated_tests_dir=generated_dir,
        test_results_dir=results_dir,
        journey_contract=contract,
    )

    assert metrics.failure_kind == "missing-expected-side-effect"
    assert metrics.failure_diagnosis is not None
    assert metrics.failure_diagnosis.kind == "missing-expected-side-effect"
    assert metrics.missing_expected_service_calls == [
            {
                "method": "POST",
                "path": "/api/v1/adminuserservice/users",
                "interface": "rest",
                "purpose": "",
                "trigger_action": "submit add user",
                "trigger_selector_hint": "scope text=Add User; action text=Add",
            }
    ]


def test_locator_failure_before_trigger_does_not_mask_as_missing_side_effect(tmp_path: Path):
    generated_dir = tmp_path / "generated-tests"
    results_dir = tmp_path / "test-results"
    generated_dir.mkdir()
    results_dir.mkdir()
    (generated_dir / "add_test.py").write_text(
        "def test_example(page):\n"
        "    page.goto('http://example.test')\n"
        "    add_button = page.locator('button').first\n"
        "    add_button.click()\n"
        "    with page.expect_response(lambda resp: '/api/v1/adminuserservice/users' in resp.url):\n"
        "        page.locator('[data-am-modal-confirm]').click()\n",
        encoding="utf-8",
    )
    (results_dir / "add_test.network.json").write_text(
        '{"filename":"add_test.py","requests":[]}',
        encoding="utf-8",
    )
    contract = JourneyContract(
        expected_service_calls=[
            ServiceCallRequirement(
                method="POST",
                path="/api/v1/adminuserservice/users",
                required=True,
                trigger_action="submit_add_user",
                trigger_selector_hint="container=Add User; action=[data-am-modal-confirm]",
            )
        ],
        state_changing=True,
    )

    metrics = build_phase1_metrics(
        result=ExecutionResult(
            filename="add_test.py",
            exit_code=1,
            stdout=(
                "generated-tests\\add_test.py:4: in test_example\n"
                "E   AssertionError: Locator expected to be visible\n"
                "E   Actual value: hidden\n"
                "E   Call log:\n"
                "E     - waiting for locator(\"button\").first\n"
            ),
        ),
        generated_tests_dir=generated_dir,
        test_results_dir=results_dir,
        journey_contract=contract,
    )

    assert metrics.failure_kind == "assertion-failure"
    assert metrics.failure_diagnosis is not None
    assert metrics.failure_diagnosis.kind == "hidden-element"
    assert metrics.failure_diagnosis.blocked_before_required_call is True
    assert metrics.failure_diagnosis.failing_line == 4
    assert metrics.missing_expected_service_calls


def test_trigger_click_timeout_is_not_masked_as_missing_side_effect(tmp_path: Path):
    generated_dir = tmp_path / "generated-tests"
    results_dir = tmp_path / "test-results"
    generated_dir.mkdir()
    results_dir.mkdir()
    (generated_dir / "add_test.py").write_text(
        "def test_example(page):\n"
        "    with page.expect_response(lambda resp: '/api/v1/entities' in resp.url):\n"
        "        modal.get_by_role('button', name='Submit').click()\n",
        encoding="utf-8",
    )
    (results_dir / "add_test.network.json").write_text(
        '{"filename":"add_test.py","requests":[]}',
        encoding="utf-8",
    )
    contract = JourneyContract(
        expected_service_calls=[
            ServiceCallRequirement(
                method="POST",
                path="/api/v1/entities",
                required=True,
                trigger_action="Submit",
                trigger_selector_hint="container=.modal; action=role:button|Submit",
            )
        ],
        state_changing=True,
    )

    metrics = build_phase1_metrics(
        result=ExecutionResult(
            filename="add_test.py",
            exit_code=1,
            stdout=(
                "generated-tests\\add_test.py:3: in test_example\n"
                "E   playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.\n"
                "E   Call log:\n"
                "E     - waiting for modal.get_by_role(\"button\", name=\"Submit\")\n"
            ),
        ),
        generated_tests_dir=generated_dir,
        test_results_dir=results_dir,
        journey_contract=contract,
    )

    assert metrics.failure_kind != "missing-expected-side-effect"
    assert metrics.failure_diagnosis is not None
    assert metrics.failure_diagnosis.kind == "action-timeout"
    assert metrics.failure_diagnosis.blocked_before_required_call is True
    assert "exact validated control" in metrics.failure_diagnosis.suggested_repair_strategy


def test_strict_mode_failure_is_diagnosed(tmp_path: Path):
    generated_dir = tmp_path / "generated-tests"
    results_dir = tmp_path / "test-results"
    generated_dir.mkdir()
    results_dir.mkdir()
    (generated_dir / "add_test.py").write_text(
        "def test_example(page):\n"
        "    page.locator('text=Add').click()\n",
        encoding="utf-8",
    )
    (results_dir / "add_test.network.json").write_text(
        '{"filename":"add_test.py","requests":[]}',
        encoding="utf-8",
    )

    metrics = build_phase1_metrics(
        result=ExecutionResult(
            filename="add_test.py",
            exit_code=1,
            stdout=(
                "generated-tests/add_test.py:2: in test_example\n"
                "E   Error: strict mode violation: locator('text=Add') resolved to 3 elements\n"
            ),
        ),
        generated_tests_dir=generated_dir,
        test_results_dir=results_dir,
    )

    assert metrics.failure_diagnosis is not None
    assert metrics.failure_diagnosis.kind == "strict-mode-ambiguity"
    assert "locator('text=Add')" in metrics.failure_diagnosis.failing_locator


def test_strict_mode_aka_suggestions_become_repair_candidates(tmp_path: Path):
    generated_dir = tmp_path / "generated-tests"
    results_dir = tmp_path / "test-results"
    generated_dir.mkdir()
    results_dir.mkdir()
    (generated_dir / "create_test.py").write_text(
        "def test_example(page):\n"
        "    expect(page.get_by_text(re.compile(entity_name))).to_be_visible()\n",
        encoding="utf-8",
    )
    (results_dir / "create_test.network.json").write_text(
        '{"filename":"create_test.py","requests":[]}',
        encoding="utf-8",
    )

    metrics = build_phase1_metrics(
        result=ExecutionResult(
            filename="create_test.py",
            exit_code=1,
            stdout=(
                "generated-tests/create_test.py:2: in test_example\n"
                "E   Error: strict mode violation: get_by_text(re.compile(r\"abc\")) resolved to 2 elements:\n"
                "E       1) <td>abc</td> aka get_by_role(\"cell\", name=\"abc\", exact=True)\n"
                "E       2) <td>abc@example.com</td> aka get_by_role(\"cell\", name=\"abc@example.\")\n"
                "E   Call log:\n"
                "E     - waiting for get_by_text(re.compile(r\"abc\"))\n"
            ),
        ),
        generated_tests_dir=generated_dir,
        test_results_dir=results_dir,
    )

    assert metrics.failure_diagnosis is not None
    assert metrics.failure_diagnosis.kind == "strict-mode-ambiguity"
    assert [
        candidate.value for candidate in metrics.failure_diagnosis.repair_candidates
    ] == [
        'get_by_role("cell", name="abc", exact=True)',
        'get_by_role("cell", name="abc@example.")',
    ]


def test_repair_candidates_prefer_semantic_surface_alignment(tmp_path: Path):
    generated_dir = tmp_path / "generated-tests"
    results_dir = tmp_path / "test-results"
    generated_dir.mkdir()
    results_dir.mkdir()
    (generated_dir / "add_station_test.py").write_text(
        "def test_example(page):\n"
        "    expect(page.locator(\"input[placeholder='Station Name']\")).to_be_visible()\n"
        "    with page.expect_response(lambda resp: '/api/v1/stations' in resp.url):\n"
        "        page.locator('text=Submit').click()\n",
        encoding="utf-8",
    )
    (results_dir / "add_station_test.network.json").write_text(
        '{"filename":"add_station_test.py","requests":[]}',
        encoding="utf-8",
    )
    contract = JourneyContract(
        expected_service_calls=[
            ServiceCallRequirement(
                method="POST",
                path="/api/v1/stations",
                required=True,
                trigger_action="Submit",
                trigger_selector_hint="container=.modal; action text=Submit",
            )
        ],
        state_changing=True,
    )
    contract.interaction_contracts = [
        InteractionContract.from_dict(
            {
                "surface_type": "web_modal",
                "container": {"kind": "modal", "anchor_text": "Add Station"},
                "actions": [
                    {
                        "text": "Submit",
                        "side_effects": [
                            {
                                "method": "POST",
                                "path": "/api/v1/stations",
                                "purpose": "business_state_change",
                            }
                        ],
                    }
                ],
            }
        )
    ]

    metrics = build_phase1_metrics(
        result=ExecutionResult(
            filename="add_station_test.py",
            exit_code=1,
            stdout=(
                "generated-tests/add_station_test.py:2: in test_example\n"
                "E   Error: strict mode violation: locator(\"input[placeholder='Station Name']\") resolved to 2 elements:\n"
                "E       1) <input id=\"update-station-name\"/> aka locator(\"#update-station-name\")\n"
                "E       2) <input id=\"add-station-name\"/> aka locator(\"#add-station-name\")\n"
                "E   Call log:\n"
                "E     - waiting for locator(\"input[placeholder='Station Name']\")\n"
            ),
        ),
        generated_tests_dir=generated_dir,
        test_results_dir=results_dir,
        journey_contract=contract,
    )

    assert metrics.failure_diagnosis is not None
    assert metrics.failure_diagnosis.repair_candidates[0].value == 'locator("#add-station-name")'


def test_duplicate_cell_strict_mode_suggests_structural_scoped_assertion(tmp_path: Path):
    generated_dir = tmp_path / "generated-tests"
    results_dir = tmp_path / "test-results"
    generated_dir.mkdir()
    results_dir.mkdir()
    (generated_dir / "update_test.py").write_text(
        "def test_example(page):\n"
        "    row.get_by_role('cell', name=value)\n",
        encoding="utf-8",
    )
    (results_dir / "update_test.network.json").write_text(
        '{"filename":"update_test.py","requests":[]}',
        encoding="utf-8",
    )

    metrics = build_phase1_metrics(
        result=ExecutionResult(
            filename="update_test.py",
            exit_code=1,
            stdout=(
                "generated-tests/update_test.py:2: in test_example\n"
                "E   Error: strict mode violation: get_by_role(\"row\", name=re.compile(r\"A 7 7 8\")).get_by_role(\"cell\", name=\"7\") resolved to 2 elements:\n"
                "E       1) <td>7</td> aka get_by_role(\"cell\", name=\"7\").first\n"
                "E       2) <td>7</td> aka get_by_role(\"cell\", name=\"7\").nth(1)\n"
                "E   Call log:\n"
                "E     - waiting for get_by_role(\"row\", name=re.compile(r\"A 7 7 8\")).get_by_role(\"cell\", name=\"7\")\n"
            ),
        ),
        generated_tests_dir=generated_dir,
        test_results_dir=results_dir,
    )

    assert metrics.failure_diagnosis is not None
    assert metrics.failure_diagnosis.kind == "strict-mode-ambiguity"
    assert "assert fields structurally" in metrics.failure_diagnosis.suggested_repair_strategy
