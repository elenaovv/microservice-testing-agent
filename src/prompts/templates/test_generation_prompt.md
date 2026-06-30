Using the execution brief, your logged actions, and your recorded timings below, write a pytest-playwright test that reproduces the intended successful journey steps exactly (exclude exploratory detours and failed intermediate attempts). Derive every assertion from the use case success criteria. Never assert states observed incidentally during browsing that are not part of the success criteria. For tests involving delete, update, or similar operations on existing data, do not hardcode a specific entity name or ID observed during browsing. Select the first available entity matching the preconditions dynamically at runtime, capture that target identifier from the chosen row, and use that same identifier for all post-action checks (network assertion and refreshed-list verification). Do not switch target rows mid-test. If a stable destructive target cannot be identified safely, prefer creating a disposable entity first and deleting that exact entity, or fail fast with a clear precondition assertion. Use `import os` and define `BASE_URL = os.environ.get("BASE_URL", "$base_url")` once near the top of the file. Always navigate with `page.goto(BASE_URL, ...)` instead of hardcoding the URL.

For create/register flows, generate unique values at runtime (for example time.time_ns() or a UUID suffix) and reuse those variables for assertions. Avoid hardcoded static usernames/emails/document numbers that could collide across runs.

Use the observed backend requests to add focused network-aware checks where appropriate. Prefer `page.expect_request()` or `page.expect_response()` for critical booking and order operations, and wrap them around the exact action that triggers the request. You are strictly forbidden from writing custom JavaScript (fetch, XMLHttpRequest, etc.) to synthesize API requests or bypass the UI. Let the frontend application handle all network communication.

For date fields in booking/search forms, interact through the UI control format (often locale-formatted) and commit the value with blur/Tab before clicking Search. Do not force backend timestamp text into the input field. When possible, assert the outbound search request payload contains the expected route/date semantics from the use case.

Execution brief:
$execution_brief

Minimal replay plan derived from browsing:
$replay_plan

Exploratory browse actions are archived in the journey guide. Use this replay plan and the structured journey contract as the default source of truth; consult full logs only when the replay plan is incomplete.

Use baseline_observations only to choose targets, remember original values, compute changed values, and compare preserved fields after the action. Never treat baseline observations as final success assertions. For final assertions, prefer structured success_observations from the contract. They are the exact evidence verified during browsing. Preserve their scoping and exactness instead of replacing them with broad page-level text matches. If a success observation has a scope_locator and field assertions, emit the scope first and then emit each scoped assertion exactly; do not rewrite structural assertions into text or accessible-name locators.

Recorded timings:
$timing_summary

Backend requests observed during exploration:
$observed_requests_block

Structured journey contract:
$journey_contract_block

Save it as '$filename' using create_python_test_file, then run it with run_test_file. If it fails, fix and retry at most $max_retries times.

Locator strategy reminder: use get_by_role over get_by_text for interactive elements. Strict mode will fail if a locator matches more than one element. For every locator you write, ask: 'is this word unique on the page?' For form inputs, never use the field's current value as its locator - JS-filled values are invisible to CSS attribute selectors. Prefer id-based locators (#id), positional locators (locator('input').nth(N)), or get_by_placeholder() only when the placeholder attribute is set in the HTML source. If you see a pre-filled form during browsing, locate its fields by structure, not by content.

Login submission: always click the actual login form submit control by role (button or input[type=submit]) scoped to the login form. Do not use get_by_text fallbacks or body clicks for login.

If the browse logs include element ids for modal fields, prefer id-based locators over role/label lookups inside the modal. Only use role/label when ids are missing. Always scope modal field locators to the anchored modal container (for example modal.locator('#add_user_name')).

Locator policy: use validated executable locator candidates first, scoped to their captured container. If none are validated, use stable executable CSS/test-id candidates, then scoped role/label candidates, then text candidates. Use positional locators only inside a validated container. Ignore non-executable snapshot locators such as browser refs, generic[ref=...], textbox[aria-label=...], combobox[aria-label=...], or button/text=....

If the browse logs include the modal submit control tag/id/class/data attributes, use that exact selector within the modal. Do not assume the confirm control has a button role; if it is a span/div, locate it by tag/class/text and click it.

Never use coordinate-based interactions in generated tests (for example page.mouse.click(x, y)); click explicit locators scoped to the correct container instead.

For any form field that showed autocomplete behaviour during browsing (a dropdown appeared after typing), use `locator.press_sequentially(value)` instead of `locator.fill(value)` in the generated test. `fill()` sets the value silently without triggering JavaScript input events, so autocomplete never fires and the UI submits an unrecognised value - causing empty search results or silent form failures. After `press_sequentially()`, wait for the dropdown option to appear and click it before continuing: `page.get_by_role('option', name=value).first.click()` or the equivalent visible suggestion locator.

If the browse logs include select option values, prefer `select_option(value=...)` over labels. Use label-based selection only when the label is confirmed visible in the control.

For all text content assertions use re.compile('...', re.IGNORECASE) rather than a plain string - never rely on remembered capitalisation.

Modal-scoping helper: when a modal/dialog/overlay is involved, always locate a reliable modal anchor (unique heading text or distinctive phrase) and scope subsequent actions to that container using Playwright locators. Example:

modal = page.locator(":has-text('<modal anchor>')").last
modal.wait_for(state="visible")
modal.locator("#add_user_name").fill(value)
modal.locator("[data-am-modal-confirm]").click()
modal.wait_for(state="hidden")

This keeps locators unambiguous across UI frameworks and avoids background clicks.

When a modal is open, never use page-level locators for its buttons or fields. Always use modal-scoped locators anchored to modal text captured during browsing.

For repeated-record success assertions, use the contract's scope locator and field assertions directly. If two fields can contain the same visible value, assert by stable child selector or position within the already-matched scope, such as `row.locator('td').nth(index).to_have_text(value)`, rather than `row.get_by_role('cell', name=value)`.

Repair rule: use the failure_diagnosis first. If it says the test was blocked before the required service call, repair that first failing locator/action instead of chasing the missing network call. Only repair the service trigger when the diagnosis shows the flow reached the trigger action without emitting the required side effect.

$msa_spec_instruction
