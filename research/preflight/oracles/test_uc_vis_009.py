"""Oracle for UC-VIS-009 (Collect a Ticket).

PASS on healthy MSA (assumes >=1 collectable order in the Collect list);
FAIL on F-VIS-009-{01,02,03}.
Asserts: collected order disappears from the Collect list after refresh.
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


def test_uc_vis_009_collect_oracle(page: Page) -> None:
    page.set_default_timeout(20000)
    _login(page)

    page.goto(f"{BASE_URL}/client_ticket_collect.html", wait_until="domcontentloaded")
    body = page.locator("table tbody")
    expect(body).to_be_visible(timeout=15000)

    rows = body.locator("tr")
    assert rows.count() > 0, "Precondition failed: empty Ticket Collect list"
    target = rows.first
    target_id = target.locator("td").nth(1).inner_text().strip()
    assert target_id, "Precondition failed: row has no order id"

    with page.expect_response(
        lambda r: r.request.method == "GET"
        and f"/api/v1/executeservice/execute/collected/{target_id}" in r.url,
        timeout=15000,
    ) as resp_info:
        target.locator("button#reserve_collect_button").click()
    assert resp_info.value.ok, f"collect response not ok: {resp_info.value.status}"

    # The frontend auto-navigates back to the collect page after success.
    # Wait for that to settle, then force-reload to ensure fresh server state.
    page.wait_for_load_state("networkidle", timeout=15000)
    page.reload(wait_until="domcontentloaded")

    # success_criterion: "after refresh, the collected order no longer appears"
    expect(page.locator("table tbody")).to_be_visible(timeout=15000)
    ids = [t.strip() for t in page.locator("table tbody tr td:nth-child(2)").all_inner_texts()]
    assert target_id not in ids, f"order {target_id} still in Collect list after refresh"
