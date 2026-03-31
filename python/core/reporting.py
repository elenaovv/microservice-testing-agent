from pathlib import Path
import json
import re

from core.models import (
    CoverageSnapshot,
    ExecutionArtifact,
    ExecutionReport,
    ExecutionResult,
    JourneyCapture,
    JourneyGuide,
)

TEST_RESULTS_DIR = Path("test-results")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "after",
    "before",
    "page",
    "button",
    "form",
    "user",
    "users",
    "ticket",
    "tickets",
    "train",
    "route",
    "booking",
    "book",
    "clicked",
    "click",
    "waited",
    "verified",
    "verify",
    "opened",
    "open",
    "page",
}


def build_execution_report(
    result: ExecutionResult,
    journey_guide: JourneyGuide | None = None,
) -> ExecutionReport:
    status = "passed" if result.succeeded else "failed"
    summary = (
        f"Test '{result.filename}' passed."
        if result.succeeded
        else f"Test '{result.filename}' failed."
    )

    artifacts = result.artifacts.copy()
    coverage = None
    if journey_guide is not None:
        coverage = journey_guide.coverage
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

    return ExecutionReport(
        filename=result.filename,
        status=status,
        exit_code=result.exit_code,
        summary=summary,
        details=result.output.strip(),
        artifacts=artifacts,
        coverage=coverage,
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
        notes=notes,
    )


def write_execution_report(
    report: ExecutionReport,
    output_dir: Path = TEST_RESULTS_DIR,
) -> Path:
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / report_filename_for_test(report.filename)
    report.report_path = report_path
    report_path.write_text(report.to_json(), encoding="utf-8")
    return report_path


def report_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.report.json"


def journey_markdown_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.journey.md"


def journey_json_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.journey.json"


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


def infer_endpoint_candidates(
    requested_journey: str,
    capture: JourneyCapture,
    msa_spec: str,
) -> list[str]:
    tokens = coverage_tokens(requested_journey, capture)
    if not tokens:
        return []

    candidates: list[str] = []
    for endpoint in extract_spec_endpoints(msa_spec):
        haystack = " ".join(endpoint.values()).lower()
        matched = [token for token in tokens if token in haystack]
        if matched:
            label = (
                f"{endpoint['method']} {endpoint['path']}"
                f" ({endpoint['service']})"
            )
            if endpoint["description"]:
                label += f" - {endpoint['description']}"
            candidates.append(label)

    return dedupe_preserve_order(candidates)


def coverage_tokens(
    requested_journey: str,
    capture: JourneyCapture,
) -> set[str]:
    capture_text = " ".join(
        f"{step.action} {step.note}" for step in capture.actions
    )
    text = f"{requested_journey} {capture_text}".lower()
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", text)
        if len(token) > 2 and token not in STOPWORDS
    }


def extract_spec_endpoints(msa_spec: str) -> list[dict[str, str]]:
    endpoints: list[dict[str, str]] = []
    current_service = ""
    current_endpoint: dict[str, str] | None = None

    for raw_line in msa_spec.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if indent == 4 and stripped.endswith(":") and not stripped.startswith("- "):
            current_service = stripped[:-1]
            continue

        if stripped.startswith("- path:"):
            if current_endpoint is not None:
                endpoints.append(current_endpoint)
            current_endpoint = {
                "service": current_service,
                "path": stripped.split(":", 1)[1].strip(),
                "method": "",
                "description": "",
            }
            continue

        if current_endpoint is None:
            continue

        if stripped.startswith("method:"):
            current_endpoint["method"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("description:"):
            current_endpoint["description"] = stripped.split(":", 1)[1].strip()
        elif indent <= 4 and stripped:
            endpoints.append(current_endpoint)
            current_endpoint = None

    if current_endpoint is not None:
        endpoints.append(current_endpoint)

    return endpoints


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def extract_service_name(endpoint_label: str) -> str:
    match = re.search(r"\(([^()]+)\)", endpoint_label)
    if match is None:
        return ""
    return match.group(1).strip()
