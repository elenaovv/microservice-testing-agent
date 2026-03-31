"""Coverage utilities: endpoint/service inference from the MSA spec and journey captures."""

import re
from pathlib import Path

from core.models import JourneyCapture

MSA_SPEC_PATH = Path(__file__).resolve().parent.parent / "spec" / "msa.yaml"

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "after",
    "before",
    "page",
    "button",
    "form",
    "user",
    "users",
    "ticket",
    "tickets",
    "train",
    "route",
    "booking",
    "book",
    "clicked",
    "click",
    "waited",
    "verified",
    "verify",
    "opened",
    "open",
    "page",
}


def load_msa_spec_text(path: Path = MSA_SPEC_PATH) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def extract_spec_endpoints(msa_spec: str) -> list[dict[str, str]]:
    endpoints: list[dict[str, str]] = []
    current_service = ""
    current_endpoint: dict[str, str] | None = None

    for raw_line in msa_spec.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if indent == 4 and stripped.endswith(":") and not stripped.startswith("- "):
            current_service = stripped[:-1]
            continue

        if stripped.startswith("- path:"):
            if current_endpoint is not None:
                endpoints.append(current_endpoint)
            current_endpoint = {
                "service": current_service,
                "path": stripped.split(":", 1)[1].strip(),
                "method": "",
                "description": "",
            }
            continue

        if current_endpoint is None:
            continue

        if stripped.startswith("method:"):
            current_endpoint["method"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("description:"):
            current_endpoint["description"] = stripped.split(":", 1)[1].strip()
        elif indent <= 4 and stripped:
            endpoints.append(current_endpoint)
            current_endpoint = None

    if current_endpoint is not None:
        endpoints.append(current_endpoint)

    return endpoints


def extract_service_name(endpoint_label: str) -> str:
    match = re.search(r"\(([^()]+)\)", endpoint_label)
    if match is None:
        return ""
    return match.group(1).strip()


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def coverage_tokens(
    requested_journey: str,
    capture: JourneyCapture,
) -> set[str]:
    capture_text = " ".join(
        f"{step.action} {step.note}" for step in capture.actions
    )
    text = f"{requested_journey} {capture_text}".lower()
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", text)
        if len(token) > 2 and token not in STOPWORDS
    }


def infer_endpoint_candidates(
    requested_journey: str,
    capture: JourneyCapture,
    msa_spec: str,
) -> list[str]:
    tokens = coverage_tokens(requested_journey, capture)
    if not tokens:
        return []

    candidates: list[str] = []
    for endpoint in extract_spec_endpoints(msa_spec):
        haystack = " ".join(endpoint.values()).lower()
        matched = [token for token in tokens if token in haystack]
        if matched:
            label = (
                f"{endpoint['method']} {endpoint['path']}"
                f" ({endpoint['service']})"
            )
            if endpoint["description"]:
                label += f" - {endpoint['description']}"
            candidates.append(label)

    return dedupe_preserve_order(candidates)


def match_service_for_request(
    request_path: str,
    request_method: str,
    endpoints: list[dict[str, str]],
) -> str:
    for endpoint in endpoints:
        endpoint_method = endpoint.get("method", "").upper()
        if endpoint_method and endpoint_method != request_method:
            continue
        endpoint_path = endpoint.get("path", "")
        placeholder_path = re.sub(r"\{[^/]+\}", "__PARAM__", endpoint_path)
        endpoint_regex = "^" + re.escape(placeholder_path).replace(
            "__PARAM__",
            r"[^/]+",
        ) + "$"
        if re.match(endpoint_regex, request_path):
            return endpoint.get("service", "unmapped")
    return "unmapped"


def count_api_calls_by_service(
    requests: list[dict],
    msa_spec: str,
) -> dict[str, int]:
    from collections import defaultdict

    endpoints = extract_spec_endpoints(msa_spec)
    counts: dict[str, int] = defaultdict(int)
    for request in requests:
        method = str(request.get("method", "")).upper()
        path = str(request.get("path", ""))
        service_name = match_service_for_request(path, method, endpoints)
        counts[service_name] += 1
    return dict(sorted(counts.items()))
