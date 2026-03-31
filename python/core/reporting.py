import ast
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
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
    Phase1Metrics,
)

TEST_RESULTS_DIR = Path("test-results")
GENERATED_TESTS_DIR = Path("generated-tests")
PHASE1_HISTORY_FILENAME = "phase1-runs.jsonl"
PHASE1_SUMMARY_FILENAME = "phase1-summary.md"
MSA_SPEC_PATH = Path(__file__).resolve().parent.parent / "spec" / "msa.yaml"
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
GUI_PATTERN = re.compile(
    r"(page\.(?:get_by_[a-z_]+|locator|click|fill|check|uncheck|press|select_option|hover)\([^\n]+\)|expect\([^\n]+\))"
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


def build_phase1_metrics(
    result: ExecutionResult,
    generated_tests_dir: Path = GENERATED_TESTS_DIR,
    test_results_dir: Path = TEST_RESULTS_DIR,
) -> Phase1Metrics:
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

    network_capture = load_network_capture(result.filename, output_dir=test_results_dir)
    if network_capture:
        requests = list(network_capture.get("requests", []))
        frontend_api_call_count = len(requests)
        frontend_api_calls_by_service = count_api_calls_by_service(
            requests=requests,
            msa_spec=load_msa_spec_text(),
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
        failure_kind=failure_kind,
        failure_signature=failure_signature,
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


def load_execution_report(
    filename: str,
    output_dir: Path = TEST_RESULTS_DIR,
) -> ExecutionReport | None:
    report_path = output_dir / report_filename_for_test(filename)
    if not report_path.exists():
        return None
    data = json.loads(report_path.read_text(encoding="utf-8"))
    return ExecutionReport.from_dict(data)


def report_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.report.json"


def journey_markdown_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.journey.md"


def journey_json_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.journey.json"


def network_filename_for_test(filename: str) -> str:
    base_name = Path(filename).stem
    return f"{base_name}.network.json"


def phase1_history_path(output_dir: Path = TEST_RESULTS_DIR) -> Path:
    return output_dir / PHASE1_HISTORY_FILENAME


def phase1_summary_path(output_dir: Path = TEST_RESULTS_DIR) -> Path:
    return output_dir / PHASE1_SUMMARY_FILENAME


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


def load_network_capture(
    test_filename: str,
    output_dir: Path = TEST_RESULTS_DIR,
) -> dict | None:
    network_path = output_dir / network_filename_for_test(test_filename)
    if not network_path.exists():
        return None
    return json.loads(network_path.read_text(encoding="utf-8"))


def append_phase1_history(
    report: ExecutionReport,
    output_dir: Path = TEST_RESULTS_DIR,
) -> Path:
    output_dir.mkdir(exist_ok=True)
    record = report.to_dict()
    record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    history_path = phase1_history_path(output_dir)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")
    write_phase1_summary(output_dir=output_dir)
    return history_path


def load_phase1_history(output_dir: Path = TEST_RESULTS_DIR) -> list[dict]:
    history_path = phase1_history_path(output_dir)
    if not history_path.exists():
        return []

    records: list[dict] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        records.append(json.loads(stripped))
    return records


def write_phase1_summary(output_dir: Path = TEST_RESULTS_DIR) -> Path:
    records = load_phase1_history(output_dir)
    summary_path = phase1_summary_path(output_dir)
    summary_path.write_text(render_phase1_summary(records), encoding="utf-8")
    return summary_path


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


def render_phase1_summary(records: list[dict]) -> str:
    lines = [
        "# Phase 1 Metrics",
        "",
        f"Recorded runs: {len(records)}",
        "Target runs per journey for statistical relevance: 10",
        "",
    ]

    if not records:
        lines.append("No Phase 1 runs recorded yet.")
        return "\n".join(lines)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        journey = str(record.get("requested_journey") or record.get("filename") or "unknown")
        grouped[journey].append(record)

    lines.extend(
        [
            "## Journey Summary",
            "",
            "| Journey | Runs | Generated | Pass | Fail | Blocked | Syntax invalid | Suspected FP | Variants | Stability | Same fault | Avg GUI | Avg API | Avg lines |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |",
        ]
    )

    for journey, journey_records in sorted(grouped.items()):
        phase1_records = [record.get("phase1") or {} for record in journey_records]
        hashes = [
            str(phase1.get("generated_test_hash", ""))
            for phase1 in phase1_records
            if phase1.get("generated_test_hash")
        ]
        hash_counts = Counter(hashes)
        most_common_hash_count = hash_counts.most_common(1)[0][1] if hash_counts else 0
        failure_signatures = {
            str(phase1.get("failure_signature", "")).strip()
            for phase1 in phase1_records
            if str(phase1.get("failure_signature", "")).strip()
        }
        same_fault = "n/a"
        if failure_signatures:
            same_fault = "yes" if len(failure_signatures) == 1 else "no"

        lines.append(
            "| {journey} | {runs} | {generated} | {passed} | {failed} | {blocked} | {syntax_invalid} | {suspected_fp} | {variants} | {stability} | {same_fault} | {avg_gui:.1f} | {avg_api:.1f} | {avg_lines:.1f} |".format(
                journey=escape_md_cell(journey),
                runs=len(journey_records),
                generated=count_true(phase1_records, "generated_test"),
                passed=count_status(journey_records, "passed"),
                failed=count_status(journey_records, "failed"),
                blocked=count_true(phase1_records, "blocked"),
                syntax_invalid=count_false(phase1_records, "syntax_valid"),
                suspected_fp=count_true(phase1_records, "suspected_false_positive"),
                variants=len(hash_counts) or 0,
                stability=format_stability(most_common_hash_count, len(journey_records)),
                same_fault=same_fault,
                avg_gui=average_int(phase1_records, "gui_element_count"),
                avg_api=average_int(phase1_records, "frontend_api_call_count"),
                avg_lines=average_int(phase1_records, "generated_test_lines"),
            )
        )

    lines.extend(
        [
            "",
            "## Recent Runs",
            "",
            "| Recorded at | Journey | File | Status | Blocked | Failure kind | GUI | API | Lines |",
            "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |",
        ]
    )

    for record in sorted(
        records,
        key=lambda item: str(item.get("recorded_at", "")),
        reverse=True,
    )[:20]:
        phase1 = record.get("phase1") or {}
        lines.append(
            "| {recorded_at} | {journey} | {filename} | {status} | {blocked} | {failure_kind} | {gui} | {api} | {lines_count} |".format(
                recorded_at=escape_md_cell(str(record.get("recorded_at", ""))),
                journey=escape_md_cell(str(record.get("requested_journey") or "")),
                filename=escape_md_cell(str(record.get("filename", ""))),
                status=escape_md_cell(str(record.get("status", ""))),
                blocked=phase1.get("blocked", False),
                failure_kind=escape_md_cell(str(phase1.get("failure_kind", ""))),
                gui=int(phase1.get("gui_element_count", 0)),
                api=int(phase1.get("frontend_api_call_count", 0)),
                lines_count=int(phase1.get("generated_test_lines", 0)),
            )
        )

    fault_rows = build_fault_rows(grouped)
    if fault_rows:
        lines.extend(
            [
                "",
                "## Failure Distribution",
                "",
                "| Journey | Failure kind | Failure signature | Count |",
                "| --- | --- | --- | ---: |",
            ]
        )
        lines.extend(fault_rows)

    service_rows = build_service_rows(grouped)
    if service_rows:
        lines.extend(
            [
                "",
                "## Frontend API Calls By Service",
                "",
                "| Journey | Service | Calls |",
                "| --- | --- | ---: |",
            ]
        )
        lines.extend(service_rows)

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


def count_gui_elements_checked(code: str) -> int:
    if not code.strip():
        return 0
    return len({match.group(1).strip() for match in GUI_PATTERN.finditer(code)})


def load_msa_spec_text(path: Path = MSA_SPEC_PATH) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def count_api_calls_by_service(
    requests: list[dict],
    msa_spec: str,
) -> dict[str, int]:
    endpoints = extract_spec_endpoints(msa_spec)
    counts: dict[str, int] = defaultdict(int)
    for request in requests:
        method = str(request.get("method", "")).upper()
        path = str(request.get("path", ""))
        service_name = match_service_for_request(path, method, endpoints)
        counts[service_name] += 1
    return dict(sorted(counts.items()))


def match_service_for_request(
    request_path: str,
    request_method: str,
    endpoints: list[dict[str, str]],
) -> str:
    for endpoint in endpoints:
        endpoint_method = endpoint.get("method", "").upper()
        if endpoint_method and endpoint_method != request_method:
            continue
        endpoint_path = endpoint.get("path", "")
        placeholder_path = re.sub(r"\{[^/]+\}", "__PARAM__", endpoint_path)
        endpoint_regex = "^" + re.escape(placeholder_path).replace(
            "__PARAM__",
            r"[^/]+",
        ) + "$"
        if re.match(endpoint_regex, request_path):
            return endpoint.get("service", "unmapped")
    return "unmapped"


def count_status(records: list[dict], status: str) -> int:
    return sum(1 for record in records if record.get("status") == status)


def count_true(records: list[dict], key: str) -> int:
    return sum(1 for record in records if bool(record.get(key)))


def count_false(records: list[dict], key: str) -> int:
    return sum(1 for record in records if key in record and not bool(record.get(key)))


def average_int(records: list[dict], key: str) -> float:
    values = [int(record.get(key, 0)) for record in records]
    if not values:
        return 0.0
    return sum(values) / len(values)


def format_stability(most_common: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{(most_common / total) * 100:.0f}% ({most_common}/{total})"


def build_fault_rows(grouped_records: dict[str, list[dict]]) -> list[str]:
    rows: list[str] = []
    for journey, records in sorted(grouped_records.items()):
        counter: Counter[tuple[str, str]] = Counter()
        for record in records:
            phase1 = record.get("phase1") or {}
            failure_kind = str(phase1.get("failure_kind", "")).strip()
            failure_signature = str(phase1.get("failure_signature", "")).strip()
            if not failure_kind or not failure_signature:
                continue
            counter[(failure_kind, failure_signature)] += 1
        for (failure_kind, failure_signature), count in counter.most_common():
            rows.append(
                f"| {escape_md_cell(journey)} | {escape_md_cell(failure_kind)} | {escape_md_cell(failure_signature)} | {count} |"
            )
    return rows


def build_service_rows(grouped_records: dict[str, list[dict]]) -> list[str]:
    rows: list[str] = []
    for journey, records in sorted(grouped_records.items()):
        counts: dict[str, int] = defaultdict(int)
        for record in records:
            phase1 = record.get("phase1") or {}
            for service, count in dict(phase1.get("frontend_api_calls_by_service", {})).items():
                counts[str(service)] += int(count)
        for service, count in sorted(counts.items()):
            rows.append(f"| {escape_md_cell(journey)} | {escape_md_cell(service)} | {count} |")
    return rows


def escape_md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()
