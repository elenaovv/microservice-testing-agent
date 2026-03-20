import argparse
import asyncio

from agent import Deps, agent


async def generate_test(filename: str, journey: str, max_retries: int = 3) -> None:
    """Browse the journey, write a pytest-playwright test, and verify it passes."""
    deps = Deps()
    async with agent:
        nav = await agent.run(
            f"Follow this user journey step by step in the browser. "
            f"Call log_action after every interaction and use start_timer/stop_timer around slow steps. "
            f"Journey: {journey}",
            deps=deps,
        )

        action_summary = "\n".join(
            f"- {e['action']}: {e['note']}" for e in deps.action_log
        ) or "No actions logged."

        result = await agent.run(
            f"Using your logged actions below, write a pytest-playwright test that reproduces every step exactly.\n\n"
            f"Logged actions:\n{action_summary}\n\n"
            f"Save it as '{filename}' using create_test_file, then run it with run_test_file. "
            f"If it fails, fix and retry at most {max_retries} times.",
            message_history=nav.all_messages(),
            deps=deps,
        )
        print(result.output)


async def main(url: str, task: str) -> None:
    async with agent:
        history = []
        if url != "about:blank":
            nav = await agent.run(f"Navigate to {url}")
            history = nav.all_messages()
        result = await agent.run(task, message_history=history)
        print(result.output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI browsing agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a task in the browser")
    run_parser.add_argument("task", help="What to do")
    run_parser.add_argument("--url", default="about:blank", help="Starting URL")

    test_parser = subparsers.add_parser("test", help="Generate and validate a pytest-playwright test")
    test_parser.add_argument("journey", help="User journey to test")
    test_parser.add_argument("--filename", default="test_generated.py", help="Output filename (default: test_generated.py)")
    test_parser.add_argument("--max-retries", type=int, default=3, help="Max fix attempts if test fails (default: 3)")

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.command == "run":
        asyncio.run(main(args.url, args.task))
    elif args.command == "test":
        asyncio.run(generate_test(args.filename, args.journey, args.max_retries))
