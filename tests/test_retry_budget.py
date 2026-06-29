from core.retry_budget import (
    max_test_executions,
    remaining_test_executions,
    render_repair_budget,
    repair_attempts_used,
    repair_budget_exhausted,
)


def test_max_retries_means_initial_execution_plus_repairs():
    assert max_test_executions(5) == 6
    assert repair_attempts_used(1) == 0
    assert repair_attempts_used(6) == 5


def test_repair_budget_exhaustion_is_based_on_total_test_executions():
    assert repair_budget_exhausted(max_retries=5, test_attempts=5) is False
    assert remaining_test_executions(max_retries=5, test_attempts=5) == 1
    assert repair_budget_exhausted(max_retries=5, test_attempts=6) is True
    assert remaining_test_executions(max_retries=5, test_attempts=6) == 0


def test_negative_retry_budget_is_normalized_to_initial_attempt_only():
    assert max_test_executions(-1) == 1
    assert repair_budget_exhausted(max_retries=-1, test_attempts=0) is False
    assert repair_budget_exhausted(max_retries=-1, test_attempts=1) is True


def test_render_repair_budget_is_report_friendly():
    rendered = render_repair_budget(max_retries=5, test_attempts=2)

    assert "test_executions=2/6" in rendered
    assert "repair_attempts=1/5" in rendered
    assert "remaining_test_executions=4" in rendered
    assert "remaining_repairs=4" in rendered
