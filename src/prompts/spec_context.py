from pathlib import Path
import re

from core.coverage.coverage_utils import extract_spec_endpoints
from core.text.vocabulary import BRIEF_STOPWORDS, CONCEPT_ALIASES

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MSA_SPEC_PATH = PROJECT_ROOT / "spec" / "msa.yaml"
SYSTEM_DESCRIPTION_PATH = PROJECT_ROOT / "spec" / "system_description.md"


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
    max_services: int = 12,
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
