"""Build a structured journey contract from browse observations.

The contract is intentionally microservice-system oriented. It does not assume
a particular benchmark application, administrative flows, authentication,
REST-only backends, or a browser-only future. Current live evidence is mostly
web UI plus HTTP requests, so the builder extracts that shape while leaving
room for gRPC/non-web surfaces.
"""

from __future__ import annotations

import re

from core.models import (
    ApiCall,
    InteractionActionContract,
    InteractionContract,
    InteractionServiceEffect,
    JourneyActionContract,
    JourneyCapture,
    JourneyContract,
    LocatorCandidate,
    ServiceCallRequirement,
)

STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
TRIGGER_WORDS = (
    "submit",
    "create",
    "add",
    "delete",
    "update",
    "confirm",
    "save",
    "pay",
    "book",
    "register",
)


def build_journey_contract(
    requested_journey: str,
    capture: JourneyCapture,
    *,
    interaction_surface: str = "web-ui",
) -> JourneyContract:
    actions = [
        JourneyActionContract(
            index=index,
            action=step.action,
            note=step.note,
            selector_hints=_selector_hints_from_text(f"{step.action} {step.note}"),
        )
        for index, step in enumerate(capture.actions, start=1)
    ]
    interaction_contracts = _latest_interaction_contracts(capture.interaction_contracts)
    service_calls = [
        _service_call_requirement(
            call,
            actions,
            interaction_contracts,
            requested_journey=requested_journey,
        )
        for call in _dedupe_observed_and_declared_calls(
            capture.api_calls,
            interaction_contracts,
        )
    ]
    service_interfaces = _service_interfaces(service_calls)
    state_changing = any(call.required for call in service_calls)
    issues = _completeness_issues(
        service_calls,
        interaction_contracts=interaction_contracts,
        interaction_surface=interaction_surface,
        observed_api_calls=capture.api_calls,
    )

    return JourneyContract(
        interaction_surface=interaction_surface,
        service_interfaces=service_interfaces,
        actions=actions,
        interaction_contracts=interaction_contracts,
        expected_service_calls=service_calls,
        baseline_observations=list(capture.baseline_observations),
        success_observations=list(capture.success_observations),
        success_checks=_success_checks(requested_journey, capture),
        state_changing=state_changing,
        complete=not issues,
        completeness_issues=issues,
    )


def _latest_interaction_contracts(
    interaction_contracts: list[InteractionContract],
) -> list[InteractionContract]:
    """Keep the latest contract for the same observed interaction surface.

    Browsing often learns a surface in stages: first a modal's labels are visible,
    then a DOM inspection discovers stable IDs or a better submit locator. The
    agent should re-log the same surface with the corrected structured evidence.
    This merge lets that later, more precise contract supersede the earlier
    sketch instead of leaving the old incomplete surface to block generation.
    """
    ordered: list[InteractionContract] = []
    index_by_key: dict[tuple[str, str, str, str, str], int] = {}
    for interaction in interaction_contracts:
        key = _interaction_contract_identity(interaction)
        if key is None:
            ordered.append(interaction)
            continue
        if key in index_by_key:
            ordered[index_by_key[key]] = interaction
            continue
        index_by_key[key] = len(ordered)
        ordered.append(interaction)
    return ordered


def _interaction_contract_identity(
    interaction: InteractionContract,
) -> tuple[str, str, str, str, str] | None:
    container = interaction.container
    surface_type = interaction.surface_type.strip().lower()
    selector = container.selector.strip()
    element_id = container.element_id.strip()
    anchor_text = _normalize_identity_text(container.anchor_text)
    kind = container.kind.strip().lower()
    url = container.url.strip()
    if not any((selector, element_id, anchor_text, url)):
        return None
    if anchor_text:
        return (surface_type, kind, anchor_text, url, "")
    return (surface_type, kind, selector or element_id, "", url)


