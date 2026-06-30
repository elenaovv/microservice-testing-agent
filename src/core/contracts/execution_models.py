from dataclasses import dataclass, field
from pathlib import Path

from core.contracts.basic_models import ActionStep, TimingSample


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
