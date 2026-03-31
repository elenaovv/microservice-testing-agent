from pathlib import Path
import re

from core.models import JourneyCapture

MSA_SPEC_PATH = Path(__file__).resolve().parent.parent / "spec" / "msa.yaml"
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


def build_browse_prompt(journey: str, msa_spec: str) -> str:
    return (
        "Follow this user journey step by step in the browser. "
        "Call log_action after every interaction and use start_timer/stop_timer around slow steps. "
        "Use the MSA specification below as domain context, but verify the actual UI live before deciding the flow.\n\n"
        f"Journey: {journey}\n\n"
        f"MSA specification:\n{msa_spec}"
    )


def build_test_generation_prompt(
    journey: str,
    filename: str,
    max_retries: int,
    msa_spec: str,
    capture: JourneyCapture,
) -> str:
    return (
        "Using the MSA specification, your logged actions, and your recorded timings below, "
        "write a pytest-playwright test that reproduces every step exactly.\n\n"
        f"Journey: {journey}\n\n"
        f"MSA specification:\n{msa_spec}\n\n"
        f"Logged actions:\n{capture.action_summary()}\n\n"
        f"Recorded timings:\n{capture.timing_summary()}\n\n"
        f"Save it as '{filename}' using create_python_test_file, then run it with run_test_file. "
        f"If it fails, fix and retry at most {max_retries} times."
    )


def validate_python_test_filename(filename: str) -> None:
    if not filename.endswith(".py"):
        raise ValueError(
            f"Generated test filename must end with '.py': {filename}"
        )
