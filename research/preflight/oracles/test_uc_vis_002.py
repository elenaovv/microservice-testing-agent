"""Oracle test for UC-VIS-002 (Search for Tickets).

Hand-crafted ground-truth detector. Must:
  - PASS on a healthy MSA routed through mitmproxy in PASSTHROUGH mode
  - FAIL when any of F-VIS-002-{01,02,03,04} is injected via mitmproxy

Each assertion is tied to a specific success_criterion in the use-case spec
(spec/use_cases/user/research_cases/UC-VIS-002-search-for-tickets.yaml):
  C1: "the system returns at least one trip matching the submitted query"
  C2: "each returned trip shows identifying trip information and seat availability"

Detection mapping:
  F-VIS-002-01 (empty results)         -> fails C1 row-count assertion
  F-VIS-002-02 (drop train identifier) -> fails C2 train-id text assertion
  F-VIS-002-03 (drop seat fields)      -> fails C2 seat-availability assertion
  F-VIS-002-04 (canned wrong query)    -> fails C1 origin/destination match
"""
import os
import re

from playwright.sync_api import Page, expect


BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")

ORIGIN = "Shang Hai"
DESTINATION = "Su Zhou"
DATE = "2026-06-01"


def test_uc_vis_002_search_oracle(page: Page) -> None:
    page.set_default_timeout(15000)

    page.goto(f"{BASE_URL.rstrip('/')}/index.html", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Ticket Reserve")).to_be_visible(timeout=15000)

    page.locator("#travel_booking_startingPlace").fill(ORIGIN)
    page.locator("#travel_booking_terminalPlace").fill(DESTINATION)
    page.locator("#travel_booking_date").fill(DATE)
    page.locator("#travel_booking_date").press("Tab")
    page.locator("#search_select_train_type").select_option(value="0")  # All
    page.locator("#travel_searching_button").click()

    rows = page.locator("table tbody tr")
    expect(rows.first).to_be_visible(timeout=20000)

    # C1: at least one result row was returned.
    assert rows.count() >= 1, "no result rows rendered (violates: returns >=1 trip)"

    first = rows.first
    cells = first.locator("td")

    # C2: row carries an identifying train number / type (cell 1 is train id).
    expect(cells.nth(1)).to_contain_text(re.compile(r"\S"), timeout=10000)

    # C1: row's from/to columns reflect the submitted query (cells 3 and 4).
    expect(cells.nth(3)).to_contain_text(re.compile(r"shanghai", re.IGNORECASE))
    expect(cells.nth(4)).to_contain_text(re.compile(r"suzhou", re.IGNORECASE))

    # C2: row exposes seat-availability counts for both classes (cells 7, 8).
    expect(cells.nth(7)).to_contain_text(re.compile(r"\d"))
    expect(cells.nth(8)).to_contain_text(re.compile(r"\d"))
