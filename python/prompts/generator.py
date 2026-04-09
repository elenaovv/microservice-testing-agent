from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from core.coverage_utils import extract_spec_endpoints
from core.models import JourneyCapture

try:
    import yaml
except ImportError:  # pragma: no cover - depends on environment packaging
    yaml = None

MSA_SPEC_PATH = Path(__file__).resolve().parent.parent / "spec" / "msa.yaml"
SYSTEM_DESCRIPTION_PATH = (
    Path(__file__).resolve().parent.parent / "spec" / "system_description.md"
)
USE_CASES_PATH = Path(__file__).resolve().parent.parent / "spec" / "use-cases.txt"
STRUCTURED_USE_CASES_DIR = Path(__file__).resolve().parent.parent / "spec" / "use_cases"
STRUCTURED_USE_CASE_INDEX_PATH = STRUCTURED_USE_CASES_DIR / "index.yaml"

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

BRIEF_STOPWORDS = FILENAME_STOPWORDS | {
    "success",
    "criteria",
    "preconditions",
    "authenticated",
    "state",
    "actor",
    "role",
    "admin",
    "traveler",
}

CONCEPT_ALIASES = {
    "book": ["booking", "reserve", "reservation", "purchase"],
    "booking": ["book", "reserve", "reservation", "purchase"],
    "login": ["authenticate", "authentication", "signin", "session"],
    "logout": ["signout", "session"],
    "pay": ["payment", "checkout", "purchase"],
    "payment": ["pay", "checkout", "purchase"],
    "cancel": ["refund", "revoke", "void"],
    "rebook": ["change", "modify", "exchange"],
    "order": ["purchase", "reservation", "checkout"],
    "route": ["path", "trip", "travel"],
    "station": ["location", "stop", "terminal"],
    "train": ["trip", "travel", "service"],
    "price": ["fare", "cost", "amount"],
    "schedule": ["trip", "timetable", "departure"],
    "user": ["account", "profile", "identity"],
}


@dataclass(slots=True)
class StructuredUseCase:
    id: str
    actor: str
    name: str
    goal: str
    preconditions: list[str]
    success_criteria: list[str]
    notes: str = ""
    smith_equivalent: str = ""
    source_path: Path | None = None

    def journey_text(self) -> str:
        parts = [
            f"{self.actor.title()} use case {self.id}: {self.name}.",
            self.goal.strip(),
        ]
        if self.preconditions:
            parts.append("Preconditions: " + "; ".join(self.preconditions) + ".")
        if self.success_criteria:
            parts.append(
                "Success criteria: " + "; ".join(self.success_criteria) + "."
            )
        return " ".join(part for part in parts if part)

    def prompt_context(self) -> str:
        lines = [
            f"ID: {self.id}",
            f"Actor: {self.actor}",
            f"Name: {self.name}",
            f"Goal: {self.goal.strip()}",
        ]
        if self.preconditions:
            lines.append("Preconditions:")
            lines.extend(f"- {item}" for item in self.preconditions)
        if self.success_criteria:
            lines.append("Success criteria:")
            lines.extend(f"- {item}" for item in self.success_criteria)
        if self.smith_equivalent and self.smith_equivalent.lower() != "none":
            lines.append(f"Smith equivalent: {self.smith_equivalent}")
        if self.notes:
            lines.append(f"Notes: {self.notes}")
        if self.source_path is not None:
            lines.append(f"Source file: {self.source_path}")
        return "\n".join(lines)


def _require_yaml() -> Any:
    if yaml is None:
        raise RuntimeError(
            "Structured use case support requires PyYAML in the Python environment."
        )
    return yaml


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")
    yaml_module = _require_yaml()
    data = yaml_module.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return data


