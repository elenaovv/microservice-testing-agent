# Contracts

Shared data structures and contract construction for the runtime.

- `models.py` re-exports the public dataclasses so existing imports stay stable.
- `basic_models.py` contains simple action, timing, and API-call records.
- `locator_models.py` contains locator candidates and selector normalization helpers.
- `interaction_models.py` contains web/API interaction-surface contracts.
- `journey_models.py` contains journey contracts, success observations, and browse capture state.
- `execution_models.py` contains generated-test and pytest execution result records.
- `evaluation_models.py` contains run metrics, failure diagnosis, and evaluation context records.
- `report_models.py` contains coverage snapshots, journey guides, and execution reports.
- `deps.py` contains the agent dependency state object.
- `journey_contract.py` builds the structured journey contract from captured actions, interaction contracts, API calls, and success observations.

Keep this package free of subprocess execution, file rendering, and heuristic evaluation logic. It should describe runtime data, not perform a run.
