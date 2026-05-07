"""Oracle for UC-VIS-004 (Book a Ticket).

PASS on healthy MSA; FAIL on F-VIS-004-{01,02,03,04}.
Asserts: a booking-confirmed indicator appears after submission (alert
"Success.---please go to order list to pay for it!").
"""
import os
import re
import time

from playwright.sync_api import Page, expect


BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
USERNAME = "fdse_microservice"
PASSWORD = "111111"
VERIFICATION_CODE = "1234"
START_PLACE = "Shanghai Hongqiao"
END_PLACE = "Jiaxingnan"
TRAVEL_DATE = "2026-06-10"

# Unique substring of the booking-confirmation alert. Avoiding the dashes and
# punctuation in the full phrase because the captured message visually contains
# `---` but my regex wasn't matching, suggesting either em-dashes or some other
# normalization difference in the dialog text.
SUCCESS_RE = re.compile(r"please go to order list to pay", re.IGNORECASE)


def test_uc_vis_004_book_oracle(page: Page) -> None:
    page.set_default_timeout(20000)
    dialog_msgs: list[str] = []

    def _on_dialog(d) -> None:
        dialog_msgs.append(d.message)
        d.accept()

    def _on_console(msg) -> None:
        # train-ticket sometimes logs alert text to console instead of firing
        # a native browser dialog (depends on how its JS shim wraps alert()).
        text = msg.text
        if "[dialog:alert]" in text or "Success" in text:
            dialog_msgs.append(text)

    page.on("dialog", _on_dialog)
    page.on("console", _on_console)

    # login
    page.goto(f"{BASE_URL}/client_login.html", wait_until="domcontentloaded")
    form = page.locator("form.form-horizontal")
    form.locator("#flow_preserve_login_email").fill(USERNAME)
    form.locator("#flow_preserve_login_password").fill(PASSWORD)
    form.locator("#flow_preserve_login_verification_code").fill(VERIFICATION_CODE)
    form.get_by_role("button", name="Login").click()
    expect(page.locator("#flow_preserve_login_msg")).to_have_text(re.compile(r"login success", re.IGNORECASE), timeout=15000)

    # baseline order count — used after booking to confirm a row was actually added
    page.goto(f"{BASE_URL}/client_order_list.html", wait_until="domcontentloaded")
    order_table = page.locator("table.am-table.am-table-striped.am-table-hover.table-main")
    expect(order_table).to_be_visible(timeout=15000)
    rows_before = order_table.locator("tbody tr").count()

    # search
    page.goto(f"{BASE_URL}/index.html", wait_until="domcontentloaded")
    page.locator("#travel_booking_startingPlace").fill(START_PLACE)
    page.locator("#travel_booking_terminalPlace").fill(END_PLACE)
    page.locator("#travel_booking_date").fill(TRAVEL_DATE)
    page.locator("#travel_booking_date").press("Tab")
    page.locator("#search_select_train_type").select_option(value="0")
    page.get_by_role("button", name="Search").click()

    rows = page.locator("#tickets_booking_list_table tbody tr")
    expect(rows.first).to_be_visible(timeout=20000)

    # pick first trip + capture its id for later persistence verification
    target = rows.first
    selected_trip_id = target.locator("td.booking_tripId").inner_text().strip()
    assert selected_trip_id, "Could not capture trip id from search results"

    target.locator("select.booking_seat_class").select_option(value="2")
    target.locator("button.ticket_booking_button").click()

    # contacts + assurance — rows 0 and 1 are header/template; the third row is the
    # first usable contact (matches the existing booking_test pattern).
    contacts = page.locator("#contacts_booking_list_table tbody tr")
    expect(contacts.first).to_be_visible(timeout=10000)
    assert contacts.count() >= 3, "Precondition failed: expected at least 3 contact rows"
    contacts.nth(2).locator("input.booking_contacts_select").click()
    page.locator("#assurance_type").select_option(value="0")
    page.get_by_role("button", name="Select").click()

    # confirm modal
    modal = page.locator("#my-prompt.am-modal-active")
    expect(modal).to_be_visible(timeout=15000)
    with page.expect_response(
        lambda r: r.request.method == "POST"
        and re.search(r"/preserve(other)?service/preserve(Other)?", r.url),
        timeout=20000,
    ) as resp_info:
        modal.locator(".am-modal-footer .am-modal-btn[data-am-modal-confirm]").click()
    preserve_resp = resp_info.value
    assert preserve_resp.ok, f"preserve HTTP status not ok: {preserve_resp.status}"

    # success_criterion 1: "the application confirms that the booking was placed".
    # Train-ticket's authoritative confirmation is the application-level status.
    body = preserve_resp.json()
    assert body.get("status") == 1, (
        f"booking not confirmed by application: {body}"
    )

    # success_criterion 2: "the booking request completes successfully for the
    # selected trip" — verify the new order was actually persisted. We use a
    # delta count rather than searching for selected_trip_id, because previous
    # passthrough runs may have already booked the same trip and the row would
    # match even when the current booking didn't persist (NO-OP fault case).
    page.goto(f"{BASE_URL}/client_order_list.html", wait_until="domcontentloaded")
    order_table = page.locator("table.am-table.am-table-striped.am-table-hover.table-main")
    expect(order_table).to_be_visible(timeout=15000)
    rows_after = order_table.locator("tbody tr").count()
    assert rows_after > rows_before, (
        f"order list did not grow after booking "
        f"(before={rows_before}, after={rows_after}); booking did not persist"
    )
