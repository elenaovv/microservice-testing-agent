"""Core reporting: report/journey builders and file I/O.

Heavy analysis helpers live in:
  - core.coverage_utils  – MSA spec parsing and endpoint/service inference
  - core.evaluation_utils – run metrics, failure analysis, and summary rendering
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
    ExecutionArtifact,
    ExecutionReport,
    ExecutionResult,
    JourneyCapture,
    JourneyGuide,
)
from core.evaluation_utils import build_phase1_metrics, load_network_capture

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
    )


def build_execution_report(
    result: ExecutionResult,
    journey_guide: JourneyGuide | None = None,
    generated_tests_dir: Path = GENERATED_TESTS_DIR,
    test_results_dir: Path = TEST_RESULTS_DIR,
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
    if journey_guide is not None:
        coverage = journey_guide.coverage
        requested_journey = journey_guide.requested_journey
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
    if coverage is not None and network_capture is not None:
        coverage = apply_operation_coverage(
            coverage=coverage,
            requests=list(network_capture.get("requests", [])),
            msa_spec=load_msa_spec_text(),
        )
    phase1 = build_phase1_metrics(
        result=result,
        generated_tests_dir=generated_tests_dir,
        test_results_dir=test_results_dir,
    )

    return ExecutionReport(
        filename=result.filename,
        status=status,
        exit_code=result.exit_code,
        summary=summary,
        details=result.output.strip(),
        requested_journey=requested_journey,
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
    output_dir.mkdir(exist_ok=True)
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
    output_dir.mkdir(exist_ok=True)
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


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_execution_report(report: ExecutionReport) -> str:
    lines = [
        "Execution report:",
        f"- file: {report.filename}",
        f"- status: {report.status}",
        f"- exit_code: {report.exit_code}",
        f"- summary: {report.summary}",
    ]

    if report.artifacts:
        artifact_summary = ", ".join(
            f"{artifact.kind}={artifact.path}" for artifact in report.artifacts
        )
        lines.append(f"- artifacts: {artifact_summary}")
    else:
        lines.append("- artifacts: none")

    if report.report_path is not None:
        lines.append(f"- report: {report.report_path}")

    if report.coverage is not None:
        lines.append(f"- coverage.ui_steps: {report.coverage.ui_step_count}")
        lines.append(f"- coverage.unique_actions: {report.coverage.unique_action_count}")
        lines.append(f"- coverage.timed_steps: {report.coverage.timed_step_count}")
        lines.append(
            f"- coverage.endpoint_candidates: {report.coverage.endpoint_candidate_count}"
        )
        lines.append(
            f"- coverage.services: {report.coverage.service_candidate_count}"
        )
        if report.coverage.service_operation_totals:
            operation_summary = ", ".join(
                f"{service}={report.coverage.service_operation_covered.get(service, 0)}/{total}"
                for service, total in sorted(
                    report.coverage.service_operation_totals.items()
                )
            )
            lines.append(f"- coverage.operations: {operation_summary}")

    if report.phase1 is not None:
        lines.append(f"- phase1.blocked: {report.phase1.blocked}")
        lines.append(f"- phase1.syntax_valid: {report.phase1.syntax_valid}")
        lines.append(
            f"- phase1.suspected_false_positive: {report.phase1.suspected_false_positive}"
        )
        lines.append(f"- phase1.gui_elements: {report.phase1.gui_element_count}")
        lines.append(
            f"- phase1.frontend_api_calls: {report.phase1.frontend_api_call_count}"
        )
        if report.phase1.failure_kind:
            lines.append(f"- phase1.failure_kind: {report.phase1.failure_kind}")

    if report.details:
        lines.extend(
            [
                "",
                "Raw output:",
                report.details,
            ]
        )

    return "\n".join(lines)


def render_journey_guide_summary(guide: JourneyGuide) -> str:
    lines = [
        "Journey guide saved:",
    ]
    if guide.markdown_path is not None:
        lines.append(f"- markdown: {guide.markdown_path}")
    if guide.json_path is not None:
        lines.append(f"- json: {guide.json_path}")
    lines.append(f"- requested_journey: {guide.requested_journey}")
    lines.append(f"- ui_steps: {guide.coverage.ui_step_count}")
    lines.append(f"- unique_actions: {guide.coverage.unique_action_count}")
    lines.append(f"- timed_steps: {guide.coverage.timed_step_count}")
    lines.append(f"- endpoint_candidates: {guide.coverage.endpoint_candidate_count}")
    lines.append(f"- services: {guide.coverage.service_candidate_count}")
    return "\n".join(lines)


def render_journey_guide(guide: JourneyGuide) -> str:
    lines = [
        "# Journey Guide",
        "",
        f"Requested journey: {guide.requested_journey}",
        f"Target test file: {guide.test_filename}",
        "",
        "## UI Steps",
    ]

    if guide.capture.actions:
        for index, step in enumerate(guide.capture.actions, start=1):
            lines.append(f"{index}. {step.action}")
            lines.append(f"   Note: {step.note}")
    else:
        lines.append("No UI steps were recorded.")

    lines.extend(
        [
            "",
            "## Timings",
        ]
    )
    if guide.capture.timings:
        for sample in guide.capture.timings:
            lines.append(f"- {sample.name}: {sample.elapsed_seconds:.1f}s")
    else:
        lines.append("No timings were recorded.")

    lines.extend(
        [
            "",
            "## Coverage Snapshot",
            f"- UI steps: {guide.coverage.ui_step_count}",
            f"- Unique actions: {guide.coverage.unique_action_count}",
            f"- Timed steps: {guide.coverage.timed_step_count}",
            f"- Endpoint candidates: {guide.coverage.endpoint_candidate_count}",
            f"- Services: {guide.coverage.service_candidate_count}",
        ]
    )

    if guide.coverage.endpoint_candidates:
        lines.append("")
        lines.append("### Endpoint Candidates")
        for candidate in guide.coverage.endpoint_candidates:
            lines.append(f"- {candidate}")

    if guide.coverage.service_candidates:
        lines.append("")
        lines.append("### Service Candidates")
        for candidate in guide.coverage.service_candidates:
            lines.append(f"- {candidate}")

    if guide.coverage.notes:
        lines.append("")
        lines.append("### Coverage Notes")
        for note in guide.coverage.notes:
            lines.append(f"- {note}")

    return "\n".join(lines)
