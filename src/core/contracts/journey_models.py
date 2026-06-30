from dataclasses import dataclass, field

from core.contracts.basic_models import ActionStep, ApiCall, TimingSample
from core.contracts.interaction_models import InteractionContract
from core.contracts.locator_models import (
    LocatorCandidate,
    locator_candidates_from_observation_locator,
    sanitize_executable_selector,
)


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
            locators = locator_candidates_from_observation_locator(
                locator,
                scope=scope,
            )
        return cls(
            field_name=str(data.get("field", data.get("field_name", data.get("name", "")))).strip(),
            assertion=str(data.get("assertion", "visible")).strip() or "visible",
            locator=sanitize_executable_selector(locator),
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
            locators = locator_candidates_from_observation_locator(
                locator,
                scope=scope,
            )
        scope_locators = [
            LocatorCandidate.from_dict(item)
            for item in list(data.get("scope_validated_locators", data.get("scope_locator_candidates", [])))
            if isinstance(item, dict)
        ]
        if not scope_locators:
            scope_locators = locator_candidates_from_observation_locator(
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
            locator=sanitize_executable_selector(locator),
            scope_locator=sanitize_executable_selector(scope_locator),
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
