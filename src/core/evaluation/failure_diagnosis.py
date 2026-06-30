import re

from core.contracts.models import FailureDiagnosis, JourneyContract, LocatorCandidate


def diagnose_failure(
    *,
    output: str,
    code: str,
    failure_kind: str,
    missing_expected_service_calls: list[dict],
    journey_contract: JourneyContract | None,
) -> FailureDiagnosis:
    kind = failure_diagnosis_kind(output, failure_kind)
    failing_line = extract_failing_line(output)
    failing_locator = extract_failing_locator(output)
    repair_candidates = extract_repair_candidates(output)
    suggested_surface = suggest_contract_surface(
        journey_contract=journey_contract,
        missing_expected_service_calls=missing_expected_service_calls,
    )
    repair_candidates = rank_repair_candidates(
        repair_candidates,
        failing_locator=failing_locator,
        suggested_surface=suggested_surface,
    )
    blocked_before_required_call = blocked_before_required_call_check(
        code=code,
        failing_line=failing_line,
        missing_expected_service_calls=missing_expected_service_calls,
    )
    return FailureDiagnosis(
        kind=kind,
        failing_line=failing_line,
        failing_locator=failing_locator,
        blocked_before_required_call=blocked_before_required_call,
        suggested_contract_surface=suggested_surface,
        repair_candidates=repair_candidates,
        suggested_repair_strategy=suggest_repair_strategy(
            kind=kind,
            failing_locator=failing_locator,
            repair_candidates=repair_candidates,
        ),
    )


def failure_diagnosis_kind(output: str, failure_kind: str) -> str:
    lower = output.lower()
    if "strict mode violation" in lower:
        return "strict-mode-ambiguity"
    if "actual value: hidden" in lower or "unexpected value \"hidden\"" in lower:
        return "hidden-element"
    if "locator.click: timeout" in lower or "locator.dblclick: timeout" in lower:
        return "action-timeout"
    if "element(s) not found" in lower or "does not match any elements" in lower:
        return "locator-not-found"
    if "locator.fill" in lower or ".fill:" in lower:
        return "form-fill"
    if "to_have_url" in lower or "page.goto" in lower:
        return "navigation"
    if "assertionerror" in lower:
        return "assertion"
    return failure_kind or "runtime-failure"


def extract_failing_line(output: str) -> int:
    for pattern in (
        r"generated-tests[\\/][^:\n]+\.py:(\d+)",
        r"generated-tests\\[^:\n]+\.py:(\d+)",
        r"generated-tests/[^:\n]+\.py:(\d+)",
    ):
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
    return 0


def extract_failing_locator(output: str) -> str:
    patterns = (
        r"waiting for ([^\n]+)",
        r"Expect \"[^\"]+\"[^\n]*\n\s+- waiting for ([^\n]+)",
        r"(locator\([^\n]+?\))",
        r"(get_by_[a-z_]+\([^\n]+?\))",
        r"(getBy[A-Za-z]+\([^\n]+?\))",
    )
    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            return match.group(1).strip().strip('"')
    return ""


def extract_repair_candidates(output: str) -> list[LocatorCandidate]:
    candidates: list[LocatorCandidate] = []
    seen: set[str] = set()
    for line in output.splitlines():
        if " aka " not in line:
            continue
        _, _, raw_candidate = line.partition(" aka ")
        value = raw_candidate.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        candidates.append(
            LocatorCandidate(
                strategy="playwright",
                value=value,
                validated=False,
                executable=True,
                note="Playwright strict-mode suggestion",
            )
        )
    return sorted(
        candidates,
        key=lambda candidate: (
            "exact=True" in candidate.value,
            "re.compile" not in candidate.value,
            -len(candidate.value),
        ),
        reverse=True,
    )


def rank_repair_candidates(
    candidates: list[LocatorCandidate],
    *,
    failing_locator: str,
    suggested_surface: str,
) -> list[LocatorCandidate]:
    if not candidates:
        return []
    context_tokens = locator_context_tokens(
        f"{failing_locator} {suggested_surface}"
    )
    if not context_tokens:
        return candidates
    return sorted(
        candidates,
        key=lambda candidate: (
            semantic_candidate_score(candidate.value, context_tokens),
            "exact=True" in candidate.value,
            "re.compile" not in candidate.value,
            -len(candidate.value),
        ),
        reverse=True,
    )


def locator_context_tokens(text: str) -> set[str]:
    tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", text)
        if len(token) > 2
    }
    return tokens - {
        "locator",
        "role",
        "name",
        "text",
        "compile",
        "ignorecase",
        "exact",
        "true",
        "false",
        "input",
        "button",
        "textbox",
    }


