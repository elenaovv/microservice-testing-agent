from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import py_compile
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(REPO_ROOT / ".env")

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from pydantic_ai import RunContext

from core.evaluation_utils import (
    EVALUATION_HISTORY_FILENAME,
    append_evaluation_history,
    write_evaluation_summary,
)
from core.executor import run_generated_test
from core.models import (
    EvaluationContext,
    ExecutionArtifact,
    ExecutionReport,
    ExecutionResult,
    UseCaseMetadata,
)
from core.prompt_capture import write_prompt_capture_entries
from core.reporting import (
    build_execution_report,
    load_execution_report,
    write_execution_report,
)
from core.report_rendering import render_execution_report
from core.retry_budget import render_repair_budget, repair_budget_exhausted
from prompts.generator import (
    MSA_SPEC_PATH,
    SYSTEM_DESCRIPTION_PATH,
    STRUCTURED_USE_CASE_INDEX_PATH,
    StructuredUseCase,
    derive_use_case_test_filename,
    load_msa_spec,
    load_structured_use_case,
    load_structured_use_case_by_id,
    load_system_description,
    validate_python_test_filename,
)

DEFAULT_INDEX_PATH = Path(__file__).resolve().parent / "research_12_index.yaml"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "openai:gpt-5.4").strip() or "openai:gpt-5.4"
DEFAULT_BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080").strip() or "http://localhost:8080"
AGENT_USAGE_LIMITS = UsageLimits(request_limit=120)
FAILURE_STATE_CONFTEXT = r'''import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

VISIBLE_TEXT_LIMIT = 12000


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"direct_baseline_rep_{report.when}", report)


@pytest.fixture(autouse=True)
def direct_baseline_capture_failure_state(request, page):
    responses = []

    def on_response(playwright_response):
        parsed = urlparse(playwright_response.url)
        if "/api/" not in parsed.path:
            return
        responses.append(
            {
                "method": playwright_response.request.method.upper(),
                "url": playwright_response.url,
                "path": parsed.path,
                "status": playwright_response.status,
            }
        )

    page.context.on("response", on_response)
    yield

    call_report = getattr(request.node, "direct_baseline_rep_call", None)
    if call_report is None or not call_report.failed:
        return

    test_path = Path(str(getattr(request.node, "path", request.node.fspath)))
    output_dir = Path(__import__("os").environ.get("NETWORK_RESULTS_DIR", "test-results"))
    output_dir.mkdir(parents=True, exist_ok=True)
    failure_state = {
        "filename": test_path.name,
        "url": "",
        "title": "",
        "visible_text": "",
        "status_lines": [],
        "api_responses": responses,
        "capture_error": "",
    }
    try:
        visible_text = page.locator("body").inner_text(timeout=1000)
        failure_state["url"] = page.url
        failure_state["title"] = page.title()
        failure_state["visible_text"] = visible_text[:VISIBLE_TEXT_LIMIT]
        failure_state["status_lines"] = [
            line.strip()
            for line in visible_text.splitlines()
            if any(
                marker in line.lower()
                for marker in (
                    "incorrect",
                    "invalid",
                    "error",
                    "fail",
                    "failed",
                    "not login",
                    "login status",
                    "success",
                )
            )
        ][:20]
    except Exception as exc:
        failure_state["capture_error"] = f"{type(exc).__name__}: {exc}"

    state_path = output_dir / f"{test_path.stem}.failure-state.json"
    state_path.write_text(json.dumps(failure_state, indent=2), encoding="utf-8")
'''

BASELINE_SYSTEM_PROMPT = (
    "You are a pytest-playwright test generation agent for a direct-generation baseline. "
    "Generate tests from the static structured use case and MSA specification context. "
    "The only available tools are create_python_test_file and run_test_file. "
    "Use the page fixture, read BASE_URL from the environment with a localhost fallback, "
    "and derive assertions from the use-case success criteria. "
    "Do not read local files, source files, result folders, prompt captures, journey guides, "
    "screenshots, or prior experiment artifacts from generated test code. "
    "Do not use custom JavaScript, fetch, XMLHttpRequest, page.evaluate, or direct API calls "
    "to bypass the UI. The frontend application must trigger all backend communication. "
    "Repair failures using only the generated code and run_test_file output/artifacts. "
    "Use native Playwright interactions for all UI actions, scope modal/dialog/overlay "
    "interactions to the active container, and avoid page-level locators when an overlay "
    "may contain duplicate labels."
)


