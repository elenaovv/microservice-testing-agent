"""Evaluation rendering helpers: Markdown generation for evaluation summaries."""

from collections import Counter, defaultdict
from core.mutation_utils import (
    build_phase3_fault_rows,
    build_phase3_mutation_rows,
    build_phase3_operation_rows,
    evaluation_fields,
    has_phase3_context,
)

# ---------------------------------------------------------------------------
# Stats and formatting helpers
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Main renderers
# ---------------------------------------------------------------------------

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
