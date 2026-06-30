import json
from dataclasses import dataclass, field
from pathlib import Path

from core.contracts.evaluation_models import EvaluationContext, Phase1Metrics
from core.contracts.execution_models import ExecutionArtifact
from core.contracts.journey_models import JourneyCapture, JourneyContract


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
