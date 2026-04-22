# Research Evaluation Scope Notes

This note records how the current agent uses the MSA specification and which
use cases are recommended for the first empirical evaluation set.

## How `spec/msa.yaml` Is Used

The MSA specification has two different roles in the current runtime.

During prompt construction, the full YAML file is loaded by the workflow, but it
is not dumped directly into the main prompt. The prompt builder parses the spec
and creates a focused MSA slice by matching the selected journey and structured
use-case text against the service and endpoint descriptions. This keeps the
prompt smaller while still giving the agent domain context.

During browsing, the agent can call `read_spec_file(...)` if it needs details
that were not included in the focused slice, such as known credentials, gateway
entry points, or test data. Keeping the full YAML available is useful because
the agent can retrieve exact specification data when required, but keeping it out
of the default prompt avoids unnecessary context size and reduces distraction.

During reporting, the full YAML is parsed structurally to compute service and
operation coverage. Observed frontend requests are matched against the YAML by
HTTP method and path.

## Endpoint And Service Counts

The current `spec/msa.yaml` contains 231 unique endpoint operations under
`msa.services.*.endpoints`.

The endpoint parser counts:

| Measure | Count |
|---|---:|
| Unique endpoint operations | 231 |
| Services with endpoint definitions | 43 |
| GET operations | 97 |
| POST operations | 81 |
| PUT operations | 26 |
| DELETE operations | 26 |
| PATCH operations | 1 |

The `microservice_count: 47` value in `spec/msa.yaml` is architecture metadata
from the TrainTicket system description. It is not computed from the endpoint
map. The parser reports 43 services because it counts only services that have
endpoint definitions represented under `msa.services`. The difference means
that the architecture-level system has more microservices than the current YAML
endpoint map explicitly models as API-owning services.

## Recommended User Research Subset

Running every user use case is useful eventually, but it is not necessary for
the first stable research evaluation. A smaller subset is easier to repeat and
still covers the main system behavior.

The current user research subset is stored under
`spec/use_cases/user/research_cases/`:

| Use case | Purpose |
|---|---|
| `UC-VIS-001` Login | Authentication baseline |
| `UC-VIS-002` Search for Tickets | Read-only search flow |
| `UC-VIS-004` Book a Ticket | State-changing order creation |
| `UC-VIS-005` View Orders | Order retrieval and verification |
| `UC-VIS-006` Pay for an Order | Payment flow |
| `UC-VIS-007` Cancel an Order | Cancellation and fault-sensitive state change |

This subset covers authentication, search, booking, order reading, payment, and
cancellation. It is sufficient for an initial repeated-run study if each use
case is executed multiple times.

## Recommended Admin Research Subset

The matching admin research subset is stored under
`spec/use_cases/admin/research_cases/`:

| Use case | Purpose |
|---|---|
| `UC-ADM-037` Login | Admin authentication baseline |
| `UC-ADM-004` View All Users | Read-only admin listing |
| `UC-ADM-009` Add Route | Admin create operation |
| `UC-ADM-010` Delete Route | Admin delete operation |
| `UC-ADM-011` Update Route | Admin update operation |
| `UC-ADM-012` View All Routes | Admin route-list verification |

This subset gives an admin-side equivalent to the user subset: login, read-only
listing, create, update, delete, and post-action verification. It avoids running
all admin CRUD categories while still exercising representative management
behavior.

## Practical Evaluation Recommendation

For the first research paper evaluation, use the selected user subset and admin
subset rather than all YAML use cases. A practical design is 10 repeated runs per
selected use case, recording generated tests, pass/fail status, blocked tests,
repair attempts, network API coverage, and fault signatures.

After the selected subset is stable, expand to the remaining use cases for
broader coverage.
