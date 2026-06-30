import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src/ to path so moved packages are found automatically
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.contracts.models import UseCaseMetadata
from prompts.generator import (
    STRUCTURED_USE_CASE_INDEX_PATH,
    SYSTEM_DESCRIPTION_PATH,
    MSA_SPEC_PATH,
    USE_CASES_PATH,
    StructuredUseCase,
    derive_python_test_filename,
    derive_use_case_test_filename,
    load_structured_use_case,
    load_structured_use_case_by_id,
    load_use_case_index,
    load_use_cases,
    resolve_indexed_use_case_path,
)

# workflow is imported lazily inside each command handler so that --model can
# set OPENAI_MODEL before agent.py reads it at module level.
_workflow_cache: tuple | None = None


def _import_workflow():
    global _workflow_cache
    if _workflow_cache is None:
        from workflow import generate_test, retest_generated_test, run_browser_task
        _workflow_cache = (generate_test, retest_generated_test, run_browser_task)
    return _workflow_cache


def safe_print(output: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe_output = output.encode(encoding, errors="replace").decode(encoding)
    print(safe_output)


def add_evaluation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--variant-label",
        default="original",
        help="Variant label recorded in evaluation artifacts (default: original)",
    )
    parser.add_argument(
        "--mutation-id",
        default="",
        help="Optional mutation or branch identifier for Phase 3 tracking",
    )
    parser.add_argument(
        "--fault-service",
        default="",
        help="Optional microservice name that contains the injected fault",
    )
    parser.add_argument(
        "--base-url",
        help="App base URL for browsing and test execution (defaults to BASE_URL env or http://localhost:8080)",
    )
    parser.add_argument(
        "--msa-spec",
        help=f"MSA specification YAML path (default: {MSA_SPEC_PATH})",
    )
    parser.add_argument(
        "--prompt-capture-dir",
        default="prompt-captures",
        help="Directory to store prompt capture files (default: prompt-captures)",
    )


def add_input_spec_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--system-description",
        help=f"System description path (default: {SYSTEM_DESCRIPTION_PATH})",
    )
    parser.add_argument(
        "--use-cases-file",
        help=f"Legacy text use-case file path (default: {USE_CASES_PATH})",
    )
    parser.add_argument(
        "--use-case-index",
        help=f"Structured use-case index path (default: {STRUCTURED_USE_CASE_INDEX_PATH})",
    )


def _read_use_case_at_line(line_number: int, path: Path = USE_CASES_PATH) -> str:
    if line_number < 1:
        raise ValueError("--line must be >= 1")
    if not path.exists():
        raise FileNotFoundError(f"Use case file not found: {path}")

    raw_lines = path.read_text(encoding="utf-8").splitlines()
    if line_number > len(raw_lines):
        raise ValueError(
            f"Line {line_number} is out of range for {path} (total lines: {len(raw_lines)})"
        )

    selected = raw_lines[line_number - 1].strip()
    if not selected:
        raise ValueError(f"Line {line_number} is blank in {path}")
    if selected.startswith("#"):
        raise ValueError(f"Line {line_number} is a comment in {path}")
    return selected


async def _generate_single_test(
    journey: str,
    filename: str | None,
    args: argparse.Namespace,
    use_case_context: str = "",
    use_case: UseCaseMetadata | None = None,
) -> str:
    generate_test, _, _ = _import_workflow()
    return await generate_test(
        filename,
        journey,
        args.max_retries,
        variant_label=args.variant_label,
        mutation_id=args.mutation_id,
        fault_service=args.fault_service,
        base_url=args.base_url,
        use_case_context=use_case_context,
        use_case=use_case,
        msa_spec_path=args.msa_spec,
        system_description_path=args.system_description,
        prompt_capture_path=args.prompt_capture_dir,
    )


async def _generate_all_use_case_tests(args: argparse.Namespace) -> str:
    use_cases_path = Path(args.use_cases_file) if args.use_cases_file else USE_CASES_PATH
    use_cases = load_use_cases(use_cases_path)
    if not use_cases:
        raise ValueError(f"No runnable use cases found in {use_cases_path}")

    outputs: list[str] = []
    total = len(use_cases)
    for index, journey in enumerate(use_cases, start=1):
        filename = derive_python_test_filename(journey)
        result = await _generate_single_test(journey, filename, args)
        outputs.append(
            "\n".join(
                [
                    f"[{index}/{total}] {filename}",
                    f"Journey: {journey}",
                    result,
                ]
            )
        )
    return "\n\n".join(outputs)


