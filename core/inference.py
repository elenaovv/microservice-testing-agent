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

REPAIR_HINTS: dict[str, str] = {
    "locator-failure": (
        "The element could not be found. Do not reuse the same locator. "
        "Try: id-based (#id), nth() positional, get_by_placeholder(), or scope to a "
        "parent container first. If a modal is open, scope all locators to the modal "
        "container before searching for buttons inside it."
    ),
    "timeout": (
        "The test timed out waiting for an element or action. "
        "Increase per-step timeouts to 2-3x the observed browse timings. "
        "Check whether a modal or overlay is blocking the page and must be dismissed first."
    ),
    "assertion-failure": (
        "An assertion failed - the expected state was not reached. "
        "Re-examine the success criteria and verify the exact text or element state "
        "visible on the page at that point. Use re.compile with IGNORECASE for text assertions."
    ),
    "syntax-error": (
        "The test has a Python syntax error. Fix it before running again. "
        "Check indentation, unclosed brackets, and string quoting."
    ),
    "import-error": (
        "An import failed. Ensure all modules used are from the standard library or "
        "already installed in the test environment (pytest, playwright, re, os)."
    ),
    "runtime-failure": (
        "The test crashed at runtime. Read the full traceback to identify the exact line "
        "and exception type. Common causes: calling a method on None, wrong Playwright API usage, "
        "or an element interaction before the page has loaded."
    ),
}


def repair_hint(failure_kind: str) -> str:
    return REPAIR_HINTS.get(failure_kind, "")


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
