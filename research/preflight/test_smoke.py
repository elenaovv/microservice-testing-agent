"""Smoke test for the mitmproxy fault-injection mechanism.

Mirrors the shape of an existing generated login test, but routes all browser
traffic through mitmproxy via the proxy fixture in conftest.py.

Expected outcomes when run with the train-ticket MSA up and mitmdump running:
  --set inject=passthrough   this test PASSES (proxy is transparent)
  --set inject=break_login   this test FAILS at expect_response (401 instead of 200)
"""
import os
import re

from playwright.sync_api import Page, expect


BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")


def test_login_through_proxy(page: Page) -> None:
    page.set_default_timeout(15000)

    page.goto(f"{BASE_URL.rstrip('/')}/client_login.html", wait_until="domcontentloaded")

    form = page.locator("form")
    expect(form).to_be_visible(timeout=10000)

    form.locator("#flow_preserve_login_email").fill("fdse_microservice")
    form.locator("#flow_preserve_login_password").fill("111111")
    form.locator("#flow_preserve_login_verification_code").fill("1234")

    with page.expect_response(
        lambda r: r.request.method == "POST"
        and r.url.endswith("/api/v1/users/login")
        and r.status == 200,
        timeout=15000,
    ):
        form.get_by_role("button", name="Login").click()

    expect(page.locator("li").filter(has_text="fdse_microservice")).to_be_visible(timeout=15000)
    expect(page.get_by_text(re.compile(r"login success", re.IGNORECASE))).to_be_visible(timeout=15000)
