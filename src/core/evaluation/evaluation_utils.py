"""Evaluation metrics: run analysis, history, and summary rendering across phases."""

import json
from datetime import datetime, timezone
from pathlib import Path

from core.coverage.coverage_utils import (
    count_api_calls_by_service,
    list_unmapped_api_calls,
    load_msa_spec_text,
)
from core.evaluation.evaluation_rendering import render_evaluation_summary
from core.evaluation.failure_diagnosis import (
    diagnose_failure,
    missing_side_effect_signature,
)
from core.analysis.inference import (
    count_gui_elements_checked,
    infer_blocked,
    infer_failure_kind,
    infer_failure_signature,
    infer_suspected_false_positive,
    test_syntax_is_valid,
)
from core.contracts.models import (
    ExecutionReport,
    ExecutionResult,
    JourneyContract,
    Phase1Metrics,
)
from core.execution.run_artifacts import TEST_RESULTS_DIR
from core.analysis.sequence_extractor import action_sequence_hash as compute_seq_hash
from core.analysis.sequence_extractor import extract_action_sequence

EVALUATION_HISTORY_FILENAME = "evaluation-runs.jsonl"
LEGACY_HISTORY_FILENAME = "phase1-runs.jsonl"
EVALUATION_SUMMARY_FILENAME = "evaluation-summary.md"
SMITH_BUCKETS_PATH = Path(__file__).resolve().parent.parent.parent.parent / "spec" / "use_cases" / "smith_buckets.yaml"

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
    failure_diagnosis = diagnose_failure(
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
        failure_signature = missing_side_effect_signature(
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
