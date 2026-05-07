"""Oracle for UC-ADM-027 (Update System Configuration).

PASS on healthy MSA; FAIL on F-ADM-027-{01,02,03,04}.

CAUTION: this UC writes to a live config that downstream services may parse
as a number. The oracle reads the current Value, parses it, and writes
current_as_float + 0.1 formatted as a numeric string. Avoids the
"updated-value-178..." disaster where the LLM wrote a non-numeric string and
broke search.

The oracle deliberately targets the TestConfig row when present (a known
playground entry); otherwise targets the first row whose current Value parses
as a float.
"""
import os
import re

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


def _safe_new_value(current: str) -> str:
    try:
        return f"{float(current) + 0.1:.2f}"
    except ValueError:
        return "0.5"  # fall back to a known-safe numeric string


def test_uc_adm_027_update_config_oracle(page: Page) -> None:
    page.set_default_timeout(20000)
    _admin_login(page)
    page.goto(f"{BASE_URL}/admin_config.html", wait_until="domcontentloaded")

    rows = page.locator("table tbody tr")
    expect(rows.first).to_be_visible(timeout=15000)

    # prefer TestConfig row if present
    target = rows.filter(has=page.locator("td:nth-child(1)", has_text=re.compile(r"^TestConfig$"))).first
    if target.count() == 0:
        target = rows.first

    name = target.locator("td").nth(0).inner_text().strip()
    current_value = target.locator("td").nth(1).inner_text().strip()
    description = target.locator("td").nth(2).inner_text().strip()
    new_value = _safe_new_value(current_value)
    if new_value == current_value:
        new_value = f"{float(current_value) + 0.2:.2f}"

    target.get_by_role("button", name="Update").click()
    modal = page.locator('.am-modal-dialog:has-text("Update Configure")').filter(
        has=page.locator("#update-config-name")
    ).last
    expect(modal).to_be_visible(timeout=10000)

    value_input = modal.locator("#update-config-value")
    value_input.click()
    value_input.press("ControlOrMeta+A")
    value_input.press_sequentially(new_value)
    expect(value_input).to_have_value(new_value, timeout=5000)

    modal.locator(".am-modal-footer span").filter(has_text=re.compile(r"Submit", re.IGNORECASE)).click()
    expect(modal).to_be_hidden(timeout=15000)

    page.reload(wait_until="domcontentloaded")
    persisted = page.locator("table tbody tr").filter(
        has=page.locator(f'td:nth-child(1):text-is("{name}")')
    ).first
    expect(persisted).to_be_visible(timeout=15000)
    cells = persisted.locator("td")
    # success_criterion: Value updated; Name and Description unchanged
    expect(cells.nth(0)).to_have_text(re.compile(rf"^{re.escape(name)}$"), timeout=10000)
    expect(cells.nth(1)).to_have_text(re.compile(rf"^{re.escape(new_value)}$"), timeout=10000)
    expect(cells.nth(2)).to_have_text(re.compile(rf"^{re.escape(description)}$"), timeout=10000)
