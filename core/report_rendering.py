"""Rendering helpers for execution reports and journey guides."""

from core.models import ExecutionReport, JourneyGuide

# ---------------------------------------------------------------------------
# Execution report rendering
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

    if report.evaluation is not None:
        lines.append(f"- evaluation.variant: {report.evaluation.variant_label}")
        lines.append(f"- evaluation.run_kind: {report.evaluation.run_kind}")
        lines.append(f"- evaluation.base_url: {report.evaluation.base_url}")
        if report.evaluation.mutation_id:
            lines.append(f"- evaluation.mutation_id: {report.evaluation.mutation_id}")
        if report.evaluation.fault_service:
            lines.append(
                f"- evaluation.fault_service: {report.evaluation.fault_service}"
            )

    if report.phase1 is not None:
        lines.append(f"- phase1.blocked: {report.phase1.blocked}")
        lines.append(f"- phase1.syntax_valid: {report.phase1.syntax_valid}")
        lines.append(
            f"- phase1.suspected_false_positive: {report.phase1.suspected_false_positive}"
        )
        lines.append(
            f"- phase1.generated_test_hash: {report.phase1.generated_test_hash or '-'}"
        )
        if report.phase1.max_retries > 0:
            lines.append(
                f"- phase1.retries_used: {report.phase1.retries_used}/{report.phase1.max_retries}"
            )
            lines.append(
                f"- phase1.test_attempts: {report.phase1.test_attempts}"
            )
            lines.append(
                f"- phase1.failed_attempts: {report.phase1.failed_attempts}"
            )
        lines.append(f"- phase1.gui_elements: {report.phase1.gui_element_count}")
        lines.append(
            f"- phase1.frontend_api_calls: {report.phase1.frontend_api_call_count}"
        )
        lines.append(
            f"- phase1.unmapped_api_calls: {len(report.phase1.unmapped_api_calls)}"
        )
        if report.phase1.failure_kind:
            lines.append(f"- phase1.failure_kind: {report.phase1.failure_kind}")

    if report.use_case is not None:
        lines.append(f"- use_case.id: {report.use_case.id}")
        lines.append(f"- use_case.name: {report.use_case.name}")
        if report.use_case.reference_bucket:
            lines.append(
                f"- use_case.reference_bucket: {report.use_case.reference_bucket}"
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

# ---------------------------------------------------------------------------
# Journey guide rendering
# ---------------------------------------------------------------------------

def render_journey_guide_summary(guide: JourneyGuide) -> str:
    lines = [
        "Journey guide saved:",
    ]
    if guide.markdown_path is not None:
        lines.append(f"- markdown: {guide.markdown_path}")
    if guide.json_path is not None:
        lines.append(f"- json: {guide.json_path}")
    lines.append(f"- requested_journey: {guide.requested_journey}")
    if guide.use_case is not None:
        lines.append(f"- use_case.id: {guide.use_case.id}")
        lines.append(f"- use_case.name: {guide.use_case.name}")
        if guide.use_case.reference_bucket:
            lines.append(f"- use_case.reference_bucket: {guide.use_case.reference_bucket}")
    lines.append(f"- ui_steps: {guide.coverage.ui_step_count}")
    lines.append(f"- unique_actions: {guide.coverage.unique_action_count}")
    lines.append(f"- timed_steps: {guide.coverage.timed_step_count}")
    lines.append(f"- endpoint_candidates: {guide.coverage.endpoint_candidate_count}")
    lines.append(f"- services: {guide.coverage.service_candidate_count}")
    lines.append(f"- browse_api_requests: {len(guide.browse_network_requests)}")
    return "\n".join(lines)

def render_journey_guide(guide: JourneyGuide) -> str:
    lines = [
        "# Journey Guide",
        "",
        f"Requested journey: {guide.requested_journey}",
        f"Target test file: {guide.test_filename}",
        "",
    ]

    if guide.use_case is not None:
        lines.extend(
            [
                "## Structured Use Case",
                f"- ID: {guide.use_case.id}",
                f"- Name: {guide.use_case.name}",
            ]
        )
        if guide.use_case.role:
            lines.append(f"- Role: {guide.use_case.role}")
        if guide.use_case.reference_bucket:
            lines.append(f"- Reference bucket: {guide.use_case.reference_bucket}")
        if guide.use_case.source_path:
            lines.append(f"- Source file: {guide.use_case.source_path}")
        lines.append("")

    lines.append("## UI Steps")

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

    if guide.browse_network_requests:
        lines.append("")
        lines.append("### Browse Network Requests")
        for item in guide.browse_network_requests:
            method = str(item.get("method", "")).upper().strip()
            path = str(item.get("path", "")).strip()
            url = str(item.get("url", "")).strip()
            if method and path:
                lines.append(f"- {method} {path}")
            elif url:
                lines.append(f"- {url}")

    return "\n".join(lines)