SHARED_TEST_AUTHORING_POLICY = (
    "- Use the pytest `page` fixture; do not create or manage browsers manually.\n"
    "- Generated tests must not read local files or prior experiment artifacts. Do not "
    "use open(), pathlib/path reads, json/yaml file loads, prompt-capture files, "
    "journey guides, screenshots, result folders, or source-code inspection as test "
    "inputs. Use only the prompt-provided static context, environment variables, "
    "normal UI interaction, and run_test_file failure output.\n"
    "- Set `page.set_default_timeout(30000)` near the start of the test.\n"
    "- Use native Playwright interactions such as locator.click(), locator.fill(), "
    "locator.press_sequentially(), select_option(), and keyboard Tab/blur. Do not use "
    "custom JavaScript, page.evaluate, fetch, XMLHttpRequest, or direct API calls.\n"
    "- Prefer stable CSS ids from the frozen MSA when they are available. Otherwise "
    "prefer scoped get_by_role/get_by_label locators for interactive elements and "
    "reserve text locators for assertions or stable anchors.\n"
    "- Scope locators to the active form, modal, table row, or page section when the "
    "same label/text can appear more than once.\n"
    "- Treat visible modals, dialogs, drawers, and overlays as the active interaction "
    "scope. First locate a reliable modal/container anchor, then fill fields and click "
    "actions inside that container. Never click a page-level button when a modal may "
    "contain a same-named action.\n"
    "- Do not assume confirmation controls have a button role. If role lookup fails, "
    "use a scoped CSS/text locator inside the active container.\n"
    "- For create/register flows, generate unique runtime values and reuse those exact "
    "variables for assertions.\n"
    "- For date or autocomplete controls, enter values through the UI format and commit "
    "them with blur/Tab or by selecting the visible suggestion/option before submitting.\n"
    "- Derive assertions from the success criteria only. Do not assert incidental errors "
    "or intermediate states unless the use case explicitly requires them.\n"
    "- Use re.compile(r'...', re.IGNORECASE) for text assertions when capitalization may vary. "
    "Always use raw strings inside re.compile(): write re.compile(r'pattern\\s*text') not "
    "re.compile('pattern\\s*text').\n"
    "- to_contain_text() and get_by_text() are case-sensitive by default. Match the exact "
    "case from the UI or wrap the expected text in re.compile('...', re.IGNORECASE).\n"
    "- Use expect(locator).to_be_visible() before interacting with elements so failures "
    "are clear.\n"
    "- Playwright API specifics: .first is a property, write locator.first not "
    "locator.first(). to_have_url() accepts only a string or a re.compile() pattern, "
    "never a lambda.\n"
    "- page.wait_for_response() does not exist. For network assertions in tests use "
    "page.expect_response() or page.expect_request() as context managers wrapping the "
    "action that triggers the request.\n"
    "- For dialog handling, register page.on('dialog', lambda d: d.accept()) BEFORE the "
    "click that triggers the dialog; page.expect_dialog() does not exist.\n"
    "- Add an `if __name__ == '__main__':` block at the bottom of the file that launches "
    "Playwright with sync_playwright() and calls the test function, so the file can also "
    "be run directly as a Python script.\n"
)


