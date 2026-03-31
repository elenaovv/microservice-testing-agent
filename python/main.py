import argparse
import asyncio
import sys

from workflow import generate_test, run_browser_task


def safe_print(output: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe_output = output.encode(encoding, errors="replace").decode(encoding)
    print(safe_output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI browsing agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a task in the browser")
    run_parser.add_argument("task", help="What to do")
    run_parser.add_argument("--url", default="about:blank", help="Starting URL")

    test_parser = subparsers.add_parser("test", help="Generate and validate a pytest-playwright test")
    test_parser.add_argument("journey", help="User journey to test")
    test_parser.add_argument("--filename", default="test_generated.py", help="Output filename (default: test_generated.py)")
    test_parser.add_argument("--max-retries", type=int, default=5, help="Max fix attempts if test fails (default: 5)")

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.command == "run":
        safe_print(asyncio.run(run_browser_task(args.url, args.task)))
    elif args.command == "test":
        safe_print(
            asyncio.run(generate_test(args.filename, args.journey, args.max_retries))
        )
