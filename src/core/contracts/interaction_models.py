from dataclasses import dataclass, field

from core.contracts.locator_models import (
    LocatorCandidate,
    locator_candidates_from_legacy_selector,
    sanitize_executable_selector,
)


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
            locators = locator_candidates_from_legacy_selector(
                selector=selector,
                label=label,
                role=role,
                element_id=element_id,
            )
        return cls(
            semantic_name=str(data.get("semantic_name", data.get("name", ""))),
            label=label,
            selector=sanitize_executable_selector(selector),
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
            locators = locator_candidates_from_legacy_selector(
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
            selector=sanitize_executable_selector(selector),
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
