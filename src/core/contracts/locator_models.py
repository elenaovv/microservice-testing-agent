from dataclasses import dataclass


@dataclass(slots=True)
class LocatorCandidate:
    strategy: str = ""
    value: str = ""
    scope: str = ""
    validated: bool = False
    executable: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "value": self.value,
            "scope": self.scope,
            "validated": self.validated,
            "executable": self.executable,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LocatorCandidate":
        return cls(
            strategy=str(data.get("strategy", data.get("type", ""))).strip(),
            value=str(data.get("value", data.get("selector", ""))).strip(),
            scope=str(data.get("scope", "")).strip(),
            validated=bool(data.get("validated", False)),
            executable=bool(data.get("executable", True)),
            note=str(data.get("note", "")).strip(),
        )


SNAPSHOT_SELECTOR_PREFIXES = (
    "generic[ref=",
    "button[ref=",
    "textbox[",
    "combobox[",
    "link[",
    "cell[",
    "row[",
)


def is_snapshot_selector(selector: str) -> bool:
    normalized = selector.strip().lower()
    if not normalized:
        return False
    if "[ref=" in normalized:
        return True
    if any(normalized.startswith(prefix) for prefix in SNAPSHOT_SELECTOR_PREFIXES):
        return True
    if "/" in normalized and not normalized.startswith(("/", "./", "../")):
        return True
    return False


def sanitize_executable_selector(selector: str) -> str:
    cleaned = selector.strip()
    if is_snapshot_selector(cleaned):
        return ""
    return cleaned


def locator_candidates_from_legacy_selector(
    *,
    selector: str,
    label: str = "",
    role: str = "",
    text: str = "",
    element_id: str = "",
    scope: str = "",
) -> list[LocatorCandidate]:
    candidates: list[LocatorCandidate] = []
    executable_selector = sanitize_executable_selector(selector)
    if executable_selector:
        strategy = "xpath" if executable_selector.startswith(("/", "./", "../")) else "css"
        candidates.append(
            LocatorCandidate(
                strategy=strategy,
                value=executable_selector,
                scope=scope,
                validated=False,
                executable=True,
                note="legacy selector",
            )
        )
    elif selector.strip():
        candidates.append(
            LocatorCandidate(
                strategy="snapshot",
                value=selector.strip(),
                scope=scope,
                validated=False,
                executable=False,
                note="non-executable browser snapshot selector",
            )
        )
    if element_id.strip():
        candidates.append(
            LocatorCandidate(
                strategy="css",
                value=f"#{element_id.strip()}",
                scope=scope,
                validated=False,
                executable=True,
                note="element id",
            )
        )
    if role.strip() and (label.strip() or text.strip()):
        candidates.append(
            LocatorCandidate(
                strategy="role",
                value=f"{role.strip()}|{(label or text).strip()}",
                scope=scope,
                validated=False,
                executable=True,
                note="role/name fallback",
            )
        )
    elif label.strip():
        candidates.append(
            LocatorCandidate(
                strategy="label",
                value=label.strip(),
                scope=scope,
                validated=False,
                executable=True,
                note="label fallback",
            )
        )
    elif text.strip():
        candidates.append(
            LocatorCandidate(
                strategy="text",
                value=text.strip(),
                scope=scope,
                validated=False,
                executable=True,
                note="text fallback",
            )
        )

    deduped: list[LocatorCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        key = (candidate.strategy, candidate.value, candidate.scope)
        if not candidate.value or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def locator_candidates_from_observation_locator(
    locator: str,
    *,
    scope: str = "",
) -> list[LocatorCandidate]:
    cleaned = locator.strip()
    if not cleaned:
        return []
    if is_snapshot_selector(cleaned):
        return [
            LocatorCandidate(
                strategy="snapshot",
                value=cleaned,
                scope=scope,
                validated=False,
                executable=False,
                note="non-executable browser snapshot selector",
            )
        ]
    playwright_prefixes = (
        "page.",
        "modal.",
        "container.",
        "locator(",
        "get_by_",
        "getBy",
    )
    if cleaned.startswith(playwright_prefixes):
        strategy = "playwright"
    elif cleaned.startswith(("/", "./", "../")):
        strategy = "xpath"
    else:
        strategy = "css"
    return [
        LocatorCandidate(
            strategy=strategy,
            value=cleaned,
            scope=scope,
            validated=False,
            executable=True,
            note="success observation locator",
        )
    ]


_is_snapshot_selector = is_snapshot_selector
_sanitize_executable_selector = sanitize_executable_selector
_locator_candidates_from_legacy_selector = locator_candidates_from_legacy_selector
_locator_candidates_from_observation_locator = locator_candidates_from_observation_locator
