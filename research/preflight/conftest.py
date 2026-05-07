import os

import pytest


PROXY_URL = os.environ.get("MITM_PROXY", "http://localhost:8888")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "proxy": {"server": PROXY_URL},
        "ignore_https_errors": True,
    }
