"""Evaluation metrics: run analysis, history, and summary rendering across phases."""

import json
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
from core.models import ExecutionReport, ExecutionResult, Phase1Metrics

TEST_RESULTS_DIR = Path("test-results")
EVALUATION_HISTORY_FILENAME = "evaluation-runs.jsonl"
LEGACY_HISTORY_FILENAME = "phase1-runs.jsonl"
EVALUATION_SUMMARY_FILENAME = "evaluation-summary.md"

# ---------------------------------------------------------------------------
# Artifact path helpers
# ---------------------------------------------------------------------------

def network_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.network.json"


def evaluation_history_path(output_dir: Path = TEST_RESULTS_DIR) -> Path:
    return output_dir / EVALUATION_HISTORY_FILENAME


def legacy_history_path(output_dir: Path = TEST_RESULTS_DIR) -> Path:
    return output_dir / LEGACY_HISTORY_FILENAME


def evaluation_summary_path(output_dir: Path = TEST_RESULTS_DIR) -> Path:
    return output_dir / EVALUATION_SUMMARY_FILENAME


def load_network_capture(
    test_filename: str,
    output_dir: Path = TEST_RESULTS_DIR,
) -> dict | None:
    network_path = output_dir / network_filename_for_test(test_filename)
    if not network_path.exists():
        return None
    return json.loads(network_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Per-run metrics
# ---------------------------------------------------------------------------

def build_phase1_metrics(
    result: ExecutionResult,
    generated_tests_dir: Path,
    test_results_dir: Path,
    msa_spec: str = "",
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

    network_capture = load_network_capture(result.filename, output_dir=test_results_dir)
    if network_capture:
        requests = list(network_capture.get("requests", []))
        frontend_api_call_count = len(requests)
        resolved_msa_spec = msa_spec or load_msa_spec_text()
        frontend_api_calls_by_service = count_api_calls_by_service(
            requests=requests,
            msa_spec=resolved_msa_spec,
        )
        unmapped_api_calls = list_unmapped_api_calls(
            requests=requests,
            msa_spec=resolved_msa_spec,
        )

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
        frontend_api_calls_by_service=frontend_api_calls_by_service,
        unmapped_api_calls=unmapped_api_calls,
        failure_kind=failure_kind,
        failure_signature=failure_signature,
    )


# ---------------------------------------------------------------------------
# Evaluation history and summary persistence
# ---------------------------------------------------------------------------

def append_evaluation_history(
    report: ExecutionReport,
    output_dir: Path = TEST_RESULTS_DIR,
) -> Path:
    output_dir.mkdir(exist_ok=True)
    record = report.to_dict()
    record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    history_path = evaluation_history_path(output_dir)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")
    write_evaluation_summary(output_dir=output_dir)
    return history_path


def load_evaluation_history(output_dir: Path = TEST_RESULTS_DIR) -> list[dict]:
    records: list[dict] = []
    for history_path in (
        legacy_history_path(output_dir),
        evaluation_history_path(output_dir),
    ):
        if not history_path.exists():
            continue
        for line in history_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            records.append(json.loads(stripped))
    return records


def write_evaluation_summary(output_dir: Path = TEST_RESULTS_DIR) -> Path:
    records = load_evaluation_history(output_dir)
    summary_path = evaluation_summary_path(output_dir)
    summary_path.write_text(render_evaluation_summary(records), encoding="utf-8")
    return summary_path
