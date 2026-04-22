"""Phase 3 mutation comparison helpers."""

from collections import Counter, defaultdict


def count_status(records: list[dict], status: str) -> int:
    return sum(1 for record in records if record.get("status") == status)


def escape_md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def evaluation_fields(record: dict) -> tuple[str, str, str, str]:
    evaluation = record.get("evaluation") or {}
    variant_label = str(evaluation.get("variant_label", "original")).strip() or "original"
    mutation_id = str(evaluation.get("mutation_id", "")).strip()
    fault_service = str(evaluation.get("fault_service", "")).strip()
    run_kind = str(evaluation.get("run_kind", "generated")).strip() or "generated"
    return variant_label, mutation_id, fault_service, run_kind


def has_phase3_context(record: dict) -> bool:
    variant_label, mutation_id, fault_service, run_kind = evaluation_fields(record)
    return (
        variant_label != "original"
        or bool(mutation_id)
        or bool(fault_service)
        or run_kind != "generated"
    )


def failure_signatures(records: list[dict]) -> set[str]:
    signatures: set[str] = set()
    for record in records:
        phase1 = record.get("phase1") or {}
        signature = str(phase1.get("failure_signature", "")).strip()
        if signature:
            signatures.add(signature)
    return signatures


def build_phase3_mutation_rows(grouped_records: dict[str, list[dict]]) -> list[str]:
    rows: list[str] = []
    for journey, records in sorted(grouped_records.items()):
        original_records = [
            record for record in records if evaluation_fields(record)[0] == "original"
        ]
        original_pass = count_status(original_records, "passed")
        original_fail = count_status(original_records, "failed")
        original_signatures = failure_signatures(original_records)
        variant_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

        for record in records:
            variant_label, mutation_id, fault_service, _ = evaluation_fields(record)
            if variant_label != "original":
                variant_groups[(variant_label, mutation_id, fault_service)].append(record)

        for (variant_label, mutation_id, fault_service), variant_records in sorted(
            variant_groups.items()
        ):
            variant_fail = count_status(variant_records, "failed")
            variant_pass = count_status(variant_records, "passed")
            variant_signatures = failure_signatures(variant_records)
            if original_records:
                new_faults = variant_signatures - original_signatures
                fault_delta = f"yes ({len(new_faults)})" if new_faults else "no"
                mutation_detected = "yes" if original_pass > 0 and variant_fail > 0 else "no"
            else:
                fault_delta = "n/a"
                mutation_detected = "n/a"
            rows.append(
                "| {journey} | {variant} | {mutation_id} | {fault_service} | {original_pass} | {original_fail} | {variant_pass} | {variant_fail} | {mutation_detected} | {fault_delta} |".format(
                    journey=escape_md_cell(journey),
                    variant=escape_md_cell(variant_label),
                    mutation_id=escape_md_cell(mutation_id or "-"),
                    fault_service=escape_md_cell(fault_service or "-"),
                    original_pass=original_pass,
                    original_fail=original_fail,
                    variant_pass=variant_pass,
                    variant_fail=variant_fail,
                    mutation_detected=mutation_detected,
                    fault_delta=fault_delta,
                )
            )
    return rows


def build_phase3_fault_rows(records: list[dict]) -> list[str]:
    counter: Counter[tuple[str, str, str, str, str, str]] = Counter()
    for record in records:
        phase1 = record.get("phase1") or {}
        failure_kind = str(phase1.get("failure_kind", "")).strip()
        failure_signature = str(phase1.get("failure_signature", "")).strip()
        if not failure_kind or not failure_signature:
            continue
        variant_label, mutation_id, fault_service, _ = evaluation_fields(record)
        journey = str(record.get("requested_journey") or record.get("filename") or "unknown")
        counter[
            (
                journey,
                variant_label,
                mutation_id or "-",
                fault_service or "-",
                failure_kind,
                failure_signature,
            )
        ] += 1

    rows: list[str] = []
    for item, count in counter.most_common():
        journey, variant_label, mutation_id, fault_service, failure_kind, failure_signature = item
        rows.append(
            "| {journey} | {variant} | {mutation_id} | {fault_service} | {failure_kind} | {failure_signature} | {count} |".format(
                journey=escape_md_cell(journey),
                variant=escape_md_cell(variant_label),
                mutation_id=escape_md_cell(mutation_id),
                fault_service=escape_md_cell(fault_service),
                failure_kind=escape_md_cell(failure_kind),
                failure_signature=escape_md_cell(failure_signature),
                count=count,
            )
        )
    return rows


def build_phase3_operation_rows(grouped_records: dict[str, list[dict]]) -> list[str]:
    rows: list[str] = []
    for journey, records in sorted(grouped_records.items()):
        variant_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        for record in records:
            variant_label, mutation_id, fault_service, _ = evaluation_fields(record)
            variant_groups[(variant_label, mutation_id, fault_service)].append(record)

        for (variant_label, mutation_id, fault_service), variant_records in sorted(
            variant_groups.items()
        ):
            totals: dict[str, int] = {}
            covered_operations: dict[str, set[str]] = defaultdict(set)
            for record in variant_records:
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
                    "| {journey} | {variant} | {mutation_id} | {fault_service} | {service} | {covered_count} | {total} | {coverage_pct:.1f}% | {operations} |".format(
                        journey=escape_md_cell(journey),
                        variant=escape_md_cell(variant_label),
                        mutation_id=escape_md_cell(mutation_id or "-"),
                        fault_service=escape_md_cell(fault_service or "-"),
                        service=escape_md_cell(service),
                        covered_count=len(covered),
                        total=total,
                        coverage_pct=coverage_pct,
                        operations=escape_md_cell(", ".join(covered) if covered else "-"),
                    )
                )
    return rows