def _normalize_identity_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _dedupe_api_calls(api_calls: list[ApiCall]) -> list[ApiCall]:
    seen: set[tuple[str, str, int]] = set()
    ordered: list[ApiCall] = []
    for call in api_calls:
        key = (call.method.upper(), call.path, call.status_code)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(call)
    return ordered


def _dedupe_observed_and_declared_calls(
    api_calls: list[ApiCall],
    interaction_contracts: list[InteractionContract],
) -> list[ApiCall]:
    ordered = _dedupe_api_calls(api_calls)
    seen = {(call.method.upper(), call.path) for call in ordered}
    for interaction in interaction_contracts:
        for action in interaction.actions:
            for effect in _action_effects(action):
                key = (effect.method.upper(), effect.path)
                if key in seen:
                    continue
                seen.add(key)
                ordered.append(
                    ApiCall(
                        method=effect.method.upper(),
                        path=effect.path,
                        status_code=effect.status_code,
                    )
                )
    return ordered


def _service_interfaces(
    service_calls: list[ServiceCallRequirement],
) -> list[str]:
    interfaces = _dedupe_strings(
        [call.interface for call in service_calls if call.interface]
    )
    return interfaces


def _service_call_requirement(
    call: ApiCall,
    actions: list[JourneyActionContract],
    interaction_contracts: list[InteractionContract],
    *,
    requested_journey: str,
) -> ServiceCallRequirement:
    method = call.method.upper()
    linked_interaction = _find_interaction_effect(call, interaction_contracts)
    purpose = _service_call_purpose(call, linked_interaction, requested_journey)
    required = purpose == "business_state_change"
    trigger = _find_trigger_action(call, actions) if required else None
    interaction_action = linked_interaction[1] if linked_interaction else None
    interaction_effect = linked_interaction[2] if linked_interaction else None
    action_selector_hint = _recent_trigger_selector_hint(actions) if required else ""
    interaction_selector_hint = _interaction_selector_hint(linked_interaction)
    fallback_selector_hint = _trigger_selector_hint(trigger) if trigger else ""
    return ServiceCallRequirement(
        method=method,
        path=call.path,
        interface=interaction_effect.interface if interaction_effect else "rest",
        status_code=call.status_code or (interaction_effect.status_code if interaction_effect else 0),
        required=required,
        purpose=purpose,
        trigger_action_index=interaction_action.observed_at_step
        if interaction_action and interaction_action.observed_at_step is not None
        else (trigger.index if trigger else None),
        trigger_action=_interaction_action_label(interaction_action)
        or (trigger.action if trigger else ""),
        trigger_selector_hint=action_selector_hint
        or interaction_selector_hint
        or fallback_selector_hint,
    )


def _find_interaction_effect(
    call: ApiCall,
    interaction_contracts: list[InteractionContract],
) -> tuple[InteractionContract, InteractionActionContract, InteractionServiceEffect] | None:
    method = call.method.upper()
    matches: list[
        tuple[InteractionContract, InteractionActionContract, InteractionServiceEffect]
    ] = []
    for interaction in interaction_contracts:
        for action in interaction.actions:
            for effect in _action_effects(action):
                if effect.method.upper() == method and effect.path == call.path:
                    matches.append((interaction, action, effect))
    if not matches:
        return None
    return sorted(matches, key=_interaction_effect_rank, reverse=True)[0]


def _action_effects(action: InteractionActionContract) -> list[InteractionServiceEffect]:
    effects: list[InteractionServiceEffect] = []
    seen: set[tuple[str, str]] = set()
    for effect in [*action.side_effects, *action.expected_service_calls]:
        key = (effect.method.upper(), effect.path)
        if not effect.path or key in seen:
            continue
        seen.add(key)
        effects.append(effect)
    return effects


