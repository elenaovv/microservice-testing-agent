import argparse
import asyncio
import sys
from pathlib import Path

from prompts.generator import (
    USE_CASES_PATH,
    derive_python_test_filename,
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
) -> str:
    return await generate_test(
        filename,
        journey,
        args.max_retries,
        variant_label=args.variant_label,
        mutation_id=args.mutation_id,
        fault_service=args.fault_service,
        base_url=args.base_url,
    )


async def _generate_all_use_case_tests(args: argparse.Namespace) -> str:
    use_cases = load_use_cases()
    if not use_cases:
        raise ValueError(f"No runnable use cases found in {USE_CASES_PATH}")

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
        "--filename",
        help="Output filename for ad-hoc/--line mode (ignored when running all use cases)",
    )
    test_parser.add_argument("--max-retries", type=int, default=5, help="Max fix attempts if test fails (default: 5)")
    add_evaluation_args(test_parser)

    retest_parser = subparsers.add_parser(
        "retest",
        help="Rerun an existing generated test for evaluation or mutation comparison",
    )
    retest_parser.add_argument("filename", help="Generated test filename to rerun")
    add_evaluation_args(retest_parser)

    args = parser.parse_args()

    if args.command == "test":
        if args.journey and args.line is not None:
            parser.error("test: provide either JOURNEY text or --line, not both")
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
                journey = _read_use_case_at_line(args.line)
                filename = args.filename or derive_python_test_filename(journey)
                output = asyncio.run(
                    _generate_single_test(journey, filename, args)
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
                )
            )
        )
