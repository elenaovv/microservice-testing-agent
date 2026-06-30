# Text

Shared text-processing vocabulary for prompt and coverage helpers.

- `vocabulary.py` contains common stopword sets and concept aliases used when deriving filenames, prompt service slices, and coverage token matches.

Keep domain-specific parsing in the caller package. This package should only hold reusable text constants or small text normalization helpers.
