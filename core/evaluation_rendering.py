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

def format_retry_ratio(used: int, max_retries: int) -> str:
    if max_retries < 0:
        return str(used) if used > 0 else "-"
    return f"{used}/{max_retries}"

def format_dominant_hash(hash_counts: Counter[str], total: int) -> str:
    if not hash_counts or total <= 0:
        return "-"
    hash_value, count = hash_counts.most_common(1)[0]
    return f"{hash_value} ({count}/{total})"

def escape_md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()

def use_case_fields(record: dict) -> tuple[str, str, str]:
    use_case = record.get("use_case") or {}
    use_case_id = str(use_case.get("id", "")).strip()
    use_case_name = str(use_case.get("name", "")).strip()
    reference_bucket = str(
        use_case.get("reference_bucket", use_case.get("smith_equivalent", ""))
    ).strip()
    return use_case_id, use_case_name, reference_bucket

def scenario_label(record: dict) -> str:
    use_case_id, use_case_name, _ = use_case_fields(record)
    if use_case_id and use_case_name:
        return f"{use_case_id} {use_case_name}"
    if use_case_id:
        return use_case_id
    return str(record.get("requested_journey") or record.get("filename") or "unknown")

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

def build_browse_operation_rows(grouped_records: dict[str, list[dict]]) -> list[str]:
    rows: list[str] = []
    for journey, records in sorted(grouped_records.items()):
        n_runs = len(records)
        # (method, path) -> list of status codes seen across runs (one per run that hit it)
        op_run_hits: dict[tuple[str, str], list[int]] = defaultdict(list)
        op_total_calls: dict[tuple[str, str], int] = defaultdict(int)
        for record in records:
            phase1 = record.get("phase1") or {}
            seen_this_run: set[tuple[str, str]] = set()
            for call in list(phase1.get("browse_api_calls", [])):
                method = str(call.get("method", "")).upper()
                path = str(call.get("path", ""))
                status = int(call.get("status_code", 0))
                if not method or not path:
                    continue
                key = (method, path)
                op_total_calls[key] += 1
                if key not in seen_this_run:
                    op_run_hits[key].append(status)
                    seen_this_run.add(key)
        for (method, path), statuses in sorted(op_run_hits.items()):
            run_count = len(statuses)
            total_calls = op_total_calls[(method, path)]
            avg_calls = total_calls / n_runs
            unique_statuses = sorted(set(s for s in statuses if s))
            status_str = "/".join(str(s) for s in unique_statuses) if unique_statuses else "?"
            avg_str = f"{avg_calls:.1f}" if avg_calls != int(avg_calls) else str(int(avg_calls))
            rows.append(
                f"| {escape_md_cell(journey)} | {escape_md_cell(method)} | {escape_md_cell(path)}"
                f" | {run_count}/{n_runs} | {status_str} | {avg_str} |"
            )
    return rows

def build_phase2_operation_rows(grouped_records: dict[str, list[dict]]) -> list[str]:
    rows: list[str] = []
    for journey, records in sorted(grouped_records.items()):
        n_runs = len(records)
        totals: dict[str, int] = {}
        # Track how many runs covered each specific operation per service.
        operation_run_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for record in records:
            coverage = record.get("coverage") or {}
            for service, total in dict(coverage.get("service_operation_totals", {})).items():
                totals[str(service)] = int(total)
            for service, operations in dict(
                coverage.get("covered_operations_by_service", {})
            ).items():
                for op in list(operations):
                    operation_run_counts[str(service)][str(op)] += 1

        for service, total in sorted(totals.items()):
            ops = operation_run_counts.get(service, {})
            covered = sorted(ops.keys())
            coverage_pct = (len(covered) / total * 100) if total > 0 else 0.0
            # Annotate each operation with how many runs covered it, e.g. "POST /x (3/5)".
            op_labels = [
                f"{op} ({count}/{n_runs})" for op, count in sorted(ops.items())
            ]
            rows.append(
                "| {journey} | {service} | {covered_count} | {total} | {coverage_pct:.1f}% | {operations} |".format(
                    journey=escape_md_cell(journey),
                    service=escape_md_cell(service),
                    covered_count=len(covered),
                    total=total,
                    coverage_pct=coverage_pct,
                    operations=escape_md_cell(", ".join(op_labels) if op_labels else "-"),
                )
            )
    return rows

