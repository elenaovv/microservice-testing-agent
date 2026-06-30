"""Extract ordered Playwright action sequences from generated test files.

Parses the AST of a generated pytest-playwright test and produces a normalized
list of actions (e.g. click, fill, goto, expect assertions) with their
locator selectors. Fill values and assertion text are dropped so that two tests
that fill the same field with different data still produce the same sequence.

Variable assignments are tracked so that assigned locators can be resolved
when methods are called on them later.
"""

import ast
import hashlib

PLAYWRIGHT_ACTIONS = frozenset({
    "click",
    "fill",
    "press",
    "type",
    "check",
    "uncheck",
    "select_option",
    "tap",
    "hover",
    "focus",
    "clear",
    "wait_for",
    "wait_for_url",
    "wait_for_load_state",
    "wait_for_selector",
    "goto",
    "reload",
    "to_be_visible",
    "to_be_hidden",
    "to_be_enabled",
    "to_be_disabled",
    "to_have_text",
    "to_contain_text",
    "to_have_value",
    "to_have_attribute",
    "to_be_checked",
    "to_have_count",
    "to_have_url",
    "not_to_be_visible",
    "not_to_have_text",
    "not_to_be_enabled",
})

LOCATOR_METHODS = frozenset({
    "locator",
    "get_by_role",
    "get_by_text",
    "get_by_label",
    "get_by_placeholder",
    "get_by_test_id",
    "get_by_alt_text",
    "get_by_title",
    "filter",
    "nth",
    "first",
    "last",
})


def _selector_from_node(node: ast.expr, var_map: dict[str, str]) -> str:
    """Walk a call/attribute chain and return the first meaningful locator label."""
    if isinstance(node, ast.Name):
        return var_map.get(node.id, "")

    if isinstance(node, ast.Attribute):
        attr = node.attr
        if attr in ("first", "last"):
            return _selector_from_node(node.value, var_map)
        if attr in LOCATOR_METHODS:
            return f"{attr}"
        return _selector_from_node(node.value, var_map)

    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            method = func.attr

            if method in LOCATOR_METHODS:
                if node.args and isinstance(node.args[0], ast.Constant):
                    val = str(node.args[0].value)
                    if method == "get_by_role":
                        for kw in node.keywords:
                            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                                val = f"{val}[name={kw.value.value}]"
                    return f"{method}:{val}"
                return method

            # Recurse into the object the method is called on
            return _selector_from_node(func.value, var_map)

        if isinstance(func, ast.Name) and func.id == "expect":
            # expect(locator) - look inside the first argument
            if node.args:
                return _selector_from_node(node.args[0], var_map)

    return ""


def _process_call(node: ast.expr, sequence: list[str], var_map: dict[str, str]) -> None:
    """If node is a Playwright action call, append a step to sequence."""
    if not isinstance(node, ast.Call):
        return
    func = node.func
    if not isinstance(func, ast.Attribute):
        return

    action = func.attr
    if action not in PLAYWRIGHT_ACTIONS:
        return

    if action == "goto":
        if node.args:
            arg = node.args[0]
            url = str(arg.value) if isinstance(arg, ast.Constant) else "BASE_URL"
        else:
            url = "..."
        sequence.append(f"goto({url})")
        return

    selector = _selector_from_node(func.value, var_map)
    if selector:
        sequence.append(f"{action}({selector})")
    else:
        sequence.append(action)


def _walk(stmts: list[ast.stmt], sequence: list[str], var_map: dict[str, str]) -> None:
    for stmt in stmts:
        if isinstance(stmt, ast.Assign):
            # Track: name = page.locator(...) or similar
            if stmt.value is not None:
                sel = _selector_from_node(stmt.value, var_map)
                if sel:
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            var_map[target.id] = sel

        elif isinstance(stmt, ast.Expr):
            _process_call(stmt.value, sequence, var_map)

        elif isinstance(stmt, ast.With):
            _walk(stmt.body, sequence, var_map)

        elif isinstance(stmt, ast.If):
            _walk(stmt.body, sequence, var_map)
            _walk(stmt.orelse, sequence, var_map)

        elif isinstance(stmt, (ast.For, ast.While)):
            _walk(stmt.body, sequence, var_map)

        elif isinstance(stmt, ast.Try):
            _walk(stmt.body, sequence, var_map)
            for handler in stmt.handlers:
                _walk(handler.body, sequence, var_map)
            _walk(stmt.orelse, sequence, var_map)
            _walk(stmt.finalbody, sequence, var_map)

        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _walk(stmt.body, sequence, var_map)


def extract_action_sequence(code: str) -> list[str]:
    """Return the ordered Playwright action sequence from a test file's source."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    sequence: list[str] = []
    var_map: dict[str, str] = {}

    # Find test function first (most reliable), fallback to module level
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                _walk(node.body, sequence, var_map)
                return sequence

    _walk(tree.body, sequence, var_map)
    return sequence


def action_sequence_hash(sequence: list[str]) -> str:
    """Return a 12-char hex hash of the action sequence."""
    if not sequence:
        return ""
    content = "\n".join(sequence)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
