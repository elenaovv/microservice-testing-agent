import os
import subprocess
from pathlib import Path

from core.models import ExecutionArtifact, ExecutionResult
from core.run_artifacts import RUNTIME_RESULTS_DIR

DEFAULT_RUNTIME_RESULTS_DIR = RUNTIME_RESULTS_DIR
PYTEST_ARGS_BASE = (
    "-v",
    "--tb=short",
    "--headed",
    "--timeout=180",
    "--screenshot=only-on-failure",
)


def _build_pytest_args(runtime_results_dir: Path) -> list[str]:
    return [*PYTEST_ARGS_BASE, "--output", str(runtime_results_dir)]


def run_generated_test(
    filename: str,
    generated_tests_dir: Path,
    test_results_dir: Path = DEFAULT_RUNTIME_RESULTS_DIR,
    base_url: str | None = None,
    network_results_dir: Path | None = None,
    runtime_results_dir: Path | None = None,
) -> ExecutionResult:
    test_path = generated_tests_dir / filename
    if not test_path.exists():
        return ExecutionResult(
            filename=filename,
            exit_code=1,
            stderr=f"File not found: {test_path}",
        )

    env = os.environ.copy()
    if base_url:
        env["BASE_URL"] = base_url
    if network_results_dir is not None:
        network_results_dir.mkdir(parents=True, exist_ok=True)
        env["NETWORK_RESULTS_DIR"] = str(network_results_dir)

    resolved_runtime_results_dir = runtime_results_dir or test_results_dir
    resolved_runtime_results_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["uv", "run", "pytest", str(test_path), *_build_pytest_args(resolved_runtime_results_dir)],
        capture_output=True,
        env=env,
        text=True,
        check=False,
    )

    artifacts: list[ExecutionArtifact] = []
    if result.returncode != 0:
        screenshot = find_latest_artifact(resolved_runtime_results_dir, ".png")
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
