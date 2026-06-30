"""Rendering helpers for execution reports and journey guides."""

from core.contracts.models import ExecutionReport, JourneyGuide

# ---------------------------------------------------------------------------
# Execution report rendering
# ---------------------------------------------------------------------------

def render_execution_report(report: ExecutionReport) -> str:
    lines = [
        "Execution report:",
        f"- file: {report.filename}",
        f"- status: {report.status}",
        f"- exit_code: {report.exit_code}",
        f"- summary: {report.summary}",
    ]

    if report.artifacts:
        artifact_summary = ", ".join(
            f"{artifact.kind}={artifact.path}" for artifact in report.artifacts
        )
        lines.append(f"- artifacts: {artifact_summary}")
    else:
        lines.append("- artifacts: none")

    if report.report_path is not None:
        lines.append(f"- report: {report.report_path}")

    if report.coverage is not None:
        lines.append(f"- coverage.ui_steps: {report.coverage.ui_step_count}")
        lines.append(f"- coverage.unique_actions: {report.coverage.unique_action_count}")
        lines.append(f"- coverage.timed_steps: {report.coverage.timed_step_count}")
        lines.append(
            f"- coverage.endpoint_candidates: {report.coverage.endpoint_candidate_count}"
        )
        lines.append(
            f"- coverage.services: {report.coverage.service_candidate_count}"
        )
        if report.coverage.service_operation_totals:
            operation_summary = ", ".join(
                f"{service}={report.coverage.service_operation_covered.get(service, 0)}/{total}"
                for service, total in sorted(
                    report.coverage.service_operation_totals.items()
                )
            )
            lines.append(f"- coverage.operations: {operation_summary}")

    if report.evaluation is not None:
        lines.append(f"- evaluation.variant: {report.evaluation.variant_label}")
        lines.append(f"- evaluation.run_kind: {report.evaluation.run_kind}")
        lines.append(f"- evaluation.base_url: {report.evaluation.base_url}")
        if report.evaluation.mutation_id:
            lines.append(f"- evaluation.mutation_id: {report.evaluation.mutation_id}")
        if report.evaluation.fault_service:
            lines.append(
                f"- evaluation.fault_service: {report.evaluation.fault_service}"
            )

    if report.phase1 is not None:
        lines.append(f"- phase1.blocked: {report.phase1.blocked}")
        lines.append(f"- phase1.syntax_valid: {report.phase1.syntax_valid}")
        lines.append(
            f"- phase1.suspected_false_positive: {report.phase1.suspected_false_positive}"
        )
        lines.append(
            f"- phase1.generated_test_hash: {report.phase1.generated_test_hash or '-'}"
        )
        if report.phase1.max_retries > 0:
            lines.append(
                f"- phase1.retries_used: {report.phase1.retries_used}/{report.phase1.max_retries}"
            )
            lines.append(
                f"- phase1.test_attempts: {report.phase1.test_attempts}"
            )
            lines.append(
                f"- phase1.failed_attempts: {report.phase1.failed_attempts}"
            )
        lines.append(f"- phase1.gui_elements: {report.phase1.gui_element_count}")
        lines.append(
            f"- phase1.frontend_api_calls: {report.phase1.frontend_api_call_count}"
        )
        lines.append(
            f"- phase1.unmapped_api_calls: {len(report.phase1.unmapped_api_calls)}"
        )
        if report.phase1.failure_kind:
            lines.append(f"- phase1.failure_kind: {report.phase1.failure_kind}")
        if report.phase1.failure_diagnosis is not None:
            diagnosis = report.phase1.failure_diagnosis
            if diagnosis.kind:
                lines.append(f"- phase1.failure_diagnosis.kind: {diagnosis.kind}")
            if diagnosis.failing_line:
                lines.append(
                    f"- phase1.failure_diagnosis.failing_line: {diagnosis.failing_line}"
                )
            if diagnosis.failing_locator:
                lines.append(
                    f"- phase1.failure_diagnosis.failing_locator: {diagnosis.failing_locator}"
                )
            lines.append(
                "- phase1.failure_diagnosis.blocked_before_required_call: "
                f"{diagnosis.blocked_before_required_call}"
            )
            if diagnosis.suggested_contract_surface:
                lines.append(
                    "- phase1.failure_diagnosis.suggested_contract_surface: "
                    f"{diagnosis.suggested_contract_surface}"
                )
            if diagnosis.suggested_repair_strategy:
                lines.append(
                    "- phase1.failure_diagnosis.suggested_repair_strategy: "
                    f"{diagnosis.suggested_repair_strategy}"
                )
            if diagnosis.repair_candidates:
                rendered_candidates = ", ".join(
                    f"{candidate.strategy}={candidate.value}"
                    for candidate in diagnosis.repair_candidates[:3]
                )
                lines.append(
                    "- phase1.failure_diagnosis.repair_candidates: "
                    f"{rendered_candidates}"
                )
        if report.phase1.missing_expected_service_calls:
            missing = ", ".join(
                f"{item.get('method', '')} {item.get('path', '')}"
                for item in report.phase1.missing_expected_service_calls
            )
            lines.append(f"- phase1.missing_expected_service_calls: {missing}")

    if report.use_case is not None:
        lines.append(f"- use_case.id: {report.use_case.id}")
        lines.append(f"- use_case.name: {report.use_case.name}")
        if report.use_case.reference_bucket:
            lines.append(
                f"- use_case.reference_bucket: {report.use_case.reference_bucket}"
            )

    if report.details:
        lines.extend(
            [
                "",
                "Raw output:",
                report.details,
            ]
        )

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Journey guide rendering
# ---------------------------------------------------------------------------

