# Analysis

Heuristic analysis helpers used by reporting and evaluation.

- `inference.py` infers failure kind, syntax validity, blocked status, GUI element counts, and related labels.
- `mutation_utils.py` groups and summarizes mutation/fault-detection records.
- `sequence_extractor.py` extracts and hashes generated-test action sequences for stability analysis.

This package contains interpretation logic. It should not mutate test files, run pytest, or write the main reports.
