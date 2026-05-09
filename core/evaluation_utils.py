"""Evaluation metrics: run analysis, history, and summary rendering across phases."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from core.coverage_utils import (
    count_api_calls_by_service,
    list_unmapped_api_calls,
    load_msa_spec_text,
)
from core.evaluation_rendering import render_evaluation_summary
from core.inference import (
    count_gui_elements_checked,
    infer_blocked,
    infer_failure_kind,
    infer_failure_signature,
    infer_suspected_false_positive,
    test_syntax_is_valid,
)
from core.models import (
    ExecutionReport,
    ExecutionResult,
    FailureDiagnosis,
    JourneyContract,
    LocatorCandidate,
    Phase1Metrics,
)
from core.sequence_extractor import action_sequence_hash as compute_seq_hash
from core.sequence_extractor import extract_action_sequence

TEST_RESULTS_DIR = Path("test-results")
EVALUATION_HISTORY_FILENAME = "evaluation-runs.jsonl"
LEGACY_HISTORY_FILENAME = "phase1-runs.jsonl"
EVALUATION_SUMMARY_FILENAME = "evaluation-summary.md"
SMITH_BUCKETS_PATH = Path(__file__).resolve().parent.parent / "spec" / "use_cases" / "smith_buckets.yaml"

try:
    import yaml
except ImportError:  # pragma: no cover - depends on environment packaging
    yaml = None

# ---------------------------------------------------------------------------
# Artifact path helpers
# ---------------------------------------------------------------------------

def network_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.network.json"


def evaluation_history_path(history_dir: Path = TEST_RESULTS_DIR) -> Path:
    return history_dir / EVALUATION_HISTORY_FILENAME


def legacy_history_path(history_dir: Path = TEST_RESULTS_DIR) -> Path:
    return history_dir / LEGACY_HISTORY_FILENAME


def evaluation_summary_path(history_dir: Path = TEST_RESULTS_DIR) -> Path:
    return history_dir / EVALUATION_SUMMARY_FILENAME


def load_network_capture(
    test_filename: str,
    output_dir: Path = TEST_RESULTS_DIR,
) -> dict | None:
    network_path = output_dir / network_filename_for_test(test_filename)
    if not network_path.exists():
        return None
    return json.loads(network_path.read_text(encoding="utf-8"))


def load_smith_buckets(path: Path = SMITH_BUCKETS_PATH) -> dict[str, list[str]]:
    if yaml is None or not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    buckets = data.get("buckets", {})
    if not isinstance(buckets, dict):
        return {}

    normalized: dict[str, list[str]] = {}
    for bucket_name, use_case_ids in buckets.items():
        bucket = str(bucket_name).strip()
        if not bucket:
            continue
        if not isinstance(use_case_ids, list):
            continue
        normalized[bucket] = [
            str(use_case_id).strip()
            for use_case_id in use_case_ids
            if str(use_case_id).strip()
        ]
    return normalized


# ---------------------------------------------------------------------------
# Per-run metrics
# ---------------------------------------------------------------------------

def build_phase1_metrics(
    result: ExecutionResult,
    generated_tests_dir: Path,
    test_results_dir: Path,
    msa_spec: str = "",
    max_retries: int = -1,
    test_attempts: int = 0,
    failed_test_attempts: int = 0,
    browse_api_calls: list[dict] | None = None,
    journey_contract: JourneyContract | None = None,
) -> Phase1Metrics:
    import hashlib

    test_path = generated_tests_dir / result.filename
    code = ""
    if test_path.exists():
        code = test_path.read_text(encoding="utf-8")

    syntax_valid = test_syntax_is_valid(code)
    blocked = infer_blocked(result.output, syntax_valid)
    failure_kind = ""
    failure_signature = ""
    if result.failed:
        failure_kind = infer_failure_kind(result.output, syntax_valid)
        failure_signature = infer_failure_signature(result.output, failure_kind)

    frontend_api_calls_by_service: dict[str, int] = {}
    frontend_api_call_count = 0
    unmapped_api_calls: list[dict[str, str | int]] = []
    observed_requests: list[dict] = []

    network_capture = load_network_capture(result.filename, output_dir=test_results_dir)
    if network_capture:
        observed_requests = list(network_capture.get("requests", []))
        frontend_api_call_count = len(observed_requests)
        resolved_msa_spec = msa_spec or load_msa_spec_text()
        frontend_api_calls_by_service = count_api_calls_by_service(
            requests=observed_requests,
            msa_spec=resolved_msa_spec,
        )
        unmapped_api_calls = list_unmapped_api_calls(
            requests=observed_requests,
            msa_spec=resolved_msa_spec,
        )
    required_calls = _required_service_calls(
        browse_api_calls=browse_api_calls,
        journey_contract=journey_contract,
    )
    missing_expected_service_calls = _missing_expected_service_calls(
        expected_calls=required_calls,
        observed_requests=observed_requests,
    )
    failure_diagnosis = _diagnose_failure(
        output=result.output,
        code=code,
        failure_kind=failure_kind,
        missing_expected_service_calls=missing_expected_service_calls,
        journey_contract=journey_contract,
    )
    if (
        result.failed
        and missing_expected_service_calls
        and not failure_diagnosis.blocked_before_required_call
        and failure_diagnosis.kind
        not in {
            "action-timeout",
            "locator-not-found",
            "hidden-element",
            "strict-mode-ambiguity",
            "form-fill",
        }
    ):
        failure_kind = "missing-expected-side-effect"
        failure_signature = _missing_side_effect_signature(
            missing_expected_service_calls
        )
        failure_diagnosis.kind = "missing-expected-side-effect"

    # -1 means unconfigured (no cap); 0 means retries explicitly disabled; >0 is the limit.
    resolved_max_retries = int(max_retries)
    resolved_test_attempts = max(int(test_attempts), 0)
    if resolved_test_attempts == 0 and test_path.exists():
        # If attempts were not tracked (older runs/retest path), assume one attempt.
        resolved_test_attempts = 1
    resolved_failed_attempts = max(int(failed_test_attempts), 0)
    resolved_failed_attempts = min(resolved_failed_attempts, resolved_test_attempts)
    resolved_retries_used = max(resolved_test_attempts - 1, 0)
    if resolved_max_retries >= 0:
        resolved_retries_used = min(resolved_retries_used, resolved_max_retries)

    return Phase1Metrics(
        generated_test=test_path.exists(),
        generated_test_lines=len(code.splitlines()) if code else 0,
        generated_test_bytes=len(code.encode("utf-8")) if code else 0,
        generated_test_hash=hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]
        if code
        else "",
        syntax_valid=syntax_valid,
        blocked=blocked,
        suspected_false_positive=infer_suspected_false_positive(
            result=result,
            code=code,
        ),
        gui_element_count=count_gui_elements_checked(code),
        frontend_api_call_count=frontend_api_call_count,
        network_capture_available=network_capture is not None,
        frontend_api_calls_by_service=frontend_api_calls_by_service,
        unmapped_api_calls=unmapped_api_calls,
        failure_kind=failure_kind,
        failure_signature=failure_signature,
        failure_diagnosis=failure_diagnosis if result.failed else None,
        max_retries=resolved_max_retries,
        test_attempts=resolved_test_attempts,
        failed_attempts=resolved_failed_attempts,
        retries_used=resolved_retries_used,
        browse_api_calls=[
            {
                "method": str(c.get("method", "")),
                "path": str(c.get("path", "")),
                "status_code": int(c.get("status_code", 0)),
            }
            for c in (browse_api_calls or [])
            if isinstance(c, dict)
        ],
        missing_expected_service_calls=missing_expected_service_calls,
        service_call_diff={
            "expected_required": [
                {
                    "method": str(call.get("method", "")),
                    "path": str(call.get("path", "")),
                    "interface": str(call.get("interface", "")),
                }
                for call in required_calls
            ],
            "observed": [
                {
                    "method": str(request.get("method", "")),
                    "path": str(request.get("path", "")),
                }
                for request in observed_requests
            ],
            "missing": missing_expected_service_calls,
        },
        action_sequence=(_seq := extract_action_sequence(code)),
        action_sequence_hash=compute_seq_hash(_seq),
    )


def _required_service_calls(
    *,
    browse_api_calls: list[dict] | None,
    journey_contract: JourneyContract | None,
) -> list[dict]:
    if journey_contract is not None:
        return [
            {
                "method": call.method,
                "path": call.path,
                "interface": call.interface,
                "purpose": call.purpose,
                "trigger_action": call.trigger_action,
                "trigger_selector_hint": call.trigger_selector_hint,
            }
            for call in journey_contract.expected_service_calls
            if call.required
        ]

    required_methods = {"POST", "PUT", "PATCH", "DELETE"}
    return [
        {
            "method": str(call.get("method", "")).upper(),
            "path": str(call.get("path", "")),
            "interface": "rest",
            "purpose": "business_state_change",
            "trigger_action": "",
            "trigger_selector_hint": "",
        }
        for call in (browse_api_calls or [])
        if isinstance(call, dict)
        and str(call.get("method", "")).upper() in required_methods
    ]


def _missing_expected_service_calls(
    *,
    expected_calls: list[dict],
    observed_requests: list[dict],
) -> list[dict]:
    observed = {
        (str(request.get("method", "")).upper(), str(request.get("path", "")))
        for request in observed_requests
    }
    missing: list[dict] = []
    for call in expected_calls:
        method = str(call.get("method", "")).upper()
        path = str(call.get("path", ""))
        if not method or not path or (method, path) in observed:
            continue
        missing.append(
            {
                "method": method,
                "path": path,
                "interface": str(call.get("interface", "")),
                "purpose": str(call.get("purpose", "")),
                "trigger_action": str(call.get("trigger_action", "")),
                "trigger_selector_hint": str(call.get("trigger_selector_hint", "")),
            }
        )
    return missing


def _diagnose_failure(
    *,
    output: str,
    code: str,
    failure_kind: str,
    missing_expected_service_calls: list[dict],
    journey_contract: JourneyContract | None,
) -> FailureDiagnosis:
    kind = _failure_diagnosis_kind(output, failure_kind)
    failing_line = _extract_failing_line(output)
    failing_locator = _extract_failing_locator(output)
    repair_candidates = _extract_repair_candidates(output)
    suggested_surface = _suggest_contract_surface(
        journey_contract=journey_contract,
        missing_expected_service_calls=missing_expected_service_calls,
    )
    repair_candidates = _rank_repair_candidates(
        repair_candidates,
        failing_locator=failing_locator,
        suggested_surface=suggested_surface,
    )
    blocked_before_required_call = _blocked_before_required_call(
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
        suggested_repair_strategy=_suggest_repair_strategy(
            kind=kind,
            failing_locator=failing_locator,
            repair_candidates=repair_candidates,
        ),
    )


def _failure_diagnosis_kind(output: str, failure_kind: str) -> str:
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


def _extract_failing_line(output: str) -> int:
    for pattern in (
        r"generated-tests[\\/][^:\n]+\.py:(\d+)",
        r"generated-tests\\[^:\n]+\.py:(\d+)",
        r"generated-tests/[^:\n]+\.py:(\d+)",
    ):
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
    return 0


def _extract_failing_locator(output: str) -> str:
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


def _extract_repair_candidates(output: str) -> list[LocatorCandidate]:
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


def _rank_repair_candidates(
    candidates: list[LocatorCandidate],
    *,
    failing_locator: str,
    suggested_surface: str,
) -> list[LocatorCandidate]:
    if not candidates:
        return []
    context_tokens = _locator_context_tokens(
        f"{failing_locator} {suggested_surface}"
    )
    if not context_tokens:
        return candidates
    return sorted(
        candidates,
        key=lambda candidate: (
            _semantic_candidate_score(candidate.value, context_tokens),
            "exact=True" in candidate.value,
            "re.compile" not in candidate.value,
            -len(candidate.value),
        ),
        reverse=True,
    )


def _locator_context_tokens(text: str) -> set[str]:
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


def _semantic_candidate_score(value: str, context_tokens: set[str]) -> int:
    candidate_tokens = _locator_context_tokens(value)
    return len(candidate_tokens & context_tokens)


def _suggest_repair_strategy(
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
    if _has_duplicate_candidate_names(repair_candidates):
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


def _has_duplicate_candidate_names(candidates: list[LocatorCandidate]) -> bool:
    names: list[str] = []
    for candidate in candidates:
        match = re.search(r"name=(['\"])(.*?)\1", candidate.value)
        if match:
            names.append(match.group(2))
    return len(names) != len(set(names))


def _blocked_before_required_call(
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
        if _looks_like_trigger_action_failure(failing_code):
            context_start = max(failing_index - 6, 0)
            nearby_code = "\n".join(lines[context_start : failing_index + 1])
            for call in missing_expected_service_calls:
                path = str(call.get("path", "")).strip()
                if path and path in nearby_code:
                    return True
    for call in missing_expected_service_calls:
        path = str(call.get("path", "")).strip()
        trigger_selector = str(call.get("trigger_selector_hint", "")).strip()
        required_line = _first_required_call_line(
            lines=lines,
            path=path,
            trigger_selector=trigger_selector,
        )
        if required_line and failing_index + 1 < required_line:
            return True
    return False


def _looks_like_trigger_action_failure(line: str) -> bool:
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


def _first_required_call_line(
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


def _suggest_contract_surface(
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


def _missing_side_effect_signature(missing_calls: list[dict]) -> str:
    labels = [
        f"{str(call.get('method', '')).upper()} {call.get('path', '')}"
        for call in missing_calls[:3]
    ]
    return "missing expected service call: " + ", ".join(labels)


# ---------------------------------------------------------------------------
# Evaluation history and summary persistence
# ---------------------------------------------------------------------------

def append_evaluation_history(
    report: ExecutionReport,
    history_dir: Path = TEST_RESULTS_DIR,
) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    record = report.to_dict()
    record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    history_path = evaluation_history_path(history_dir)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")
    write_evaluation_summary(history_dir=history_dir)
    return history_path


def load_evaluation_history(history_dir: Path = TEST_RESULTS_DIR) -> list[dict]:
    records: list[dict] = []
    for history_path in (
        legacy_history_path(history_dir),
        evaluation_history_path(history_dir),
    ):
        if not history_path.exists():
            continue
        for line in history_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            records.append(json.loads(stripped))
    return records


def write_evaluation_summary(history_dir: Path = TEST_RESULTS_DIR) -> Path:
    records = load_evaluation_history(history_dir)
    summary_path = evaluation_summary_path(history_dir)
    summary_path.write_text(
        render_evaluation_summary(records, smith_buckets=load_smith_buckets()),
        encoding="utf-8",
    )
    return summary_path
