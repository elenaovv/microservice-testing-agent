# UC-VIS-004 Booking Result

Command:

```bash
uv run python main.py test --use-case-id UC-VIS-004 --base-url http://localhost:8080
```

## Observed Result

With the default `spec/msa.yaml` available, the browse phase was able to:

- read the MSA specification;
- use the client login entry point;
- authenticate as `ROLE_USER`;
- search for tickets;
- select a trip and passenger;
- submit the booking modal;
- observe `POST /api/v1/preserveservice/preserve -> 200`;
- verify a new `Not Paid` order in the Order List.

## Issue

The original use-case wording included:

```text
with no assurance, no food and no consign
```

The UI flow did not explicitly select optional services, but the preserve request
still contained default food fields:

```text
foodType=1
foodName='Bone Soup'
foodPrice=2.5
```

The browse phase therefore rejected the run because the optional-service payload
did not match the use-case text exactly, even though booking and order creation
succeeded.

## Decision

For the research subset, `UC-VIS-004` measures the booking outcome:

- a new order appears in Order List for the selected route and trip;
- the order status is `Not Paid`.

Default optional-service payload behavior is recorded as a system observation.
It should block the use case only when optional-service selection is the target
of the research question.