BASELINE_PROMPT_PARITY_POLICY = (
    "- For tests involving delete, update, or similar operations on existing data, do "
    "not hardcode a specific entity name or ID. Select an entity matching the "
    "preconditions dynamically at runtime, capture that target identifier from the "
    "chosen row, and use that same identifier for all post-action checks. Do not "
    "switch target rows mid-test.\n"
    "- If a stable destructive target cannot be identified safely, prefer creating a "
    "disposable entity first and deleting that exact entity, or fail fast with a clear "
    "precondition assertion.\n"
    "- Use frontend-observed network checks only when the test itself can observe the "
    "request caused by a UI action. Prefer page.expect_request() or "
    "page.expect_response() around the exact action that triggers the request. Never "
    "synthesize network calls directly.\n"
    "- For date fields in booking/search forms, interact through the UI control format "
    "and commit the value with blur/Tab before clicking Search. Do not force backend "
    "timestamp text into the visible input field.\n"
    "- Locator strategy reminder: use get_by_role over get_by_text for interactive "
    "elements. Strict mode will fail if a locator matches more than one element. For "
    "every locator, ask whether the chosen word is unique on the page.\n"
    "- For form inputs, never use the field's current value as its locator. Prefer "
    "id-based locators, scoped structural locators, get_by_label(), or "
    "get_by_placeholder() only when the placeholder is actually available.\n"
    "- Login submission: always click the actual login form submit control by role "
    "(button or input[type=submit]) scoped to the login form. Do not use get_by_text "
    "fallbacks or body clicks for login.\n"
    "- If the static inputs or failure output expose element ids for modal fields, "
    "prefer id-based locators over role/label lookups inside the modal. Only use "
    "role/label when ids are missing. Always scope modal field locators to the "
    "anchored modal container.\n"
    "- Locator policy: use stable executable CSS/test-id candidates first when known, "
    "then scoped role/label candidates, then text candidates. Use positional locators "
    "only inside a validated or otherwise stable container. Ignore non-executable "
    "snapshot-style locator text such as browser refs or generic ref labels.\n"
    "- If the static inputs or failure output expose the modal submit control "
    "tag/id/class/data attributes, use that exact selector within the modal. Do not "
    "assume the confirm control has a button role; if it is a span/div/a element, "
    "locate it by tag/class/text inside the modal and click it.\n"
    "- Never use coordinate-based interactions in generated tests, for example "
    "page.mouse.click(x, y). Click explicit locators scoped to the correct container.\n"
    "- For any field likely to use autocomplete, use locator.press_sequentially(value) "
    "instead of locator.fill(value), then wait for and select the visible suggestion "
    "before continuing.\n"
    "- If select option values are available from static inputs or failure output, "
    "prefer select_option(value=...) over labels. Use label-based selection only when "
    "the label is confirmed visible in the control.\n"
    "- For all text content assertions, use re.compile('...', re.IGNORECASE) rather "
    "than a plain string.\n"
    "- Modal-scoping helper: when a modal/dialog/overlay is involved, locate a "
    "reliable modal anchor first, such as unique heading text, distinctive phrase, "
    "role=dialog, or an element with class containing modal/overlay. Scope subsequent "
    "actions to that container using Playwright locators. Example:\n"
    "  modal = page.locator(\":has-text('<modal anchor>')\").last\n"
    "  modal.wait_for(state=\"visible\")\n"
    "  modal.locator('<field selector>').fill(value)\n"
    "  modal.locator('<submit selector>').click()\n"
    "  modal.wait_for(state=\"hidden\")\n"
    "- When a modal is open, never use page-level locators for its buttons or fields. "
    "Always use modal-scoped locators anchored to the active modal/container.\n"
    "- For repeated-record success assertions, use a stable row/container scope and "
    "field assertions inside that scope. If two fields can contain the same visible "
    "value, assert by stable child selector or position within the already-matched "
    "scope, such as row.locator('td').nth(index), rather than broad page text.\n"
    "- Repair rule: use failure_diagnosis first. If it says the test was blocked "
    "before the required service call, repair that first failing locator/action "
    "instead of chasing the missing network call. Only repair the service trigger "
    "when the diagnosis shows the flow reached the trigger action without emitting "
    "the required side effect.\n"
)


@dataclass(slots=True)
class BaselineDeps:
    evaluation: EvaluationContext
    max_retries: int
    output_dir: Path
    history_dir: Path
    generated_tests_dir: Path
    runtime_results_dir: Path
    msa_spec_path: Path
    requested_journey: str
    capture_failure_state: bool = False
    use_case: UseCaseMetadata | None = None
    test_attempts: int = 0
    failed_test_attempts: int = 0
    generation_attempts: int = 0
    last_test_hash: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_transcript: list[dict[str, Any]] = field(default_factory=list)


def _require_yaml() -> Any:
    if yaml is None:
        raise RuntimeError("PyYAML is required to run the direct baseline.")
    return yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")
    data = _require_yaml().safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {path}")
    return data


