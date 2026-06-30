Follow this user journey step by step in the browser. Call log_action after every interaction and use start_timer/stop_timer around slow steps. Use the execution brief below as domain context, but verify the actual UI live before deciding the flow. If the spec you read provides a specific entry point URL for the journey, navigate there directly - do not explore intermediate pages to rediscover information you already have. The UI under test is served from $base_url; navigate there before you start browsing.

Execution brief:
$execution_brief

The success criteria describe the end state you must reach by actively performing every step of the journey. Observing text on the current page is not completion - you must take actions to drive the UI to the goal state. After any delete or update action, do not rely on the current table view to confirm success - the page may have reloaded or scrolled. Explicitly verify by reloading or re-querying and confirming the entity is truly absent or updated in the refreshed view.

You must strictly use native Playwright interactions (e.g., locator.click(), locator.press_sequentially()) for all form submissions and button presses to ensure frontend reactive frameworks properly bind data. Never use browser_evaluate to bypass the UI.

For date inputs or date-picker controls, use the format shown in the UI control, then commit the value with a blur action (for example Tab or clicking outside) before pressing Search/Submit. Do not assume the backend payload date format from the input text; the frontend may normalize it (for example to YYYY-MM-DD 00:00:00).

After every state-changing browser action (clicking a confirm button, submitting a form, triggering a deletion), call browser_network_requests and then call log_api_call once for each significant backend request you observe (method, path, and status code). Do not summarise network activity in text - use log_api_call so it is recorded structurally. This is especially important after confirmation modals: log the DELETE/POST/PUT that the confirmation triggered and its response status, so you can verify the operation reached the backend.

For search/filter journeys specifically, inspect the outbound search request after clicking Search. If the payload semantics do not match the UI values you entered (for example wrong route keys or date value), adjust the UI interaction sequence (picker selection, sequential typing, blur/Tab) and retry once before concluding failure. Do not validate by value similarity alone: verify exact payload key names and values from the outbound JSON body, and log those exact keys in log_action (for example startPlace vs startingPlace, endPlace vs terminalPlace).

At the end of browsing, you MUST call report_journey_outcome(success, reason) to record the outcome. Call with success=True only if all success criteria were met and verified, AND for state-changing journeys you have called log_api_call confirming a 2xx response. Call with success=False if the journey could not be completed for any reason - whether the UI could not be interacted with, or the system responded with an error. In both cases include the reason clearly. Stop immediately after calling report_journey_outcome(success=False).

If a modal, dialog, or overlay is open, it has interaction priority over the background page. Take a fresh snapshot and interact only with refs inside the top-most open container until it closes. If labels are duplicated (for example Confirm/Delete/Submit), choose the element inside the open modal, not the background page. If this requires disambiguation, add a log_action note labelled 'modal scope resolution' that records the modal text anchor and the control you chose.

Modal priority is strict: when a modal is visible, take a fresh snapshot and interact ONLY with refs inside the modal container. Never click background elements with matching labels. If you cannot find the intended control inside the modal, log a note and re-snapshot before trying again.

When a modal opens, immediately log a modal anchor note with: container id/class, heading text, and the exact labels of its action buttons. This anchor text will be used to scope test locators.

When you inspect select fields, record both the visible option label and its value attribute (for example 'Female' -> value=1). Log the select id and the label/value pairs.

For modal form fields, log each input/select id with its label text. Use log_action so the generator can prefer id-based locators in the test.

If modal action buttons are not discoverable by role, locate them by text/tag inside the modal container using the latest snapshot and click by element ref. Log the submit control tag, text, and id/class.

For every required interaction surface, call log_interaction_contract after you inspect the live UI/API surface. This contract must record actual observed facts, not prose guesses. Use generic surface types such as web_page, web_modal, web_drawer, rest_endpoint, graphql_operation, grpc_method, cli_command, or message_event. For web surfaces, include container.kind, a stable container selector or anchor text, every required visible editable field with selector/id/label/tag/type/options plus validated_locators when known, and every submit/confirm action with actual selector/tag/text/role. If one action opens a modal and another action submits it, record opens_surface on the first action and expected_service_calls or side_effects only on the submitting action.

For required fields and state-changing actions, validate at least one executable locator with a live lookup inside the active surface before logging the interaction contract. Do not record impossible selector/tag combinations, such as an observed div action with a button-only selector.

If you already logged an interaction contract and later discover better executable locators (for example stable input IDs, scoped selectors, or the real modal submit element), call log_interaction_contract again for that same surface with the corrected fields/actions and validated_locators. Corrected locator evidence must be in the structured contract, not only in a log_action note.

When inspecting pre-action state needed later, call log_baseline_observation with structured facts such as the selected target record and original field values. Baseline observations are setup evidence only; they must not be used as final success proof. After verifying the requested success criteria, call log_success_observation with the exact proof you used. Include the surface_type, assertion, target value/source when applicable, and executable locator candidates that were validated live. Prefer scoped or exact locators over broad text matches, especially when the same text appears in multiple fields. For repeated records such as table rows, list items, cards, detail panels, API objects, CLI rows, or message payloads, record observation_kind='record', a scope_locator for the record/container, and assertions for each important field. If duplicate visible values appear within the same record, use structural locators inside the scope, not another text/name lookup.

When creating new records, generate unique values (timestamp/nonce suffix) and log the exact values used, so retries and generated tests avoid duplicate collisions.

When you observe a confirmation or status message, record its exact text (preserving capitalisation) in your log_action note. After clicking any button that triggers an action (login, booking, payment, cancellation), check the browser console for messages prefixed with [dialog:alert] - these are JavaScript alerts captured without blocking the page. Important: console messages are cumulative. A [dialog:alert] message visible after a click may have been logged at page load, not as a response to your click. Only treat a [dialog:alert] as a response to your action if it appears AFTER the action completes. Always also check the DOM state (visible text, status fields) to confirm the actual outcome.

$msa_spec_instruction
