"""Compatibility facade for prompt loading and prompt construction.

The implementation is split across focused modules so prompt templates,
structured use-case loading, MSA context selection, and journey rendering can
change independently while existing imports from `prompts.generator` keep
working.
"""

from prompts.builders import build_browse_prompt, build_test_generation_prompt
from core.text.vocabulary import BRIEF_STOPWORDS, CONCEPT_ALIASES, FILENAME_STOPWORDS
from prompts.filenames import (
    derive_python_test_filename,
    derive_use_case_test_filename,
    validate_python_test_filename,
)
from prompts.journey_rendering import (
    _render_journey_contract_for_prompt,
    _render_replay_plan,
    render_journey_contract_for_prompt,
    render_replay_plan,
)
from prompts.spec_context import (
    MSA_SPEC_PATH,
    SYSTEM_DESCRIPTION_PATH,
    build_execution_brief,
    build_relevant_msa_excerpt,
    load_msa_spec,
    load_system_description,
)
from prompts.use_cases import (
    STRUCTURED_USE_CASES_DIR,
    STRUCTURED_USE_CASE_INDEX_PATH,
    USE_CASES_PATH,
    StructuredUseCase,
    load_structured_use_case,
    load_structured_use_case_by_id,
    load_use_case_index,
    load_use_cases,
    resolve_indexed_use_case_path,
)

__all__ = [
    "BRIEF_STOPWORDS",
    "CONCEPT_ALIASES",
    "FILENAME_STOPWORDS",
    "MSA_SPEC_PATH",
    "STRUCTURED_USE_CASES_DIR",
    "STRUCTURED_USE_CASE_INDEX_PATH",
    "SYSTEM_DESCRIPTION_PATH",
    "USE_CASES_PATH",
    "StructuredUseCase",
    "_render_journey_contract_for_prompt",
    "_render_replay_plan",
    "build_browse_prompt",
    "build_execution_brief",
    "build_relevant_msa_excerpt",
    "build_test_generation_prompt",
    "derive_python_test_filename",
    "derive_use_case_test_filename",
    "load_msa_spec",
    "load_structured_use_case",
    "load_structured_use_case_by_id",
    "load_system_description",
    "load_use_case_index",
    "load_use_cases",
    "render_journey_contract_for_prompt",
    "render_replay_plan",
    "resolve_indexed_use_case_path",
    "validate_python_test_filename",
]
