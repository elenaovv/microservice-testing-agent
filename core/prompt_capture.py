from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

PROMPT_PART_KINDS = {
    "system-prompt",
    "user-prompt",
    "retry-prompt",
}


def resolve_prompt_capture_output_path(raw_path: str, test_filename: str) -> Path:
    path = Path(raw_path)
    if path.suffix.lower() == ".txt":
        return path
    return path / f"{Path(test_filename).stem}.prompts.txt"


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, (list, tuple)):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue

            nested_content = getattr(item, "content", None)
            if isinstance(nested_content, str):
                parts.append(nested_content)
                continue

            parts.append(str(item))
        return "\n".join(part for part in parts if part)

    if isinstance(content, dict):
        return json.dumps(content, indent=2, ensure_ascii=False)

    return str(content)


def _extract_prompt_entries(messages: Sequence[object]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []

    for message_index, message in enumerate(messages, start=1):
        if str(getattr(message, "kind", "")) != "request":
            continue

        timestamp_value = getattr(message, "timestamp", None)
        timestamp_text = str(timestamp_value) if timestamp_value is not None else ""

        instructions = getattr(message, "instructions", None)
        if isinstance(instructions, str) and instructions.strip():
            entries.append(
                {
                    "message_index": str(message_index),
                    "part": "request.instructions",
                    "timestamp": timestamp_text,
                    "text": instructions,
                }
            )

        parts = getattr(message, "parts", None) or []
        for part_index, part in enumerate(parts, start=1):
            part_kind = str(getattr(part, "part_kind", "")).strip()
            if part_kind not in PROMPT_PART_KINDS:
                continue

            text = _content_to_text(getattr(part, "content", None))
            if not text.strip():
                continue

            entries.append(
                {
                    "message_index": str(message_index),
                    "part": f"{part_kind}[{part_index}]",
                    "timestamp": timestamp_text,
                    "text": text,
                }
            )

    return entries


def write_prompt_capture(
    output_path: Path,
    *,
    filename: str,
    requested_journey: str,
    system_prompt: str,
    browse_prompt: str,
    test_generation_prompt: str,
    all_messages: Sequence[object],
) -> Path:
    entries = _extract_prompt_entries(all_messages)
    captured_at = datetime.now(timezone.utc).isoformat()

    lines: list[str] = [
        "=" * 120,
        f"PROMPT CAPTURE: {filename}",
        "=" * 120,
        f"captured_at_utc: {captured_at}",
        f"requested_journey: {requested_journey}",
        f"captured_prompt_entries: {len(entries)}",
        "",
        "SYSTEM PROMPT",
        "-" * 120,
        system_prompt,
        "",
        "BROWSE PHASE PROMPT",
        "-" * 120,
        browse_prompt,
        "",
        "TEST GENERATION PHASE PROMPT",
        "-" * 120,
        test_generation_prompt,
        "",
        "REQUEST PROMPT TEXT OBSERVED BY MODEL",
        "-" * 120,
    ]

    if entries:
        for entry in entries:
            lines.append(
                "\n".join(
                    [
                        f"message_index: {entry['message_index']}",
                        f"part: {entry['part']}",
                        f"timestamp: {entry['timestamp']}",
                        entry["text"],
                        "",
                    ]
                )
            )
    else:
        lines.append("No request prompt text entries were found in message history.")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")

    return output_path
