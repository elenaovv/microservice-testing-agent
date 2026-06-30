import re

from core.contracts.models import JourneyCapture, JourneyContract, LocatorCandidate


def render_replay_plan(
    capture: JourneyCapture,
    contract: JourneyContract | None,
) -> str:
    if contract is None:
        return capture.action_summary()

    lines: list[str] = []
    if not contract.interaction_contracts:
        lines.append(
            capture.action_summary()
            if capture is not None
            else "No interaction surfaces recorded."
        )
    for index, interaction in enumerate(contract.interaction_contracts, start=1):
        container = interaction.container
        surface = interaction.surface_type
        anchor = container.anchor_text or container.selector or container.url or "unanchored"
        lines.append(f"{index}. Surface {surface}: {anchor}")
        for field in interaction.fields:
            name = field.semantic_name or field.label or field.name or "field"
            locator = best_locator_for_prompt(field.validated_locators, field.selector)
            value_strategy = f"; value_strategy={field.value_strategy}" if field.value_strategy else ""
            lines.append(f"   - fill/select {name}: {locator or 'no executable locator'}{value_strategy}")
            if field.options:
                options = ", ".join(
                    f"{option.get('label', '')}={option.get('value', '')}"
                    for option in field.options
                )
                lines.append(f"     options: {options}")
        for action in interaction.actions:
            name = action.semantic_name or action.label or action.text or "action"
            locator = best_action_locator_for_prompt(action)
            suffix = f"; opens={action.opens_surface}" if action.opens_surface else ""
            lines.append(f"   - action {name}: {locator or 'no executable locator'}{suffix}")
            for effect in [*action.side_effects, *action.expected_service_calls]:
                status = f" status={effect.status_code}" if effect.status_code else ""
                purpose = f" purpose={effect.purpose}" if effect.purpose else ""
                lines.append(
                    f"     expects {effect.method} {effect.path}{status}{purpose}"
                )
    if contract.baseline_observations:
        lines.append("Baseline observations for setup/original values:")
        for observation in contract.baseline_observations:
            locator = best_locator_for_prompt(
                observation.validated_locators,
                observation.locator,
            )
            scope_locator = best_locator_for_prompt(
                observation.scope_validated_locators,
                observation.scope_locator,
            )
            target = (
                f"; target={observation.target_value}"
                if observation.target_value
                else ""
            )
            lines.append(
                f"- {observation.label or observation.assertion}: "
                f"{observation.assertion}; kind={observation.observation_kind or 'observation'}; "
                f"{locator or 'no executable locator'}{target}"
            )
            if scope_locator:
                lines.append(f"  baseline scope: {scope_locator}")
            for assertion in observation.assertions:
                assertion_locator = best_locator_for_prompt(
                    assertion.validated_locators,
                    assertion.locator,
                )
                expected = (
                    f"; value={assertion.expected_value}"
                    if assertion.expected_value
                    else ""
                )
                source = (
                    f"; value_source={assertion.expected_value_source}"
                    if assertion.expected_value_source
                    else ""
                )
                lines.append(
                    f"  remember {assertion.field_name or 'field'}: "
                    f"{assertion.assertion}; {assertion_locator or 'no executable locator'}"
                    f"{expected}{source}"
                )
    if contract.success_observations:
        lines.append("Success observations:")
        for observation in contract.success_observations:
            locator = best_locator_for_prompt(
                observation.validated_locators,
                observation.locator,
            )
            scope_locator = best_locator_for_prompt(
                observation.scope_validated_locators,
                observation.scope_locator,
            )
            target = (
                f"; target={observation.target_value}"
                if observation.target_value
                else ""
            )
            source = (
                f"; source={observation.target_value_source}"
                if observation.target_value_source
                else ""
            )
            lines.append(
                f"- {observation.label or observation.assertion}: "
                f"{observation.assertion}; kind={observation.observation_kind or 'observation'}; "
                f"{locator or 'no executable locator'}"
                f"{target}{source}"
            )
            if observation.refresh_strategy:
                refresh = ", ".join(
                    f"{key}={value}"
                    for key, value in observation.refresh_strategy.items()
                )
                lines.append(f"  refresh before assertion: {refresh}")
            if scope_locator:
                lines.append(f"  scope: {scope_locator}")
            for assertion in observation.assertions:
                assertion_locator = best_locator_for_prompt(
                    assertion.validated_locators,
                    assertion.locator,
                )
                expected = (
                    f"; expected={assertion.expected_value}"
                    if assertion.expected_value
                    else ""
                )
                source = (
                    f"; expected_source={assertion.expected_value_source}"
                    if assertion.expected_value_source
                    else ""
                )
                lines.append(
                    f"  assert {assertion.field_name or 'field'}: "
                    f"{assertion.assertion}; {assertion_locator or 'no executable locator'}"
                    f"{expected}{source}"
                )
    if contract.success_checks:
        lines.append("Success checks:")
        lines.extend(f"- {check}" for check in contract.success_checks)
    return "\n".join(lines)


