import argparse
import asyncio
import sys

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI browsing agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a task in the browser")
    run_parser.add_argument("task", help="What to do")
    run_parser.add_argument("--url", default="about:blank", help="Starting URL")

    test_parser = subparsers.add_parser("test", help="Generate and validate a pytest-playwright test")
    test_parser.add_argument("journey", help="User journey to test")
    test_parser.add_argument(
        "--filename",
        help="Output filename (defaults to a journey-based name such as booking_test.py)",
    )
    test_parser.add_argument("--max-retries", type=int, default=5, help="Max fix attempts if test fails (default: 5)")
    add_evaluation_args(test_parser)

    retest_parser = subparsers.add_parser(
        "retest",
        help="Rerun an existing generated test for evaluation or mutation comparison",
    )
    retest_parser.add_argument("filename", help="Generated test filename to rerun")
    add_evaluation_args(retest_parser)

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.command == "run":
        safe_print(asyncio.run(run_browser_task(args.url, args.task)))
    elif args.command == "test":
        safe_print(
            asyncio.run(
                generate_test(
                    args.filename,
                    args.journey,
                    args.max_retries,
                    variant_label=args.variant_label,
                    mutation_id=args.mutation_id,
                    fault_service=args.fault_service,
                    base_url=args.base_url,
                )
            )
        )
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
