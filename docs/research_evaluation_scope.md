# Research Evaluation Scope

This document records how the runtime uses `spec/msa.yaml` and which structured
use cases form the first repeated-run evaluation subset.

## MSA Specification Usage

`spec/msa.yaml` is used in three places.

| Stage | Usage |
| --- | --- |
| Prompt construction | The prompt builder creates a focused slice of relevant services, endpoints, credentials, and entry points. |
| Browse phase | The `read_spec_file(...)` tool can retrieve full spec details when the focused slice is not enough. |
| Reporting | Observed browser requests are matched against the YAML by HTTP method and path. |

The full YAML is available to the runtime, but it is not inserted wholesale into
every prompt. This keeps prompt context smaller and avoids mixing unrelated
services into a specific use case.

## Endpoint And Service Counts

Current parser counts from `spec/msa.yaml`:

| Measure | Count |
| --- | ---: |
| Unique endpoint operations | 231 |
| Services with endpoint definitions | 43 |
| GET operations | 97 |
| POST operations | 81 |
| PUT operations | 26 |
| DELETE operations | 26 |
| PATCH operations | 1 |

The YAML also contains `microservice_count: 47` as architecture metadata from
the TrainTicket system description. That value is not computed from the endpoint
map. The parser reports 43 because only services with endpoint definitions under
`msa.services` are counted.

## Study Use Cases

The repeated-run study uses the files under `research_cases/`, not every use
case in `spec/use_cases/index.yaml`.

### User Cases

| Use case | Purpose |
| --- | --- |
| `UC-VIS-001` Login | Authentication baseline. |
| `UC-VIS-002` Search for Tickets | Read-only search flow. |
| `UC-VIS-004` Book a Ticket | State-changing order creation. |
| `UC-VIS-006` Pay for an Order | Payment flow. |
| `UC-VIS-009` Collect a Ticket | State transition after payment. |
| `UC-VIS-010` Enter Station | Entry validation workflow. |

### Admin Cases

| Use case | Purpose |
| --- | --- |
| `UC-ADM-037` Admin Login | Admin authentication baseline. |
| `UC-ADM-001` Add User | Admin create operation. |
| `UC-ADM-007` Update Train | Admin update operation. |
| `UC-ADM-013` Add Station | Admin create operation. |
| `UC-ADM-014` Delete Station | Admin delete operation. |
| `UC-ADM-027` Update System Configuration | Configuration update operation. |

## Recorded Metrics

For each selected use case, the current study records:

- generated-test count;
- browse failures;
- pass/fail status after repair;
- other runtime or logging failures;
- generated-test size;
- repair attempts;
- browser-visible API calls;
- browse duration;
- failure category when available.

The subset covers authentication, read-only workflows, create/update/delete
operations, payment-related workflows, and state transitions. It does not cover
all 54 indexed use cases.