def _load_selected_structured_use_case(args: argparse.Namespace) -> StructuredUseCase:
    index_path = Path(args.use_case_index) if args.use_case_index else STRUCTURED_USE_CASE_INDEX_PATH
    if args.use_case_id:
        return load_structured_use_case_by_id(args.use_case_id, index_path=index_path)
    if args.use_case_file:
        return load_structured_use_case(Path(args.use_case_file))
    raise ValueError("No structured use case selector provided")


# ---------------------------------------------------------------------------
# experiment command
# ---------------------------------------------------------------------------

def _model_slug(model: str) -> str:
    """Convert a model identifier to a filesystem-safe directory name."""
    slug = re.sub(r"[:/\\]", "-", model).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug or "default-model"


def _is_default_structured_index(index_path: Path) -> bool:
    return index_path.resolve() == STRUCTURED_USE_CASE_INDEX_PATH.resolve()


def _is_research_case_entry(entry: dict[str, str]) -> bool:
    return "research_cases" in Path(entry.get("path", "")).parts


def _load_experiment_use_cases(args: argparse.Namespace) -> list[StructuredUseCase]:
    index_path = Path(args.use_case_index) if args.use_case_index else STRUCTURED_USE_CASE_INDEX_PATH

    if args.use_case_id:
        return [load_structured_use_case_by_id(args.use_case_id, index_path=index_path)]

    if args.use_case_file:
        return [load_structured_use_case(Path(args.use_case_file))]

    entries = load_use_case_index(index_path)
    if _is_default_structured_index(index_path):
        entries = [entry for entry in entries if _is_research_case_entry(entry)]
    if not entries:
        raise ValueError(f"No use cases found in index: {index_path}")

    use_cases: list[StructuredUseCase] = []
    for entry in entries:
        uc_path = resolve_indexed_use_case_path(index_path, entry["path"])
        if not uc_path.exists():
            print(f"\033[33mWarning: use case file not found, skipping: {uc_path}\033[0m", flush=True)
            continue
        use_cases.append(load_structured_use_case(uc_path))

    if not use_cases:
        raise ValueError("No valid use case files found from index.")
    return use_cases


def _collect_jsonl_records(root: Path, glob_pattern: str) -> list[dict]:
    """Collect evaluation-runs.jsonl records matching glob_pattern under root."""
    records: list[dict] = []
    for jsonl_path in root.glob(glob_pattern):
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                try:
                    records.append(json.loads(stripped))
                except json.JSONDecodeError:
                    pass
    return records


def _write_aggregate_summary(aggregate_dir: Path, source_root: Path, glob_pattern: str) -> None:
    """Merge evaluation-runs.jsonl records matching glob_pattern into aggregate_dir."""
    from core.evaluation.evaluation_utils import (
        EVALUATION_HISTORY_FILENAME,
        write_evaluation_summary,
    )
    aggregate_dir.mkdir(parents=True, exist_ok=True)
    records = _collect_jsonl_records(source_root, glob_pattern)
    if not records:
        return
    history_path = aggregate_dir / EVALUATION_HISTORY_FILENAME
    with history_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")
    write_evaluation_summary(history_dir=aggregate_dir)