def render_journey_guide_summary(guide: JourneyGuide) -> str:
    lines = [
        "Journey guide saved:",
    ]
    if guide.markdown_path is not None:
        lines.append(f"- markdown: {guide.markdown_path}")
    if guide.json_path is not None:
        lines.append(f"- json: {guide.json_path}")
    lines.append(f"- requested_journey: {guide.requested_journey}")
    if guide.use_case is not None:
        lines.append(f"- use_case.id: {guide.use_case.id}")
        lines.append(f"- use_case.name: {guide.use_case.name}")
        if guide.use_case.reference_bucket:
            lines.append(f"- use_case.reference_bucket: {guide.use_case.reference_bucket}")
    lines.append(f"- ui_steps: {guide.coverage.ui_step_count}")
    lines.append(f"- unique_actions: {guide.coverage.unique_action_count}")
    lines.append(f"- timed_steps: {guide.coverage.timed_step_count}")
    lines.append(f"- endpoint_candidates: {guide.coverage.endpoint_candidate_count}")
    lines.append(f"- services: {guide.coverage.service_candidate_count}")
    lines.append(f"- browse_api_requests: {len(guide.browse_network_requests)}")
    if guide.contract is not None:
        lines.append(f"- contract.complete: {guide.contract.complete}")
        lines.append(f"- contract.state_changing: {guide.contract.state_changing}")
    return "\n".join(lines)

