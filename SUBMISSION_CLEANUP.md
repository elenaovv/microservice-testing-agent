# Submission Cleanup

Use this checklist before creating the artifact or camera-ready repository
snapshot. It separates source files from local run outputs and paper scratch
material.

## Commit These Files

- Runtime source: `main.py`, `agent/`, `workflow/`, `prompts/`, `core/`, and
  `direct_baseline/`.
- Experiment inputs: `spec/`, including `msa.yaml`, `system_description.md`,
  use cases, and fault catalog.
- Analysis utilities: `research/` and `tests/`.
- Curated documentation: `README.md`, `docs/`, and the review-response notes
  if they are useful for camera-ready editing.
- Dependency files: `pyproject.toml`, `uv.lock`, `.python-version`, and
  `.env.example`.

## Do Not Commit Local Outputs

- Secrets and local configuration: `.env`.
- Python and browser caches: `.venv/`, `__pycache__/`, `.pytest_cache/`,
  `.playwright-mcp/`, `.tmp/`, and `tmp/`.
- Generated runtime outputs: `generated-tests/`, `test-results/`,
  `runtime-results/`, and `prompt-captures/`.
- Root-level manual debug captures such as `*-network.json`,
  `*_network.json`, and `add_user_*_snapshot.*`.
- Local manuscript scratch folders such as `.OLD_PDF/`.

## Evidence Package

Generated tests, journey JSON, network traces, and repair-attempt archives
support reproducibility. Package them deliberately under a named evidence
directory or external archive. Do not mix them with the clean source tree unless
the artifact README explains their role.

Recommended evidence shape:

```text
results/
  study-2026/
    openai-gpt-5.4/
      <use-case-id>/
        run-XX/
          generated-tests/
          test-results/
          runtime-results/
          prompt-captures/
```

## Cleanup Commands

Preview ignored local files before removing anything:

```powershell
git clean -ndX
```

Only run destructive cleanup after copying any evidence you still need:

```powershell
git clean -fdX
```

Do not use `git clean -fd` for submission cleanup unless you have reviewed every
untracked path. That command would also remove untracked paper drafts, review
notes, PDFs, and sample evidence folders.
