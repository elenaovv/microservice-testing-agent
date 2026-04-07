"""Inference and analysis helpers: analyze code and test output."""

import ast
import re
from core.models import ExecutionResult

GUI_PATTERN = re.compile(
    r"(page\.(?:get_by_[a-z_]+|locator|click|fill|check|uncheck|press|select_option|hover)\([^\n]+\)|expect\([^\n]+\))"
)

# ---------------------------------------------------------------------------
# Syntax and blockage checks
# ---------------------------------------------------------------------------

def test_syntax_is_valid(code: str) -> bool:
    if not code.strip():
        return False
    try:
        ast.parse(code)
    except SyntaxError:
        return False
    return True

def infer_blocked(output: str, syntax_valid: bool) -> bool:
    output_lower = output.lower()
    if not syntax_valid:
        return True
    blocked_markers = (
        "errors during collection",
        "importerror while importing test module",
        "modulenotfounderror",
        "collected 0 items",
    )
    return any(marker in output_lower for marker in blocked_markers)

# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

def infer_failure_kind(output: str, syntax_valid: bool) -> str:
    if not output.strip():
        return "no-output"
    output_lower = output.lower()
    if not syntax_valid or "syntaxerror" in output_lower or "indentationerror" in output_lower:
        return "syntax-error"
    if "errors during collection" in output_lower:
        return "collection-error"
    if "importerror while importing test module" in output_lower or "modulenotfounderror" in output_lower:
        return "import-error"
    if "timeouterror" in output_lower or "timed out" in output_lower:
        return "timeout"
    if "assertionerror" in output_lower or "failed:" in output_lower:
        return "assertion-failure"
    if "locator" in output_lower or "to_be_visible" in output_lower:
        return "locator-failure"
    return "runtime-failure"

def infer_failure_signature(output: str, failure_kind: str) -> str:
    if not output.strip() or failure_kind == "no-output":
        return ""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("E   "):
            return normalize_failure_line(stripped[4:])
        if stripped.startswith("FAILED ") or stripped.startswith("ERROR "):
            return normalize_failure_line(stripped)
    return normalize_failure_line(output.splitlines()[-1].strip())

def normalize_failure_line(line: str) -> str:
    normalized = re.sub(r"\d+\.\d+s", "<time>", line)
    normalized = re.sub(r"0x[0-9a-fA-F]+", "<addr>", normalized)
    normalized = re.sub(r"\b\d+\b", "<n>", normalized)
    return normalized[:180]

def infer_suspected_false_positive(result: ExecutionResult, code: str) -> bool:
    if result.failed or not code.strip():
        return False
    has_assertion = "expect(" in code or re.search(r"(^|\s)assert(\s|\()", code) is not None
    return not has_assertion

# ---------------------------------------------------------------------------
# Generated-code heuristics
# ---------------------------------------------------------------------------

def count_gui_elements_checked(code: str) -> int:
    if not code.strip():
        return 0
    return len({match.group(1).strip() for match in GUI_PATTERN.finditer(code)})