def _interaction_effect_rank(
    match: tuple[InteractionContract, InteractionActionContract, InteractionServiceEffect],
) -> tuple[int, int, int, int, int]:
    interaction, action, effect = match
    container_kind = interaction.container.kind.lower()
    is_modal = int(
        interaction.surface_type == "web_modal"
        or container_kind in {"modal", "dialog", "overlay"}
    )
    has_validated_locator = int(
        any(locator.validated and locator.executable for locator in action.validated_locators)
    )
    has_executable_locator = int(
        bool(action.selector)
        or any(locator.executable for locator in action.validated_locators)
    )
    has_business_purpose = int(effect.purpose == "business_state_change")
    observed_at = action.observed_at_step or 0
    return (
        has_business_purpose,
        is_modal,
        has_validated_locator,
        has_executable_locator,
        observed_at,
    )


def _service_call_purpose(
    call: ApiCall,
    linked_interaction: tuple[
        InteractionContract,
        InteractionActionContract,
        InteractionServiceEffect,
    ]
    | None,
    requested_journey: str,
) -> str:
    method = call.method.upper()
    if method in STATE_CHANGING_METHODS:
        if _looks_like_auth_call(call.path) and not _journey_is_auth_goal(requested_journey):
            return "auth_precondition"
    if linked_interaction is not None:
        purpose = linked_interaction[2].purpose.strip()
        if purpose:
            return purpose

    if method not in STATE_CHANGING_METHODS:
        return "verification_read"
    return "business_state_change"


def _looks_like_auth_call(path: str) -> bool:
    return bool(re.search(r"/(?:auth|login|logout|session|token)(?:/|$)", path, re.I))


def _journey_is_auth_goal(requested_journey: str) -> bool:
    return bool(re.search(r"\b(log\s*in|login|sign\s*in|authenticate|logout)\b", requested_journey, re.I))


def _interaction_action_label(action: InteractionActionContract | None) -> str:
    if action is None:
        return ""
    for value in (action.semantic_name, action.label, action.text):
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return ""


def _interaction_selector_hint(
    linked_interaction: tuple[
        InteractionContract,
        InteractionActionContract,
        InteractionServiceEffect,
    ]
    | None,
) -> str:
    if linked_interaction is None:
        return ""
    interaction, action, _ = linked_interaction
    pieces: list[str] = []
    if interaction.container.selector:
        pieces.append(f"container={interaction.container.selector}")
    elif interaction.container.anchor_text:
        pieces.append(f"container text={interaction.container.anchor_text}")
    locator = _best_executable_locator(
        _compatible_action_locators(action.validated_locators, action.tag)
    )
    if locator and locator.validated:
        scope = f" scope={locator.scope};" if locator.scope else ""
        pieces.append(f"action={locator.strategy}:{locator.value}{scope}")
    elif action.selector and not _selector_conflicts_with_observed_tag(action.selector, action.tag):
        pieces.append(f"action={action.selector}")
    elif locator:
        scope = f" scope={locator.scope};" if locator.scope else ""
        pieces.append(f"action={locator.strategy}:{locator.value}{scope}")
    elif action.label or action.text:
        pieces.append(f"action text={action.label or action.text}")
    return "; ".join(pieces)


def _best_executable_locator(locators: list[LocatorCandidate]) -> LocatorCandidate | None:
    executable = [locator for locator in locators if locator.executable]
    if not executable:
        return None
    return sorted(
        executable,
        key=lambda locator: (
            locator.validated,
            locator.strategy in {"css", "test_id"},
            locator.strategy in {"role", "label"},
        ),
        reverse=True,
    )[0]


def _compatible_action_locators(
    locators: list[LocatorCandidate],
    action_tag: str,
) -> list[LocatorCandidate]:
    return [
        locator
        for locator in locators
        if not (
            locator.strategy == "css"
            and _selector_conflicts_with_observed_tag(locator.value, action_tag)
        )
    ]


