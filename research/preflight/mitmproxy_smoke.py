"""mitmproxy addon used for the fault-injection smoke test.

Two modes, selected at startup with mitmproxy's --set option:

  --set inject=passthrough   no mutation; the proxy is transparent
  --set inject=break_login   return 401 to POST /api/v1/users/login

If the smoke test passes through `passthrough` and fails through `break_login`,
the injection mechanism is verified end-to-end.

Run from a separate terminal (with the train-ticket MSA already up):

  mitmdump -s research/preflight/mitmproxy_smoke.py -p 8888 --set inject=passthrough
"""
from mitmproxy import ctx, http


def load(loader) -> None:
    loader.add_option(
        name="inject",
        typespec=str,
        default="passthrough",
        help="Fault mode: passthrough | break_login",
    )


def response(flow: http.HTTPFlow) -> None:
    mode = ctx.options.inject
    if mode == "passthrough":
        return
    if mode == "break_login":
        path = flow.request.path or ""
        if flow.request.method == "POST" and path.endswith("/api/v1/users/login"):
            flow.response = http.Response.make(
                401,
                b'{"status": 0, "msg": "fault-injected: login refused by smoke test"}',
                {"Content-Type": "application/json"},
            )
