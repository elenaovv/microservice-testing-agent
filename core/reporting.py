"""Core reporting: report/journey builders and file I/O.

Heavy analysis helpers live in:
  - core.coverage_utils  – MSA spec parsing and endpoint/service inference
  - core.inference       – code and failure analysis
  - core.evaluation_rendering – evaluation summary markdown rendering
  - core.report_rendering     – execution-report and journey-guide rendering
"""

import json
from pathlib import Path

from core.coverage_utils import (
    apply_operation_coverage,
    dedupe_preserve_order,
    extract_service_name,
    infer_endpoint_candidates,
    load_msa_spec_text,
    service_operation_totals,
)
from core.models import (
    CoverageSnapshot,
    EvaluationContext,
    ExecutionArtifact,
    ExecutionReport,
    ExecutionResult,
    JourneyCapture,
    JourneyGuide,
    UseCaseMetadata,
)
from core.evaluation_utils import build_phase1_metrics, load_network_capture
from core.journey_contract import build_journey_contract
from core.report_rendering import render_journey_guide

TEST_RESULTS_DIR = Path("test-results")
GENERATED_TESTS_DIR = Path("generated-tests")


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------


def report_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.report.json"


def journey_markdown_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.journey.md"


def journey_json_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.journey.json"


# ---------------------------------------------------------------------------
# Core builders
# ---------------------------------------------------------------------------


def build_coverage_snapshot(
    requested_journey: str,
    capture: JourneyCapture,
    msa_spec: str,
) -> CoverageSnapshot:
    action_names = [step.action for step in capture.actions]
    unique_action_count = len(set(action_names))
    endpoint_candidates = infer_endpoint_candidates(
        requested_journey=requested_journey,
        capture=capture,
        msa_spec=msa_spec,
    )
    service_candidates: list[str] = []
    for endpoint_label in endpoint_candidates:
        service_name = extract_service_name(endpoint_label)
        if service_name:
            service_candidates.append(service_name)
    service_candidates = dedupe_preserve_order(service_candidates)
    notes = [
        "UI coverage currently uses logged browser steps, not DOM-level node instrumentation.",
        "Endpoint coverage is heuristic and based on matching journey text plus logged actions against the MSA spec.",
        "Service coverage is derived from the endpoint candidates and acts as a first-pass node coverage estimate.",
    ]
    return CoverageSnapshot(
        ui_step_count=len(capture.actions),
        unique_action_count=unique_action_count,
        timed_step_count=len(capture.timings),
        endpoint_candidate_count=len(endpoint_candidates),
        service_candidate_count=len(service_candidates),
        endpoint_candidates=endpoint_candidates,
        service_candidates=service_candidates,
        service_operation_totals=service_operation_totals(msa_spec),
        service_operation_covered={},
        covered_operations_by_service={},
        notes=notes,
    )


def build_journey_guide(
    test_filename: str,
    requested_journey: str,
    capture: JourneyCapture,
    msa_spec: str,
    use_case: UseCaseMetadata | None = None,
    browse_network_requests: list[dict[str, str]] | None = None,
    msa_spec_path: str = "",
) -> JourneyGuide:
    coverage = build_coverage_snapshot(
        requested_journey=requested_journey,
        capture=capture,
        msa_spec=msa_spec,
    )
    return JourneyGuide(
        test_filename=test_filename,
        requested_journey=requested_journey,
        capture=capture.clone(),
        coverage=coverage,
        use_case=use_case,
        browse_network_requests=list(browse_network_requests or []),
        contract=build_journey_contract(requested_journey, capture),
        msa_spec_path=msa_spec_path,
    )


def build_execution_report(
    result: ExecutionResult,
    journey_guide: JourneyGuide | None = None,
    generated_tests_dir: Path = GENERATED_TESTS_DIR,
    test_results_dir: Path = TEST_RESULTS_DIR,
    evaluation: EvaluationContext | None = None,
    msa_spec_path: str | None = None,
    max_retries: int = -1,
    test_attempts: int = 0,
    failed_test_attempts: int = 0,
) -> ExecutionReport:
    status = "passed" if result.succeeded else "failed"
    summary = (
        f"Test '{result.filename}' passed."
        if result.succeeded
        else f"Test '{result.filename}' failed."
    )

    artifacts = result.artifacts.copy()
    coverage = None
    requested_journey = None
    use_case = None
    if journey_guide is not None:
        coverage = journey_guide.coverage
        requested_journey = journey_guide.requested_journey
        use_case = journey_guide.use_case
        if journey_guide.markdown_path is not None:
            artifacts.append(
                ExecutionArtifact(
                    kind="journey-guide",
                    path=journey_guide.markdown_path,
                )
            )
        if journey_guide.json_path is not None:
            artifacts.append(
                ExecutionArtifact(
                    kind="journey-json",
                    path=journey_guide.json_path,
                )
            )
    network_capture = load_network_capture(
        result.filename,
        output_dir=test_results_dir,
    )
    resolved_msa_spec_path = (
        msa_spec_path
        or (journey_guide.msa_spec_path if journey_guide is not None else "")
    )
    msa_spec_text = (
        load_msa_spec_text(Path(resolved_msa_spec_path))
        if resolved_msa_spec_path
        else load_msa_spec_text()
    )
    if coverage is not None and network_capture is not None:
        coverage = apply_operation_coverage(
            coverage=coverage,
            requests=list(network_capture.get("requests", [])),
            msa_spec=msa_spec_text,
        )
    phase1 = build_phase1_metrics(
        result=result,
        generated_tests_dir=generated_tests_dir,
        test_results_dir=test_results_dir,
        msa_spec=msa_spec_text,
        max_retries=max_retries,
        test_attempts=test_attempts,
        failed_test_attempts=failed_test_attempts,
        browse_api_calls=list(journey_guide.browse_network_requests) if journey_guide is not None else None,
        journey_contract=journey_guide.contract if journey_guide is not None else None,
    )

    return ExecutionReport(
        filename=result.filename,
        status=status,
        exit_code=result.exit_code,
        summary=summary,
        details=result.output.strip(),
        requested_journey=requested_journey,
        use_case=use_case,
        evaluation=evaluation,
        artifacts=artifacts,
        coverage=coverage,
        phase1=phase1,
    )


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def write_execution_report(
    report: ExecutionReport,
    output_dir: Path = TEST_RESULTS_DIR,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / report_filename_for_test(report.filename)
    report.report_path = report_path
    report_path.write_text(report.to_json(), encoding="utf-8")
    return report_path


def load_execution_report(
    filename: str,
    output_dir: Path = TEST_RESULTS_DIR,
) -> ExecutionReport | None:
    report_path = output_dir / report_filename_for_test(filename)
    if not report_path.exists():
        return None
    data = json.loads(report_path.read_text(encoding="utf-8"))
    return ExecutionReport.from_dict(data)


def write_journey_guide(
    guide: JourneyGuide,
    output_dir: Path = TEST_RESULTS_DIR,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / journey_markdown_filename_for_test(guide.test_filename)
    json_path = output_dir / journey_json_filename_for_test(guide.test_filename)
    guide.markdown_path = markdown_path
    guide.json_path = json_path
    markdown_path.write_text(render_journey_guide(guide), encoding="utf-8")
    json_path.write_text(guide.to_json(), encoding="utf-8")
    return markdown_path, json_path


def load_journey_guide(
    test_filename: str,
    output_dir: Path = TEST_RESULTS_DIR,
) -> JourneyGuide | None:
    json_path = output_dir / journey_json_filename_for_test(test_filename)
    if not json_path.exists():
        return None
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return JourneyGuide.from_dict(data)
