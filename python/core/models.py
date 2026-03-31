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
            notes=list(data.get("notes", [])),
        )


@dataclass
class JourneyGuide:
    test_filename: str
    requested_journey: str
    capture: JourneyCapture
    coverage: CoverageSnapshot
    markdown_path: Path | None = None
    json_path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "test_filename": self.test_filename,
            "requested_journey": self.requested_journey,
            "capture": self.capture.to_dict(),
            "coverage": self.coverage.to_dict(),
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
    artifacts: list[ExecutionArtifact] = field(default_factory=list)
    report_path: Path | None = None
    coverage: CoverageSnapshot | None = None

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "status": self.status,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "details": self.details,
            "report_path": str(self.report_path) if self.report_path else None,
            "coverage": self.coverage.to_dict() if self.coverage else None,
            "artifacts": [
                {
                    "kind": artifact.kind,
                    "path": str(artifact.path),
                }
                for artifact in self.artifacts
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class Deps:
    capture: JourneyCapture = field(default_factory=JourneyCapture)
    active_timers: dict[str, float] = field(default_factory=dict)
