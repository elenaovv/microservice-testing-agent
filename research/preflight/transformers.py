"""Named transformers used by fault-catalog `transform` actions.

Each transformer takes (body: dict, args: dict) and returns the (possibly
mutated) body. Transformers operate on the parsed JSON response body in place,
but return it for chainability.

Path mini-language (used by `path` and `array_path` args):
  data                 - body["data"]
  data.field           - body["data"]["field"]
  data[*]              - every item in body["data"] (must be a list)
  data[*].field        - every item's "field" key
  data[-1].field       - last item's "field" key
  data[N].field        - Nth item's "field" key (negative index supported)
"""
import json
import re
from typing import Any, Iterable

_SEGMENT = re.compile(r"(\w+)(?:\[(\*|-?\d+)\])?")


def _resolve(body: Any, path: str) -> list[tuple[Any, Any]]:
    """Resolve `path` against `body`, returning (parent_container, key) pairs.

    Raises ValueError for malformed paths. Silently skips path branches whose
    intermediate nodes are missing — yields fewer results, never crashes.
    """
    if not path:
        raise ValueError("empty path")
    parts = path.split(".")
    cursors: list[Any] = [body]
    for i, part in enumerate(parts):
        m = _SEGMENT.fullmatch(part)
        if not m:
            raise ValueError(f"malformed path segment: {part!r} in {path!r}")
        name, idx = m.groups()
        is_last = i == len(parts) - 1
        nxt: list[Any] = []
        for cur in cursors:
            if not isinstance(cur, dict) or name not in cur:
                continue
            child = cur[name]
            if idx is None:
                if is_last:
                    nxt.append((cur, name))
                else:
                    nxt.append(child)
            else:
                if not isinstance(child, list):
                    continue
                if idx == "*":
                    indices: Iterable[int] = range(len(child))
                else:
                    n = int(idx)
                    if n < 0:
                        n = len(child) + n
                    indices = [n] if 0 <= n < len(child) else []
                for j in indices:
                    if is_last:
                        nxt.append((child, j))
                    else:
                        nxt.append(child[j])
        cursors = nxt
    return cursors  # list of (parent, key) tuples


def _get(body: Any, path: str) -> Any:
    pairs = _resolve(body, path)
    if not pairs:
        return None
    if len(pairs) == 1:
        parent, key = pairs[0]
        return parent[key]
    return [parent[key] for parent, key in pairs]


def set_response_field(body: Any, args: dict) -> Any:
    """Set the field at `args.path` to `args.value` for every match."""
    for parent, key in _resolve(body, args["path"]):
        parent[key] = args["value"]
    return body


def swap_response_field(body: Any, args: dict) -> Any:
    """Alias of set_response_field; readability for text-substitution faults."""
    return set_response_field(body, {"path": args["path"], "value": args["replacement"]})


def drop_fields_in_response_array(body: Any, args: dict) -> Any:
    """For every dict item under `args.array_path`, remove keys in `args.fields`."""
    items = _get(body, args["array_path"])
    if not isinstance(items, list):
        return body
    fields = args["fields"]
    for item in items:
        if isinstance(item, dict):
            for f in fields:
                item.pop(f, None)
    return body


def drop_records_from_array(body: Any, args: dict) -> Any:
    """Remove the first `args.count` items from the array at `args.array_path`."""
    items = _get(body, args["array_path"])
    if not isinstance(items, list):
        return body
    n = int(args["count"])
    del items[:n]
    return body


def replace_body(body: Any, args: dict) -> Any:
    """Replace the response body wholesale with the JSON in `args.body_inline`."""
    return json.loads(args["body_inline"])
