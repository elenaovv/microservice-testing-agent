"""Classify evaluation run failures from saved report/history artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SKIP_DIRS = {".git", ".venv", ".tmp", ".pytest_cache", "__pycache__"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify browse/test failure modes from evaluation-runs.jsonl files."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Result directory, evaluation-runs.jsonl, or *.report.json file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("failure-mode-summary"),
        help="Directory for failure-modes.md and failure-modes.csv.",
    )
    args = parser.parse_args()

    records = load_records(args.inputs)
    rows = [classify_record(record) for record in records]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "failure-modes.csv", rows)
    write_markdown(args.output_dir / "failure-modes.md", rows)

    print(f"records: {len(rows)}")
    print(f"markdown: {args.output_dir / 'failure-modes.md'}")
    print(f"csv: {args.output_dir / 'failure-modes.csv'}")


def load_records(inputs: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for input_path in inputs:
        for record in load_records_from_path(input_path):
            key = dedupe_key(record)
            if key in seen:
                continue
            seen.add(key)
            records.append(record)

    records.sort(
        key=lambda r: (
            use_case_label(r),
            str((r.get("evaluation") or {}).get("variant_label", "")),
            str(r.get("recorded_at", "")),
        )
    )
    return records


def load_records_from_path(path: Path) -> list[dict[str, Any]]:
    if path.is_file():
        if path.name == "evaluation-runs.jsonl":
            return load_jsonl(path)
        if path.name.endswith(".report.json"):
            return [json.loads(path.read_text(encoding="utf-8"))]
        return []

    if not path.exists():
        raise FileNotFoundError(path)

    history_files = list(find_history_files(path))
    if history_files:
        records: list[dict[str, Any]] = []
        for history_file in history_files:
            records.extend(load_jsonl(history_file))
        return records

    return [
        json.loads(report_path.read_text(encoding="utf-8"))
        for report_path in path.rglob("*.report.json")
        if not has_skipped_part(report_path)
    ]


def find_history_files(root: Path) -> list[Path]:
    direct = root / "evaluation-runs.jsonl"
    if direct.exists():
        return [direct]

    files = [
        path
        for path in root.rglob("evaluation-runs.jsonl")
        if not has_skipped_part(path)
    ]

    # Prefer aggregate files over per-run test-results files when both exist.
    aggregate_files = [
        path
        for path in files
        if path.parent.name != "test-results"
    ]
    return aggregate_files or files


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def has_skipped_part(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def dedupe_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    evaluation = record.get("evaluation") or {}
    use_case = record.get("use_case") or {}
    return (
        str(use_case.get("id") or record.get("requested_journey") or ""),
        str(evaluation.get("variant_label", "")),
        str(record.get("filename", "")),
        str(record.get("recorded_at", "")),
    )


def classify_record(record: dict[str, Any]) -> dict[str, str]:
    phase1 = record.get("phase1") or {}
    diagnosis = phase1.get("failure_diagnosis") or {}
    status = str(record.get("status", "")).strip()
    failure_kind = str(phase1.get("failure_kind", "")).strip()
    diagnosis_kind = str(diagnosis.get("kind", "")).strip()
    signature = str(phase1.get("failure_signature", "")).strip()
    details = str(record.get("details", ""))

    category, evidence = classify_failure(
        status=status,
        phase1=phase1,
        failure_kind=failure_kind,
        diagnosis_kind=diagnosis_kind,
        signature=signature,
        details=details,
    )

    use_case = record.get("use_case") or {}
    evaluation = record.get("evaluation") or {}
    return {
        "journey": use_case_label(record),
        "use_case_id": str(use_case.get("id", "")),
        "use_case_name": str(use_case.get("name", "")),
        "variant": str(evaluation.get("variant_label", "")),
        "status": status,
        "category": category,
        "failure_kind": failure_kind,
        "diagnosis_kind": diagnosis_kind,
        "failure_signature": signature,
        "retries_used": str(phase1.get("retries_used", "")),
        "max_retries": str(phase1.get("max_retries", "")),
        "generated": str(phase1.get("generated_test", "")),
        "syntax_valid": str(phase1.get("syntax_valid", "")),
        "blocked": str(phase1.get("blocked", "")),
        "evidence": evidence,
    }


def classify_failure(
    *,
    status: str,
    phase1: dict[str, Any],
    failure_kind: str,
    diagnosis_kind: str,
    signature: str,
    details: str,
) -> tuple[str, str]:
    if status == "passed":
        return "passed", "pytest passed"

    text = "\n".join([status, failure_kind, diagnosis_kind, signature, details]).lower()

    if status == "browse_failed" or (
        phase1.get("generated_test") is False and "browse" in text
    ):
        return "browse-blocked", "journey failed before test generation"

    if status == "error" or contains_any(
        text,
        [
            "connection closed",
            "mcp",
            "browser has been closed",
            "target page, context or browser has been closed",
            "unhandled exception",
        ],
    ):
        return "infrastructure/other", "tooling or browser infrastructure error"

    if not phase1.get("syntax_valid", True) or failure_kind in {
        "syntax-error",
        "collection-error",
        "import-error",
    }:
        return "syntax/collection", failure_kind or "invalid or uncollectable test"

    if failure_kind == "missing-expected-side-effect" or phase1.get(
        "missing_expected_service_calls"
    ):
        return "state/side-effect", "expected backend side effect was missing"

    if failure_kind == "timeout" or diagnosis_kind == "action-timeout" or contains_any(
        text,
        ["timed out", "timeouterror", "+++++++++++++++++++++++++++++++++++ timeout"],
    ):
        return "timeout", "timeout while replaying generated test"

    if diagnosis_kind == "strict-mode-ambiguity" or contains_any(
        text,
        ["strict mode violation", "resolved to 2 elements", "resolved to multiple"],
    ):
        return "selector-ambiguity", "locator matched more than one element"

    if diagnosis_kind in {"locator-not-found", "hidden-element"} or contains_any(
        text,
        ["element(s) not found", "locator expected to be visible", "actual value: none"],
    ):
        return "selector-not-found", "locator did not resolve to a visible element"

    if failure_kind == "assertion-failure":
        if contains_any(
            text,
            ["order", "status", "row", "already", "duplicate", "changed", "not paid", "paid"],
        ):
            return "state/data-mismatch", "assertion appears tied to mutable application data"
        return "assertion-failure", signature or "assertion failed"

    return "infrastructure/other", failure_kind or "uncategorized failed run"


def contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def use_case_label(record: dict[str, Any]) -> str:
    use_case = record.get("use_case") or {}
    use_case_id = str(use_case.get("id", "")).strip()
    use_case_name = str(use_case.get("name", "")).strip()
    if use_case_id and use_case_name:
        return f"{use_case_id} {use_case_name}"
    return use_case_id or str(record.get("requested_journey") or record.get("filename") or "unknown")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "journey",
        "use_case_id",
        "use_case_name",
        "variant",
        "status",
        "category",
        "failure_kind",
        "diagnosis_kind",
        "failure_signature",
        "retries_used",
        "max_retries",
        "generated",
        "syntax_valid",
        "blocked",
        "evidence",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict[str, str]]) -> None:
    lines = [
        "# Failure Mode Summary",
        "",
        "This report classifies saved evaluation runs from existing artifacts. It does not rerun the tests.",
        "",
        "## Category Summary",
        "",
        "| Journey | Category | Count |",
        "| --- | --- | ---: |",
    ]

    by_journey_category: Counter[tuple[str, str]] = Counter(
        (row["journey"], row["category"]) for row in rows
    )
    for (journey, category), count in sorted(by_journey_category.items()):
        lines.append(f"| {md(journey)} | {md(category)} | {count} |")

    lines.extend(
        [
            "",
            "## Failed Run Details",
            "",
            "| Journey | Variant | Status | Category | Failure kind | Diagnosis | Signature | Evidence |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for row in rows:
        if row["status"] == "passed":
            continue
        lines.append(
            "| {journey} | {variant} | {status} | {category} | {failure_kind} | {diagnosis} | {signature} | {evidence} |".format(
                journey=md(row["journey"]),
                variant=md(row["variant"]),
                status=md(row["status"]),
                category=md(row["category"]),
                failure_kind=md(row["failure_kind"]),
                diagnosis=md(row["diagnosis_kind"]),
                signature=md(row["failure_signature"]),
                evidence=md(row["evidence"]),
            )
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip() or "-"


if __name__ == "__main__":
    main()
