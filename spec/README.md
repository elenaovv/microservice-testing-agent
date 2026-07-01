# Specification Files

This directory contains the input specification used by MAESTRO. It describes the target microservice system, the use cases to test, and the seeded faults used for fault-detection evaluation.

## Directory Map

- `msa.yaml`: microservice architecture and endpoint specification.
- `system_description.md`: short functional description of the system under test.
- `use_cases/`: structured user and admin use cases.
- `faults/`: fault catalog for mutation and fault-detection experiments.
- `use-cases.txt`: legacy free-text use-case list.

## `msa.yaml`

`msa.yaml` gives MAESTRO system context. It records the UI gateway, known test credentials, microservice names, endpoint paths, HTTP methods, and service-operation mappings.

The agent does not dump the full file into every prompt. The prompt builder extracts a relevant excerpt, and the agent can call `read_spec_file(...)` when it needs full details such as credentials, gateway paths, or test data.

Coverage reporting also uses `msa.yaml`. Browser-visible HTTP requests are matched against this file to estimate which services and operations were exercised by a generated test.

## `use_cases/`

`use_cases/index.yaml` is the main index. Each entry has an ID, role, name, Smith benchmark mapping when available, and a path to the YAML file that defines the use case.

Use cases are grouped by role:

- `use_cases/user/`: traveler or visitor workflows.
- `use_cases/admin/`: administrator workflows.

The `research_cases/` folders contain the subset used for the main repeated-run research evaluation. Other YAML files are available for broader testing, but are not part of that core subset by default.

Each structured use case should state the goal, preconditions, actions, and success criteria clearly enough that the agent can browse the UI and later generate assertions from the observed outcome.

Before running an experiment, check the test data in the selected use-case YAML. Dates, source stations, and destination stations must be valid for the live TrainTicket deployment. If the date is in the past, or the route is not available in the current database, the browse journey can fail before a test is generated. The same issue can also make a generated test fail during replay.

Example:

```bash
uv run python main.py test --use-case-id UC-VIS-004 --base-url http://localhost:8080
```

or:

```bash
uv run python main.py test --use-case-file spec/use_cases/user/research_cases/UC-VIS-004-book-ticket.yaml --base-url http://localhost:8080
```

## `faults/`

`faults/catalog.yaml` defines the seeded faults used for fault-detection evaluation. Each fault is tied to a use case and describes the operator, the violated criterion, the oracle assertion, and the HTTP-boundary mutation.

These faults are not used during normal test generation. They are used later when previously generated tests are replayed against mutated behavior to measure whether the tests detect the injected fault.

## Adding Another MSA

To use this project with another microservice application, provide a new specification set with the same roles:

1. Write an `msa.yaml` for the new system gateway, credentials, services, and endpoints.
2. Write a short `system_description.md`.
3. Add structured use cases under `use_cases/` and register them in `use_cases/index.yaml`.
4. Add a `faults/catalog.yaml` only if you will run fault-detection experiments.

Then run MAESTRO with explicit paths:

```bash
uv run python main.py test --use-case-file path/to/use_case.yaml --msa-spec path/to/msa.yaml --system-description path/to/system_description.md --base-url http://localhost:8080
```