def build_smith_bucket_rows(
    records: list[dict],
    smith_buckets: dict[str, list[str]],
) -> list[str]:
    if not smith_buckets:
        return []

    bucket_by_use_case_id = {
        use_case_id: bucket
        for bucket, use_case_ids in smith_buckets.items()
        for use_case_id in use_case_ids
    }
    grouped_records: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for record in records:
        use_case_id, _, reference_bucket = use_case_fields(record)
        bucket = bucket_by_use_case_id.get(use_case_id)
        if not bucket and reference_bucket and reference_bucket.lower() != "none":
            bucket = reference_bucket
        if not bucket or bucket.lower() == "none":
            continue
        variant_label, mutation_id, fault_service, _ = evaluation_fields(record)
        grouped_records[(bucket, variant_label, mutation_id, fault_service)].append(record)

    rows: list[str] = []
    for (bucket, variant_label, mutation_id, fault_service), bucket_records in sorted(
        grouped_records.items()
    ):
        use_case_ids = sorted(
            {
                use_case_id
                for record in bucket_records
                for use_case_id, _, _ in [use_case_fields(record)]
                if use_case_id
            }
        )
        totals: dict[str, int] = {}
        covered_operations: dict[str, set[str]] = defaultdict(set)
        for record in bucket_records:
            coverage = record.get("coverage") or {}
            for service, total in dict(coverage.get("service_operation_totals", {})).items():
                totals[str(service)] = int(total)
            for service, operations in dict(
                coverage.get("covered_operations_by_service", {})
            ).items():
                covered_operations[str(service)].update(str(item) for item in operations)

        for service, total in sorted(totals.items()):
            covered = sorted(covered_operations.get(service, set()))
            coverage_pct = (len(covered) / total) * 100 if total > 0 else 0.0
            rows.append(
                "| {bucket} | {variant} | {mutation_id} | {fault_service} | {runs} | {use_cases} | {service} | {covered_count} | {total} | {coverage_pct:.1f}% | {operations} |".format(
                    bucket=escape_md_cell(bucket),
                    variant=escape_md_cell(variant_label),
                    mutation_id=escape_md_cell(mutation_id or "-"),
                    fault_service=escape_md_cell(fault_service or "-"),
                    runs=len(bucket_records),
                    use_cases=escape_md_cell(", ".join(use_case_ids) if use_case_ids else "-"),
                    service=escape_md_cell(service),
                    covered_count=len(covered),
                    total=total,
                    coverage_pct=coverage_pct,
                    operations=escape_md_cell(", ".join(covered) if covered else "-"),
                )
            )
    return rows

# ---------------------------------------------------------------------------
# Action sequence comparison section
# ---------------------------------------------------------------------------

def _build_sequence_section(grouped: dict[str, list[dict]]) -> list[str]:
    lines: list[str] = []
    for journey, records in sorted(grouped.items()):
        seq_groups: dict[str, list[tuple[str, list[str]]]] = {}
        for record in records:
            phase1 = record.get("phase1") or {}
            h = str(phase1.get("action_sequence_hash", "")).strip()
            seq = [str(s) for s in list(phase1.get("action_sequence", []))]
            if not h or not seq:
                continue
            filename = str(record.get("filename", ""))
            seq_groups.setdefault(h, []).append((filename, seq))
        if not seq_groups:
            continue
        n_runs = len(records)
        lines.append(f"### {escape_md_cell(journey)}")
        lines.append("")
        for seq_hash, runs in sorted(seq_groups.items(), key=lambda kv: -len(kv[1])):
            run_count = len(runs)
            filenames = ", ".join(r[0] for r in runs)
            seq = runs[0][1]
            lines.append(f"**Seq `{seq_hash}` - {run_count}/{n_runs} runs** ({filenames})")
            lines.append("")
            for i, step in enumerate(seq, 1):
                lines.append(f"{i}. `{step}`")
            lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Main renderers
# ---------------------------------------------------------------------------