def _safe_print(output: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    print(output.encode(encoding, errors="replace").decode(encoding))


def _model_slug(model: str) -> str:
    slug = re.sub(r"[:/\\]", "-", model).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug or "default-model"


def _syntax_check(path: Path) -> str | None:
    if not path.exists():
        return f"File not found: {path}"
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        return str(exc)
    return None


def _write_failure_state_conftest(generated_tests_dir: Path) -> None:
    generated_tests_dir.mkdir(parents=True, exist_ok=True)
    conftest_path = generated_tests_dir / "conftest.py"
    conftest_path.write_text(FAILURE_STATE_CONFTEXT, encoding="utf-8")


def _append_tool_transcript(deps: BaselineDeps, event: dict[str, Any]) -> None:
    payload = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    deps.tool_transcript.append(payload)
    transcript_path = deps.output_dir.parent / "tool-transcript.jsonl"
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    with transcript_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload))
        handle.write("\n")


def _structured_use_case_context(use_case: StructuredUseCase) -> str:
    lines = [
        f"ID: {use_case.id}",
        f"Role: {use_case.role}",
        f"Name: {use_case.name}",
        f"Goal: {use_case.goal.strip()}",
    ]
    if use_case.preconditions:
        lines.append("Preconditions:")
        lines.extend(f"- {item}" for item in use_case.preconditions)
    if use_case.success_criteria:
        lines.append("Success criteria:")
        lines.extend(f"- {item}" for item in use_case.success_criteria)
    if use_case.notes:
        lines.append(f"Notes: {use_case.notes}")
    return "\n".join(lines)


def _build_execution_brief(
    *,
    use_case: StructuredUseCase,
    journey: str,
    msa_spec: str,
    system_description: str,
) -> str:
    sections = [
        f"Use case description:\n{journey}",
        f"Structured use case:\n{_structured_use_case_context(use_case)}",
    ]
    if system_description:
        sections.append(f"System description:\n{system_description}")
    sections.append(f"Full frozen MSA specification:\n{msa_spec}")
    return "\n\n".join(sections)


def _build_baseline_prompt(
    *,
    use_case: StructuredUseCase,
    journey: str,
    filename: str,
    max_retries: int,
    msa_spec: str,
    system_description: str,
    base_url: str,
) -> str:
    execution_brief = _build_execution_brief(
        use_case=use_case,
        journey=journey,
        msa_spec=msa_spec,
        system_description=system_description,
    )
    return "\n\n".join(
        [
            "DIRECT GENERATION BASELINE. Write a pytest-playwright test that "
            "implements the use case below from the static inputs only.",
            f"The application under test is served from {base_url}. "
            "Use `import os` and define `BASE_URL = os.environ.get(\"BASE_URL\", "
            f"\"{base_url}\")` once near the top of the file. Use BASE_URL as the "
            "host for all navigation. If the full frozen MSA specification provides "
            "a relevant UI entry point, navigate to it by joining it with BASE_URL "
            "(for example, `page.goto(f\"{BASE_URL}/client_login.html\", ...)`). "
            "Do not hardcode the host URL.",
            "Implement the use case goal, preconditions, and success criteria. "
            "Derive every assertion from the success criteria. Do not invent extra checks.",
            "Choose Playwright locators from user-visible labels, roles, names, and "
            "page structure implied by the use case and full frozen MSA specification. "
            "Prefer get_by_role and get_by_label for interactive elements. Use CSS ids only "
            "when supplied by the frozen MSA or when failure output shows they are needed.",
            "For create/register flows, generate unique values at runtime, for example "
            "with time.time_ns() or a UUID suffix, and reuse those variables for assertions.",
            "Do not use custom JavaScript, fetch, XMLHttpRequest, page.evaluate, or "
            "direct API calls to synthesize backend requests or bypass the UI.",
            SHARED_TEST_AUTHORING_POLICY,
            BASELINE_PROMPT_PARITY_POLICY,
            f"Execution brief:\n{execution_brief}",
            f"Save it as '{filename}' using create_python_test_file, then run it with "
            f"run_test_file. If it fails, repair the test using only run_test_file output "
            f"and artifacts. Retry at most {max_retries} times.",
        ]
    )


