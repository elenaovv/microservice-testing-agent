from argparse import Namespace
from pathlib import Path

from main import _load_experiment_use_cases
from prompts.generator import (
    STRUCTURED_USE_CASES_DIR,
    load_use_case_index,
    resolve_indexed_use_case_path,
)


def test_main_index_paths_resolve_to_existing_files():
    missing = [
        entry
        for entry in load_use_case_index()
        if not resolve_indexed_use_case_path(
            STRUCTURED_USE_CASES_DIR / "index.yaml",
            entry["path"],
        ).exists()
    ]

    assert missing == []


def test_default_experiment_uses_research_cases_only():
    args = Namespace(use_case_id="", use_case_file="", use_case_index="")

    use_cases = _load_experiment_use_cases(args)

    assert len(use_cases) == 12
    assert all("research_cases" in Path(str(use_case.source_path)).parts for use_case in use_cases)