def best_locator_for_prompt(locators: list[LocatorCandidate], selector: str = "") -> str:
    executable_locators = [
        locator for locator in locators if getattr(locator, "executable", False)
    ]
    if executable_locators:
        locator = sorted(
            executable_locators,
            key=lambda item: (
                getattr(item, "validated", False),
                getattr(item, "strategy", "") in {"css", "test_id"},
                getattr(item, "strategy", "") in {"role", "label"},
            ),
            reverse=True,
        )[0]
        scope = f" scoped to {locator.scope}" if locator.scope else ""
        state = "validated" if locator.validated else "candidate"
        return f"{state} {locator.strategy}={locator.value}{scope}"
    return selector


def best_action_locator_for_prompt(action) -> str:
    locators = [
        locator
        for locator in getattr(action, "validated_locators", [])
        if not _locator_conflicts_with_action_tag(locator, getattr(action, "tag", ""))
    ]
    selector = getattr(action, "selector", "")
    if _selector_conflicts_with_tag(selector, getattr(action, "tag", "")):
        selector = ""
    return best_locator_for_prompt(locators, selector)


def _locator_conflicts_with_action_tag(locator, action_tag: str) -> bool:
    return (
        getattr(locator, "strategy", "") == "css"
        and _selector_conflicts_with_tag(getattr(locator, "value", ""), action_tag)
    )


def _selector_conflicts_with_tag(selector: str, tag: str) -> bool:
    selector_tag = _single_target_selector_tag(selector)
    expected_tag = str(tag).strip().lower()
    return bool(selector_tag and expected_tag and selector_tag != expected_tag)


def _single_target_selector_tag(selector: str) -> str:
    cleaned = str(selector).strip()
    if "," in cleaned or re.search(r"\s|[>+~]", cleaned):
        return ""
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*)", cleaned)
    return match.group(1).lower() if match else ""


def render_journey_contract_for_prompt(
    contract: JourneyContract | None,
) -> str:
    if contract is None:
        return "No structured journey contract was available."

    lines = [
        f"interaction_surface: {contract.interaction_surface}",
        "service_interfaces: "
        + (", ".join(contract.service_interfaces) if contract.service_interfaces else "none observed"),
        f"state_changing: {contract.state_changing}",
        f"complete: {contract.complete}",
    ]
    if contract.completeness_issues:
        lines.append("completeness_issues:")
        lines.extend(f"- {issue}" for issue in contract.completeness_issues)
    if contract.expected_service_calls:
        lines.append("expected_service_calls:")
        for call in contract.expected_service_calls:
            required = "required" if call.required else "observed"
            purpose = f"; purpose={call.purpose}" if call.purpose else ""
            trigger = f"; trigger={call.trigger_action}" if call.trigger_action else ""
            selector = (
                f"; selector_hint={call.trigger_selector_hint}"
                if call.trigger_selector_hint
                else ""
            )
            status = f"; status={call.status_code}" if call.status_code else ""
            lines.append(
                f"- {call.method} {call.path} ({required}{status}{purpose}{trigger}{selector})"
            )
    if contract.interaction_contracts:
        lines.append("interaction_contracts:")
        for index, interaction in enumerate(contract.interaction_contracts, start=1):
            container = interaction.container
            container_bits = [
                f"kind={container.kind or 'unknown'}",
                f"selector={container.selector}" if container.selector else "",
                f"anchor={container.anchor_text}" if container.anchor_text else "",
                f"role={container.role}" if container.role else "",
            ]
            lines.append(
                f"- interaction {index}: surface={interaction.surface_type}; "
                + "; ".join(bit for bit in container_bits if bit)
            )
            for field in interaction.fields:
                field_bits = [
                    f"name={field.semantic_name or field.name or field.label}",
                    f"label={field.label}" if field.label else "",
                    f"selector={field.selector}" if field.selector else "",
                    f"id={field.element_id}" if field.element_id else "",
                    f"tag={field.tag}" if field.tag else "",
                    f"type={field.input_type}" if field.input_type else "",
                    f"role={field.role}" if field.role else "",
                    f"visible={field.visible}",
                    f"editable={field.editable}",
                    f"value_strategy={field.value_strategy}" if field.value_strategy else "",
                ]
                lines.append("  field: " + "; ".join(bit for bit in field_bits if bit))
                for locator in field.validated_locators:
                    state = "validated" if locator.validated else "candidate"
                    executable = "executable" if locator.executable else "non-executable"
                    scope = f"; scope={locator.scope}" if locator.scope else ""
                    lines.append(
                        f"    locator: {state}; {executable}; "
                        f"{locator.strategy}={locator.value}{scope}"
                    )
                if field.options:
                    options = ", ".join(
                        f"{option.get('label', '')}={option.get('value', '')}"
                        for option in field.options
                    )
                    lines.append(f"    options: {options}")
            for action in interaction.actions:
                action_bits = [
                    f"name={action.semantic_name or action.label or action.text}",
                    f"label={action.label}" if action.label else "",
                    f"text={action.text}" if action.text else "",
                    f"selector={action.selector}" if action.selector else "",
                    "selector_tag_mismatch=True"
                    if _selector_conflicts_with_tag(action.selector, action.tag)
                    else "",
                    f"id={action.element_id}" if action.element_id else "",
                    f"tag={action.tag}" if action.tag else "",
                    f"role={action.role or 'none'}",
                    f"opens_surface={action.opens_surface}" if action.opens_surface else "",
                    f"observed_at_step={action.observed_at_step}"
                    if action.observed_at_step is not None
                    else "",
                ]
                lines.append("  action: " + "; ".join(bit for bit in action_bits if bit))
                for locator in action.validated_locators:
                    state = "validated" if locator.validated else "candidate"
                    executable = "executable" if locator.executable else "non-executable"
                    scope = f"; scope={locator.scope}" if locator.scope else ""
                    lines.append(
                        f"    locator: {state}; {executable}; "
                        f"{locator.strategy}={locator.value}{scope}"
                    )
                for effect in [*action.side_effects, *action.expected_service_calls]:
                    lines.append(
                        f"    triggers: {effect.method} {effect.path}"
                        f" status={effect.status_code or '?'}"
                        f" interface={effect.interface}"
                        f" purpose={effect.purpose or 'unspecified'}"
                    )
    if contract.baseline_observations:
        lines.append("baseline_observations:")
        for observation in contract.baseline_observations:
            lines.extend(_render_observation_for_prompt(observation, indent=""))
    if contract.success_observations:
        lines.append("success_observations:")
        for observation in contract.success_observations:
            lines.extend(_render_observation_for_prompt(observation, indent=""))
    if contract.success_checks:
        lines.append("success_checks:")
        lines.extend(f"- {check}" for check in contract.success_checks)
    return "\n".join(lines)