def render_evaluation_summary(
    records: list[dict],
    *,
    smith_buckets: dict[str, list[str]] | None = None,
) -> str:
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
        grouped[scenario_label(record)].append(record)

    fault_rows = build_fault_rows(grouped)
    service_rows = build_browse_operation_rows(grouped)
    phase2_rows = build_phase2_operation_rows(grouped)
    smith_bucket_rows = build_smith_bucket_rows(records, smith_buckets or {})
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
            "`Journey` is the structured use-case ID and name when available, otherwise the requested journey text or filename fallback; `Runs`, `Generated`, `Pass`, and `Fail` are run counts.",
            "`Blocked` means the run failed before meaningful execution, `Error` means the run crashed before any test was generated or executed (e.g. browser connection lost), `Syntax invalid` means invalid Python, `Suspected FP` means a likely false positive, `Variants` counts distinct generated code hashes, `Stability` is the share of runs using the most common hash, and `Top hash` shows that dominant hash value and count.",
            "`Seq variants` counts distinct action sequences (Playwright step order + selectors, fill values dropped), `Seq stability` is the share of runs with the most common sequence - these measure structural non-determinism independently of code hash.",
            "`Retries avg` is the average repair retries used per run in `used/max` form, `Pass w/o repairs` is how many passing runs used `0/max`, `Same fault` checks whether all failures share one signature, and `Avg GUI`/`Avg API`/`Avg lines` are averages for GUI checks, frontend API calls, and test size.",
        ],
    )
    add_column_guide(
        lines,
        "Phase 1 Recent Runs",
        [
            "`Recorded at` is the UTC append time; `Journey`, `Use case`, `Reference bucket`, `File`, `Variant`, `Mutation`, and `Run kind` identify what was executed.",
            "`Status` is the final result, `Blocked` and `Failure kind` explain failed runs, `Hash` is the generated test code hash, and `Retries` is repair retries used in `used/max` form for that run.",
            "`GUI`/`API`/`Lines` record the per-run GUI count, frontend API count, and generated test size.",
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
            "Phase 1 Browse API Operations",
            [
                "`Journey` is the grouping key, `Method`/`Path` identify the backend operation called during the agent browse phase, `Runs hit` is how many runs called it (e.g. 5/5), `Status` is the HTTP status code(s) observed (multiple if runs differed), and `Avg calls/run` is the average number of times the operation was called per run (>1 means the agent called it repeatedly in some runs).",
            ],
        )
    if phase2_rows:
        add_column_guide(
            lines,
            "Phase 2 Operation Coverage By Service",
            [
                "`Journey` is the grouping key, `Service` is the MSA service name, `Covered ops` is the number of distinct observed operations, `Total ops` is the spec total, `Coverage` is covered divided by total, and `Operations` lists each matched operation with its per-run hit count in `(N/runs)` form - e.g. `POST /x (3/5)` means 3 of 5 runs covered that operation.",
            ],
        )
    if smith_bucket_rows:
        add_column_guide(
            lines,
            "Reference Bucket Operation Coverage",
            [
                "`Bucket` is the optional benchmark or reference bucket, `Variant`/`Mutation`/`Fault service` identify the evaluated system state, `Runs` is the number of recorded runs in that bucket, and `Use cases` lists the contributing structured use-case IDs.",
                "`Service`, `Covered ops`, `Total ops`, `Coverage`, and `Operations` aggregate operation coverage across all use cases recorded in that bucket.",
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
            "| Journey | Runs | Generated | Pass | Fail | Error | Blocked | Syntax invalid | Suspected FP | Variants | Stability | Top hash | Seq variants | Seq stability | Retries avg | Pass w/o repairs | Same fault | Avg GUI | Avg API | Avg lines |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: |",
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
        dominant_hash = format_dominant_hash(hash_counts, len(journey_records))
        failure_signatures = {
            str(phase1.get("failure_signature", "")).strip()
            for phase1 in phase1_records
            if str(phase1.get("failure_signature", "")).strip()
        }
        same_fault = "n/a"
        if failure_signatures:
            same_fault = "yes" if len(failure_signatures) == 1 else "no"
        max_retries = max(int(phase1.get("max_retries", -1)) for phase1 in phase1_records)
        avg_retries_used = average_int(phase1_records, "retries_used")
        if max_retries >= 0:
            retries_avg = f"{avg_retries_used:.1f}/{max_retries}"
        elif avg_retries_used > 0:
            retries_avg = f"{avg_retries_used:.1f}"
        else:
            retries_avg = "-"
        passed_count = count_status(journey_records, "passed")
        pass_without_repairs = sum(
            1
            for record, phase1 in zip(journey_records, phase1_records)
            if record.get("status") == "passed"
            and int(phase1.get("retries_used", 0)) == 0
        )
        pass_without_repairs_label = (
            f"{pass_without_repairs}/{passed_count}"
            if passed_count > 0
            else "n/a"
        )
        seq_hashes = [
            str(phase1.get("action_sequence_hash", ""))
            for phase1 in phase1_records
            if phase1.get("action_sequence_hash")
        ]
        seq_hash_counts = Counter(seq_hashes)
        most_common_seq_count = seq_hash_counts.most_common(1)[0][1] if seq_hash_counts else 0
        seq_variants = len(seq_hash_counts) if seq_hash_counts else 0
        seq_stability = format_stability(most_common_seq_count, len(journey_records)) if seq_hash_counts else "-"

        lines.append(
            "| {journey} | {runs} | {generated} | {passed} | {failed} | {errored} | {blocked} | {syntax_invalid} | {suspected_fp} | {variants} | {stability} | {dominant_hash} | {seq_variants} | {seq_stability} | {retries_avg} | {pass_without_repairs} | {same_fault} | {avg_gui:.1f} | {avg_api:.1f} | {avg_lines:.1f} |".format(
                journey=escape_md_cell(journey),
                runs=len(journey_records),
                generated=count_true(phase1_records, "generated_test"),
                passed=count_status(journey_records, "passed"),
                failed=count_status(journey_records, "failed"),
                errored=count_status(journey_records, "error"),
                blocked=count_true(phase1_records, "blocked"),
                syntax_invalid=count_false(phase1_records, "syntax_valid"),
                suspected_fp=count_true(phase1_records, "suspected_false_positive"),
                variants=len(hash_counts) or 0,
                stability=format_stability(most_common_hash_count, len(journey_records)),
                dominant_hash=escape_md_cell(dominant_hash),
                seq_variants=seq_variants or "-",
                seq_stability=seq_stability,
                retries_avg=escape_md_cell(retries_avg),
                pass_without_repairs=escape_md_cell(pass_without_repairs_label),
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
            "| Recorded at | Journey | Use case | Reference bucket | File | Variant | Mutation | Run kind | Status | Blocked | Failure kind | Hash | Seq hash | Retries | GUI | API | Lines |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |",
        ]
    )

    for record in sorted(
        records,
        key=lambda item: str(item.get("recorded_at", "")),
        reverse=True,
    )[:20]:
        phase1 = record.get("phase1") or {}
        variant_label, mutation_id, _, run_kind = evaluation_fields(record)
        use_case_id, use_case_name, reference_bucket = use_case_fields(record)
        use_case_label = " ".join(part for part in (use_case_id, use_case_name) if part)
        generated_hash = str(phase1.get("generated_test_hash", "")).strip() or "-"
        seq_hash = str(phase1.get("action_sequence_hash", "")).strip() or "-"
        retries_label = format_retry_ratio(
            int(phase1.get("retries_used", 0)),
            int(phase1.get("max_retries", -1)),
        )
        lines.append(
            "| {recorded_at} | {journey} | {use_case} | {reference_bucket} | {filename} | {variant} | {mutation_id} | {run_kind} | {status} | {blocked} | {failure_kind} | {generated_hash} | {seq_hash} | {retries} | {gui} | {api} | {lines_count} |".format(
                recorded_at=escape_md_cell(str(record.get("recorded_at", ""))),
                journey=escape_md_cell(scenario_label(record)),
                use_case=escape_md_cell(use_case_label or "-"),
                reference_bucket=escape_md_cell(reference_bucket or "-"),
                filename=escape_md_cell(str(record.get("filename", ""))),
                variant=escape_md_cell(variant_label),
                mutation_id=escape_md_cell(mutation_id or "-"),
                run_kind=escape_md_cell(run_kind),
                status=escape_md_cell(str(record.get("status", ""))),
                blocked=phase1.get("blocked", False),
                failure_kind=escape_md_cell(str(phase1.get("failure_kind", ""))),
                generated_hash=escape_md_cell(generated_hash),
                seq_hash=escape_md_cell(seq_hash),
                retries=escape_md_cell(retries_label),
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
                "## Phase 1 Browse API Operations",
                "",
                "| Journey | Method | Path | Runs hit | Status | Avg calls/run |",
                "| --- | --- | --- | --- | --- | ---: |",
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

    seq_section = _build_sequence_section(grouped)
    if seq_section:
        lines.extend(["", "## Phase 1 Action Sequence Comparison", ""])
        lines.extend(seq_section)

    if smith_bucket_rows:
        lines.extend(
            [
                "",
                "## Reference Bucket Operation Coverage",
                "",
                "| Bucket | Variant | Mutation | Fault service | Runs | Use cases | Service | Covered ops | Total ops | Coverage | Operations |",
                "| --- | --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        lines.extend(smith_bucket_rows)

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
