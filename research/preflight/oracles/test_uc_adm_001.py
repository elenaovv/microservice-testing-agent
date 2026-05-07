"""Oracle for UC-ADM-001 (Add User).

PASS on healthy MSA; FAIL on F-ADM-001-{01,02,03,04}.
Asserts: new user appears in the admin user list with submitted username/email.
"""
import os
import re
import time

from playwright.sync_api import Page, expect


BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "222222"


def _admin_login(page: Page) -> None:
    page.goto(f"{BASE_URL}/adminlogin.html", wait_until="domcontentloaded")
    page.locator('input[placeholder="Username"]').fill(ADMIN_USERNAME)
    page.locator('input[placeholder="Password"]').fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Login").click()
    expect(page).to_have_url(re.compile(r".*/admin\.html$"), timeout=15000)


def test_uc_adm_001_add_user_oracle(page: Page) -> None:
    page.set_default_timeout(20000)
    suffix = str(time.time_ns())[-8:]
    new_user = f"oracle_{suffix}"
    new_email = f"{new_user}@example.com"
    new_doc = f"DOC{suffix}"
    new_pass = f"Adm#{suffix}!"

    _admin_login(page)
    page.get_by_role("link", name=re.compile(r"user", re.IGNORECASE)).click()
    expect(page).to_have_url(re.compile(r".*/admin_user\.html$"), timeout=15000)

    page.get_by_role("button", name=re.compile(r"add", re.IGNORECASE)).click()
    modal = page.locator("#add_prompt")
    expect(modal).to_be_visible(timeout=15000)

    modal.locator("#add_user_name").fill(new_user)
    modal.locator("#add_user_password").fill(new_pass)
    modal.locator("#add_user_gender").select_option(value="1")
    modal.locator("#add_user_email").fill(new_email)
    modal.locator("#add_user_document_type").select_option(value="2")
    modal.locator("#add_user_document_number").fill(new_doc)
    modal.locator(".am-modal-btn").filter(has_text=re.compile(r"^Add$", re.IGNORECASE)).click()
    expect(modal).to_be_hidden(timeout=15000)

    # success_criterion: new account appears with submitted username and email
    row = page.locator("table tr").filter(has=page.locator("td", has_text=new_user)).first
    expect(row).to_be_visible(timeout=15000)
    expect(row.locator("td").nth(2)).to_have_text(re.compile(rf"^{re.escape(new_user)}$"), timeout=10000)
    expect(row.locator("td").nth(5)).to_have_text(re.compile(rf"^{re.escape(new_email)}$"), timeout=10000)
