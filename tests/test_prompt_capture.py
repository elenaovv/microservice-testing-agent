from pathlib import Path
from types import SimpleNamespace

from core.capture.prompt_capture import write_prompt_capture_entries


def test_prompt_capture_entries_are_run_scoped(tmp_path: Path):
    write_prompt_capture_entries(
        output_dir=tmp_path,
        filename="add_test.py",
        requested_journey="journey",
        system_prompt="system",
        browse_prompt="browse",
        test_generation_prompt="generate",
        all_messages=[],
        run_id="run-a",
    )
    write_prompt_capture_entries(
        output_dir=tmp_path,
        filename="add_test.py",
        requested_journey="journey",
        system_prompt="system",
        browse_prompt="browse",
        test_generation_prompt="generate",
        all_messages=[],
        run_id="run-b",
    )

    assert (tmp_path / "add_test" / "run-a").is_dir()
    assert (tmp_path / "add_test" / "run-b").is_dir()
    assert (tmp_path / "add_test" / "run-a" / "000-reference-prompts.txt").is_file()
    assert (tmp_path / "add_test" / "run-b" / "000-reference-prompts.txt").is_file()


def test_prompt_capture_entries_omit_empty_browse_reference(tmp_path: Path):
    message = SimpleNamespace(
        kind="request",
        timestamp="now",
        instructions=None,
        parts=[
            SimpleNamespace(
                part_kind="user-prompt",
                content="generate from static inputs",
            )
        ],
    )

    written = write_prompt_capture_entries(
        output_dir=tmp_path,
        filename="login_test.py",
        requested_journey="journey",
        system_prompt="system",
        browse_prompt="",
        test_generation_prompt="generate",
        all_messages=[message],
        run_id="run-a",
    )

    assert len(written) == 1
    text = written[0].read_text(encoding="utf-8")
    assert "BROWSE PHASE PROMPT" not in text
    assert "TEST GENERATION PHASE PROMPT" not in text

    reference_text = (
        tmp_path / "login_test" / "run-a" / "000-reference-prompts.txt"
    ).read_text(encoding="utf-8")
    assert "BROWSE PHASE PROMPT" not in reference_text
    assert "TEST GENERATION PHASE PROMPT" in reference_text
