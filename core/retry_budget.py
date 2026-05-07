"""Explicit retry-budget semantics for generated test repair."""


def normalize_max_retries(max_retries: int) -> int:
    return max(int(max_retries), 0)


def max_test_executions(max_retries: int) -> int:
    """Initial test execution plus the configured number of repair attempts."""
    return normalize_max_retries(max_retries) + 1


def repair_attempts_used(test_attempts: int) -> int:
    return max(int(test_attempts) - 1, 0)


def remaining_test_executions(max_retries: int, test_attempts: int) -> int:
    return max(max_test_executions(max_retries) - max(int(test_attempts), 0), 0)


def repair_budget_exhausted(max_retries: int, test_attempts: int) -> bool:
    return remaining_test_executions(max_retries, test_attempts) <= 0


def render_repair_budget(max_retries: int, test_attempts: int) -> str:
    max_executions = max_test_executions(max_retries)
    used_repairs = repair_attempts_used(test_attempts)
    remaining_executions = remaining_test_executions(max_retries, test_attempts)
    remaining_repairs = max(normalize_max_retries(max_retries) - used_repairs, 0)
    return (
        "Repair budget: "
        f"test_executions={max(int(test_attempts), 0)}/{max_executions}; "
        f"repair_attempts={used_repairs}/{normalize_max_retries(max_retries)}; "
        f"remaining_test_executions={remaining_executions}; "
        f"remaining_repairs={remaining_repairs}"
    )
