"""Oracle for UC-VIS-010 (Enter Station).

PASS on healthy MSA (assumes >=1 order in Enter Station list);
FAIL on F-VIS-010-{01,02,03}.
Asserts: entered order disappears from the Enter Station list after refresh.
"""
import os
import re

from playwright.sync_api import Page, expect


BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
USERNAME = "fdse_microservice"
PASSWORD = "111111"
VERIFICATION_CODE = "1234"


def _login(page: Page) -> None:
    page.goto(f"{BASE_URL}/client_login.html", wait_until="domcontentloaded")
    form = page.locator("form").first
    form.locator("#flow_preserve_login_email").fill(USERNAME)
    form.locator("#flow_preserve_login_password").fill(PASSWORD)
    form.locator("#flow_preserve_login_verification_code").fill(VERIFICATION_CODE)
    form.get_by_role("button", name="Login").click()
    expect(page.locator("li").filter(has_text=USERNAME)).to_be_visible(timeout=15000)


def test_uc_vis_010_enter_oracle(page: Page) -> None:
    page.set_default_timeout(20000)
    _login(page)

    page.goto(f"{BASE_URL}/client_enter_station.html", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name=re.compile(r"Enter Station", re.IGNORECASE))).to_be_visible(timeout=10000)

    rows = page.locator("table tbody tr")
    expect(rows.first).to_be_visible(timeout=10000)
    assert rows.count() > 0, "Precondition failed: empty Enter Station list"
    target = rows.first
    target_id = target.locator("td").nth(1).inner_text().strip()
    assert target_id, "Precondition failed: row has no order id"

    target.locator("button#enter_reserve_execute_order_button").click()
    page.wait_for_load_state("networkidle", timeout=15000)

    # success_criterion: "after refresh, the entered order no longer appears"
    page.goto(f"{BASE_URL}/client_enter_station.html", wait_until="domcontentloaded")
    expect(page.locator("table")).not_to_contain_text(re.compile(re.escape(target_id), re.IGNORECASE), timeout=10000)