def load_msa_spec(path: Path | None = None) -> str:
    path = path or MSA_SPEC_PATH
    if not path.exists():
        raise FileNotFoundError(f"MSA specification file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_system_description(path: Path | None = None) -> str:
    path = path or SYSTEM_DESCRIPTION_PATH
    if not path.exists():
        raise FileNotFoundError(f"System description file not found: {path}")
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


def load_use_case_index(
    path: Path = STRUCTURED_USE_CASE_INDEX_PATH,
) -> list[dict[str, str]]:
    data = _load_yaml_file(path)
    use_cases = data.get("use_cases", [])
    if not isinstance(use_cases, list):
        raise ValueError(f"Expected 'use_cases' list in {path}")
    normalized: list[dict[str, str]] = []
    for item in use_cases:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": str(item.get("id", "")).strip(),
                "actor": str(item.get("actor", "")).strip(),
                "name": str(item.get("name", "")).strip(),
                "path": str(item.get("path", "")).strip(),
                "smith_equivalent": str(item.get("smith_equivalent", "")).strip(),
            }
        )
    return normalized


def _normalize_preconditions(data: dict[str, Any]) -> list[str]:
    preconditions_data = data.get("preconditions", {})
    if not isinstance(preconditions_data, dict):
        return []

    preconditions: list[str] = []
    authenticated_as = str(preconditions_data.get("authenticated_as", "")).strip()
    if authenticated_as and authenticated_as.lower() != "none":
        preconditions.append(f"authenticated as {authenticated_as}")

    for item in list(preconditions_data.get("state", [])):
        text = str(item).strip()
        if text:
            preconditions.append(text)

    return preconditions


def load_structured_use_case(path: Path) -> StructuredUseCase:
    data = _load_yaml_file(path)
    success_criteria = [
        str(item).strip()
        for item in list(data.get("success_criteria", []))
        if str(item).strip()
    ]
    return StructuredUseCase(
        id=str(data.get("id", "")).strip(),
        actor=str(data.get("actor", "")).strip(),
        name=str(data.get("name", "")).strip(),
        goal=str(data.get("goal", "")).strip(),
        preconditions=_normalize_preconditions(data),
        success_criteria=success_criteria,
        notes=str(data.get("notes", "")).strip(),
        smith_equivalent=str(data.get("smith_equivalent", "")).strip(),
        source_path=path,
    )


def load_structured_use_case_by_id(
    use_case_id: str,
    index_path: Path = STRUCTURED_USE_CASE_INDEX_PATH,
) -> StructuredUseCase:
    normalized_id = use_case_id.strip()
    for item in load_use_case_index(index_path):
        if item.get("id") != normalized_id:
            continue
        relative_path = item.get("path", "")
        if not relative_path:
            raise ValueError(f"Use case {normalized_id} has no path in {index_path}")
        use_case = load_structured_use_case(index_path.parent / relative_path)
        if not use_case.smith_equivalent:
            use_case.smith_equivalent = item.get("smith_equivalent", "")
        return use_case
    raise ValueError(f"Unknown use case ID: {normalized_id}")


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


def derive_use_case_test_filename(use_case: StructuredUseCase) -> str:
    return derive_python_test_filename(use_case.name)


def _brief_tokens(*parts: str) -> list[str]:
    text = " ".join(part.lower() for part in parts if part)
    base_tokens = [
        token
        for token in re.findall(r"[a-z0-9_]+", text)
        if len(token) > 2 and token not in BRIEF_STOPWORDS
    ]
    expanded_tokens = list(base_tokens)
    for token in base_tokens:
        expanded_tokens.extend(CONCEPT_ALIASES.get(token, []))
    return expanded_tokens