def _make_agent(model: str) -> Agent:
    baseline_agent = Agent(
        model,
        deps_type=BaselineDeps,
        retries=int(os.environ.get("BASELINE_INTERNAL_RETRIES", "2")),
        system_prompt=BASELINE_SYSTEM_PROMPT,
    )

    @baseline_agent.tool
    def create_python_test_file(ctx: RunContext[BaselineDeps], filename: str, code: str) -> str:
        """Create or replace a pytest-playwright test file."""
        validate_python_test_filename(filename)
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]
        ctx.deps.tool_calls.append(
            {
                "tool": "create_python_test_file",
                "filename": filename,
                "code_hash": code_hash,
                "line_count": len(code.splitlines()),
            }
        )
        if code_hash == ctx.deps.last_test_hash:
            result_text = (
                f"Rejected: generated code is identical to the previous attempt "
                f"(hash {code_hash}). Make a meaningful repair before running again."
            )
            _append_tool_transcript(
                ctx.deps,
                {
                    "tool": "create_python_test_file",
                    "filename": filename,
                    "attempt_number": ctx.deps.generation_attempts + 1,
                    "code_hash": code_hash,
                    "line_count": len(code.splitlines()),
                    "rejected": True,
                    "returned_to_model": result_text,
                },
            )
            return result_text
        ctx.deps.last_test_hash = code_hash
        ctx.deps.generation_attempts += 1
        ctx.deps.generated_tests_dir.mkdir(parents=True, exist_ok=True)
        path = ctx.deps.generated_tests_dir / filename
        path.write_text(code, encoding="utf-8")

        archive_dir = ctx.deps.output_dir / "test-attempts" / Path(filename).stem
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"attempt-{ctx.deps.generation_attempts:03d}-{code_hash}.py"
        archive_path.write_text(code, encoding="utf-8")
        result_text = f"Created {path}"
        _append_tool_transcript(
            ctx.deps,
            {
                "tool": "create_python_test_file",
                "filename": filename,
                "attempt_number": ctx.deps.generation_attempts,
                "code_hash": code_hash,
                "line_count": len(code.splitlines()),
                "archive_path": str(archive_path),
                "returned_to_model": result_text,
            },
        )
        return result_text

    @baseline_agent.tool
    def run_test_file(ctx: RunContext[BaselineDeps], filename: str) -> str:
        """Run a generated pytest-playwright test and write an execution report."""
        validate_python_test_filename(filename)
        ctx.deps.tool_calls.append(
            {
                "tool": "run_test_file",
                "filename": filename,
                "attempt_number": ctx.deps.test_attempts + 1,
            }
        )
        if repair_budget_exhausted(ctx.deps.max_retries, ctx.deps.test_attempts):
            result_text = (
                "Repair budget exhausted before another execution. "
                + render_repair_budget(ctx.deps.max_retries, ctx.deps.test_attempts)
            )
            _append_tool_transcript(
                ctx.deps,
                {
                    "tool": "run_test_file",
                    "filename": filename,
                    "attempt_number": ctx.deps.test_attempts + 1,
                    "rejected": True,
                    "returned_to_model": result_text,
                },
            )
            return result_text

        ctx.deps.test_attempts += 1
        test_path = ctx.deps.generated_tests_dir / filename
        syntax_error = _syntax_check(test_path)
        if syntax_error:
            result = ExecutionResult(
                filename=filename,
                exit_code=2,
                stderr=f"Syntax check failed:\n{syntax_error}",
            )
        else:
            if ctx.deps.capture_failure_state:
                _write_failure_state_conftest(ctx.deps.generated_tests_dir)
            failure_state_path = ctx.deps.output_dir / f"{Path(filename).stem}.failure-state.json"
            if failure_state_path.exists():
                failure_state_path.unlink()
            result = run_generated_test(
                filename=filename,
                generated_tests_dir=ctx.deps.generated_tests_dir,
                base_url=ctx.deps.evaluation.base_url,
                network_results_dir=ctx.deps.output_dir,
                runtime_results_dir=ctx.deps.runtime_results_dir,
            )
            if (
                ctx.deps.capture_failure_state
                and result.failed
                and failure_state_path.exists()
            ):
                result.artifacts.append(
                    ExecutionArtifact(kind="failure-state", path=failure_state_path)
                )
        if result.failed:
            ctx.deps.failed_test_attempts += 1

        report = build_execution_report(
            result,
            journey_guide=None,
            generated_tests_dir=ctx.deps.generated_tests_dir,
            test_results_dir=ctx.deps.output_dir,
            evaluation=ctx.deps.evaluation,
            msa_spec_path=str(ctx.deps.msa_spec_path),
            max_retries=ctx.deps.max_retries,
            test_attempts=ctx.deps.test_attempts,
            failed_test_attempts=ctx.deps.failed_test_attempts,
        )
        report.requested_journey = ctx.deps.requested_journey
        report.use_case = ctx.deps.use_case
        write_execution_report(report, output_dir=ctx.deps.output_dir)
        result_text = (
            render_execution_report(report)
            + "\n- baseline.repair_budget: "
            + render_repair_budget(ctx.deps.max_retries, ctx.deps.test_attempts)
        )
        _append_tool_transcript(
            ctx.deps,
            {
                "tool": "run_test_file",
                "filename": filename,
                "attempt_number": ctx.deps.test_attempts,
                "status": report.status,
                "exit_code": report.exit_code,
                "failed": result.failed,
                "failed_attempts_so_far": ctx.deps.failed_test_attempts,
                "returned_to_model": result_text,
            },
        )
        return result_text

    return baseline_agent


