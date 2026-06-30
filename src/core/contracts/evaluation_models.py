from dataclasses import dataclass, field

from core.contracts.locator_models import LocatorCandidate


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
