"""Evaluation metrics: run analysis, history, and summary rendering across phases."""

import ast
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from core.coverage_utils import count_api_calls_by_service, load_msa_spec_text
from core.models import ExecutionReport, ExecutionResult, Phase1Metrics
from core.mutation_utils import (
    build_phase3_fault_rows,
    build_phase3_mutation_rows,
    build_phase3_operation_rows,
    evaluation_fields,
    has_phase3_context,
)

GUI_PATTERN = re.compile(
    r"(page\.(?:get_by_[a-z_]+|locator|click|fill|check|uncheck|press|select_option|hover)\([^\n]+\)|expect\([^\n]+\))"
)
TEST_RESULTS_DIR = Path("test-results")
EVALUATION_HISTORY_FILENAME = "evaluation-runs.jsonl"
LEGACY_HISTORY_FILENAME = "phase1-runs.jsonl"
EVALUATION_SUMMARY_FILENAME = "evaluation-summary.md"

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


def build_phase1_metrics(
    result: ExecutionResult,
    generated_tests_dir: Path,
    test_results_dir: Path,
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
    for history_path in (legacy_history_path(output_dir), evaluation_history_path(output_dir)):
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

def escape_md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()

def add_column_guide(
    lines: list[str],
    title: str,
    descriptions: list[str],
) -> None:
    lines.extend(
        [
            f"### {title}",
            "",
        ]
    )
    for description in descriptions:
        lines.append(f"- {description}")
    lines.append("")


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


def build_phase2_operation_rows(grouped_records: dict[str, list[dict]]) -> list[str]:
    rows: list[str] = []
    for journey, records in sorted(grouped_records.items()):
        totals: dict[str, int] = {}
        covered_operations: dict[str, set[str]] = defaultdict(set)
        for record in records:
            coverage = record.get("coverage") or {}
            for service, total in dict(coverage.get("service_operation_totals", {})).items():
                totals[str(service)] = int(total)
            for service, operations in dict(
                coverage.get("covered_operations_by_service", {})
            ).items():
                covered_operations[str(service)].update(str(item) for item in operations)

        for service, total in sorted(totals.items()):
            covered = sorted(covered_operations.get(service, set()))
            coverage_pct = 0.0
            if total > 0:
                coverage_pct = (len(covered) / total) * 100
            rows.append(
                "| {journey} | {service} | {covered_count} | {total} | {coverage_pct:.1f}% | {operations} |".format(
                    journey=escape_md_cell(journey),
                    service=escape_md_cell(service),
                    covered_count=len(covered),
                    total=total,
                    coverage_pct=coverage_pct,
                    operations=escape_md_cell(", ".join(covered) if covered else "-"),
                )
            )
    return rows


def render_evaluation_summary(records: list[dict]) -> str:
    lines = [
        "# Evaluation Metrics",
        "",
        f"Recorded runs: {len(records)}",
        "Target runs per journey for statistical relevance: 10",
        "",
    ]

    if not records:
        lines.append("No evaluation runs recorded yet.")
        return "\n".join(lines)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        journey = str(record.get("requested_journey") or record.get("filename") or "unknown")
        grouped[journey].append(record)

    fault_rows = build_fault_rows(grouped)
    service_rows = build_service_rows(grouped)
    phase2_rows = build_phase2_operation_rows(grouped)
    has_phase3 = any(has_phase3_context(record) for record in records)
    phase3_mutation_rows = build_phase3_mutation_rows(grouped) if has_phase3 else []
    phase3_fault_rows = build_phase3_fault_rows(records) if has_phase3 else []
    phase3_operation_rows = build_phase3_operation_rows(grouped) if has_phase3 else []

    lines.extend(
        [
            "## Column Guide",
            "",
        ]
    )
    add_column_guide(
        lines,
        "Phase 1 Journey Summary",
        [
            "`Journey` is the requested journey text or filename fallback; `Runs`, `Generated`, `Pass`, and `Fail` are run counts.",
            "`Blocked` means the run failed before meaningful execution, `Syntax invalid` means invalid Python, `Suspected FP` means a likely false positive, `Variants` counts distinct generated code hashes, `Stability` is the share of runs using the most common hash, `Same fault` checks whether all failures share one signature, and `Avg GUI`/`Avg API`/`Avg lines` are averages for GUI checks, frontend API calls, and test size.",
        ],
    )
    add_column_guide(
        lines,
        "Phase 1 Recent Runs",
        [
            "`Recorded at` is the UTC append time; `Journey`, `File`, `Variant`, `Mutation`, and `Run kind` identify what was executed.",
            "`Status` is the final result, `Blocked` and `Failure kind` explain failed runs, and `GUI`/`API`/`Lines` record the per-run GUI count, frontend API count, and test size.",
        ],
    )
    if fault_rows:
        add_column_guide(
            lines,
            "Phase 1 Failure Distribution",
            [
                "`Journey` is the grouping key, `Failure kind` is the normalized category, `Failure signature` is the normalized fault fingerprint, and `Count` is how often that fault appeared.",
            ],
        )
    if service_rows:
        add_column_guide(
            lines,
            "Phase 1 Frontend API Calls By Service",
            [
                "`Journey` is the grouping key, `Service` is inferred from observed frontend requests plus the MSA spec, and `Calls` is the total frontend `/api/` call count across recorded runs.",
            ],
        )
    if phase2_rows:
        add_column_guide(
            lines,
            "Phase 2 Operation Coverage By Service",
            [
                "`Journey` is the grouping key, `Service` is the MSA service name, `Covered ops` is the number of distinct observed operations, `Total ops` is the spec total, `Coverage` is covered divided by total, and `Operations` lists the matched labels.",
            ],
        )
    if phase3_mutation_rows:
        add_column_guide(
            lines,
            "Phase 3 Mutation Effectiveness",
            [
                "`Journey`, `Variant`, `Mutation`, and `Fault service` identify the compared system state; `Original pass`/`Original fail` and `Variant pass`/`Variant fail` summarize outcomes.",
                "`Mutation detected` means the variant failed where the original passed, and `New or different faults` means the variant produced failure signatures not seen in the original.",
            ],
        )
    if phase3_fault_rows:
        add_column_guide(
            lines,
            "Phase 3 Fault Distribution",
            [
                "`Journey`, `Variant`, `Mutation`, and `Fault service` identify the compared system state; `Failure kind` and `Failure signature` describe the fault; `Count` is how often it occurred for that variant.",
            ],
        )
    if phase3_operation_rows:
        add_column_guide(
            lines,
            "Phase 3 Operation Coverage By Variant",
            [
                "`Journey`, `Variant`, `Mutation`, and `Fault service` identify the compared system state; `Service` is the MSA service name; `Covered ops`, `Total ops`, `Coverage`, and `Operations` show per-variant API operation coverage.",
            ],
        )

    lines.extend(
        [
            "## Phase 1 Journey Summary",
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
            "## Phase 1 Recent Runs",
            "",
            "| Recorded at | Journey | File | Variant | Mutation | Run kind | Status | Blocked | Failure kind | GUI | API | Lines |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |",
        ]
    )

    for record in sorted(
        records,
        key=lambda item: str(item.get("recorded_at", "")),
        reverse=True,
    )[:20]:
        phase1 = record.get("phase1") or {}
        variant_label, mutation_id, _, run_kind = evaluation_fields(record)
        lines.append(
            "| {recorded_at} | {journey} | {filename} | {variant} | {mutation_id} | {run_kind} | {status} | {blocked} | {failure_kind} | {gui} | {api} | {lines_count} |".format(
                recorded_at=escape_md_cell(str(record.get("recorded_at", ""))),
                journey=escape_md_cell(str(record.get("requested_journey") or "")),
                filename=escape_md_cell(str(record.get("filename", ""))),
                variant=escape_md_cell(variant_label),
                mutation_id=escape_md_cell(mutation_id or "-"),
                run_kind=escape_md_cell(run_kind),
                status=escape_md_cell(str(record.get("status", ""))),
                blocked=phase1.get("blocked", False),
                failure_kind=escape_md_cell(str(phase1.get("failure_kind", ""))),
                gui=int(phase1.get("gui_element_count", 0)),
                api=int(phase1.get("frontend_api_call_count", 0)),
                lines_count=int(phase1.get("generated_test_lines", 0)),
            )
        )

    if fault_rows:
        lines.extend(
            [
                "",
                "## Phase 1 Failure Distribution",
                "",
                "| Journey | Failure kind | Failure signature | Count |",
                "| --- | --- | --- | ---: |",
            ]
        )
        lines.extend(fault_rows)

    if service_rows:
        lines.extend(
            [
                "",
                "## Phase 1 Frontend API Calls By Service",
                "",
                "| Journey | Service | Calls |",
                "| --- | --- | ---: |",
            ]
        )
        lines.extend(service_rows)

    if phase2_rows:
        lines.extend(
            [
                "",
                "## Phase 2 Operation Coverage By Service",
                "",
                "| Journey | Service | Covered ops | Total ops | Coverage | Operations |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        lines.extend(phase2_rows)

    if has_phase3:
        if phase3_mutation_rows:
            lines.extend(
                [
                    "",
                    "## Phase 3 Mutation Effectiveness",
                    "",
                    "| Journey | Variant | Mutation | Fault service | Original pass | Original fail | Variant pass | Variant fail | Mutation detected | New or different faults |",
                    "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
                ]
            )
            lines.extend(phase3_mutation_rows)

        if phase3_fault_rows:
            lines.extend(
                [
                    "",
                    "## Phase 3 Fault Distribution",
                    "",
                    "| Journey | Variant | Mutation | Fault service | Failure kind | Failure signature | Count |",
                    "| --- | --- | --- | --- | --- | --- | ---: |",
                ]
            )
            lines.extend(phase3_fault_rows)

        if phase3_operation_rows:
            lines.extend(
                [
                    "",
                    "## Phase 3 Operation Coverage By Variant",
                    "",
                    "| Journey | Variant | Mutation | Fault service | Service | Covered ops | Total ops | Coverage | Operations |",
                    "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
                ]
            )
            lines.extend(phase3_operation_rows)

    return "\n".join(lines)
