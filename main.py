import argparse
import asyncio
import sys
from pathlib import Path

from core.models import UseCaseMetadata
from prompts.generator import (
    STRUCTURED_USE_CASE_INDEX_PATH,
    SYSTEM_DESCRIPTION_PATH,
    MSA_SPEC_PATH,
    USE_CASES_PATH,
    StructuredUseCase,
    derive_python_test_filename,
    derive_use_case_test_filename,
    load_structured_use_case,
    load_structured_use_case_by_id,
    load_use_cases,
)
from workflow import generate_test, retest_generated_test, run_browser_task


def safe_print(output: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe_output = output.encode(encoding, errors="replace").decode(encoding)
    print(safe_output)


def add_evaluation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--variant-label",
        default="original",
        help="Variant label recorded in evaluation artifacts (default: original)",
    )
    parser.add_argument(
        "--mutation-id",
        default="",
        help="Optional mutation or branch identifier for Phase 3 tracking",
    )
    parser.add_argument(
        "--fault-service",
        default="",
        help="Optional microservice name that contains the injected fault",
    )
    parser.add_argument(
        "--base-url",
        help="App base URL for browsing and test execution (defaults to BASE_URL env or http://localhost:8080)",
    )
    parser.add_argument(
        "--msa-spec",
        help=f"MSA specification YAML path (default: {MSA_SPEC_PATH})",
    )


def add_input_spec_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--system-description",
        help=f"System description path (default: {SYSTEM_DESCRIPTION_PATH})",
    )
    parser.add_argument(
        "--use-cases-file",
        help=f"Legacy text use-case file path (default: {USE_CASES_PATH})",
    )
    parser.add_argument(
        "--use-case-index",
        help=f"Structured use-case index path (default: {STRUCTURED_USE_CASE_INDEX_PATH})",
    )


def _read_use_case_at_line(line_number: int, path: Path = USE_CASES_PATH) -> str:
    if line_number < 1:
        raise ValueError("--line must be >= 1")
    if not path.exists():
        raise FileNotFoundError(f"Use case file not found: {path}")

    raw_lines = path.read_text(encoding="utf-8").splitlines()
    if line_number > len(raw_lines):
        raise ValueError(
            f"Line {line_number} is out of range for {path} (total lines: {len(raw_lines)})"
        )

    selected = raw_lines[line_number - 1].strip()
    if not selected:
        raise ValueError(f"Line {line_number} is blank in {path}")
    if selected.startswith("#"):
        raise ValueError(f"Line {line_number} is a comment in {path}")
    return selected


async def _generate_single_test(
    journey: str,
    filename: str | None,
    args: argparse.Namespace,
    use_case_context: str = "",
    use_case: UseCaseMetadata | None = None,
) -> str:
    return await generate_test(
        filename,
        journey,
        args.max_retries,
        variant_label=args.variant_label,
        mutation_id=args.mutation_id,
        fault_service=args.fault_service,
        base_url=args.base_url,
        use_case_context=use_case_context,
        use_case=use_case,
        msa_spec_path=args.msa_spec,
        system_description_path=args.system_description,
    )


async def _generate_all_use_case_tests(args: argparse.Namespace) -> str:
    use_cases_path = Path(args.use_cases_file) if args.use_cases_file else USE_CASES_PATH
    use_cases = load_use_cases(use_cases_path)
    if not use_cases:
        raise ValueError(f"No runnable use cases found in {use_cases_path}")

    outputs: list[str] = []
    total = len(use_cases)
    for index, journey in enumerate(use_cases, start=1):
        filename = derive_python_test_filename(journey)
        result = await _generate_single_test(journey, filename, args)
        outputs.append(
            "\n".join(
                [
                    f"[{index}/{total}] {filename}",
                    f"Journey: {journey}",
                    result,
                ]
            )
        )
    return "\n\n".join(outputs)


