from pathlib import Path
import re

from core.models import JourneyCapture

MSA_SPEC_PATH = Path(__file__).resolve().parent.parent / "spec" / "msa.yaml"
USE_CASES_PATH = Path(__file__).resolve().parent.parent / "spec" / "use-cases.txt"
FILENAME_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "then",
    "that",
    "this",
    "user",
    "users",
    "ticket",
    "tickets",
    "point",
    "train",
    "route",
    "page",
}


def load_msa_spec(path: Path = MSA_SPEC_PATH) -> str:
    if not path.exists():
        raise FileNotFoundError(f"MSA specification file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_use_cases(path: Path = USE_CASES_PATH) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Use case file not found: {path}")
    use_cases: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        use_cases.append(line)
    return use_cases


def derive_python_test_filename(journey: str) -> str:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", journey.lower())
        if len(token) > 2 and token not in FILENAME_STOPWORDS
    ]
    if not tokens:
        return "journey_test.py"
    if tokens[0] == "book":
        tokens[0] = "booking"
    return f"{'_'.join(tokens[:3])}_test.py"


def build_browse_prompt(journey: str, msa_spec: str, base_url: str) -> str:
    return (
        "Follow this user journey step by step in the browser. "
        "Call log_action after every interaction and use start_timer/stop_timer around slow steps. "
        "Use the MSA specification below as domain context, but verify the actual UI live before deciding the flow. "
        f"The UI under test is served from {base_url}; navigate there before you start browsing.\n\n"
        f"Journey: {journey}\n\n"
        f"MSA specification:\n{msa_spec}\n\n"
        "If the browser tooling exposes `browser_network_requests`, call it after exploration and include the JSON result in your final response. "
        "If that tool is not available, finish the exploration normally."
    )


def build_test_generation_prompt(
    journey: str,
    filename: str,
    max_retries: int,
    msa_spec: str,
    capture: JourneyCapture,
    browse_network_requests: list[dict[str, str]],
    base_url: str,
) -> str:
    observed_requests = [
        f"{str(item.get('method', '')).upper():<5} {str(item.get('path', ''))}"
        for item in browse_network_requests
        if str(item.get("method", "")).strip() and str(item.get("path", "")).strip()
    ]
    observed_requests_block = (
        "\n".join(observed_requests)
        if observed_requests
        else "No backend API requests were captured during exploration."
    )

    return (
        "Using the MSA specification, your logged actions, and your recorded timings below, "
        "write a pytest-playwright test that reproduces every step exactly. "
        "Use `import os` and define `BASE_URL = os.environ.get(\"BASE_URL\", "
        f"\"{base_url}\")` once near the top of the file. "
        "Always navigate with `page.goto(BASE_URL, ...)` instead of hardcoding the URL.\n\n"
        "Use the observed backend requests to add focused network-aware checks where appropriate. "
        "Prefer `page.expect_request()` or `page.wait_for_response()` for critical booking and order operations.\n\n"
        f"Journey: {journey}\n\n"
        f"MSA specification:\n{msa_spec}\n\n"
        f"Logged actions:\n{capture.action_summary()}\n\n"
        f"Recorded timings:\n{capture.timing_summary()}\n\n"
        "## Backend requests observed during exploration\n"
        f"{observed_requests_block}\n\n"
        f"Save it as '{filename}' using create_python_test_file, then run it with run_test_file. "
        f"If it fails, fix and retry at most {max_retries} times."
    )


def validate_python_test_filename(filename: str) -> None:
    if not filename.endswith(".py"):
        raise ValueError(
            f"Generated test filename must end with '.py': {filename}"
        )