def semantic_candidate_score(value: str, context_tokens: set[str]) -> int:
    candidate_tokens = locator_context_tokens(value)
    return len(candidate_tokens & context_tokens)


def suggest_repair_strategy(
    *,
    kind: str,
    failing_locator: str,
    repair_candidates: list[LocatorCandidate],
) -> str:
    if kind == "action-timeout":
        return (
            "The trigger action locator timed out before the required request was emitted. "
            "Keep prior setup stable and replace the trigger with the exact validated "
            "control inside the active surface; do not chase the missing network call yet."
        )
    if kind != "strict-mode-ambiguity":
        return ""
    locator = failing_locator.lower()
    if has_duplicate_candidate_names(repair_candidates):
        if "get_by_role(\"cell\"" in locator or "get_by_role('cell'" in locator:
            return (
                "The failing assertion is inside a repeated record and the same cell "
                "text matched multiple fields. Keep the already-matched record scope "
                "and assert fields structurally within it, for example with "
                "scope.locator('td').nth(index).to_have_text(value), instead of "
                "using another accessible-name lookup for the duplicated value."
            )
        return (
            "The same visible value matched multiple elements. Preserve the nearest "
            "validated scope and add a structural or positional locator inside that "
            "scope, rather than broadening the text/role lookup."
        )
    if repair_candidates:
        return (
            "Prefer the narrowest Playwright-suggested candidate that preserves the "
            "intended scope and exact expected value."
        )
    return ""


def has_duplicate_candidate_names(candidates: list[LocatorCandidate]) -> bool:
    names: list[str] = []
    for candidate in candidates:
        match = re.search(r"name=(['\"])(.*?)\1", candidate.value)
        if match:
            names.append(match.group(2))
    return len(names) != len(set(names))


def blocked_before_required_call_check(
    *,
    code: str,
    failing_line: int,
    missing_expected_service_calls: list[dict],
) -> bool:
    if not failing_line or not missing_expected_service_calls:
        return False
    lines = code.splitlines()
    failing_index = max(failing_line - 1, 0)
    if failing_index < len(lines):
        failing_code = lines[failing_index]
        if looks_like_trigger_action_failure(failing_code):
            context_start = max(failing_index - 6, 0)
            nearby_code = "\n".join(lines[context_start : failing_index + 1])
            for call in missing_expected_service_calls:
                path = str(call.get("path", "")).strip()
                if path and path in nearby_code:
                    return True
    for call in missing_expected_service_calls:
        path = str(call.get("path", "")).strip()
        trigger_selector = str(call.get("trigger_selector_hint", "")).strip()
        required_line = first_required_call_line(
            lines=lines,
            path=path,
            trigger_selector=trigger_selector,
        )
        if required_line and failing_index + 1 < required_line:
            return True
    return False


def looks_like_trigger_action_failure(line: str) -> bool:
    return any(
        token in line
        for token in (
            ".click(",
            ".dblclick(",
            ".press(",
            ".select_option(",
            ".check(",
            ".uncheck(",
        )
    )


def first_required_call_line(
    *,
    lines: list[str],
    path: str,
    trigger_selector: str,
) -> int:
    trigger_text = ""
    action_match = re.search(r"action=([^;]+)", trigger_selector)
    if action_match:
        trigger_text = action_match.group(1).strip()
    for index, line in enumerate(lines, start=1):
        if path and path in line:
            return index
        if trigger_text and trigger_text in line:
            return index
    return 0


def suggest_contract_surface(
    *,
    journey_contract: JourneyContract | None,
    missing_expected_service_calls: list[dict],
) -> str:
    if journey_contract is None:
        return ""
    missing = {
        (str(call.get("method", "")).upper(), str(call.get("path", "")))
        for call in missing_expected_service_calls
    }
    for interaction in journey_contract.interaction_contracts:
        for action in interaction.actions:
            for effect in [*action.side_effects, *action.expected_service_calls]:
                if (effect.method.upper(), effect.path) in missing:
                    container = interaction.container
                    bits = [interaction.surface_type]
                    if container.kind:
                        bits.append(container.kind)
                    if container.anchor_text:
                        bits.append(container.anchor_text)
                    return " / ".join(bits)
    return ""


def missing_side_effect_signature(missing_calls: list[dict]) -> str:
    labels = [
        f"{str(call.get('method', '')).upper()} {call.get('path', '')}"
        for call in missing_calls[:3]
    ]
    return "missing expected service call: " + ", ".join(labels)


_diagnose_failure = diagnose_failure
_missing_side_effect_signature = missing_side_effect_signature