def build_relevant_msa_excerpt(
    journey: str,
    msa_spec: str,
    *,
    use_case_context: str = "",
    max_services: int = 6,
    max_endpoints_per_service: int = 4,
) -> str:
    tokens = _brief_tokens(journey, use_case_context)
    if not tokens:
        return "No focused service slice could be derived from the selected journey."

    grouped_matches: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for endpoint in extract_spec_endpoints(msa_spec):
        haystack = " ".join(endpoint.values()).lower()
        score = sum(1 for token in tokens if token in haystack)
        if score <= 0:
            continue
        service = endpoint.get("service", "unmapped")
        grouped_matches.setdefault(service, []).append((score, endpoint))

    if not grouped_matches:
        return "No focused service slice could be derived from the selected journey."

    ranked_services = sorted(
        grouped_matches.items(),
        key=lambda item: (
            -sum(score for score, _ in item[1]),
            item[0],
        ),
    )

    lines: list[str] = []
    for service, matches in ranked_services[:max_services]:
        lines.append(f"{service}:")
        ranked_endpoints = sorted(
            matches,
            key=lambda item: (-item[0], item[1].get("path", "")),
        )
        for _, endpoint in ranked_endpoints[:max_endpoints_per_service]:
            description = endpoint.get("description", "").strip()
            endpoint_line = (
                f"- {endpoint.get('method', '').upper()} {endpoint.get('path', '')}"
            )
            if description:
                endpoint_line += f" - {description}"
            lines.append(endpoint_line)
    return "\n".join(lines)


def build_execution_brief(
    journey: str,
    msa_spec: str,
    *,
    system_description: str = "",
    use_case_context: str = "",
) -> str:
    sections = [f"Journey:\n{journey}"]
    if system_description:
        sections.append(f"System description:\n{system_description}")
    if use_case_context:
        sections.append(f"Structured use case:\n{use_case_context}")
    sections.append(
        "Relevant MSA slice:\n"
        + build_relevant_msa_excerpt(
            journey=journey,
            msa_spec=msa_spec,
            use_case_context=use_case_context,
        )
    )
    return "\n\n".join(sections)


def build_browse_prompt(
    journey: str,
    msa_spec: str,
    base_url: str,
    *,
    system_description: str = "",
    use_case_context: str = "",
) -> str:
    execution_brief = build_execution_brief(
        journey=journey,
        msa_spec=msa_spec,
        system_description=system_description,
        use_case_context=use_case_context,
    )
    sections = [
        "Follow this user journey step by step in the browser. "
        "Call log_action after every interaction and use start_timer/stop_timer around slow steps. "
        "Use the execution brief below as domain context, but verify the actual UI live before deciding the flow. "
        f"The UI under test is served from {base_url}; navigate there before you start browsing.",
        f"Execution brief:\n{execution_brief}",
        "If the browser tooling exposes `browser_network_requests`, call it after exploration and include the JSON result in your final response. "
        "If that tool is not available, finish the exploration normally.",
    ]
    return "\n\n".join(sections)


def build_test_generation_prompt(
    journey: str,
    filename: str,
    max_retries: int,
    msa_spec: str,
    capture: JourneyCapture,
    browse_network_requests: list[dict[str, str]],
    base_url: str,
    *,
    system_description: str = "",
    use_case_context: str = "",
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

    execution_brief = build_execution_brief(
        journey=journey,
        msa_spec=msa_spec,
        system_description=system_description,
        use_case_context=use_case_context,
    )
    sections = [
        "Using the execution brief, your logged actions, and your recorded timings below, "
        "write a pytest-playwright test that reproduces every step exactly. "
        "Use `import os` and define `BASE_URL = os.environ.get(\"BASE_URL\", "
        f"\"{base_url}\")` once near the top of the file. "
        "Always navigate with `page.goto(BASE_URL, ...)` instead of hardcoding the URL.",
        "Use the observed backend requests to add focused network-aware checks where appropriate. "
        "Prefer `page.expect_request()` or `page.wait_for_response()` for critical booking and order operations.",
        f"Execution brief:\n{execution_brief}",
        f"Logged actions:\n{capture.action_summary()}",
        f"Recorded timings:\n{capture.timing_summary()}",
        "Backend requests observed during exploration:\n"
        f"{observed_requests_block}",
        f"Save it as '{filename}' using create_python_test_file, then run it with run_test_file. "
        f"If it fails, fix and retry at most {max_retries} times.",
    ]
    return "\n\n".join(sections)


def validate_python_test_filename(filename: str) -> None:
    if not filename.endswith(".py"):
        raise ValueError(
            f"Generated test filename must end with '.py': {filename}"
        )
