"""Run artifact paths shared by workflow, tools, reporting, and evaluation."""

from dataclasses import dataclass
from pathlib import Path

TEST_RESULTS_DIR = Path("test-results")
GENERATED_TESTS_DIR = Path("generated-tests")
RUNTIME_RESULTS_DIR = Path("runtime-results")
PROMPT_CAPTURES_DIR = Path("prompt-captures")
TEST_ATTEMPTS_DIRNAME = "test-attempts"


@dataclass(frozen=True)
class RunArtifactPaths:
    output_dir: Path = TEST_RESULTS_DIR
    history_dir: Path = TEST_RESULTS_DIR
    generated_tests_dir: Path = GENERATED_TESTS_DIR
    runtime_results_dir: Path = RUNTIME_RESULTS_DIR
    source_dir: Path = TEST_RESULTS_DIR
    aggregate_history_dir: Path | None = None

    def test_attempts_dir(self, filename: str) -> Path:
        return self.output_dir / TEST_ATTEMPTS_DIRNAME / Path(filename).stem


def resolve_generation_artifacts(
    *,
    output_dir: Path | None = None,
    history_dir: Path | None = None,
    generated_tests_dir: Path | None = None,
    runtime_results_dir: Path | None = None,
    aggregate_history_dir: Path | None = None,
) -> RunArtifactPaths:
    resolved_output_dir = output_dir or TEST_RESULTS_DIR
    return RunArtifactPaths(
        output_dir=resolved_output_dir,
        history_dir=history_dir or resolved_output_dir,
        generated_tests_dir=generated_tests_dir or GENERATED_TESTS_DIR,
        runtime_results_dir=runtime_results_dir or RUNTIME_RESULTS_DIR,
        source_dir=resolved_output_dir,
        aggregate_history_dir=aggregate_history_dir,
    )


def resolve_retest_artifacts(
    *,
    output_dir: Path | None = None,
    history_dir: Path | None = None,
    source_dir: Path | None = None,
    generated_tests_dir: Path | None = None,
    runtime_results_dir: Path | None = None,
    aggregate_history_dir: Path | None = None,
) -> RunArtifactPaths:
    resolved_output_dir = output_dir or TEST_RESULTS_DIR
    return RunArtifactPaths(
        output_dir=resolved_output_dir,
        history_dir=history_dir or resolved_output_dir,
        generated_tests_dir=generated_tests_dir or GENERATED_TESTS_DIR,
        runtime_results_dir=runtime_results_dir or RUNTIME_RESULTS_DIR,
        source_dir=source_dir or TEST_RESULTS_DIR,
        aggregate_history_dir=aggregate_history_dir,
    )