def render_journey_guide(guide: JourneyGuide) -> str:
    lines = [
        "# Journey Guide",
        "",
        f"Requested journey: {guide.requested_journey}",
        f"Target test file: {guide.test_filename}",
        "",
    ]

    if guide.use_case is not None:
        lines.extend(
            [
                "## Structured Use Case",
                f"- ID: {guide.use_case.id}",
                f"- Name: {guide.use_case.name}",
            ]
        )
        if guide.use_case.role:
            lines.append(f"- Role: {guide.use_case.role}")
        if guide.use_case.reference_bucket:
            lines.append(f"- Reference bucket: {guide.use_case.reference_bucket}")
        if guide.use_case.source_path:
            lines.append(f"- Source file: {guide.use_case.source_path}")
        lines.append("")

    lines.append("## UI Steps")

    if guide.capture.actions:
        for index, step in enumerate(guide.capture.actions, start=1):
            lines.append(f"{index}. {step.action}")
            lines.append(f"   Note: {step.note}")
    else:
        lines.append("No UI steps were recorded.")

    lines.extend(
        [
            "",
            "## Timings",
        ]
    )
    if guide.capture.timings:
        for sample in guide.capture.timings:
            lines.append(f"- {sample.name}: {sample.elapsed_seconds:.1f}s")
    else:
        lines.append("No timings were recorded.")

    if guide.contract is not None:
        lines.extend(
            [
                "",
                "## Journey Contract",
                f"- Interaction surface: {guide.contract.interaction_surface}",
                "- Service interfaces: "
                + (
                    ", ".join(guide.contract.service_interfaces)
                    if guide.contract.service_interfaces
                    else "none observed"
                ),
                f"- State changing: {guide.contract.state_changing}",
                f"- Complete: {guide.contract.complete}",
            ]
        )
        if guide.contract.completeness_issues:
            lines.append("")
            lines.append("### Contract Issues")
            for issue in guide.contract.completeness_issues:
                lines.append(f"- {issue}")
        if guide.contract.expected_service_calls:
            lines.append("")
            lines.append("### Expected Service Calls")
            for call in guide.contract.expected_service_calls:
                required = "required" if call.required else "observed"
                status = f" -> {call.status_code}" if call.status_code else ""
                purpose = f"; purpose={call.purpose}" if call.purpose else ""
                trigger = (
                    f"; trigger={call.trigger_action}"
                    if call.trigger_action
                    else ""
                )
                selector = (
                    f"; selector_hint={call.trigger_selector_hint}"
                    if call.trigger_selector_hint
                    else ""
                )
                lines.append(
                    f"- {call.method} {call.path}{status} ({required}{purpose}{trigger}{selector})"
                )
        if guide.contract.interaction_contracts:
            lines.append("")
            lines.append("### Interaction Contracts")
            for index, interaction in enumerate(
                guide.contract.interaction_contracts,
                start=1,
            ):
                container = interaction.container
                lines.append(
                    f"- {index}. surface={interaction.surface_type}; "
                    f"kind={container.kind or 'unknown'}; "
                    f"selector={container.selector or '-'}; "
                    f"anchor={container.anchor_text or '-'}"
                )
                for field in interaction.fields:
                    label = field.semantic_name or field.label or field.name or "field"
                    lines.append(
                        f"  - field {label}: selector={field.selector or '-'}; "
                        f"id={field.element_id or '-'}; tag={field.tag or '-'}; "
                        f"type={field.input_type or '-'}; visible={field.visible}; "
                        f"editable={field.editable}"
                    )
                    for locator in field.validated_locators:
                        state = "validated" if locator.validated else "candidate"
                        executable = "executable" if locator.executable else "non-executable"
                        scope = f"; scope={locator.scope}" if locator.scope else ""
                        lines.append(
                            f"    - locator {state}/{executable}: "
                            f"{locator.strategy}={locator.value}{scope}"
                        )
                for action in interaction.actions:
                    label = action.semantic_name or action.label or action.text or "action"
                    lines.append(
                        f"  - action {label}: selector={action.selector or '-'}; "
                        f"tag={action.tag or '-'}; role={action.role or '-'}; "
                        f"text={action.text or action.label or '-'}"
                    )
                    if action.opens_surface:
                        lines.append(f"    - opens surface: {action.opens_surface}")
                    for locator in action.validated_locators:
                        state = "validated" if locator.validated else "candidate"
                        executable = "executable" if locator.executable else "non-executable"
                        scope = f"; scope={locator.scope}" if locator.scope else ""
                        lines.append(
                            f"    - locator {state}/{executable}: "
                            f"{locator.strategy}={locator.value}{scope}"
                        )
                    for effect in [*action.side_effects, *action.expected_service_calls]:
                        status = f" -> {effect.status_code}" if effect.status_code else ""
                        purpose = f"; purpose={effect.purpose}" if effect.purpose else ""
                        lines.append(
                            f"    - triggers {effect.method} {effect.path}{status}"
                            f" ({effect.interface}{purpose})"
                        )
        if guide.contract.success_checks:
            lines.append("")
            lines.append("### Success Checks")
            for check in guide.contract.success_checks:
                lines.append(f"- {check}")
        if guide.contract.baseline_observations:
            lines.append("")
            lines.append("### Baseline Observations")
            for observation in guide.contract.baseline_observations:
                _append_observation_lines(lines, observation, success=False)
        if guide.contract.success_observations:
            lines.append("")
            lines.append("### Success Observations")
            for observation in guide.contract.success_observations:
                _append_observation_lines(lines, observation, success=True)

    lines.extend(
        [
            "",
            "## Coverage Snapshot",
            f"- UI steps: {guide.coverage.ui_step_count}",
            f"- Unique actions: {guide.coverage.unique_action_count}",
            f"- Timed steps: {guide.coverage.timed_step_count}",
            f"- Endpoint candidates: {guide.coverage.endpoint_candidate_count}",
            f"- Services: {guide.coverage.service_candidate_count}",
        ]
    )

    if guide.coverage.endpoint_candidates:
        lines.append("")
        lines.append("### Endpoint Candidates")
        for candidate in guide.coverage.endpoint_candidates:
            lines.append(f"- {candidate}")

    if guide.coverage.service_candidates:
        lines.append("")
        lines.append("### Service Candidates")
        for candidate in guide.coverage.service_candidates:
            lines.append(f"- {candidate}")

    if guide.coverage.notes:
        lines.append("")
        lines.append("### Coverage Notes")
        for note in guide.coverage.notes:
            lines.append(f"- {note}")

    if guide.browse_network_requests:
        lines.append("")
        lines.append("### Browse Network Requests")
        for item in guide.browse_network_requests:
            method = str(item.get("method", "")).upper().strip()
            path = str(item.get("path", "")).strip()
            url = str(item.get("url", "")).strip()
            status_code = int(item.get("status_code", 0) or 0)
            status = f" -> {status_code}" if status_code else ""
            if method and path:
                lines.append(f"- {method} {path}{status}")
            elif url:
                lines.append(f"- {url}")

    return "\n".join(lines)


