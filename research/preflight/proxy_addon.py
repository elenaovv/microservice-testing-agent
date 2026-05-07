"""mitmproxy addon that applies a fault-catalog entry to live traffic.

Usage (passthrough):
  mitmdump -s research/preflight/proxy_addon.py -p 8888

Usage (inject a specific fault):
  mitmdump -s research/preflight/proxy_addon.py -p 8888 \
    --set fault_id=F-VIS-006-01

  mitmdump -s research/preflight/proxy_addon.py -p 8888 \
    --set fault_file=spec/faults/catalog.yaml \
    --set fault_id=F-ADM-014-02
"""
import json
import re
import sys
from pathlib import Path

import yaml
from mitmproxy import ctx, http

# Make sibling modules importable regardless of how mitmdump invokes the script.
sys.path.insert(0, str(Path(__file__).parent))
import transformers  # noqa: E402


_FAULT: dict | None = None
_DEFAULT_CATALOG = "spec/faults/catalog.yaml"


def load(loader) -> None:
    loader.add_option(
        name="fault_file",
        typespec=str,
        default=_DEFAULT_CATALOG,
        help="Path to fault catalog YAML",
    )
    loader.add_option(
        name="fault_id",
        typespec=str,
        default="PASSTHROUGH",
        help="Fault id to inject, or PASSTHROUGH for transparent proxy",
    )


def configure(updates) -> None:
    if "fault_id" not in updates and "fault_file" not in updates:
        return
    global _FAULT
    fid = ctx.options.fault_id
    if fid == "PASSTHROUGH":
        _FAULT = None
        ctx.log.info("[fault-proxy] PASSTHROUGH (no mutations)")
        return
    catalog_path = Path(ctx.options.fault_file)
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    for uc in catalog.get("use_cases", []):
        for fault in uc.get("faults", []):
            if fault["id"] == fid:
                _FAULT = fault
                ctx.log.info(
                    f"[fault-proxy] loaded {fid} ({len(fault['mutations'])} mutation(s))"
                )
                return
    raise ValueError(f"fault id not found in catalog: {fid}")


def _matches(mutation: dict, flow: http.HTTPFlow) -> bool:
    m = mutation["match"]
    if flow.request.method != m["method"]:
        return False
    path = flow.request.path.split("?", 1)[0]
    return bool(re.fullmatch(m["path_pattern"], path))


def request(flow: http.HTTPFlow) -> None:
    """Handle `respond` actions before forwarding to the MSA."""
    if _FAULT is None:
        return
    for mut in _FAULT["mutations"]:
        if not _matches(mut, flow):
            continue
        action = mut["action"]
        if action["type"] == "respond":
            body = action.get("body_inline", "").encode("utf-8")
            headers = action.get("headers", {"Content-Type": "application/json"})
            flow.response = http.Response.make(action.get("status", 200), body, headers)
            ctx.log.info(
                f"[fault-proxy] respond {action.get('status', 200)} on "
                f"{flow.request.method} {flow.request.path}"
            )
            return


def response(flow: http.HTTPFlow) -> None:
    """Handle `transform` actions after the MSA responds."""
    if _FAULT is None:
        return
    for mut in _FAULT["mutations"]:
        if not _matches(mut, flow):
            continue
        action = mut["action"]
        if action["type"] != "transform":
            continue
        try:
            body = json.loads(flow.response.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            ctx.log.warn(
                f"[fault-proxy] non-JSON response on {flow.request.path}; "
                f"skipping transform"
            )
            continue
        transformer_fn = getattr(transformers, action["transformer"], None)
        if transformer_fn is None:
            ctx.log.error(f"[fault-proxy] unknown transformer: {action['transformer']}")
            continue
        new_body = transformer_fn(body, action.get("args", {}))
        flow.response.content = json.dumps(new_body).encode("utf-8")
        ctx.log.info(
            f"[fault-proxy] transform({action['transformer']}) on "
            f"{flow.request.method} {flow.request.path}"
        )
        return
