from pathlib import Path

from core.execution.run_artifacts import (
    GENERATED_TESTS_DIR,
    RUNTIME_RESULTS_DIR,
    TEST_RESULTS_DIR,
    resolve_generation_artifacts,
    resolve_retest_artifacts,
)


def test_generation_artifact_defaults_share_output_and_history_dirs():
    artifacts = resolve_generation_artifacts()

    assert artifacts.output_dir == TEST_RESULTS_DIR
    assert artifacts.history_dir == TEST_RESULTS_DIR
    assert artifacts.source_dir == TEST_RESULTS_DIR
    assert artifacts.generated_tests_dir == GENERATED_TESTS_DIR
    assert artifacts.runtime_results_dir == RUNTIME_RESULTS_DIR
    assert artifacts.test_attempts_dir("booking_test.py") == (
        TEST_RESULTS_DIR / "test-attempts" / "booking_test"
    )


def test_retest_artifacts_allow_separate_source_dir():
    artifacts = resolve_retest_artifacts(
        output_dir=Path("out"),
        history_dir=Path("history"),
        source_dir=Path("source"),
        generated_tests_dir=Path("generated"),
        runtime_results_dir=Path("runtime"),
        aggregate_history_dir=Path("aggregate"),
    )

    assert artifacts.output_dir == Path("out")
    assert artifacts.history_dir == Path("history")
    assert artifacts.source_dir == Path("source")
    assert artifacts.generated_tests_dir == Path("generated")
    assert artifacts.runtime_results_dir == Path("runtime")
    assert artifacts.aggregate_history_dir == Path("aggregate")