def _append_observation_lines(lines: list[str], observation, *, success: bool) -> None:
    label = observation.label or observation.assertion or (
        "success" if success else "baseline"
    )
    bits = [
        f"surface={observation.surface_type}" if observation.surface_type else "",
        f"kind={observation.observation_kind}" if observation.observation_kind else "",
        f"assertion={observation.assertion}",
        f"scope={observation.scope_locator}" if observation.scope_locator else "",
        f"target={observation.target_value}" if observation.target_value else "",
        f"source={observation.target_value_source}"
        if observation.target_value_source
        else "",
    ]
    lines.append(f"- {label}: " + "; ".join(bit for bit in bits if bit))
    if observation.reason:
        lines.append(f"  - reason: {observation.reason}")
    for locator in observation.validated_locators:
        state = "validated" if locator.validated else "candidate"
        executable = "executable" if locator.executable else "non-executable"
        scope = f"; scope={locator.scope}" if locator.scope else ""
        lines.append(
            f"  - locator {state}/{executable}: "
            f"{locator.strategy}={locator.value}{scope}"
        )
    for locator in observation.scope_validated_locators:
        state = "validated" if locator.validated else "candidate"
        executable = "executable" if locator.executable else "non-executable"
        scope = f"; scope={locator.scope}" if locator.scope else ""
        lines.append(
            f"  - scope locator {state}/{executable}: "
            f"{locator.strategy}={locator.value}{scope}"
        )
    for assertion in observation.assertions:
        assertion_bits = [
            f"assertion={assertion.assertion}",
            f"locator={assertion.locator}" if assertion.locator else "",
            f"expected={assertion.expected_value}" if assertion.expected_value else "",
            f"expected_source={assertion.expected_value_source}"
            if assertion.expected_value_source
            else "",
        ]
        field = assertion.field_name or "field"
        lines.append(
            f"  - assertion {field}: "
            + "; ".join(bit for bit in assertion_bits if bit)
        )
        for locator in assertion.validated_locators:
            state = "validated" if locator.validated else "candidate"
            executable = "executable" if locator.executable else "non-executable"
            scope = f"; scope={locator.scope}" if locator.scope else ""
            lines.append(
                f"    - locator {state}/{executable}: "
                f"{locator.strategy}={locator.value}{scope}"
            )
    if observation.refresh_strategy:
        refresh = ", ".join(
            f"{key}={value}"
            for key, value in observation.refresh_strategy.items()
        )
        lines.append(f"  - refresh strategy: {refresh}")
