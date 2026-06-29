"""Oracle for UC-ADM-013 (Add Station).

PASS on healthy MSA; FAIL on F-ADM-013-{01,02,03}.
Asserts: new station appears in the station list with submitted name and stay time.
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
    page.get_by_role("textbox", name="Username").fill(ADMIN_USERNAME)
    page.get_by_role("textbox", name="Password").fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Login").click()
    expect(page).to_have_url(re.compile(r".*/admin\.html"), timeout=15000)


def test_uc_adm_013_add_station_oracle(page: Page) -> None:
    page.set_default_timeout(20000)
    new_name = f"oracle_st_{time.time_ns()}"
    stay_time = "11"

    _admin_login(page)
    page.goto(f"{BASE_URL}/admin_station.html", wait_until="domcontentloaded")
    expect(page.locator("table").first).to_be_visible(timeout=15000)

    page.get_by_role("button", name=re.compile(r"Add", re.IGNORECASE)).click()
    modal = page.locator("div").filter(
        has=page.get_by_text(re.compile(r"^Add Station$", re.IGNORECASE))
    ).filter(has=page.get_by_placeholder("Station Name")).last
    expect(modal).to_be_visible(timeout=15000)

    modal.get_by_placeholder("Station Name").fill(new_name)
    modal.get_by_placeholder("Stay Time").fill(stay_time)
    modal.locator("span").filter(has_text=re.compile(r"^Submit$", re.IGNORECASE)).click()
    expect(modal).to_be_hidden(timeout=20000)

    # success_criterion: new station appears with submitted name and stay time
    row = page.locator(f"table tr:has-text('{new_name}')")
    expect(row).to_be_visible(timeout=20000)
    expect(row.locator("td").nth(2)).to_have_text(re.compile(rf"^{re.escape(stay_time)}$"), timeout=10000)
