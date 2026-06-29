"""Pre-flight verifier for the fault catalog.

For each fault, runs the corresponding oracle test through mitmproxy twice:
once in passthrough mode (must pass) and once with the fault injected (must
fail). Emits a verdict per fault and persists per-run logs and Playwright
traces for later inspection.

Usage:
  python research/preflight/run_preflight.py
  python research/preflight/run_preflight.py --filter F-VIS-002
"""
import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "spec" / "faults" / "catalog.yaml"
DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_PROXY_PORT = 8888
ADDON = Path(__file__).parent / "proxy_addon.py"
ORACLES_DIR = Path(__file__).parent / "oracles"

CSV_FIELDS = [
    "fault_id", "use_case", "oracle_file",
    "passthrough", "mutant", "verdict",
    "passthrough_duration_s", "mutant_duration_s", "timestamp",
]


def oracle_path_for(use_case_id: str) -> Path:
    """UC-VIS-002 -> oracles/test_uc_vis_002.py"""
    return ORACLES_DIR / f"test_{use_case_id.lower().replace('-', '_')}.py"


def recover_known_fragile_state(base_url: str) -> None:
    """PUT known-fragile config back to its safe value.

    DirectTicketAllocationProportion governs ticket-availability filtering;
    if a prior test left a non-numeric value there, search and book break
    until it is reset.
    """
    payloads = [
        {
            "name": "DirectTicketAllocationProportion",
            "value": "0.5",
            "description": "Allocation Proportion Of The Direct Ticket - From Start To End",
        },
    ]
    for body in payloads:
        try:
            resp = requests.put(
                f"{base_url}/api/v1/configservice/configs",
                json=body,
                timeout=5,
            )
            print(f"[recover] {body['name']} <- {body['value']!r} ({resp.status_code})")
        except Exception as exc:
            print(f"[recover] {body['name']} FAILED: {exc}", file=sys.stderr)


def _port_in_use(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def launch_mitmdump(port: int, fault_id: str | None,
                    catalog_path: Path, log_path: Path) -> subprocess.Popen:
    # Allow a brief grace window in case our own previous mitmdump is still releasing.
    grace = time.time() + 3
    while _port_in_use(port) and time.time() < grace:
        time.sleep(0.2)
    if _port_in_use(port):
        raise RuntimeError(
            f"port {port} is already bound - likely a stale mitmdump from a prior run. "
            f"Kill it and retry: Get-Process mitmdump | Stop-Process -Force"
        )
    cmd = [
        "mitmdump",
        "-s", str(ADDON),
        "-p", str(port),
        "--set", f"fault_file={catalog_path}",
        "--set", f"fault_id={fault_id or 'PASSTHROUGH'}",
    ]
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
    # wait for mitmdump to bind the port (or fail to)
    deadline = time.time() + 8
    while time.time() < deadline:
        if _port_in_use(port):
            return proc
        if proc.poll() is not None:
            log_file.close()
            raise RuntimeError(
                f"mitmdump exited before binding port {port}; see {log_path}"
            )
        time.sleep(0.2)
    proc.terminate()
    raise RuntimeError(f"mitmdump did not bind port {port} within 8s")


def stop_mitmdump(proc: subprocess.Popen, port: int) -> None:
    if platform.system() == "Windows":
        # mitmdump spawns worker children on Windows; killing the parent leaves
        # the listening socket bound. Use taskkill /T to take down the tree.
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True, check=False,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    # Wait for the OS to release the listening socket before returning.
    deadline = time.time() + 5
    while time.time() < deadline:
        if not _port_in_use(port):
            return
        time.sleep(0.2)


def run_oracle(oracle_path: Path, log_path: Path, trace_dir: Path,
               proxy_url: str, base_url: str, timeout: int) -> tuple[str, float]:
    trace_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "pytest", str(oracle_path), "-v",
        "--tracing", "on",
        "--output", str(trace_dir),
    ]
    env = {**os.environ,
           "MITM_PROXY": proxy_url,
           "BASE_URL": base_url,
           "PYTHONUNBUFFERED": "1"}
    t0 = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, env=env)
        log_path.write_text(
            (result.stdout or "") +
            (("\n--- STDERR ---\n" + result.stderr) if result.stderr else ""),
            encoding="utf-8",
        )
        status = "passed" if result.returncode == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        log_path.write_text(
            f"TIMEOUT after {timeout}s\n{exc.stdout or ''}\n{exc.stderr or ''}",
            encoding="utf-8",
        )
        status = "timeout"
    return status, time.time() - t0


def derive_verdict(passthrough: str, mutant: str) -> str:
    if passthrough != "passed":
        return "ORACLE-BROKEN"
    if mutant == "failed" or mutant == "timeout":
        return "USE"
    if mutant == "passed":
        return "EQUIVALENT-DROP"
    return "UNKNOWN"


def run_phase(phase: str, fault_id_for_proxy: str | None, oracle: Path,
              phase_dir: Path, args, catalog_path: Path) -> tuple[str, float]:
    phase_dir.mkdir(parents=True, exist_ok=True)
    mitm_log = phase_dir / "mitmdump.log"
    pytest_log = phase_dir / "pytest.log"
    trace_dir = phase_dir / "trace"
    proxy_url = f"http://localhost:{args.proxy_port}"

    proc = launch_mitmdump(args.proxy_port, fault_id_for_proxy, catalog_path, mitm_log)
    try:
        status, dur = run_oracle(
            oracle, pytest_log, trace_dir,
            proxy_url, args.base_url, args.timeout,
        )
    finally:
        stop_mitmdump(proc, args.proxy_port)
    print(f"  {phase:11s} -> {status} ({dur:.1f}s)")
    return status, dur


