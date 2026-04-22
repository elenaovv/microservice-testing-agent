# UC-VIS-004 Booking Finding

This note records the issue observed while running:

```bash
uv run python main.py test --use-case-id UC-VIS-004 --base-url http://localhost:8080
```

## Observation

After the default `spec/msa.yaml` path was passed into the prompt, the agent was
able to read the MSA specification, use the correct client login entry point,
authenticate as `ROLE_USER`, search for tickets, select a trip and passenger,
submit the booking modal, and observe:

```text
POST /api/v1/preserveservice/preserve -> 200
```

The created order appeared in the Order List with status `Not Paid`.

## Failure Cause

The browse phase still marked the journey as failed because the use-case goal
contained the phrase:

```text
with no assurance, no food and no consign
```

Although the UI was used without explicitly selecting food, the preserve request
payload still included default food fields:

```text
foodType=1
foodName='Bone Soup'
foodPrice=2.5
```

This made the agent treat the run as not satisfying the exact use-case wording,
even though the core booking and order-creation behavior succeeded.

## Decision

For the research subset, `UC-VIS-004` should focus on the booking outcome rather
than optional food/assurance/consign payload details. The success criteria should
remain:

- a new order appears in Order List for the selected trip and route
- the order status is `Not Paid`

The optional-service payload behavior may be recorded separately as a system
observation, but it should not block the booking use case unless the research
question explicitly targets optional service selection.
