from core.models import ExecutionReport, ExecutionResult


def build_execution_report(result: ExecutionResult) -> ExecutionReport:
    status = "passed" if result.succeeded else "failed"
    summary = (
        f"Test '{result.filename}' passed."
        if result.succeeded
        else f"Test '{result.filename}' failed."
    )

    return ExecutionReport(
        filename=result.filename,
        status=status,
        exit_code=result.exit_code,
        summary=summary,
        details=result.output.strip(),
        artifacts=result.artifacts.copy(),
    )


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

    if report.details:
        lines.extend(
            [
                "",
                "Raw output:",
                report.details,
            ]
        )

    return "\n".join(lines)
