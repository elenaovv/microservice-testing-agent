# Fault-injection pre-flight harness

Verifies every (use_case, fault) pair in [spec/faults/catalog.yaml](../../spec/faults/catalog.yaml)
*before* the main study, so we never spend runs measuring detection of a fault
that no oracle could possibly catch.

## Mechanism

For each fault, the runner launches mitmproxy twice and runs the matching
oracle test against each. **Passthrough run**: the proxy is transparent, the
oracle should pass. **Mutant run**: the proxy applies the catalog's
mutations, the oracle should fail. Verdict comes from the pair: pass+fail =
USE; pass+pass = EQUIVALENT-DROP; fail+anything = ORACLE-BROKEN. Per-run logs
and Playwright traces land on disk for later inspection.

## One-time setup

```powershell
.venv\Scripts\Activate.ps1
pip install mitmproxy
```

## Prerequisites for every run

- Train-ticket MSA running on `http://localhost:8080` (the configurable
  default; pass `--base-url` to override).
- Seeded user data: a `fdse_microservice` user with at least one unpaid
  order, one collectable order, and one order in the Enter Station list. The
  pay/collect/enter oracles fail their preconditions if those don't exist.

## Running

Smoke-test on a single fault (fast, ~30 seconds):

```powershell
python research\preflight\run_preflight.py --filter F-VIS-002-01
```

Run the full matrix (~15-20 minutes for 43 faults x 2 phases):

```powershell
python research\preflight\run_preflight.py
```

CLI options:
- `--filter SUBSTR`: only faults whose id contains SUBSTR (e.g. `F-VIS-002`)
- `--base-url URL`: defaults to `http://localhost:8080`
- `--proxy-port N`: defaults to 8888
- `--timeout SECS`: pytest timeout per oracle (default 180)
- `--output-dir DIR`: defaults to `research/preflight/results/preflight_<timestamp>/`

## Outputs

```
research/preflight/results/preflight_<timestamp>/
├── verdict.csv       master table, one row per fault
├── verdict.jsonl     same data in JSONL
├── summary.md        human-readable rollup
└── runs/
    └── F-VIS-002-01/
        ├── passthrough/
        │   ├── pytest.log
        │   ├── mitmdump.log
        │   └── trace/        Playwright trace.zip
        └── mutant/
            ├── pytest.log
            ├── mitmdump.log
            └── trace/
```

## Verdict meanings

| verdict | passthrough | mutant | what to do |
| --- | --- | --- | --- |
| **USE** | passed | failed | fault is detectable; goes into the main study |
| **EQUIVALENT-DROP** | passed | passed | oracle could not detect this fault; drop or rework |
| **ORACLE-BROKEN** | failed | * | oracle is broken on healthy MSA; fix the oracle before any verdict |
| **NO-ORACLE** | n/a | n/a | catalog references a use case with no oracle file |

## Recovery hook

The runner PUTs `DirectTicketAllocationProportion = "0.5"` to
`/api/v1/configservice/configs` before and after the matrix. This protects
against prior runs that may have left a non-numeric value there (which
breaks search and book throughout the rest of the system).

If new fragile state surfaces, extend `recover_known_fragile_state()` in
[run_preflight.py](run_preflight.py).

## Files

- [proxy_addon.py](proxy_addon.py) - mitmproxy addon that loads any catalog fault
- [transformers.py](transformers.py) - named response transformers used by the addon
- [conftest.py](conftest.py) - pytest fixture routing browser through mitmproxy
- [run_preflight.py](run_preflight.py) - the runner described above
- [oracles/](oracles/) - one minimal Playwright test per use case
- [mitmproxy_smoke.py](mitmproxy_smoke.py), [test_smoke.py](test_smoke.py) - the
  initial mechanism-verification scripts; kept for reproducibility, not used
  by the preflight runner

## Iterating on failures

When the verdict CSV shows EQUIVALENT-DROP rows, the fix is almost always
that the catalog mutation references a wrong response field name. The fastest
recovery loop:

1. Open `runs/<fault_id>/mutant/mitmdump.log` - confirm the route matched.
2. Open `runs/<fault_id>/mutant/pytest.log` - see what the oracle saw.
3. Open `runs/<fault_id>/mutant/trace/.../trace.zip` in
   [Playwright Trace Viewer](https://trace.playwright.dev/) - inspect the
   live DOM at the failing assertion.
4. Update the catalog `mutations:` entry, re-run with `--filter <fault_id>`.
