import subprocess
from pathlib import Path

from core.models import ExecutionArtifact, ExecutionResult

TEST_RESULTS_DIR = Path("test-results")
PYTEST_ARGS = (
    "-v",
    "--tb=short",
    "--headed",
    "--timeout=30",
    "--screenshot=only-on-failure",
    "--output=test-results",
)


def run_generated_test(
    filename: str,
    generated_tests_dir: Path,
    test_results_dir: Path = TEST_RESULTS_DIR,
) -> ExecutionResult:
    test_path = generated_tests_dir / filename
    if not test_path.exists():
        return ExecutionResult(
            filename=filename,
            exit_code=1,
            stderr=f"File not found: {test_path}",
        )

    result = subprocess.run(
        ["uv", "run", "pytest", str(test_path), *PYTEST_ARGS],
        capture_output=True,
        text=True,
    )

    artifacts: list[ExecutionArtifact] = []
    if result.returncode != 0:
        screenshot = find_latest_artifact(test_results_dir, ".png")
        if screenshot is not None:
            artifacts.append(
                ExecutionArtifact(kind="screenshot", path=screenshot)
            )

    return ExecutionResult(
        filename=filename,
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        artifacts=artifacts,
    )


def find_latest_artifact(directory: Path, suffix: str) -> Path | None:
    if not directory.exists():
        return None

    matches = sorted(
        directory.rglob(f"*{suffix}"),
        key=lambda path: path.stat().st_mtime,
    )
    if not matches:
        return None
    return matches[-1]
