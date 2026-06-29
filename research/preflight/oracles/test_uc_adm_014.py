"""Oracle for UC-ADM-014 (Delete Station).

PASS on healthy MSA (assumes >=2 stations exist); FAIL on F-ADM-014-{01,02,03,04}.

Deletes the LAST station rather than the first to minimize collateral risk
(seed stations are more likely to be referenced by trips/routes than custom ones).

Asserts after refresh:
  - deleted station no longer appears
  - other stations remain visible (catches OVERREACH)
"""
import os
import re

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


def test_uc_adm_014_delete_station_oracle(page: Page) -> None:
    page.set_default_timeout(20000)
    _admin_login(page)

    page.goto(f"{BASE_URL}/admin_station.html", wait_until="domcontentloaded")
    rows = page.locator("table tbody tr")
    expect(rows.first).to_be_visible(timeout=15000)
    initial_count = rows.count()
    assert initial_count >= 2, "Precondition failed: need >=2 stations to test delete"

    target = rows.last
    target_cells = target.locator("td")
    target_name = (target_cells.nth(1).text_content() or "").strip()
    assert target_name, "Precondition failed: target row missing name"

    # capture another station's name to verify it survives
    surviving_name = (rows.first.locator("td").nth(1).text_content() or "").strip()

    target.locator("button:has-text('Delete')").click()
    modal_h = page.locator(".am-modal-hd", has_text=re.compile(r"Delete Station Confirm", re.IGNORECASE))
    expect(modal_h).to_be_visible(timeout=10000)
    modal = modal_h.locator("xpath=ancestor::*[contains(@class, 'am-modal')][1]")
    modal.locator("[data-am-modal-confirm]").click()
    expect(modal).to_be_hidden(timeout=15000)

    page.goto(f"{BASE_URL}/admin_station.html", wait_until="domcontentloaded")
    expect(page.locator("table tbody tr").first).to_be_visible(timeout=15000)
    names = [(t or "").strip() for t in page.locator("table tbody tr td:nth-child(2)").all_text_contents()]
    # success_criteria: deleted gone; other survives
    assert target_name not in names, f"deleted station {target_name!r} still visible"
    if surviving_name and surviving_name != target_name:
        assert surviving_name in names, f"unrelated station {surviving_name!r} disappeared (overreach)"
