from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ActionStep:
    action: str
    note: str


@dataclass(slots=True)
class TimingSample:
    name: str
    elapsed_seconds: float


@dataclass
class ApiCall:
    method: str
    path: str
    status_code: int = 0


@dataclass(slots=True)
class InteractionServiceEffect:
    method: str
    path: str
    interface: str = "rest"
    status_code: int = 0
    purpose: str = ""

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "path": self.path,
            "interface": self.interface,
            "status_code": self.status_code,
            "purpose": self.purpose,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionServiceEffect":
        return cls(
            method=str(data.get("method", "")).upper(),
            path=str(data.get("path", "")),
            interface=str(data.get("interface", "rest")),
            status_code=int(data.get("status_code", 0) or 0),
            purpose=str(data.get("purpose", "")),
        )


@dataclass(slots=True)
class LocatorCandidate:
    strategy: str = ""
    value: str = ""
    scope: str = ""
    validated: bool = False
    executable: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "value": self.value,
            "scope": self.scope,
            "validated": self.validated,
            "executable": self.executable,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LocatorCandidate":
        return cls(
            strategy=str(data.get("strategy", data.get("type", ""))).strip(),
            value=str(data.get("value", data.get("selector", ""))).strip(),
            scope=str(data.get("scope", "")).strip(),
            validated=bool(data.get("validated", False)),
            executable=bool(data.get("executable", True)),
            note=str(data.get("note", "")).strip(),
        )


SNAPSHOT_SELECTOR_PREFIXES = (
    "generic[ref=",
    "button[ref=",
    "textbox[",
    "combobox[",
    "link[",
    "cell[",
    "row[",
)


def _is_snapshot_selector(selector: str) -> bool:
    normalized = selector.strip().lower()
    if not normalized:
        return False
    if "[ref=" in normalized:
        return True
    if any(normalized.startswith(prefix) for prefix in SNAPSHOT_SELECTOR_PREFIXES):
        return True
    if "/" in normalized and not normalized.startswith(("/", "./", "../")):
        # e.g. "button/text=Add" from an accessibility snapshot, not a CSS/XPath selector.
        return True
    return False


def _sanitize_executable_selector(selector: str) -> str:
    cleaned = selector.strip()
    if _is_snapshot_selector(cleaned):
        return ""
    return cleaned


