from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - depends on environment packaging
    yaml = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
USE_CASES_PATH = PROJECT_ROOT / "spec" / "use-cases.txt"
STRUCTURED_USE_CASES_DIR = PROJECT_ROOT / "spec" / "use_cases"
STRUCTURED_USE_CASE_INDEX_PATH = STRUCTURED_USE_CASES_DIR / "index.yaml"


@dataclass(slots=True)
class StructuredUseCase:
    id: str
    role: str
    name: str
    goal: str
    preconditions: list[str]
    success_criteria: list[str]
    notes: str = ""
    smith_equivalent: str = ""
    source_path: Path | None = None

    def journey_text(self) -> str:
        parts = [
            f"{self.role.title()} use case {self.id}: {self.name}.",
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
            f"Role: {self.role}",
            f"Name: {self.name}",
            f"Goal: {self.goal.strip()}",
        ]
        if self.preconditions:
            lines.append("Preconditions:")
            lines.extend(f"- {item}" for item in self.preconditions)
        if self.success_criteria:
            lines.append("Success criteria:")
            lines.extend(f"- {item}" for item in self.success_criteria)
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
                "role": str(item.get("role", "")).strip(),
                "name": str(item.get("name", "")).strip(),
                "path": str(item.get("path", "")).strip(),
                "smith_equivalent": str(item.get("smith_equivalent", "")).strip(),
            }
        )
    return normalized


def resolve_indexed_use_case_path(index_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path

    candidates = [
        index_path.parent / path,
        STRUCTURED_USE_CASES_DIR / path,
        PROJECT_ROOT / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


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
        role=str(data.get("role", "")).strip(),
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
        use_case = load_structured_use_case(
            resolve_indexed_use_case_path(index_path, relative_path)
        )
        if not use_case.smith_equivalent:
            use_case.smith_equivalent = item.get("smith_equivalent", "")
        return use_case
    raise ValueError(f"Unknown use case ID: {normalized_id}")
