# Coverage

Mapping between observed browser-visible API calls and the MSA specification.

- `coverage_utils.py` extracts endpoints from `spec/msa.yaml`, matches observed requests to service operations, counts covered operations, and lists unmapped calls.

This package handles specification-to-trace matching only. Journey-contract construction belongs in `contracts`, and backend distributed tracing is not implemented here.