def _find_trigger_action(
    call: ApiCall,
    actions: list[JourneyActionContract],
) -> JourneyActionContract | None:
    method = call.method.upper()
    path = call.path.lower()
    for action in reversed(actions):
        text = f"{action.action} {action.note}".lower()
        if method.lower() in text and path in text:
            return action
        if "backend" in text and method.lower() in text:
            return action
    for action in reversed(actions):
        text = f"{action.action} {action.note}".lower()
        if any(word in text for word in TRIGGER_WORDS):
            if method.lower() in text or "backend" in text or "request" in text:
                return action
    for action in reversed(actions):
        text = f"{action.action} {action.note}".lower()
        if any(word in text for word in TRIGGER_WORDS):
            return action
    return None


def _selector_hints_from_text(text: str) -> list[str]:
    hints: list[str] = []
    for selector in re.findall(r"(?<![\w-])#[A-Za-z][\w:-]*", text):
        hints.append(selector)
    for selector in re.findall(r"\[[A-Za-z0-9_:\-]+(?:=[^\]]+)?\]", text):
        hints.append(selector)
    for data_attr in re.findall(r"(?<![\w-])(data-[A-Za-z0-9_:\-]+)(?![\w-])", text):
        hints.append(f"[{data_attr}]")
    return _dedupe_strings(hints)


def _trigger_selector_hint(action: JourneyActionContract) -> str:
    if action.selector_hints:
        return f"action={_combine_selector_hints(action.selector_hints)}"

    text = f"{action.action} {action.note}"
    scoped_click = re.search(
        r"\b(?:clicked|press(?:ed)?|selected)\s+['\"]?([^'\".,;]+?)['\"]?"
        r"\s+in\s+the\s+([^.,;]+?)\s+(?:modal|dialog|form)\b",
        text,
        flags=re.IGNORECASE,
    )
    if scoped_click:
        label = scoped_click.group(1).strip()
        scope = scoped_click.group(2).strip()
        return f"scope text={scope}; action text={label}"

    clicked = re.search(
        r"\b(?:clicked|press(?:ed)?|selected)\s+['\"]?([^'\".,;]+?)['\"]?(?:[.,;]|$)",
        text,
        flags=re.IGNORECASE,
    )
    if clicked:
        label = clicked.group(1).strip()
        return f"action text={label}"

    label_match = re.search(
        r"\b(Add|Submit|Confirm|OK|Save|Create|Delete|Update|Pay|Book|Register)\b",
        text,
        flags=re.IGNORECASE,
    )
    if label_match:
        return f"action text={label_match.group(1)}"
    return ""


def _recent_trigger_selector_hint(actions: list[JourneyActionContract]) -> str:
    for action in reversed(actions):
        text = f"{action.action} {action.note}"
        if not action.selector_hints:
            continue
        if not re.search(r"\b(submit|confirm|save|create|add|update|delete|pay|book|register)\b", text, re.I):
            continue
        selector = _combine_selector_hints(action.selector_hints)
        if selector:
            return f"action={selector}"
    return ""


def _combine_selector_hints(selector_hints: list[str]) -> str:
    hints = [hint.strip() for hint in selector_hints if hint.strip()]
    if not hints:
        return ""
    ids = [hint for hint in hints if hint.startswith("#")]
    data_attrs = [
        hint for hint in hints if re.match(r"^\[data-[A-Za-z0-9_:\-]+(?:=[^\]]+)?\]$", hint)
    ]
    if ids and data_attrs:
        return f"{ids[0]} {data_attrs[0]}"
    return hints[0]


