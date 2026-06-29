"""Oracle for UC-VIS-001 (Login).

PASS on healthy MSA; FAIL on F-VIS-001-{01,02,03}.
Asserts: post-login authenticated header is visible (success_criterion C1).
"""
import os
import re

from playwright.sync_api import Page, expect


BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
USERNAME = "fdse_microservice"
PASSWORD = "111111"
VERIFICATION_CODE = "1234"


def test_uc_vis_001_login_oracle(page: Page) -> None:
    page.set_default_timeout(15000)
    page.goto(f"{BASE_URL.rstrip('/')}/client_login.html", wait_until="domcontentloaded")

    form = page.locator("form").first
    expect(form).to_be_visible(timeout=10000)

    form.locator("#flow_preserve_login_email").fill(USERNAME)
    form.locator("#flow_preserve_login_password").fill(PASSWORD)
    form.locator("#flow_preserve_login_verification_code").fill(VERIFICATION_CODE)
    form.get_by_role("button", name="Login").click()

    # success_criterion: "the application shows an authenticated user-facing post-login state"
    expect(page.locator("li").filter(has_text=USERNAME)).to_be_visible(timeout=15000)
    expect(page.get_by_text(re.compile(r"login success", re.IGNORECASE))).to_be_visible(timeout=15000)
