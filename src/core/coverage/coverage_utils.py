"""Coverage utilities: endpoint/service inference from the MSA spec and journey captures."""

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.contracts.models import CoverageSnapshot, JourneyCapture
from core.text.vocabulary import COVERAGE_STOPWORDS

try:
    import yaml
except ImportError:  # pragma: no cover - depends on environment packaging
    yaml = None

MSA_SPEC_PATH = Path(__file__).resolve().parent.parent.parent.parent / "spec" / "msa.yaml"

STOPWORDS = COVERAGE_STOPWORDS


def load_msa_spec_text(path: Path = MSA_SPEC_PATH) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _normalize_endpoint(
    service: str,
    item: dict[str, Any],
) -> dict[str, str] | None:
    path = str(
        item.get("path")
        or item.get("route")
        or item.get("uri")
        or item.get("url")
        or ""
    ).strip()
    method = str(item.get("method") or item.get("http_method") or "").strip().upper()
    description = str(
        item.get("description")
        or item.get("summary")
        or item.get("notes")
        or ""
    ).strip()
    if not path:
        return None
    return {
        "service": service,
        "path": path,
        "method": method,
        "description": description,
    }


def _extract_spec_endpoints_yaml(msa_spec: str) -> list[dict[str, str]]:
    if yaml is None:
        return []

    try:
        data = yaml.safe_load(msa_spec) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []

    endpoints: list[dict[str, str]] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return

        services = node.get("services")
        if isinstance(services, dict):
            for service_name, service_spec in services.items():
                if not isinstance(service_spec, dict):
                    continue
                for item in list(service_spec.get("endpoints", [])):
                    if not isinstance(item, dict):
                        continue
                    normalized = _normalize_endpoint(str(service_name), item)
                    if normalized is not None:
                        endpoints.append(normalized)
                walk(service_spec)

        for value in node.values():
            if isinstance(value, dict):
                walk(value)

    walk(data)
    return endpoints


def _extract_spec_endpoints_lines(msa_spec: str) -> list[dict[str, str]]:
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


def extract_spec_endpoints(msa_spec: str) -> list[dict[str, str]]:
    endpoints = _extract_spec_endpoints_yaml(msa_spec)
    if endpoints:
        return endpoints
    return _extract_spec_endpoints_lines(msa_spec)


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


def endpoint_operation_label(endpoint: dict[str, str]) -> str:
    return f"{endpoint.get('method', '').upper()} {endpoint.get('path', '')}".strip()


def service_operation_totals(msa_spec: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for endpoint in extract_spec_endpoints(msa_spec):
        service = endpoint.get("service", "unmapped")
        counts[service] = counts.get(service, 0) + 1
    return dict(sorted(counts.items()))


def match_endpoint_for_request(
    request_path: str,
    request_method: str,
    endpoints: list[dict[str, str]],
) -> dict[str, str] | None:
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
            return endpoint
    return None


def match_service_for_request(
    request_path: str,
    request_method: str,
    endpoints: list[dict[str, str]],
) -> str:
    endpoint = match_endpoint_for_request(
        request_path=request_path,
        request_method=request_method,
        endpoints=endpoints,
    )
    if endpoint is None:
        return "unmapped"
    return endpoint.get("service", "unmapped")


def count_api_calls_by_service(
    requests: list[dict],
    msa_spec: str,
) -> dict[str, int]:
    endpoints = extract_spec_endpoints(msa_spec)
    counts: dict[str, int] = defaultdict(int)
    for request in requests:
        method = str(request.get("method", "")).upper()
        path = str(request.get("path", ""))
        service_name = match_service_for_request(path, method, endpoints)
        counts[service_name] += 1
    return dict(sorted(counts.items()))


def list_unmapped_api_calls(
    requests: list[dict],
    msa_spec: str,
) -> list[dict[str, str | int]]:
    endpoints = extract_spec_endpoints(msa_spec)
    counts: dict[tuple[str, str], int] = defaultdict(int)

    for request in requests:
        method = str(request.get("method", "")).upper()
        path = str(request.get("path", ""))
        if not method or not path:
            continue
        endpoint = match_endpoint_for_request(path, method, endpoints)
        if endpoint is None:
            counts[(method, path)] += 1

    rows = [
        {"method": method, "path": path, "count": count}
        for (method, path), count in counts.items()
    ]
    rows.sort(key=lambda item: (-int(item["count"]), str(item["method"]), str(item["path"])))
    return rows


def covered_operations_by_service(
    requests: list[dict],
    msa_spec: str,
) -> dict[str, list[str]]:
    endpoints = extract_spec_endpoints(msa_spec)
    covered: dict[str, list[str]] = {}
    for request in requests:
        method = str(request.get("method", "")).upper()
        path = str(request.get("path", ""))
        endpoint = match_endpoint_for_request(path, method, endpoints)
        if endpoint is None:
            continue
        service = endpoint.get("service", "unmapped")
        covered.setdefault(service, [])
        covered[service].append(endpoint_operation_label(endpoint))

    return {
        service: dedupe_preserve_order(operations)
        for service, operations in sorted(covered.items())
    }


def apply_operation_coverage(
    coverage: CoverageSnapshot,
    requests: list[dict],
    msa_spec: str,
) -> CoverageSnapshot:
    totals = service_operation_totals(msa_spec)
    covered = covered_operations_by_service(requests, msa_spec)
    updated = coverage.clone()
    updated.service_operation_totals = totals
    updated.covered_operations_by_service = covered
    updated.service_operation_covered = {
        service: len(operations)
        for service, operations in covered.items()
    }
    for service in totals:
        updated.service_operation_covered.setdefault(service, 0)
        updated.covered_operations_by_service.setdefault(service, [])
    return updated
