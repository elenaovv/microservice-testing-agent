"""Oracle for UC-VIS-006 (Pay for an Order).

PASS on healthy MSA (assumes >=1 unpaid order exists);
FAIL on F-VIS-006-{01,02,03,04}.
Asserts: post-payment refresh shows "Paid & Not Collected" status.
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
    form = page.locator("form")
    form.locator("#flow_preserve_login_email").fill(USERNAME)
    form.locator("#flow_preserve_login_password").fill(PASSWORD)
    form.locator("#flow_preserve_login_verification_code").fill(VERIFICATION_CODE)
    form.get_by_role("button", name="Login").click()
    expect(page.locator("li").filter(has_text=USERNAME)).to_be_visible(timeout=15000)


def test_uc_vis_006_pay_oracle(page: Page) -> None:
    page.set_default_timeout(20000)
    _login(page)

    page.get_by_role("link", name="Order List").click()
    table = page.locator("table.am-table.am-table-striped.am-table-hover.table-main")
    expect(table).to_be_visible(timeout=15000)

    # find first unpaid order with a Pay button
    rows = table.locator("tbody tr")
    target_row = None
    target_id = None
    for i in range(rows.count()):
        row = rows.nth(i)
        status = row.locator("td").nth(7).inner_text(timeout=5000)
        if re.search(r"Not\s+Paid", status, re.IGNORECASE):
            if row.get_by_role("button", name="Pay").count() > 0:
                target_row = row
                target_id = row.locator("td").nth(1).inner_text(timeout=5000).strip()
                break
    assert target_row is not None and target_id, (
        "Precondition failed: no unpaid order with Pay button"
    )

    target_row.get_by_role("button", name="Pay").click()
    modal = page.locator(".am-modal.am-modal-active")
    expect(modal).to_be_visible(timeout=15000)
    with page.expect_response(
        lambda r: r.request.method == "POST"
        and "/api/v1/inside_pay_service/inside_payment" in r.url,
        timeout=15000,
    ) as resp_info:
        modal.locator("#pay_for_preserve").click()
    assert resp_info.value.ok, f"payment response not ok: {resp_info.value.status}"
    expect(modal).to_be_hidden(timeout=15000)

    # success_criterion: 'after refresh, target order status changes to "Paid & Not Collected"'
    page.goto(f"{BASE_URL}/client_order_list.html", wait_until="domcontentloaded")
    refreshed = page.locator("table.am-table tbody tr").filter(has_text=target_id)
    expect(refreshed).to_be_visible(timeout=15000)
    expect(refreshed.locator("td").nth(7)).to_contain_text(
        re.compile(r"Paid\s*&\s*Not\s*Collected", re.IGNORECASE), timeout=15000
    )