def _load_index(path: Path) -> list[dict[str, str]]:
    data = _load_yaml(path)
    items = data.get("use_cases", [])
    if not isinstance(items, list):
        raise ValueError(f"Expected use_cases list in {path}")
    return [item for item in items if isinstance(item, dict)]


def _resolve_use_case_path(index_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    candidates = [path]
    if not path.is_absolute():
        candidates = [index_path.parent / path, REPO_ROOT / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def _load_use_cases(args: argparse.Namespace) -> list[StructuredUseCase]:
    index_path = Path(args.use_case_index).resolve()
    if args.use_case_id:
        if index_path == STRUCTURED_USE_CASE_INDEX_PATH:
            return [load_structured_use_case_by_id(args.use_case_id, index_path=index_path)]
        for item in _load_index(index_path):
            if str(item.get("id", "")).strip() == args.use_case_id:
                return [
                    load_structured_use_case(
                        _resolve_use_case_path(index_path, str(item.get("path", "")))
                    )
                ]
        raise ValueError(f"Unknown use case ID in {index_path}: {args.use_case_id}")
    if args.use_case_file:
        return [load_structured_use_case(Path(args.use_case_file))]

    use_cases: list[StructuredUseCase] = []
    for item in _load_index(index_path):
        raw_path = str(item.get("path", "")).strip()
        if not raw_path:
            continue
        use_cases.append(load_structured_use_case(_resolve_use_case_path(index_path, raw_path)))
    if not use_cases:
        raise ValueError(f"No use cases loaded from {index_path}")
    return use_cases


def _collect_jsonl_records(root: Path, glob_pattern: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for jsonl_path in root.glob(glob_pattern):
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError:
                pass
    return records


def _write_aggregate_summary(aggregate_dir: Path, source_root: Path, glob_pattern: str) -> None:
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    records = _collect_jsonl_records(source_root, glob_pattern)
    if not records:
        return
    history_path = aggregate_dir / EVALUATION_HISTORY_FILENAME
    with history_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write("\n")
    write_evaluation_summary(history_dir=aggregate_dir)


def _write_audit(
    *,
    path: Path,
    deps: BaselineDeps,
    model: str,
    prompt: str,
    result_output: str,
    run_exception: BaseException | None,
) -> None:
    allowed_tools = {"create_python_test_file", "run_test_file"}
    forbidden = [
        call for call in deps.tool_calls if str(call.get("tool", "")) not in allowed_tools
    ]
    payload = {
        "treatment": "direct_generation_baseline",
        "model": model,
        "mcp_servers_exposed": False,
        "registered_model_tools": sorted(allowed_tools),
        "tool_transcript_path": str(path.parent / "tool-transcript.jsonl"),
        "static_artifacts": {
            "structured_use_case": True,
            "full_msa_yaml": True,
            "relevant_msa_slice": False,
            "extracted_msa_summary": False,
            "system_description": True,
        },
        "diagnostics": {
            "shared_repo_network_capture": True,
            "baseline_failure_state_capture": deps.capture_failure_state,
        },
        "forbidden_tool_calls": forbidden,
        "allowed_tool_calls": deps.tool_calls,
        "generated_attempts": deps.generation_attempts,
        "test_attempts": deps.test_attempts,
        "failed_test_attempts": deps.failed_test_attempts,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "result_output_preview": result_output[:2000],
        "exception": (
            {
                "type": type(run_exception).__name__,
                "message": str(run_exception),
            }
            if run_exception is not None
            else None
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def _run_one(
    *,
    baseline_agent: Agent,
    model: str,
    use_case: StructuredUseCase,
    run_dir: Path,
    run_num: int,
    args: argparse.Namespace,
) -> str:
    journey = use_case.journey_text()
    filename = derive_use_case_test_filename(use_case)
    output_dir = run_dir / "test-results"
    history_dir = output_dir
    generated_tests_dir = run_dir / "generated-tests"
    runtime_results_dir = run_dir / "runtime-results"
    prompt_capture_dir = run_dir / "prompt-captures"
    msa_spec_path = Path(args.msa_spec).resolve()
    system_description_path = Path(args.system_description).resolve()

    use_case_meta = UseCaseMetadata(
        id=use_case.id,
        name=use_case.name,
        role=use_case.role,
        reference_bucket=use_case.smith_equivalent,
        source_path=str(use_case.source_path) if use_case.source_path else "",
    )
    evaluation = EvaluationContext(
        variant_label=f"baseline-run-{run_num:02d}",
        base_url=args.base_url,
        run_kind="direct_baseline",
    )
    deps = BaselineDeps(
        evaluation=evaluation,
        max_retries=max(args.max_retries, 0),
        output_dir=output_dir,
        history_dir=history_dir,
        generated_tests_dir=generated_tests_dir,
        runtime_results_dir=runtime_results_dir,
        msa_spec_path=msa_spec_path,
        requested_journey=journey,
        capture_failure_state=bool(args.capture_failure_state),
        use_case=use_case_meta,
    )
    msa_spec = load_msa_spec(msa_spec_path)
    system_description = load_system_description(system_description_path)
    prompt = _build_baseline_prompt(
        use_case=use_case,
        journey=journey,
        filename=filename,
        max_retries=deps.max_retries,
        msa_spec=msa_spec,
        system_description=system_description,
        base_url=evaluation.base_url,
    )

    run_started_at = datetime.now(timezone.utc).timestamp()
    prompt_capture_run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    capture_messages: Sequence[object] = ()
    result_output = ""
    run_exception: BaseException | None = None
    try:
        async with baseline_agent:
            result = await baseline_agent.run(
                prompt,
                deps=deps,
                usage_limits=AGENT_USAGE_LIMITS,
            )
            capture_messages = result.all_messages()
            result_output = str(result.output)
            return result_output
    except BaseException as exc:
        run_exception = exc
        raise
    finally:
        write_prompt_capture_entries(
            output_dir=prompt_capture_dir,
            filename=filename,
            requested_journey=journey,
            system_prompt=BASELINE_SYSTEM_PROMPT,
            browse_prompt="",
            test_generation_prompt=prompt,
            all_messages=capture_messages,
            run_id=prompt_capture_run_id,
        )
        final_report = load_execution_report(filename, output_dir=output_dir)
        if (
            final_report is None
            or final_report.report_path is None
            or not final_report.report_path.exists()
            or final_report.report_path.stat().st_mtime < run_started_at
        ):
            if run_exception is None:
                details = (
                    "The baseline model finished without producing a fresh execution report. "
                    "It may have failed to call run_test_file."
                )
            else:
                details = f"{type(run_exception).__name__}: {run_exception}"
            final_report = ExecutionReport(
                filename=filename,
                status="error",
                exit_code=1,
                summary=f"Baseline run for '{filename}' did not complete.",
                details=details,
                requested_journey=journey,
                use_case=use_case_meta,
                evaluation=evaluation,
            )
            write_execution_report(final_report, output_dir=output_dir)
        else:
            final_report.requested_journey = journey
            final_report.use_case = use_case_meta
            final_report.evaluation = evaluation
            write_execution_report(final_report, output_dir=output_dir)

        append_evaluation_history(final_report, history_dir=history_dir)
        aggregate_dir = run_dir.parent
        append_evaluation_history(final_report, history_dir=aggregate_dir)
        _write_audit(
            path=run_dir / "baseline-audit.json",
            deps=deps,
            model=model,
            prompt=prompt,
            result_output=result_output,
            run_exception=run_exception,
        )


async def _run_experiment(args: argparse.Namespace) -> None:
    model = args.model
    os.environ["OPENAI_MODEL"] = model
    baseline_agent = _make_agent(model)

    output_root = Path(args.output_dir).resolve()
    model_dir = output_root / _model_slug(model)
    use_cases = _load_use_cases(args)
    started_at = datetime.now(timezone.utc).isoformat()

    _safe_print(
        f"Direct baseline starting: {len(use_cases)} use case(s) x {args.runs} run(s)\n"
        f"Model: {model}\n"
        f"Output root: {output_root}\n"
        "MCP/browser exploration tools exposed: no"
    )

    for uc_index, use_case in enumerate(use_cases, start=1):
        uc_dir = model_dir / use_case.id
        _safe_print(f"\n[{uc_index}/{len(use_cases)}] {use_case.id} - {use_case.name}")
        for run_num in range(args.start_run, args.start_run + args.runs):
            run_dir = uc_dir / f"run-{run_num:02d}"
            if run_dir.exists() and any(run_dir.iterdir()):
                raise ValueError(
                    f"Refusing to append to existing run directory: {run_dir}. "
                    "Use a fresh --output-dir or a later --start-run."
                )
            _safe_print(f"  Run {run_num} -> {run_dir.relative_to(output_root)}")
            try:
                output = await _run_one(
                    baseline_agent=baseline_agent,
                    model=model,
                    use_case=use_case,
                    run_dir=run_dir,
                    run_num=run_num,
                    args=args,
                )
                _safe_print(f"  Done: {output[:120].replace(chr(10), ' ')}")
            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception as exc:
                _safe_print(f"  Error in run {run_num}: {exc}")

    _safe_print(f"\nWriting model-level summary -> {model_dir}")
    _write_aggregate_summary(model_dir, model_dir, f"*/{EVALUATION_HISTORY_FILENAME}")
    _safe_print(f"Writing root-level summary -> {output_root}")
    _write_aggregate_summary(output_root, output_root, f"*/*/{EVALUATION_HISTORY_FILENAME}")

    manifest = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "treatment": "direct_generation_baseline",
        "model": model,
        "model_slug": _model_slug(model),
        "runs_per_use_case": args.runs,
        "start_run": args.start_run,
        "max_retries_per_run": args.max_retries,
        "use_cases": [use_case.id for use_case in use_cases],
        "output_root": str(output_root),
        "mcp_servers_exposed": False,
        "registered_model_tools": ["create_python_test_file", "run_test_file"],
        "shared_repo_network_capture": True,
        "baseline_failure_state_capture": bool(args.capture_failure_state),
    }
    manifest_path = model_dir / "experiment-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _safe_print(f"Experiment complete. Manifest: {manifest_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run isolated direct-generation baseline experiments."
    )
    parser.add_argument("--output-dir", required=True, help="Experiment output directory.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model identifier for pydantic-ai (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Independent runs per use case (default: 10).",
    )
    parser.add_argument(
        "--start-run",
        type=int,
        default=1,
        help="Starting run number when appending runs (default: 1).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Repair attempts after the initial execution (default: 5).",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Application base URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--msa-spec",
        default=str(MSA_SPEC_PATH),
        help=f"Frozen MSA specification path (default: {MSA_SPEC_PATH}).",
    )
    parser.add_argument(
        "--system-description",
        default=str(SYSTEM_DESCRIPTION_PATH),
        help=f"System description path (default: {SYSTEM_DESCRIPTION_PATH}).",
    )
    parser.add_argument(
        "--use-case-index",
        default=str(DEFAULT_INDEX_PATH),
        help=f"Use-case index path (default: {DEFAULT_INDEX_PATH}).",
    )
    parser.add_argument("--use-case-id", help="Run one use case from the index.")
    parser.add_argument("--use-case-file", help="Run one structured use case YAML file.")
    parser.add_argument(
        "--capture-failure-state",
        action="store_true",
        help=(
            "Write a run-local generated-tests/conftest.py that captures visible page "
            "text and API responses after failed baseline tests. Disabled by default "
            "for final comparison runs so the pytest environment matches the main run."
        ),
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    if args.start_run < 1:
        parser.error("--start-run must be >= 1")
    if args.max_retries < 0:
        parser.error("--max-retries must be >= 0")
    if args.use_case_id and args.use_case_file:
        parser.error("Provide only one of --use-case-id or --use-case-file")
    return args


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(_run_experiment(args))
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
