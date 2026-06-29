"""Oracle for UC-ADM-007 (Update Train AverageSpeed).

PASS on healthy MSA; FAIL on F-ADM-007-{01,02,03,04}.

Reads current AverageSpeed and submits current+1 - a safe delta that does
NOT corrupt downstream search/book.

Asserts after refresh:
  - target train's AverageSpeed equals submitted value
  - other fields unchanged
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


def test_uc_adm_007_update_train_oracle(page: Page) -> None:
    page.set_default_timeout(20000)
    _admin_login(page)

    page.goto(f"{BASE_URL}/admin_train.html", wait_until="domcontentloaded")
    rows = page.locator("table tbody tr")
    expect(rows.first).to_be_visible(timeout=15000)

    target = rows.first
    cells = target.locator("td")
    name = cells.nth(0).inner_text().strip()
    economy = cells.nth(1).inner_text().strip()
    confort = cells.nth(2).inner_text().strip()
    speed = cells.nth(3).inner_text().strip()
    assert speed.isdigit(), "Precondition failed: AverageSpeed must be numeric"
    new_speed = str(int(speed) + 1)

    target.get_by_role("button", name="Update").click()
    expect(page.get_by_text(re.compile(r"^Update Train$", re.IGNORECASE))).to_be_visible(timeout=15000)

    inputs = page.locator("input:visible")
    expect(inputs).to_have_count(4, timeout=10000)
    inputs.nth(0).fill(name)
    inputs.nth(1).fill(economy)
    inputs.nth(2).fill(confort)
    inputs.nth(3).fill(new_speed)

    page.locator("#update-train-table >> text=Submit").click()
    expect(page.get_by_text(re.compile(r"^Update Train$", re.IGNORECASE))).to_be_hidden(timeout=15000)

    page.goto(f"{BASE_URL}/admin_train.html", wait_until="domcontentloaded")
    refreshed = page.locator("table tbody tr").filter(has_text=name).first
    expect(refreshed).to_be_visible(timeout=15000)
    rcells = refreshed.locator("td")
    # success_criterion: AverageSpeed updated; other fields unchanged
    expect(rcells.nth(0)).to_have_text(re.compile(rf"^{re.escape(name)}$"), timeout=10000)
    expect(rcells.nth(1)).to_have_text(re.compile(rf"^{re.escape(economy)}$"), timeout=10000)
    expect(rcells.nth(2)).to_have_text(re.compile(rf"^{re.escape(confort)}$"), timeout=10000)
    expect(rcells.nth(3)).to_have_text(re.compile(rf"^{re.escape(new_speed)}$"), timeout=10000)
