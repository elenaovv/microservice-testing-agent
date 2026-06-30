from dataclasses import dataclass, field
from pathlib import Path

from core.contracts.evaluation_models import EvaluationContext
from core.contracts.journey_models import JourneyCapture


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
