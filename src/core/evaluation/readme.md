# Evaluation

Run-level evaluation history and summary generation.

- `evaluation_utils.py` appends evaluation records, computes run metrics, classifies result status, and regenerates summary tables.
- `evaluation_rendering.py` renders evaluation summaries and mutation comparison tables.
- `failure_diagnosis.py` extracts failing locators, ranks repair candidates, and explains missing side-effect failures.

Use this package for research metrics across runs. Per-run report construction belongs in `reporting`, and low-level heuristics belong in `analysis`.