def _locator_candidates_from_legacy_selector(
    *,
    selector: str,
    label: str = "",
    role: str = "",
    text: str = "",
    element_id: str = "",
    scope: str = "",
) -> list[LocatorCandidate]:
    candidates: list[LocatorCandidate] = []
    executable_selector = _sanitize_executable_selector(selector)
    if executable_selector:
        strategy = "xpath" if executable_selector.startswith(("/", "./", "../")) else "css"
        candidates.append(
            LocatorCandidate(
                strategy=strategy,
                value=executable_selector,
                scope=scope,
                validated=False,
                executable=True,
                note="legacy selector",
            )
        )
    elif selector.strip():
        candidates.append(
            LocatorCandidate(
                strategy="snapshot",
                value=selector.strip(),
                scope=scope,
                validated=False,
                executable=False,
                note="non-executable browser snapshot selector",
            )
        )
    if element_id.strip():
        candidates.append(
            LocatorCandidate(
                strategy="css",
                value=f"#{element_id.strip()}",
                scope=scope,
                validated=False,
                executable=True,
                note="element id",
            )
        )
    if role.strip() and (label.strip() or text.strip()):
        candidates.append(
            LocatorCandidate(
                strategy="role",
                value=f"{role.strip()}|{(label or text).strip()}",
                scope=scope,
                validated=False,
                executable=True,
                note="role/name fallback",
            )
        )
    elif label.strip():
        candidates.append(
            LocatorCandidate(
                strategy="label",
                value=label.strip(),
                scope=scope,
                validated=False,
                executable=True,
                note="label fallback",
            )
        )
    elif text.strip():
        candidates.append(
            LocatorCandidate(
                strategy="text",
                value=text.strip(),
                scope=scope,
                validated=False,
                executable=True,
                note="text fallback",
            )
        )

    deduped: list[LocatorCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        key = (candidate.strategy, candidate.value, candidate.scope)
        if not candidate.value or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _locator_candidates_from_observation_locator(
    locator: str,
    *,
    scope: str = "",
) -> list[LocatorCandidate]:
    cleaned = locator.strip()
    if not cleaned:
        return []
    if _is_snapshot_selector(cleaned):
        return [
            LocatorCandidate(
                strategy="snapshot",
                value=cleaned,
                scope=scope,
                validated=False,
                executable=False,
                note="non-executable browser snapshot selector",
            )
        ]
    playwright_prefixes = (
        "page.",
        "modal.",
        "container.",
        "locator(",
        "get_by_",
        "getBy",
    )
    if cleaned.startswith(playwright_prefixes):
        strategy = "playwright"
    elif cleaned.startswith(("/", "./", "../")):
        strategy = "xpath"
    else:
        strategy = "css"
    return [
        LocatorCandidate(
            strategy=strategy,
            value=cleaned,
            scope=scope,
            validated=False,
            executable=True,
            note="success observation locator",
        )
    ]


@dataclass(slots=True)
class InteractionFieldContract:
    semantic_name: str = ""
    label: str = ""
    selector: str = ""
    tag: str = ""
    input_type: str = ""
    role: str = ""
    element_id: str = ""
    name: str = ""
    visible: bool = True
    editable: bool = True
    options: list[dict[str, str]] = field(default_factory=list)
    validated_locators: list[LocatorCandidate] = field(default_factory=list)
    value_strategy: str = ""

    def to_dict(self) -> dict:
        return {
            "semantic_name": self.semantic_name,
            "label": self.label,
            "selector": self.selector,
            "tag": self.tag,
            "input_type": self.input_type,
            "role": self.role,
            "element_id": self.element_id,
            "name": self.name,
            "visible": self.visible,
            "editable": self.editable,
            "options": [dict(option) for option in self.options],
            "validated_locators": [
                locator.to_dict() for locator in self.validated_locators
            ],
            "value_strategy": self.value_strategy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionFieldContract":
        selector = str(data.get("selector", ""))
        label = str(data.get("label", ""))
        role = str(data.get("role", ""))
        element_id = str(data.get("element_id", data.get("id", "")))
        locators = [
            LocatorCandidate.from_dict(item)
            for item in list(data.get("validated_locators", data.get("locator_candidates", [])))
            if isinstance(item, dict)
        ]
        if not locators:
            locators = _locator_candidates_from_legacy_selector(
                selector=selector,
                label=label,
                role=role,
                element_id=element_id,
            )
        return cls(
            semantic_name=str(data.get("semantic_name", data.get("name", ""))),
            label=label,
            selector=_sanitize_executable_selector(selector),
            tag=str(data.get("tag", "")),
            input_type=str(data.get("input_type", data.get("type", ""))),
            role=role,
            element_id=element_id,
            name=str(data.get("name", "")),
            visible=bool(data.get("visible", True)),
            editable=bool(data.get("editable", True)),
            options=[
                {
                    "label": str(option.get("label", "")),
                    "value": str(option.get("value", "")),
                }
                for option in list(data.get("options", []))
                if isinstance(option, dict)
            ],
            validated_locators=locators,
            value_strategy=str(data.get("value_strategy", "")).strip(),
        )


@dataclass(slots=True)
class InteractionActionContract:
    semantic_name: str = ""
    label: str = ""
    selector: str = ""
    tag: str = ""
    role: str = ""
    element_id: str = ""
    classes: str = ""
    text: str = ""
    visible: bool = True
    expected_service_calls: list[InteractionServiceEffect] = field(default_factory=list)
    opens_surface: str = ""
    side_effects: list[InteractionServiceEffect] = field(default_factory=list)
    validated_locators: list[LocatorCandidate] = field(default_factory=list)
    observed_at_step: int | None = None

    def to_dict(self) -> dict:
        return {
            "semantic_name": self.semantic_name,
            "label": self.label,
            "selector": self.selector,
            "tag": self.tag,
            "role": self.role,
            "element_id": self.element_id,
            "classes": self.classes,
            "text": self.text,
            "visible": self.visible,
            "expected_service_calls": [
                call.to_dict() for call in self.expected_service_calls
            ],
            "opens_surface": self.opens_surface,
            "side_effects": [call.to_dict() for call in self.side_effects],
            "validated_locators": [
                locator.to_dict() for locator in self.validated_locators
            ],
            "observed_at_step": self.observed_at_step,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionActionContract":
        selector = str(data.get("selector", ""))
        label = str(data.get("label", ""))
        role = str(data.get("role", ""))
        element_id = str(data.get("element_id", data.get("id", "")))
        text = str(data.get("text", ""))
        locators = [
            LocatorCandidate.from_dict(item)
            for item in list(data.get("validated_locators", data.get("locator_candidates", [])))
            if isinstance(item, dict)
        ]
        if not locators:
            locators = _locator_candidates_from_legacy_selector(
                selector=selector,
                label=label,
                role=role,
                text=text,
                element_id=element_id,
            )
        raw_expected = list(data.get("expected_service_calls", []))
        raw_side_effects = list(data.get("side_effects", []))
        expected_calls = [
            InteractionServiceEffect.from_dict(item)
            for item in raw_expected
            if isinstance(item, dict)
        ]
        side_effects = [
            InteractionServiceEffect.from_dict(item)
            for item in raw_side_effects
            if isinstance(item, dict)
        ]
        raw_step = data.get("observed_at_step")
        return cls(
            semantic_name=str(data.get("semantic_name", data.get("name", ""))),
            label=label,
            selector=_sanitize_executable_selector(selector),
            tag=str(data.get("tag", "")),
            role=role,
            element_id=element_id,
            classes=str(data.get("classes", data.get("class", ""))),
            text=text,
            visible=bool(data.get("visible", True)),
            expected_service_calls=expected_calls,
            opens_surface=str(data.get("opens_surface", "")).strip(),
            side_effects=side_effects,
            validated_locators=locators,
            observed_at_step=None if raw_step is None else int(raw_step),
        )


@dataclass(slots=True)
class InteractionContainerContract:
    kind: str = ""
    selector: str = ""
    anchor_text: str = ""
    role: str = ""
    tag: str = ""
    element_id: str = ""
    classes: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "selector": self.selector,
            "anchor_text": self.anchor_text,
            "role": self.role,
            "tag": self.tag,
            "element_id": self.element_id,
            "classes": self.classes,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionContainerContract":
        return cls(
            kind=str(data.get("kind", "")),
            selector=str(data.get("selector", "")),
            anchor_text=str(data.get("anchor_text", data.get("title", ""))),
            role=str(data.get("role", "")),
            tag=str(data.get("tag", "")),
            element_id=str(data.get("element_id", data.get("id", ""))),
            classes=str(data.get("classes", data.get("class", ""))),
            url=str(data.get("url", "")),
        )


@dataclass(slots=True)
class InteractionContract:
    surface_type: str = "web_ui"
    container: InteractionContainerContract = field(
        default_factory=InteractionContainerContract
    )
    fields: list[InteractionFieldContract] = field(default_factory=list)
    actions: list[InteractionActionContract] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "surface_type": self.surface_type,
            "container": self.container.to_dict(),
            "fields": [field.to_dict() for field in self.fields],
            "actions": [action.to_dict() for action in self.actions],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionContract":
        container = data.get("container", {})
        raw_surface_type = str(data.get("surface_type", "web_ui")).strip() or "web_ui"
        surface_type, inferred_container_kind = _normalize_interaction_surface_type(
            raw_surface_type
        )
        parsed_container = (
            InteractionContainerContract.from_dict(container)
            if isinstance(container, dict)
            else InteractionContainerContract()
        )
        if inferred_container_kind and not parsed_container.kind:
            parsed_container.kind = inferred_container_kind
        if surface_type in {"web_ui", "web_page"} and parsed_container.kind:
            surface_type = _surface_type_from_container_kind(
                parsed_container.kind,
                default=surface_type,
            )
        return cls(
            surface_type=surface_type,
            container=parsed_container,
            fields=[
                InteractionFieldContract.from_dict(item)
                for item in list(data.get("fields", []))
                if isinstance(item, dict)
            ],
            actions=[
                InteractionActionContract.from_dict(item)
                for item in list(data.get("actions", []))
                if isinstance(item, dict)
            ],
            notes=str(data.get("notes", "")),
        )


def _normalize_interaction_surface_type(raw_surface_type: str) -> tuple[str, str]:
    normalized = raw_surface_type.strip().lower().replace("-", "_")
    if not normalized:
        return "web_page", ""

    surface_aliases = {
        "web": "web_page",
        "browser": "web_page",
        "browser_ui": "web_page",
        "web_ui": "web_page",
        "webui": "web_page",
        "api": "rest_endpoint",
        "rest": "rest_endpoint",
        "grpc": "grpc_method",
        "dialog": "web_modal",
        "overlay": "web_modal",
    }
    normalized = surface_aliases.get(normalized, normalized)

    if normalized.startswith("web_"):
        return normalized, normalized.removeprefix("web_")
    if normalized in {"page_form", "form", "table_action"}:
        return "web_page", normalized
    if normalized in {"modal", "drawer", "wizard", "panel"}:
        return f"web_{normalized}", normalized
    if normalized.endswith(("_endpoint", "_operation", "_method", "_command", "_event")):
        return normalized, normalized
    return normalized, ""


def _surface_type_from_container_kind(kind: str, *, default: str) -> str:
    normalized = kind.strip().lower().replace("-", "_")
    if not normalized:
        return default
    if normalized.startswith("web_"):
        return normalized
    if normalized in {"page", "page_form", "form", "table", "table_action", "list", "view"}:
        return "web_page"
    if normalized in {"dialog", "overlay"}:
        return "web_modal"
    return f"web_{normalized}"


@dataclass(slots=True)
class JourneyActionContract:
    index: int
    action: str
    note: str
    selector_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "action": self.action,
            "note": self.note,
            "selector_hints": list(self.selector_hints),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JourneyActionContract":
        return cls(
            index=int(data.get("index", 0)),
            action=str(data.get("action", "")),
            note=str(data.get("note", "")),
            selector_hints=[str(item) for item in list(data.get("selector_hints", []))],
        )


@dataclass(slots=True)
class ServiceCallRequirement:
    method: str
    path: str
    interface: str = "rest"
    status_code: int = 0
    required: bool = False
    purpose: str = ""
    trigger_action_index: int | None = None
    trigger_action: str = ""
    trigger_selector_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "path": self.path,
            "interface": self.interface,
            "status_code": self.status_code,
            "required": self.required,
            "purpose": self.purpose,
            "trigger_action_index": self.trigger_action_index,
            "trigger_action": self.trigger_action,
            "trigger_selector_hint": self.trigger_selector_hint,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ServiceCallRequirement":
        raw_index = data.get("trigger_action_index")
        trigger_action_index = None if raw_index is None else int(raw_index)
        return cls(
            method=str(data.get("method", "")).upper(),
            path=str(data.get("path", "")),
            interface=str(data.get("interface", "rest")),
            status_code=int(data.get("status_code", 0) or 0),
            required=bool(data.get("required", False)),
            purpose=str(data.get("purpose", "")),
            trigger_action_index=trigger_action_index,
            trigger_action=str(data.get("trigger_action", "")),
            trigger_selector_hint=str(data.get("trigger_selector_hint", "")),
        )


@dataclass(slots=True)
class SuccessAssertion:
    field_name: str = ""
    assertion: str = "visible"
    locator: str = ""
    expected_value: str = ""
    expected_value_source: str = ""
    validated_locators: list[LocatorCandidate] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "field": self.field_name,
            "assertion": self.assertion,
            "locator": self.locator,
            "expected_value": self.expected_value,
            "expected_value_source": self.expected_value_source,
            "validated_locators": [
                locator.to_dict() for locator in self.validated_locators
            ],
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SuccessAssertion":
        locator = str(data.get("locator", data.get("selector", ""))).strip()
        scope = str(data.get("scope", "")).strip()
        locators = [
            LocatorCandidate.from_dict(item)
            for item in list(data.get("validated_locators", data.get("locator_candidates", [])))
            if isinstance(item, dict)
        ]
        if not locators:
            locators = _locator_candidates_from_observation_locator(
                locator,
                scope=scope,
            )
        return cls(
            field_name=str(data.get("field", data.get("field_name", data.get("name", "")))).strip(),
            assertion=str(data.get("assertion", "visible")).strip() or "visible",
            locator=_sanitize_executable_selector(locator),
            expected_value=str(data.get("expected_value", data.get("value", ""))).strip(),
            expected_value_source=str(data.get("expected_value_source", "")).strip(),
            validated_locators=locators,
            reason=str(data.get("reason", data.get("note", ""))).strip(),
        )


@dataclass(slots=True)
class SuccessObservation:
    label: str = ""
    surface_type: str = ""
    observation_kind: str = ""
    assertion: str = "visible"
    locator: str = ""
    scope_locator: str = ""
    scope_validated_locators: list[LocatorCandidate] = field(default_factory=list)
    target_value: str = ""
    target_value_source: str = ""
    validated_locators: list[LocatorCandidate] = field(default_factory=list)
    assertions: list[SuccessAssertion] = field(default_factory=list)
    refresh_strategy: dict[str, str] = field(default_factory=dict)
    observed_at_step: int | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "surface_type": self.surface_type,
            "observation_kind": self.observation_kind,
            "assertion": self.assertion,
            "locator": self.locator,
            "scope_locator": self.scope_locator,
            "scope_validated_locators": [
                locator.to_dict() for locator in self.scope_validated_locators
            ],
            "target_value": self.target_value,
            "target_value_source": self.target_value_source,
            "validated_locators": [
                locator.to_dict() for locator in self.validated_locators
            ],
            "assertions": [
                assertion.to_dict() for assertion in self.assertions
            ],
            "refresh_strategy": dict(self.refresh_strategy),
            "observed_at_step": self.observed_at_step,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SuccessObservation":
        locator = str(data.get("locator", data.get("selector", ""))).strip()
        scope = str(data.get("scope", "")).strip()
        scope_locator = str(data.get("scope_locator", data.get("container_locator", ""))).strip()
        locators = [
            LocatorCandidate.from_dict(item)
            for item in list(data.get("validated_locators", data.get("locator_candidates", [])))
            if isinstance(item, dict)
        ]
        if not locators:
            locators = _locator_candidates_from_observation_locator(
                locator,
                scope=scope,
            )
        scope_locators = [
            LocatorCandidate.from_dict(item)
            for item in list(data.get("scope_validated_locators", data.get("scope_locator_candidates", [])))
            if isinstance(item, dict)
        ]
        if not scope_locators:
            scope_locators = _locator_candidates_from_observation_locator(
                scope_locator,
                scope=scope,
            )
        raw_step = data.get("observed_at_step")
        raw_refresh_strategy = data.get("refresh_strategy", {})
        refresh_strategy = (
            {
                str(key): str(value)
                for key, value in raw_refresh_strategy.items()
                if str(key).strip()
            }
            if isinstance(raw_refresh_strategy, dict)
            else {}
        )
        return cls(
            label=str(data.get("label", data.get("name", ""))).strip(),
            surface_type=str(data.get("surface_type", "")).strip(),
            observation_kind=str(data.get("observation_kind", data.get("kind", ""))).strip(),
            assertion=str(data.get("assertion", "visible")).strip() or "visible",
            locator=_sanitize_executable_selector(locator),
            scope_locator=_sanitize_executable_selector(scope_locator),
            scope_validated_locators=scope_locators,
            target_value=str(data.get("target_value", "")).strip(),
            target_value_source=str(data.get("target_value_source", "")).strip(),
            validated_locators=locators,
            assertions=[
                SuccessAssertion.from_dict(item)
                for item in list(data.get("assertions", []))
                if isinstance(item, dict)
            ],
            refresh_strategy=refresh_strategy,
            observed_at_step=None if raw_step is None else int(raw_step),
            reason=str(data.get("reason", data.get("note", ""))).strip(),
        )


@dataclass(slots=True)
class JourneyContract:
    interaction_surface: str = "web-ui"
    service_interfaces: list[str] = field(default_factory=list)
    actions: list[JourneyActionContract] = field(default_factory=list)
    interaction_contracts: list[InteractionContract] = field(default_factory=list)
    expected_service_calls: list[ServiceCallRequirement] = field(default_factory=list)
    baseline_observations: list[SuccessObservation] = field(default_factory=list)
    success_observations: list[SuccessObservation] = field(default_factory=list)
    success_checks: list[str] = field(default_factory=list)
    state_changing: bool = False
    complete: bool = True
    completeness_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "interaction_surface": self.interaction_surface,
            "service_interfaces": list(self.service_interfaces),
            "actions": [action.to_dict() for action in self.actions],
            "interaction_contracts": [
                interaction.to_dict() for interaction in self.interaction_contracts
            ],
            "expected_service_calls": [
                call.to_dict() for call in self.expected_service_calls
            ],
            "baseline_observations": [
                observation.to_dict() for observation in self.baseline_observations
            ],
            "success_observations": [
                observation.to_dict() for observation in self.success_observations
            ],
            "success_checks": list(self.success_checks),
            "state_changing": self.state_changing,
            "complete": self.complete,
            "completeness_issues": list(self.completeness_issues),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JourneyContract":
        return cls(
            interaction_surface=str(data.get("interaction_surface", "web-ui")),
            service_interfaces=[
                str(item) for item in list(data.get("service_interfaces", []))
            ],
            actions=[
                JourneyActionContract.from_dict(item)
                for item in list(data.get("actions", []))
                if isinstance(item, dict)
            ],
            interaction_contracts=[
                InteractionContract.from_dict(item)
                for item in list(data.get("interaction_contracts", []))
                if isinstance(item, dict)
            ],
            expected_service_calls=[
                ServiceCallRequirement.from_dict(item)
                for item in list(data.get("expected_service_calls", []))
                if isinstance(item, dict)
            ],
            baseline_observations=[
                SuccessObservation.from_dict(item)
                for item in list(data.get("baseline_observations", data.get("precondition_observations", [])))
                if isinstance(item, dict)
            ],
            success_observations=[
                SuccessObservation.from_dict(item)
                for item in list(data.get("success_observations", data.get("success_assertions", [])))
                if isinstance(item, dict)
            ],
            success_checks=[str(item) for item in list(data.get("success_checks", []))],
            state_changing=bool(data.get("state_changing", False)),
            complete=bool(data.get("complete", True)),
            completeness_issues=[
                str(item) for item in list(data.get("completeness_issues", []))
            ],
        )


@dataclass
class JourneyCapture:
    actions: list[ActionStep] = field(default_factory=list)
    timings: list[TimingSample] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    interaction_contracts: list[InteractionContract] = field(default_factory=list)
    baseline_observations: list[SuccessObservation] = field(default_factory=list)
    success_observations: list[SuccessObservation] = field(default_factory=list)

    def log_action(self, action: str, note: str) -> ActionStep:
        step = ActionStep(action=action, note=note)
        self.actions.append(step)
        return step

    def record_timing(self, name: str, elapsed_seconds: float) -> TimingSample:
        sample = TimingSample(name=name, elapsed_seconds=elapsed_seconds)
        self.timings.append(sample)
        return sample

    def action_summary(self) -> str:
        if not self.actions:
            return "No actions logged."
        return "\n".join(
            f"- {step.action}: {step.note}" for step in self.actions
        )

    def timing_summary(self) -> str:
        if not self.timings:
            return "No timings recorded."
        return "\n".join(
            f"- {sample.name}: {sample.elapsed_seconds:.1f}s"
            for sample in self.timings
        )

    def to_dict(self) -> dict:
        return {
            "actions": [
                {
                    "action": step.action,
                    "note": step.note,
                }
                for step in self.actions
            ],
            "timings": [
                {
                    "name": sample.name,
                    "elapsed_seconds": sample.elapsed_seconds,
                }
                for sample in self.timings
            ],
            "api_calls": [
                {
                    "method": call.method,
                    "path": call.path,
                    "status_code": call.status_code,
                }
                for call in self.api_calls
            ],
            "interaction_contracts": [
                interaction.to_dict() for interaction in self.interaction_contracts
            ],
            "baseline_observations": [
                observation.to_dict() for observation in self.baseline_observations
            ],
            "success_observations": [
                observation.to_dict() for observation in self.success_observations
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JourneyCapture":
        capture = cls()
        capture.actions = [
            ActionStep(action=item["action"], note=item["note"])
            for item in data.get("actions", [])
        ]
        capture.timings = [
            TimingSample(
                name=item["name"],
                elapsed_seconds=float(item["elapsed_seconds"]),
            )
            for item in data.get("timings", [])
        ]
        capture.api_calls = [
            ApiCall(
                method=str(item.get("method", "")).upper(),
                path=str(item.get("path", "")),
                status_code=int(item.get("status_code", 0)),
            )
            for item in data.get("api_calls", [])
            if isinstance(item, dict)
        ]
        capture.interaction_contracts = [
            InteractionContract.from_dict(item)
            for item in list(data.get("interaction_contracts", []))
            if isinstance(item, dict)
        ]
        capture.baseline_observations = [
            SuccessObservation.from_dict(item)
            for item in list(data.get("baseline_observations", data.get("precondition_observations", [])))
            if isinstance(item, dict)
        ]
        capture.success_observations = [
            SuccessObservation.from_dict(item)
            for item in list(data.get("success_observations", data.get("success_assertions", [])))
            if isinstance(item, dict)
        ]
        return capture

    def clone(self) -> "JourneyCapture":
        return JourneyCapture.from_dict(self.to_dict())


@dataclass(slots=True)
class GeneratedTest:
    filename: str
    code: str
    source_actions: list[ActionStep] = field(default_factory=list)
    source_timings: list[TimingSample] = field(default_factory=list)


@dataclass(slots=True)
class ExecutionArtifact:
    kind: str
    path: Path

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "path": str(self.path),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionArtifact":
        return cls(
            kind=data["kind"],
            path=Path(data["path"]),
        )


@dataclass
class ExecutionResult:
    filename: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    artifacts: list[ExecutionArtifact] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0

    @property
    def failed(self) -> bool:
        return not self.succeeded

    @property
    def output(self) -> str:
        return f"{self.stdout}{self.stderr}"

    def latest_artifact(self, kind: str) -> ExecutionArtifact | None:
        for artifact in reversed(self.artifacts):
            if artifact.kind == kind:
                return artifact
        return None


@dataclass(slots=True)
class CoverageSnapshot:
    ui_step_count: int
    unique_action_count: int
    timed_step_count: int
    endpoint_candidate_count: int
    service_candidate_count: int
    endpoint_candidates: list[str] = field(default_factory=list)
    service_candidates: list[str] = field(default_factory=list)
    service_operation_totals: dict[str, int] = field(default_factory=dict)
    service_operation_covered: dict[str, int] = field(default_factory=dict)
    covered_operations_by_service: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ui_step_count": self.ui_step_count,
            "unique_action_count": self.unique_action_count,
            "timed_step_count": self.timed_step_count,
            "endpoint_candidate_count": self.endpoint_candidate_count,
            "service_candidate_count": self.service_candidate_count,
            "endpoint_candidates": self.endpoint_candidates.copy(),
            "service_candidates": self.service_candidates.copy(),
            "service_operation_totals": dict(self.service_operation_totals),
            "service_operation_covered": dict(self.service_operation_covered),
            "covered_operations_by_service": {
                service: operations.copy()
                for service, operations in self.covered_operations_by_service.items()
            },
            "notes": self.notes.copy(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CoverageSnapshot":
        return cls(
            ui_step_count=int(data.get("ui_step_count", 0)),
            unique_action_count=int(data.get("unique_action_count", 0)),
            timed_step_count=int(data.get("timed_step_count", 0)),
            endpoint_candidate_count=int(data.get("endpoint_candidate_count", 0)),
            service_candidate_count=int(data.get("service_candidate_count", 0)),
            endpoint_candidates=list(data.get("endpoint_candidates", [])),
            service_candidates=list(data.get("service_candidates", [])),
            service_operation_totals=dict(data.get("service_operation_totals", {})),
            service_operation_covered=dict(data.get("service_operation_covered", {})),
            covered_operations_by_service={
                service: list(operations)
                for service, operations in dict(
                    data.get("covered_operations_by_service", {})
                ).items()
            },
            notes=list(data.get("notes", [])),
        )

    def clone(self) -> "CoverageSnapshot":
        return CoverageSnapshot.from_dict(self.to_dict())


@dataclass(slots=True)
class UseCaseMetadata:
    id: str
    name: str
    role: str = ""
    reference_bucket: str = ""
    source_path: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "reference_bucket": self.reference_bucket,
            "source_path": self.source_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UseCaseMetadata":
        return cls(
            id=str(data.get("id", "")).strip(),
            name=str(data.get("name", "")).strip(),
            role=str(data.get("role", "")).strip(),
            reference_bucket=str(
                data.get("reference_bucket", data.get("smith_equivalent", ""))
            ).strip(),
            source_path=str(data.get("source_path", "")).strip(),
        )


@dataclass(slots=True)
class FailureDiagnosis:
    kind: str = ""
    failing_line: int = 0
    failing_locator: str = ""
    blocked_before_required_call: bool = False
    suggested_contract_surface: str = ""
    repair_candidates: list[LocatorCandidate] = field(default_factory=list)
    suggested_repair_strategy: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "failing_line": self.failing_line,
            "failing_locator": self.failing_locator,
            "blocked_before_required_call": self.blocked_before_required_call,
            "suggested_contract_surface": self.suggested_contract_surface,
            "repair_candidates": [
                candidate.to_dict() for candidate in self.repair_candidates
            ],
            "suggested_repair_strategy": self.suggested_repair_strategy,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FailureDiagnosis":
        return cls(
            kind=str(data.get("kind", "")),
            failing_line=int(data.get("failing_line", 0) or 0),
            failing_locator=str(data.get("failing_locator", "")),
            blocked_before_required_call=bool(
                data.get("blocked_before_required_call", False)
            ),
            suggested_contract_surface=str(data.get("suggested_contract_surface", "")),
            repair_candidates=[
                LocatorCandidate.from_dict(item)
                for item in list(data.get("repair_candidates", []))
                if isinstance(item, dict)
            ],
            suggested_repair_strategy=str(data.get("suggested_repair_strategy", "")),
        )


@dataclass
class JourneyGuide:
    test_filename: str
    requested_journey: str
    capture: JourneyCapture
    coverage: CoverageSnapshot
    use_case: UseCaseMetadata | None = None
    browse_network_requests: list[dict[str, str]] = field(default_factory=list)
    contract: JourneyContract | None = None
    msa_spec_path: str = ""
    markdown_path: Path | None = None
    json_path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "test_filename": self.test_filename,
            "requested_journey": self.requested_journey,
            "capture": self.capture.to_dict(),
            "coverage": self.coverage.to_dict(),
            "use_case": self.use_case.to_dict() if self.use_case else None,
            "browse_network_requests": [
                {
                    "method": str(item.get("method", "")).strip(),
                    "url": str(item.get("url", "")).strip(),
                    "path": str(item.get("path", "")).strip(),
                    "status_code": int(item.get("status_code", 0) or 0),
                }
                for item in self.browse_network_requests
            ],
            "contract": self.contract.to_dict() if self.contract else None,
            "msa_spec_path": self.msa_spec_path,
            "markdown_path": str(self.markdown_path) if self.markdown_path else None,
            "json_path": str(self.json_path) if self.json_path else None,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "JourneyGuide":
        markdown_path = data.get("markdown_path")
        json_path = data.get("json_path")
        return cls(
            test_filename=data["test_filename"],
            requested_journey=data["requested_journey"],
            capture=JourneyCapture.from_dict(data.get("capture", {})),
            coverage=CoverageSnapshot.from_dict(data.get("coverage", {})),
            use_case=UseCaseMetadata.from_dict(use_case) if (use_case := data.get("use_case")) else None,
            browse_network_requests=[
                {
                    "method": str(item.get("method", "")).strip(),
                    "url": str(item.get("url", "")).strip(),
                    "path": str(item.get("path", "")).strip(),
                    "status_code": int(item.get("status_code", 0) or 0),
                }
                for item in list(data.get("browse_network_requests", []))
                if isinstance(item, dict)
            ],
            contract=JourneyContract.from_dict(contract)
            if (contract := data.get("contract"))
            else None,
            msa_spec_path=str(data.get("msa_spec_path", "")),
            markdown_path=Path(markdown_path) if markdown_path else None,
            json_path=Path(json_path) if json_path else None,
        )


@dataclass(slots=True)
class Phase1Metrics:
    generated_test: bool
    generated_test_lines: int
    generated_test_bytes: int
    generated_test_hash: str
    syntax_valid: bool
    blocked: bool
    suspected_false_positive: bool
    gui_element_count: int
    frontend_api_call_count: int
    network_capture_available: bool = False
    frontend_api_calls_by_service: dict[str, int] = field(default_factory=dict)
    unmapped_api_calls: list[dict[str, str | int]] = field(default_factory=list)
    browse_api_calls: list[dict] = field(default_factory=list)
    missing_expected_service_calls: list[dict] = field(default_factory=list)
    service_call_diff: dict = field(default_factory=dict)
    action_sequence: list[str] = field(default_factory=list)
    action_sequence_hash: str = ""
    failure_kind: str = ""
    failure_signature: str = ""
    failure_diagnosis: FailureDiagnosis | None = None
    max_retries: int = -1
    test_attempts: int = 0
    failed_attempts: int = 0
    retries_used: int = 0

    def to_dict(self) -> dict:
        return {
            "generated_test": self.generated_test,
            "generated_test_lines": self.generated_test_lines,
            "generated_test_bytes": self.generated_test_bytes,
            "generated_test_hash": self.generated_test_hash,
            "syntax_valid": self.syntax_valid,
            "blocked": self.blocked,
            "suspected_false_positive": self.suspected_false_positive,
            "gui_element_count": self.gui_element_count,
            "frontend_api_call_count": self.frontend_api_call_count,
            "network_capture_available": self.network_capture_available,
            "frontend_api_calls_by_service": dict(self.frontend_api_calls_by_service),
            "unmapped_api_calls": [item.copy() for item in self.unmapped_api_calls],
            "browse_api_calls": [item.copy() for item in self.browse_api_calls],
            "missing_expected_service_calls": [
                item.copy() for item in self.missing_expected_service_calls
            ],
            "service_call_diff": dict(self.service_call_diff),
            "action_sequence": list(self.action_sequence),
            "action_sequence_hash": self.action_sequence_hash,
            "failure_kind": self.failure_kind,
            "failure_signature": self.failure_signature,
            "failure_diagnosis": (
                self.failure_diagnosis.to_dict() if self.failure_diagnosis else None
            ),
            "max_retries": self.max_retries,
            "test_attempts": self.test_attempts,
            "failed_attempts": self.failed_attempts,
            "retries_used": self.retries_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Phase1Metrics":
        return cls(
            generated_test=bool(data.get("generated_test", False)),
            generated_test_lines=int(data.get("generated_test_lines", 0)),
            generated_test_bytes=int(data.get("generated_test_bytes", 0)),
            generated_test_hash=str(data.get("generated_test_hash", "")),
            syntax_valid=bool(data.get("syntax_valid", False)),
            blocked=bool(data.get("blocked", False)),
            suspected_false_positive=bool(data.get("suspected_false_positive", False)),
            gui_element_count=int(data.get("gui_element_count", 0)),
            frontend_api_call_count=int(data.get("frontend_api_call_count", 0)),
            network_capture_available=bool(data.get("network_capture_available", False)),
            frontend_api_calls_by_service=dict(
                data.get("frontend_api_calls_by_service", {})
            ),
            unmapped_api_calls=[
                {
                    "method": str(item.get("method", "")),
                    "path": str(item.get("path", "")),
                    "count": int(item.get("count", 0)),
                }
                for item in list(data.get("unmapped_api_calls", []))
                if isinstance(item, dict)
            ],
            browse_api_calls=[
                {
                    "method": str(item.get("method", "")),
                    "path": str(item.get("path", "")),
                    "status_code": int(item.get("status_code", 0) or 0),
                }
                for item in list(data.get("browse_api_calls", []))
                if isinstance(item, dict)
            ],
            missing_expected_service_calls=[
                {
                    "method": str(item.get("method", "")),
                    "path": str(item.get("path", "")),
                    "interface": str(item.get("interface", "")),
                    "purpose": str(item.get("purpose", "")),
                    "trigger_action": str(item.get("trigger_action", "")),
                    "trigger_selector_hint": str(
                        item.get("trigger_selector_hint", "")
                    ),
                }
                for item in list(data.get("missing_expected_service_calls", []))
                if isinstance(item, dict)
            ],
            service_call_diff=dict(data.get("service_call_diff", {})),
            action_sequence=[str(s) for s in list(data.get("action_sequence", []))],
            action_sequence_hash=str(data.get("action_sequence_hash", "")),
            failure_kind=str(data.get("failure_kind", "")),
            failure_signature=str(data.get("failure_signature", "")),
            failure_diagnosis=FailureDiagnosis.from_dict(failure_diagnosis)
            if (failure_diagnosis := data.get("failure_diagnosis"))
            else None,
            max_retries=int(data.get("max_retries", -1)),
            test_attempts=int(data.get("test_attempts", 0)),
            failed_attempts=int(data.get("failed_attempts", 0)),
            retries_used=int(data.get("retries_used", 0)),
        )


@dataclass(slots=True)
class EvaluationContext:
    variant_label: str = "original"
    mutation_id: str = ""
    fault_service: str = ""
    base_url: str = "http://localhost:8080"
    run_kind: str = "generated"

    def to_dict(self) -> dict:
        return {
            "variant_label": self.variant_label,
            "mutation_id": self.mutation_id,
            "fault_service": self.fault_service,
            "base_url": self.base_url,
            "run_kind": self.run_kind,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvaluationContext":
        return cls(
            variant_label=str(data.get("variant_label", "original")),
            mutation_id=str(data.get("mutation_id", "")),
            fault_service=str(data.get("fault_service", "")),
            base_url=str(data.get("base_url", "http://localhost:8080")),
            run_kind=str(data.get("run_kind", "generated")),
        )


@dataclass(slots=True)
class ExecutionReport:
    filename: str
    status: str
    exit_code: int
    summary: str
    details: str
    requested_journey: str | None = None
    use_case: UseCaseMetadata | None = None
    evaluation: EvaluationContext | None = None
    artifacts: list[ExecutionArtifact] = field(default_factory=list)
    report_path: Path | None = None
    coverage: CoverageSnapshot | None = None
    phase1: Phase1Metrics | None = None

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "status": self.status,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "details": self.details,
            "requested_journey": self.requested_journey,
            "use_case": self.use_case.to_dict() if self.use_case else None,
            "evaluation": self.evaluation.to_dict() if self.evaluation else None,
            "report_path": str(self.report_path) if self.report_path else None,
            "coverage": self.coverage.to_dict() if self.coverage else None,
            "phase1": self.phase1.to_dict() if self.phase1 else None,
            "artifacts": [
                artifact.to_dict()
                for artifact in self.artifacts
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionReport":
        report_path = data.get("report_path")
        coverage = data.get("coverage")
        phase1 = data.get("phase1")
        evaluation = data.get("evaluation")
        use_case = data.get("use_case")
        return cls(
            filename=data["filename"],
            status=data["status"],
            exit_code=int(data["exit_code"]),
            summary=data["summary"],
            details=data.get("details", ""),
            requested_journey=data.get("requested_journey"),
            use_case=UseCaseMetadata.from_dict(use_case) if use_case else None,
            evaluation=EvaluationContext.from_dict(evaluation) if evaluation else None,
            artifacts=[
                ExecutionArtifact.from_dict(item)
                for item in data.get("artifacts", [])
            ],
            report_path=Path(report_path) if report_path else None,
            coverage=CoverageSnapshot.from_dict(coverage) if coverage else None,
            phase1=Phase1Metrics.from_dict(phase1) if phase1 else None,
        )


@dataclass
class Deps:
    capture: JourneyCapture = field(default_factory=JourneyCapture)
    active_timers: dict[str, float] = field(default_factory=dict)
    evaluation: EvaluationContext | None = None
    max_retries: int = 0
    test_attempts: int = 0
    failed_test_attempts: int = 0
    generation_attempts: int = 0
    journey_succeeded: bool | None = None  # None = not yet reported
    journey_outcome_reason: str = ""
    browse_failure_reason: str = ""
    last_test_hash: str = ""
    output_dir: Path | None = None
    history_dir: Path | None = None
    generated_tests_dir: Path | None = None
    runtime_results_dir: Path | None = None