def _render_observation_for_prompt(observation, *, indent: str) -> list[str]:
    lines: list[str] = []
    prefix = indent
    label = observation.label or observation.assertion or "observation"
    bits = [
        f"label={label}",
        f"surface={observation.surface_type}" if observation.surface_type else "",
        f"kind={observation.observation_kind}" if observation.observation_kind else "",
        f"assertion={observation.assertion}",
        f"scope={observation.scope_locator}" if observation.scope_locator else "",
        f"target={observation.target_value}" if observation.target_value else "",
        f"target_source={observation.target_value_source}"
        if observation.target_value_source
        else "",
        f"reason={observation.reason}" if observation.reason else "",
    ]
    lines.append(prefix + "- " + "; ".join(bit for bit in bits if bit))
    for locator in observation.validated_locators:
        state = "validated" if locator.validated else "candidate"
        executable = "executable" if locator.executable else "non-executable"
        scope = f"; scope={locator.scope}" if locator.scope else ""
        lines.append(
            f"{prefix}  locator: {state}; {executable}; "
            f"{locator.strategy}={locator.value}{scope}"
        )
    for locator in observation.scope_validated_locators:
        state = "validated" if locator.validated else "candidate"
        executable = "executable" if locator.executable else "non-executable"
        scope = f"; scope={locator.scope}" if locator.scope else ""
        lines.append(
            f"{prefix}  scope_locator: {state}; {executable}; "
            f"{locator.strategy}={locator.value}{scope}"
        )
    if observation.refresh_strategy:
        refresh = ", ".join(
            f"{key}={value}"
            for key, value in observation.refresh_strategy.items()
        )
        lines.append(f"{prefix}  refresh_strategy: {refresh}")
    for assertion in observation.assertions:
        assertion_bits = [
            f"field={assertion.field_name}" if assertion.field_name else "",
            f"assertion={assertion.assertion}",
            f"locator={assertion.locator}" if assertion.locator else "",
            f"expected={assertion.expected_value}" if assertion.expected_value else "",
            f"expected_source={assertion.expected_value_source}"
            if assertion.expected_value_source
            else "",
            f"reason={assertion.reason}" if assertion.reason else "",
        ]
        lines.append(prefix + "  assertion: " + "; ".join(bit for bit in assertion_bits if bit))
        for locator in assertion.validated_locators:
            state = "validated" if locator.validated else "candidate"
            executable = "executable" if locator.executable else "non-executable"
            scope = f"; scope={locator.scope}" if locator.scope else ""
            lines.append(
                f"{prefix}    locator: {state}; {executable}; "
                f"{locator.strategy}={locator.value}{scope}"
            )
    return lines


_render_replay_plan = render_replay_plan
_render_journey_contract_for_prompt = render_journey_contract_for_prompt