async def _run_experiment(args: argparse.Namespace) -> None:
    generate_test, _, _ = _import_workflow()
    from core.evaluation.evaluation_utils import write_evaluation_summary

    output_root = Path(args.output_dir).resolve()
    model_slug = _model_slug(args.model)
    model_dir = output_root / model_slug

    use_cases = _load_experiment_use_cases(args)
    total_uc = len(use_cases)
    total_runs = args.runs

    started_at = datetime.now(timezone.utc).isoformat()
    safe_print(
        f"Experiment starting: {total_uc} use case(s) × {total_runs} run(s) "
        f"with model '{args.model}'\n"
        f"Output root: {output_root}"
    )

    for uc_index, uc in enumerate(use_cases, start=1):
        uc_dir = model_dir / uc.id
        journey = uc.journey_text()
        filename = derive_use_case_test_filename(uc)
        use_case_meta = UseCaseMetadata(
            id=uc.id,
            name=uc.name,
            role=uc.role,
            reference_bucket=uc.smith_equivalent,
            source_path=str(uc.source_path) if uc.source_path else "",
        )

        safe_print(f"\n[{uc_index}/{total_uc}] Use case: {uc.id} - {uc.name}")

        start_run = getattr(args, "start_run", 1)
        for run_num in range(start_run, start_run + total_runs):
            run_dir = uc_dir / f"run-{run_num:02d}"
            run_test_results = run_dir / "test-results"
            run_generated_tests = run_dir / "generated-tests"
            run_runtime_results = run_dir / "runtime-results"
            run_prompt_captures = str(run_dir / "prompt-captures")

            safe_print(f"  Run {run_num}/{total_runs} → {run_dir.relative_to(output_root)}")

            try:
                result = await generate_test(
                    filename,
                    journey,
                    args.max_retries,
                    variant_label=f"run-{run_num:02d}",
                    base_url=args.base_url,
                    use_case_context=uc.prompt_context(),
                    use_case=use_case_meta,
                    msa_spec_path=args.msa_spec,
                    prompt_capture_path=run_prompt_captures,
                    output_dir=run_test_results,
                    history_dir=run_test_results,
                    generated_tests_dir=run_generated_tests,
                    runtime_results_dir=run_runtime_results,
                    aggregate_history_dir=uc_dir,
                )
                safe_print(f"  Done: {result[:120].replace(chr(10), ' ')}")
            except (KeyboardInterrupt, asyncio.CancelledError):
                safe_print("Experiment interrupted.")
                raise
            except Exception as exc:
                safe_print(f"  \033[31mError in run {run_num}: {exc}\033[0m")

    # Model-level aggregate summary: collect from <uc-dir>/evaluation-runs.jsonl only
    from core.evaluation.evaluation_utils import EVALUATION_HISTORY_FILENAME
    safe_print(f"\nWriting model-level summary → {model_dir}")
    _write_aggregate_summary(model_dir, model_dir, f"*/{EVALUATION_HISTORY_FILENAME}")

    # Root-level aggregate summary: collect from <model-dir>/<uc-dir>/evaluation-runs.jsonl only
    safe_print(f"Writing overall summary → {output_root}")
    _write_aggregate_summary(output_root, output_root, f"*/*/{EVALUATION_HISTORY_FILENAME}")

    finished_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "started_at": started_at,
        "finished_at": finished_at,
        "model": args.model,
        "model_slug": model_slug,
        "runs_per_use_case": total_runs,
        "max_retries_per_run": args.max_retries,
        "use_cases": [uc.id for uc in use_cases],
        "output_root": str(output_root),
    }
    manifest_path = model_dir / "experiment-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    safe_print(f"\nExperiment complete. Manifest: {manifest_path}")


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI browsing agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a task in the browser")
    run_parser.add_argument("task", help="What to do")
    run_parser.add_argument("--url", default="about:blank", help="Starting URL")

    test_parser = subparsers.add_parser("test", help="Generate and validate a pytest-playwright test")
    test_parser.add_argument(
        "journey",
        nargs="?",
        help="Ad-hoc user journey to test (if omitted, use cases are loaded from spec/use-cases.txt)",
    )
    test_parser.add_argument(
        "--line",
        type=int,
        help="Run only one line number from spec/use-cases.txt (1-indexed)",
    )
    test_parser.add_argument(
        "--use-case-id",
        help=(
            "Run one structured use case by ID from "
            "the selected structured use-case index"
        ),
    )
    test_parser.add_argument(
        "--use-case-file",
        help="Run one structured use case YAML file by path",
    )
    test_parser.add_argument(
        "--filename",
        help=(
            "Output filename for journey, --line, or structured use case mode "
            "(ignored when running all text use cases)"
        ),
    )
    test_parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help=(
            "Max generated-test repair attempts after the initial failed execution "
            "(default: 5, allowing 6 total test executions). Does not control "
            "browser/MCP tool retries or internal agent retries."
        ),
    )
    add_evaluation_args(test_parser)
    add_input_spec_args(test_parser)

    retest_parser = subparsers.add_parser(
        "retest",
        help="Rerun an existing generated test for evaluation or mutation comparison",
    )
    retest_parser.add_argument("filename", help="Generated test filename to rerun")
    add_evaluation_args(retest_parser)

    experiment_parser = subparsers.add_parser(
        "experiment",
        help="Run N independent test-generation attempts per use case and store all artifacts in a structured output directory",
    )
    experiment_parser.add_argument(
        "--output-dir",
        required=True,
        metavar="DIR",
        help=(
            "Root directory for all experiment artifacts. "
            "Structure: DIR/<model>/<use-case-id>/run-NN/{test-results,generated-tests,...}"
        ),
    )
    experiment_parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", "openai:gpt-5.4"),
        metavar="MODEL",
        help=(
            "Model identifier passed to pydantic-ai (e.g. openai:gpt-5.4, openai:gpt-5.4-mini). "
            "Overrides the OPENAI_MODEL environment variable. "
            f"(default: {os.environ.get('OPENAI_MODEL', 'openai:gpt-5.4')})"
        ),
    )
    experiment_parser.add_argument(
        "--runs",
        type=int,
        default=10,
        metavar="N",
        help="Number of independent runs per use case (default: 10)",
    )
    experiment_parser.add_argument(
        "--start-run",
        type=int,
        default=1,
        metavar="N",
        help="Starting run number (default: 1). Use to append runs without overwriting existing ones.",
    )
    experiment_parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help=(
            "Max test-repair attempts per run after the initial failed execution "
            "(default: 5)"
        ),
    )
    experiment_parser.add_argument(
        "--base-url",
        help="App base URL (defaults to BASE_URL env var or http://localhost:8080)",
    )
    experiment_parser.add_argument(
        "--msa-spec",
        help=f"MSA specification YAML path (default: {MSA_SPEC_PATH})",
    )
    experiment_parser.add_argument(
        "--use-case-id",
        help="Run only this one use case ID (default: all use cases from the index)",
    )
    experiment_parser.add_argument(
        "--use-case-file",
        help="Run only this one use case YAML file (default: all use cases from the index)",
    )
    experiment_parser.add_argument(
        "--use-case-index",
        help=f"Structured use-case index path (default: {STRUCTURED_USE_CASE_INDEX_PATH})",
    )

    args = parser.parse_args()

    if args.command == "test":
        selectors = [
            args.journey is not None,
            args.line is not None,
            bool(args.use_case_id),
            bool(args.use_case_file),
        ]
        if sum(selectors) > 1:
            parser.error(
                "test: provide only one of JOURNEY, --line, --use-case-id, or --use-case-file"
            )
        if args.line is not None and args.line < 1:
            parser.error("test: --line must be >= 1")

    if args.command == "experiment":
        if args.runs < 1:
            parser.error("experiment: --runs must be >= 1")
        if args.max_retries < 0:
            parser.error("experiment: --max-retries must be >= 0")

    return args