def _success_checks(
    requested_journey: str,
    capture: JourneyCapture,
) -> list[str]:
    checks: list[str] = []
    match = re.search(
        r"success criteria:\s*(.+)$",
        requested_journey,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        checks.extend(_split_criteria(match.group(1)))
    for step in capture.actions:
        text = f"{step.action}: {step.note}"
        if re.search(r"\b(confirm|verify|verified|appears|visible|success)\b", text, re.I):
            checks.append(text)
    return _dedupe_strings(checks)


def _split_criteria(text: str) -> list[str]:
    normalized = text.strip().rstrip(".")
    return [
        item.strip().rstrip(".")
        for item in re.split(r";|\n+-\s*", normalized)
        if item.strip()
    ]


def _completeness_issues(
    service_calls: list[ServiceCallRequirement],
    *,
    interaction_contracts: list[InteractionContract],
    interaction_surface: str,
    observed_api_calls: list[ApiCall],
) -> list[str]:
    issues: list[str] = []
    observed_successful_calls = {
        (call.method.upper(), call.path)
        for call in observed_api_calls
        if call.status_code == 0 or 200 <= call.status_code < 300
    }
    required_calls = [call for call in service_calls if call.required]
    if (
        required_calls
        and interaction_surface in {"web-ui", "web_page", "web_modal", "web_drawer"}
        and not interaction_contracts
    ):
        issues.append(
            "Missing structured interaction contract for state-changing web UI operation."
        )
    actually_observed = {(c.method.upper(), c.path) for c in observed_api_calls}
    for call in service_calls:
        if not call.required:
            continue
        call_key = (call.method.upper(), call.path)
        # If this call was declared in an interaction contract but never actually observed,
        # and a different required call was successfully observed, the agent declared the
        # wrong service variant (e.g. preserveservice vs preserveotherservice). Skip it.
        if call_key not in actually_observed:
            other_required_observed = any(
                (sc.method.upper(), sc.path) in observed_successful_calls
                for sc in service_calls
                if sc.required and sc.path != call.path
            )
            if other_required_observed:
                continue
        label = f"{call.method} {call.path}"
        if not call.trigger_action:
            issues.append(f"Missing trigger action for required service call {label}.")
        if not call.trigger_selector_hint:
            issues.append(f"Missing trigger selector hint for required service call {label}.")
        if call_key not in observed_successful_calls:
            issues.append(
                f"Required service call {label} was declared but not observed with a successful response."
            )
    for interaction in interaction_contracts:
        if not interaction.surface_type.startswith("web_"):
            continue
        triggers_required_call = any(
            _action_triggers_business_effect(action)
            for action in interaction.actions
        )
        for field in interaction.fields:
            if not (triggers_required_call and field.visible and field.editable):
                continue
            if not _has_validated_executable_locator(field.validated_locators):
                field_label = field.semantic_name or field.label or "unnamed field"
                issues.append(
                    "Missing validated executable locator for visible editable "
                    f"field {field_label} on state-changing surface."
                )
        for action in interaction.actions:
            if _selector_conflicts_with_observed_tag(action.selector, action.tag):
                action_label = action.semantic_name or action.label or action.text or "unnamed action"
                issues.append(
                    f"Selector/tag mismatch for action {action_label}: "
                    f"selector {action.selector!r} cannot target observed tag {action.tag!r}."
                )
            compatible_locators = _compatible_action_locators(
                action.validated_locators,
                action.tag,
            )
            if _action_triggers_business_effect(action) and not _has_validated_executable_locator(
                compatible_locators
            ):
                action_label = action.semantic_name or action.label or action.text or "unnamed action"
                issues.append(
                    "Missing validated executable locator for state-changing "
                    f"action {action_label}."
                )
    return issues


def _action_triggers_business_effect(action: InteractionActionContract) -> bool:
    return any(
        effect.method.upper() in STATE_CHANGING_METHODS
        and not _looks_like_auth_call(effect.path)
        for effect in _action_effects(action)
    )


def _has_validated_executable_locator(locators: list[LocatorCandidate]) -> bool:
    return any(locator.validated and locator.executable for locator in locators)


def _selector_conflicts_with_observed_tag(selector: str, tag: str) -> bool:
    expected_tag = tag.strip().lower()
    if not selector.strip() or not expected_tag:
        return False
    selector_tag = _single_target_selector_tag(selector)
    if not selector_tag:
        return False
    return selector_tag != expected_tag


def _single_target_selector_tag(selector: str) -> str:
    cleaned = selector.strip()
    if "," in cleaned:
        return ""
    if re.search(r"\s|[>+~]", cleaned):
        return ""
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*)", cleaned)
    return match.group(1).lower() if match else ""


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered
