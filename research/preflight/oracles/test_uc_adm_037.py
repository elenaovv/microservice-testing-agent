"""Oracle for UC-ADM-037 (Admin Login).

PASS on healthy MSA; FAIL on F-ADM-037-{01,02,03}.
Asserts: post-login admin-only navigation is visible.
"""
import os
import re

from playwright.sync_api import Page, expect


BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "222222"


def test_uc_adm_037_admin_login_oracle(page: Page) -> None:
    page.set_default_timeout(15000)
    page.goto(f"{BASE_URL.rstrip('/')}/adminlogin.html", wait_until="domcontentloaded")

    page.locator('input[placeholder="Username"]').fill(ADMIN_USERNAME)
    page.locator('input[placeholder="Password"]').fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Login").click()

    expect(page).to_have_url(re.compile(r".*/admin\.html$"), timeout=15000)
    expect(page.get_by_role("link", name=re.compile(r"Travel", re.IGNORECASE))).to_be_visible(timeout=10000)
    expect(page.get_by_role("link", name=re.compile(r"User", re.IGNORECASE))).to_be_visible(timeout=10000)
