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
class JourneyCapture:
    actions: list[ActionStep] = field(default_factory=list)
    timings: list[TimingSample] = field(default_factory=list)

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


@dataclass
class JourneyGuide:
    test_filename: str
    requested_journey: str
    capture: JourneyCapture
    coverage: CoverageSnapshot
    browse_network_requests: list[dict[str, str]] = field(default_factory=list)
    markdown_path: Path | None = None
    json_path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "test_filename": self.test_filename,
            "requested_journey": self.requested_journey,
            "capture": self.capture.to_dict(),
            "coverage": self.coverage.to_dict(),
            "browse_network_requests": [
                {
                    "method": str(item.get("method", "")).strip(),
                    "url": str(item.get("url", "")).strip(),
                    "path": str(item.get("path", "")).strip(),
                }
                for item in self.browse_network_requests
            ],
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
            browse_network_requests=[
                {
                    "method": str(item.get("method", "")).strip(),
                    "url": str(item.get("url", "")).strip(),
                    "path": str(item.get("path", "")).strip(),
                }
                for item in list(data.get("browse_network_requests", []))
                if isinstance(item, dict)
            ],
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
    frontend_api_calls_by_service: dict[str, int] = field(default_factory=dict)
    unmapped_api_calls: list[dict[str, str | int]] = field(default_factory=list)
    failure_kind: str = ""
    failure_signature: str = ""

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
            "frontend_api_calls_by_service": dict(self.frontend_api_calls_by_service),
            "unmapped_api_calls": [item.copy() for item in self.unmapped_api_calls],
            "failure_kind": self.failure_kind,
            "failure_signature": self.failure_signature,
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
            failure_kind=str(data.get("failure_kind", "")),
            failure_signature=str(data.get("failure_signature", "")),
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
        return cls(
            filename=data["filename"],
            status=data["status"],
            exit_code=int(data["exit_code"]),
            summary=data["summary"],
            details=data.get("details", ""),
            requested_journey=data.get("requested_journey"),
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