def run_one_fault(fault_id: str, use_case_id: str, args,
                  results_dir: Path, catalog_path: Path,
                  passthrough_cache: dict[str, tuple[str, float]]) -> dict:
    """Run one fault. Reuses the per-UC passthrough verdict if already cached.

    The passthrough run is identical for every fault under the same UC, so we
    only run it once per UC and cache (status, duration). This roughly halves
    the matrix wall-clock and avoids paying/collecting/booking real orders
    multiple times during pre-flight."""
    oracle = oracle_path_for(use_case_id)
    if not oracle.exists():
        print(f"  [skip] no oracle file at {oracle}")
        return {
            "fault_id": fault_id, "use_case": use_case_id,
            "oracle_file": oracle.name,
            "passthrough": "n/a", "mutant": "n/a",
            "verdict": "NO-ORACLE",
            "passthrough_duration_s": 0.0, "mutant_duration_s": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    fault_dir = results_dir / "runs" / fault_id

    if use_case_id in passthrough_cache:
        pt_status, pt_dur = passthrough_cache[use_case_id]
        print(f"  passthrough -> {pt_status} (cached from this UC's first fault)")
    else:
        pt_status, pt_dur = run_phase(
            "passthrough", None, oracle, fault_dir / "passthrough",
            args, catalog_path,
        )
        passthrough_cache[use_case_id] = (pt_status, pt_dur)

    if pt_status != "passed":
        # Skip mutant phase entirely if passthrough is broken - running
        # anything against a broken oracle wastes time and produces noise.
        print("  mutant      -> skipped (passthrough not passing)")
        verdict = "ORACLE-BROKEN"
        mt_status = "skipped"
        mt_dur = 0.0
    else:
        mt_status, mt_dur = run_phase(
            "mutant", fault_id, oracle, fault_dir / "mutant",
            args, catalog_path,
        )
        verdict = derive_verdict(pt_status, mt_status)

    print(f"  verdict      -> {verdict}")
    return {
        "fault_id": fault_id,
        "use_case": use_case_id,
        "oracle_file": oracle.name,
        "passthrough": pt_status,
        "mutant": mt_status,
        "verdict": verdict,
        "passthrough_duration_s": round(pt_dur, 2),
        "mutant_duration_s": round(mt_dur, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def write_summary(results_dir: Path, rows: list[dict]) -> None:
    by_verdict: dict[str, int] = {}
    for r in rows:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
    lines = [
        "# Pre-flight verdict summary",
        "",
        f"Total faults processed: **{len(rows)}**",
        "",
    ]
    for v, n in sorted(by_verdict.items()):
        lines.append(f"- **{v}**: {n}")
    lines += [
        "",
        "## Per-fault detail",
        "",
        "| fault_id | use_case | passthrough | mutant | verdict |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['fault_id']} | {r['use_case']} | "
            f"{r['passthrough']} | {r['mutant']} | {r['verdict']} |"
        )
    (results_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--proxy-port", type=int, default=DEFAULT_PROXY_PORT)
    parser.add_argument("--timeout", type=int, default=180,
                        help="pytest timeout per oracle run (seconds)")
    parser.add_argument("--filter", default=None,
                        help="run only faults whose id contains this substring")
    parser.add_argument("--output-dir", default=None,
                        help="results directory (default: timestamped under research/preflight/results/)")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))

    if args.output_dir:
        results_dir = Path(args.output_dir)
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        results_dir = ROOT / "research" / "preflight" / "results" / f"preflight_{ts}"
    results_dir.mkdir(parents=True, exist_ok=True)

    print(f"[preflight] catalog: {catalog_path}")
    print(f"[preflight] results: {results_dir}")
    print(f"[recover-pre]")
    recover_known_fragile_state(args.base_url)

    rows: list[dict] = []
    csv_path = results_dir / "verdict.csv"
    jsonl_path = results_dir / "verdict.jsonl"

    passthrough_cache: dict[str, tuple[str, float]] = {}
    with csv_path.open("w", newline="", encoding="utf-8") as csv_f, \
            jsonl_path.open("w", encoding="utf-8") as jsonl_f:
        writer = csv.DictWriter(csv_f, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for uc in catalog["use_cases"]:
            for fault in uc["faults"]:
                fid = fault["id"]
                if args.filter and args.filter not in fid:
                    continue
                print(f"\n[preflight] {fid}  ({uc['id']})")
                row = run_one_fault(fid, uc["id"], args, results_dir,
                                    catalog_path, passthrough_cache)
                rows.append(row)
                writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})
                csv_f.flush()
                jsonl_f.write(json.dumps(row) + "\n")
                jsonl_f.flush()

    print(f"\n[recover-post]")
    recover_known_fragile_state(args.base_url)

    write_summary(results_dir, rows)

    by_verdict: dict[str, int] = {}
    for r in rows:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
    print(f"\n[preflight] complete: {len(rows)} faults")
    for v, n in sorted(by_verdict.items()):
        print(f"  {v}: {n}")
    print(f"[preflight] verdict.csv: {csv_path}")
    print(f"[preflight] summary.md:  {results_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