def _load_selected_structured_use_case(args: argparse.Namespace) -> StructuredUseCase:
    index_path = Path(args.use_case_index) if args.use_case_index else STRUCTURED_USE_CASE_INDEX_PATH
    if args.use_case_id:
        return load_structured_use_case_by_id(args.use_case_id, index_path=index_path)
    if args.use_case_file:
        return load_structured_use_case(Path(args.use_case_file))
    raise ValueError("No structured use case selector provided")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI browsing agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a task in the browser")
    run_parser.add_argument("task", help="What to do")
    run_parser.add_argument("--url", default="about:blank", help="Starting URL")

    test_parser = subparsers.add_parser("test", help="Generate and validate a pytest-playwright test")
    test_parser.add_argument(
        "journey",
        nargs="?",
        help="Ad-hoc user journey to test (if omitted, use cases are loaded from spec/use-cases.txt)",
    )
    test_parser.add_argument(
        "--line",
        type=int,
        help="Run only one line number from spec/use-cases.txt (1-indexed)",
    )
    test_parser.add_argument(
        "--use-case-id",
        help=(
            "Run one structured use case by ID from "
            "the selected structured use-case index"
        ),
    )
    test_parser.add_argument(
        "--use-case-file",
        help="Run one structured use case YAML file by path",
    )
    test_parser.add_argument(
        "--filename",
        help=(
            "Output filename for journey, --line, or structured use case mode "
            "(ignored when running all text use cases)"
        ),
    )
    test_parser.add_argument("--max-retries", type=int, default=5, help="Max fix attempts if test fails (default: 5)")
    add_evaluation_args(test_parser)
    add_input_spec_args(test_parser)

    retest_parser = subparsers.add_parser(
        "retest",
        help="Rerun an existing generated test for evaluation or mutation comparison",
    )
    retest_parser.add_argument("filename", help="Generated test filename to rerun")
    add_evaluation_args(retest_parser)

    args = parser.parse_args()

    if args.command == "test":
        selectors = [
            args.journey is not None,
            args.line is not None,
            bool(args.use_case_id),
            bool(args.use_case_file),
        ]
        if sum(selectors) > 1:
            parser.error(
                "test: provide only one of JOURNEY, --line, --use-case-id, or --use-case-file"
            )
        if args.line is not None and args.line < 1:
            parser.error("test: --line must be >= 1")

    return args


if __name__ == "__main__":
    args = parse_args()
    if args.command == "run":
        safe_print(asyncio.run(run_browser_task(args.url, args.task)))
    elif args.command == "test":
        try:
            if args.journey is not None:
                output = asyncio.run(
                    _generate_single_test(args.journey, args.filename, args)
                )
            elif args.line is not None:
                use_cases_path = (
                    Path(args.use_cases_file) if args.use_cases_file else USE_CASES_PATH
                )
                journey = _read_use_case_at_line(args.line, path=use_cases_path)
                filename = args.filename or derive_python_test_filename(journey)
                output = asyncio.run(
                    _generate_single_test(journey, filename, args)
                )
            elif args.use_case_id or args.use_case_file:
                use_case = _load_selected_structured_use_case(args)
                journey = use_case.journey_text()
                filename = args.filename or derive_use_case_test_filename(use_case)
                output = asyncio.run(
                    _generate_single_test(
                        journey,
                        filename,
                        args,
                        use_case_context=use_case.prompt_context(),
                        use_case=UseCaseMetadata(
                            id=use_case.id,
                            name=use_case.name,
                            role=use_case.role,
                            reference_bucket=use_case.smith_equivalent,
                            source_path=str(use_case.source_path) if use_case.source_path else "",
                        ),
                    )
                )
            else:
                output = asyncio.run(_generate_all_use_case_tests(args))
            safe_print(output)
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc))
    elif args.command == "retest":
        safe_print(
            asyncio.run(
                retest_generated_test(
                    args.filename,
                    variant_label=args.variant_label,
                    mutation_id=args.mutation_id,
                    fault_service=args.fault_service,
                    base_url=args.base_url,
                    msa_spec_path=args.msa_spec,
                )
            )
        )
