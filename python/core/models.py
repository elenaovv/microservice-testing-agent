from __future__ import annotations

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
class ExecutionReport:
    filename: str
    status: str
    exit_code: int
    summary: str
    details: str
    artifacts: list[ExecutionArtifact] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "status": self.status,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "details": self.details,
            "artifacts": [
                {
                    "kind": artifact.kind,
                    "path": str(artifact.path),
                }
                for artifact in self.artifacts
            ],
        }


@dataclass
class Deps:
    capture: JourneyCapture = field(default_factory=JourneyCapture)
    active_timers: dict[str, float] = field(default_factory=dict)