if __name__ == "__main__":
    args = parse_args()

    # Set the model env var before any lazy import so agent.py picks it up at module load.
    if args.command == "experiment":
        os.environ["OPENAI_MODEL"] = args.model

    if args.command == "run":
        _, _, run_browser_task = _import_workflow()
        safe_print(asyncio.run(run_browser_task(args.url, args.task)))
    elif args.command == "test":
        try:
            if args.journey is not None:
                output = asyncio.run(
                    _generate_single_test(args.journey, args.filename, args)
                )
            elif args.line is not None:
                use_cases_path = (
                    Path(args.use_cases_file) if args.use_cases_file else USE_CASES_PATH
                )
                journey = _read_use_case_at_line(args.line, path=use_cases_path)
                filename = args.filename or derive_python_test_filename(journey)
                output = asyncio.run(
                    _generate_single_test(journey, filename, args)
                )
            elif args.use_case_id or args.use_case_file:
                use_case = _load_selected_structured_use_case(args)
                journey = use_case.journey_text()
                filename = args.filename or derive_use_case_test_filename(use_case)
                output = asyncio.run(
                    _generate_single_test(
                        journey,
                        filename,
                        args,
                        use_case_context=use_case.prompt_context(),
                        use_case=UseCaseMetadata(
                            id=use_case.id,
                            name=use_case.name,
                            role=use_case.role,
                            reference_bucket=use_case.smith_equivalent,
                            source_path=str(use_case.source_path) if use_case.source_path else "",
                        ),
                    )
                )
            else:
                output = asyncio.run(_generate_all_use_case_tests(args))
            safe_print(output)
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc))
    elif args.command == "retest":
        _, retest_generated_test, _ = _import_workflow()
        safe_print(
            asyncio.run(
                retest_generated_test(
                    args.filename,
                    variant_label=args.variant_label,
                    mutation_id=args.mutation_id,
                    fault_service=args.fault_service,
                    base_url=args.base_url,
                    msa_spec_path=args.msa_spec,
                )
            )
        )
    elif args.command == "experiment":
        try:
            asyncio.run(_run_experiment(args))
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc))
