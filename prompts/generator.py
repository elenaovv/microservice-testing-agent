from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from core.coverage_utils import extract_spec_endpoints
from core.models import JourneyCapture, JourneyContract

try:
    import yaml
except ImportError:  # pragma: no cover - depends on environment packaging
    yaml = None

MSA_SPEC_PATH = Path(__file__).resolve().parent.parent / "spec" / "msa.yaml"
SYSTEM_DESCRIPTION_PATH = (
    Path(__file__).resolve().parent.parent / "spec" / "system_description.md"
)
USE_CASES_PATH = Path(__file__).resolve().parent.parent / "spec" / "use-cases.txt"
STRUCTURED_USE_CASES_DIR = Path(__file__).resolve().parent.parent / "spec" / "use_cases"
STRUCTURED_USE_CASE_INDEX_PATH = STRUCTURED_USE_CASES_DIR / "index.yaml"

FILENAME_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "then",
    "that",
    "this",
    "user",
    "users",
    "ticket",
    "tickets",
    "point",
    "train",
    "route",
    "page",
}

BRIEF_STOPWORDS = FILENAME_STOPWORDS | {
    "success",
    "criteria",
    "preconditions",
    "authenticated",
    "state",
    "user",
    "role",
    "admin",
    "traveler",
}

CONCEPT_ALIASES = {
    "book": ["booking", "reserve", "reservation", "purchase"],
    "booking": ["book", "reserve", "reservation", "purchase"],
    "login": ["authenticate", "authentication", "signin", "session"],
    "logout": ["signout", "session"],
    "pay": ["payment", "checkout", "purchase"],
    "payment": ["pay", "checkout", "purchase"],
    "cancel": ["refund", "revoke", "void"],
    "rebook": ["change", "modify", "exchange"],
    "order": ["purchase", "reservation", "checkout"],
    "route": ["path", "trip", "travel"],
    "station": ["location", "stop", "terminal"],
    "train": ["trip", "travel", "service"],
    "price": ["fare", "cost", "amount"],
    "schedule": ["trip", "timetable", "departure"],
    "user": ["account", "profile", "identity"],
}


@dataclass(slots=True)
class StructuredUseCase:
    id: str
    role: str
    name: str
    goal: str
    preconditions: list[str]
    success_criteria: list[str]
    notes: str = ""
    smith_equivalent: str = ""
    source_path: Path | None = None

    def journey_text(self) -> str:
        parts = [
            f"{self.role.title()} use case {self.id}: {self.name}.",
            self.goal.strip(),
        ]
        if self.preconditions:
            parts.append("Preconditions: " + "; ".join(self.preconditions) + ".")
        if self.success_criteria:
            parts.append(
                "Success criteria: " + "; ".join(self.success_criteria) + "."
            )
        return " ".join(part for part in parts if part)

    def prompt_context(self) -> str:
        lines = [
            f"ID: {self.id}",
            f"Role: {self.role}",
            f"Name: {self.name}",
            f"Goal: {self.goal.strip()}",
        ]
        if self.preconditions:
            lines.append("Preconditions:")
            lines.extend(f"- {item}" for item in self.preconditions)
        if self.success_criteria:
            lines.append("Success criteria:")
            lines.extend(f"- {item}" for item in self.success_criteria)
        if self.notes:
            lines.append(f"Notes: {self.notes}")
        if self.source_path is not None:
            lines.append(f"Source file: {self.source_path}")
        return "\n".join(lines)


def _require_yaml() -> Any:
    if yaml is None:
        raise RuntimeError(
            "Structured use case support requires PyYAML in the Python environment."
        )
    return yaml


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")
    yaml_module = _require_yaml()
    data = yaml_module.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return data


def load_msa_spec(path: Path | None = None) -> str:
    path = path or MSA_SPEC_PATH
    if not path.exists():
        raise FileNotFoundError(f"MSA specification file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_system_description(path: Path | None = None) -> str:
    path = path or SYSTEM_DESCRIPTION_PATH
    if not path.exists():
        raise FileNotFoundError(f"System description file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_use_cases(path: Path = USE_CASES_PATH) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Use case file not found: {path}")
    use_cases: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        use_cases.append(line)
    return use_cases


def load_use_case_index(
    path: Path = STRUCTURED_USE_CASE_INDEX_PATH,
) -> list[dict[str, str]]:
    data = _load_yaml_file(path)
    use_cases = data.get("use_cases", [])
    if not isinstance(use_cases, list):
        raise ValueError(f"Expected 'use_cases' list in {path}")
    normalized: list[dict[str, str]] = []
    for item in use_cases:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": str(item.get("id", "")).strip(),
                "role": str(item.get("role", "")).strip(),
                "name": str(item.get("name", "")).strip(),
                "path": str(item.get("path", "")).strip(),
                "smith_equivalent": str(item.get("smith_equivalent", "")).strip(),
            }
        )
    return normalized


def resolve_indexed_use_case_path(index_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path

    candidates = [
        index_path.parent / path,
        STRUCTURED_USE_CASES_DIR / path,
        Path(__file__).resolve().parent.parent / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _normalize_preconditions(data: dict[str, Any]) -> list[str]:
    preconditions_data = data.get("preconditions", {})
    if not isinstance(preconditions_data, dict):
        return []

    preconditions: list[str] = []
    authenticated_as = str(preconditions_data.get("authenticated_as", "")).strip()
    if authenticated_as and authenticated_as.lower() != "none":
        preconditions.append(f"authenticated as {authenticated_as}")

    for item in list(preconditions_data.get("state", [])):
        text = str(item).strip()
        if text:
            preconditions.append(text)

    return preconditions


def load_structured_use_case(path: Path) -> StructuredUseCase:
    data = _load_yaml_file(path)
    success_criteria = [
        str(item).strip()
        for item in list(data.get("success_criteria", []))
        if str(item).strip()
    ]
    return StructuredUseCase(
        id=str(data.get("id", "")).strip(),
        role=str(data.get("role", "")).strip(),
        name=str(data.get("name", "")).strip(),
        goal=str(data.get("goal", "")).strip(),
        preconditions=_normalize_preconditions(data),
        success_criteria=success_criteria,
        notes=str(data.get("notes", "")).strip(),
        smith_equivalent=str(data.get("smith_equivalent", "")).strip(),
        source_path=path,
    )


def load_structured_use_case_by_id(
    use_case_id: str,
    index_path: Path = STRUCTURED_USE_CASE_INDEX_PATH,
) -> StructuredUseCase:
    normalized_id = use_case_id.strip()
    for item in load_use_case_index(index_path):
        if item.get("id") != normalized_id:
            continue
        relative_path = item.get("path", "")
        if not relative_path:
            raise ValueError(f"Use case {normalized_id} has no path in {index_path}")
        use_case = load_structured_use_case(
            resolve_indexed_use_case_path(index_path, relative_path)
        )
        if not use_case.smith_equivalent:
            use_case.smith_equivalent = item.get("smith_equivalent", "")
        return use_case
    raise ValueError(f"Unknown use case ID: {normalized_id}")


def derive_python_test_filename(journey: str) -> str:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", journey.lower())
        if len(token) > 2 and token not in FILENAME_STOPWORDS
    ]
    if not tokens:
        return "journey_test.py"
    if tokens[0] == "book":
        tokens[0] = "booking"
    return f"{'_'.join(tokens[:3])}_test.py"


def derive_use_case_test_filename(use_case: StructuredUseCase) -> str:
    return derive_python_test_filename(use_case.name)


def _brief_tokens(*parts: str) -> list[str]:
    text = " ".join(part.lower() for part in parts if part)
    base_tokens = [
        token
        for token in re.findall(r"[a-z0-9_]+", text)
        if len(token) > 2 and token not in BRIEF_STOPWORDS
    ]
    expanded_tokens = list(base_tokens)
    for token in base_tokens:
        expanded_tokens.extend(CONCEPT_ALIASES.get(token, []))
    return expanded_tokens


def build_relevant_msa_excerpt(
    journey: str,
    msa_spec: str,
    *,
    use_case_context: str = "",
    max_services: int = 12,
    max_endpoints_per_service: int = 4,
) -> str:
    tokens = _brief_tokens(journey, use_case_context)
    if not tokens:
        return "No focused service slice could be derived from the selected journey."

    grouped_matches: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for endpoint in extract_spec_endpoints(msa_spec):
        haystack = " ".join(endpoint.values()).lower()
        score = sum(1 for token in tokens if token in haystack)
        if score <= 0:
            continue
        service = endpoint.get("service", "unmapped")
        grouped_matches.setdefault(service, []).append((score, endpoint))

    if not grouped_matches:
        return "No focused service slice could be derived from the selected journey."

    ranked_services = sorted(
        grouped_matches.items(),
        key=lambda item: (
            -sum(score for score, _ in item[1]),
            item[0],
        ),
    )

    lines: list[str] = []
    for service, matches in ranked_services[:max_services]:
        lines.append(f"{service}:")
        ranked_endpoints = sorted(
            matches,
            key=lambda item: (-item[0], item[1].get("path", "")),
        )
        for _, endpoint in ranked_endpoints[:max_endpoints_per_service]:
            description = endpoint.get("description", "").strip()
            endpoint_line = (
                f"- {endpoint.get('method', '').upper()} {endpoint.get('path', '')}"
            )
            if description:
                endpoint_line += f" - {description}"
            lines.append(endpoint_line)
    return "\n".join(lines)


def build_execution_brief(
    journey: str,
    msa_spec: str,
    *,
    system_description: str = "",
    use_case_context: str = "",
) -> str:
    sections = [f"Journey:\n{journey}"]
    if system_description:
        sections.append(f"System description:\n{system_description}")
    if use_case_context:
        sections.append(f"Structured use case:\n{use_case_context}")
    sections.append(
        "Relevant MSA slice:\n"
        + build_relevant_msa_excerpt(
            journey=journey,
            msa_spec=msa_spec,
            use_case_context=use_case_context,
        )
    )
    return "\n\n".join(sections)


def build_browse_prompt(
    journey: str,
    msa_spec: str,
    base_url: str,
    *,
    system_description: str = "",
    use_case_context: str = "",
    msa_spec_path: str = "",
) -> str:
    execution_brief = build_execution_brief(
        journey=journey,
        msa_spec=msa_spec,
        system_description=system_description,
        use_case_context=use_case_context,
    )
    sections = [
        "Follow this user journey step by step in the browser. "
        "Call log_action after every interaction and use start_timer/stop_timer around slow steps. "
        "Use the execution brief below as domain context, but verify the actual UI live before deciding the flow. "
        "If the spec you read provides a specific entry point URL for the journey, navigate there directly — "
        "do not explore intermediate pages to rediscover information you already have. "
        f"The UI under test is served from {base_url}; navigate there before you start browsing.",
        f"Execution brief:\n{execution_brief}",
        "The success criteria describe the end state you must reach by actively performing "
        "every step of the journey. Observing text on the current page is not completion — "
        "you must take actions to drive the UI to the goal state. "
        "After any delete or update action, do not rely on the current table view to confirm success — "
        "the page may have reloaded or scrolled. Explicitly verify by reloading or re-querying "
        "and confirming the entity is truly absent or updated in the refreshed view.",
        "You must strictly use native Playwright interactions (e.g., locator.click(), locator.press_sequentially()) "
        "for all form submissions and button presses to ensure frontend reactive frameworks properly bind data. "
        "Never use browser_evaluate to bypass the UI.",
        "For date inputs or date-picker controls, use the format shown in the UI control, then commit the value "
        "with a blur action (for example Tab or clicking outside) before pressing Search/Submit. "
        "Do not assume the backend payload date format from the input text; the frontend may normalize it "
        "(for example to YYYY-MM-DD 00:00:00).",
        "After every state-changing browser action (clicking a confirm button, submitting a form, triggering a deletion), "
        "call browser_network_requests and then call log_api_call once for each significant backend request you observe "
        "(method, path, and status code). Do not summarise network activity in text — use log_api_call so it is recorded structurally. "
        "This is especially important after confirmation modals: log the DELETE/POST/PUT that the confirmation triggered "
        "and its response status, so you can verify the operation reached the backend.",
        "For search/filter journeys specifically, inspect the outbound search request after clicking Search. "
        "If the payload semantics do not match the UI values you entered (for example wrong route keys or date value), "
        "adjust the UI interaction sequence (picker selection, sequential typing, blur/Tab) and retry once before concluding failure. "
        "Do not validate by value similarity alone: verify exact payload key names and values from the outbound JSON body, "
        "and log those exact keys in log_action (for example startPlace vs startingPlace, endPlace vs terminalPlace).",
        "At the end of browsing, you MUST call report_journey_outcome(success, reason) "
        "to record the outcome. "
        "Call with success=True only if all success criteria were met and verified, "
        "AND for state-changing journeys you have called log_api_call confirming a 2xx response. "
        "Call with success=False if the journey could not be completed for any reason — "
        "whether the UI could not be interacted with, or the system responded with an error. "
        "In both cases include the reason clearly. "
        "Stop immediately after calling report_journey_outcome(success=False).",
        "If a modal, dialog, or overlay is open, it has interaction priority over the background page. "
        "Take a fresh snapshot and interact only with refs inside the top-most open container until it closes. "
        "If labels are duplicated (for example Confirm/Delete/Submit), choose the element inside the open modal, "
        "not the background page. "
        "If this requires disambiguation, add a log_action note labelled 'modal scope resolution' "
        "that records the modal text anchor and the control you chose.",
        "Modal priority is strict: when a modal is visible, take a fresh snapshot and interact ONLY with refs "
        "inside the modal container. Never click background elements with matching labels. If you cannot find "
        "the intended control inside the modal, log a note and re-snapshot before trying again.",
        "When a modal opens, immediately log a modal anchor note with: container id/class, heading text, "
        "and the exact labels of its action buttons. This anchor text will be used to scope test locators.",
        "When you inspect select fields, record both the visible option label and its value attribute "
        "(for example 'Female' -> value=1). Log the select id and the label/value pairs.",
        "For modal form fields, log each input/select id with its label text. Use log_action so the generator "
        "can prefer id-based locators in the test.",
        "If modal action buttons are not discoverable by role, locate them by text/tag inside the modal container "
        "using the latest snapshot and click by element ref. Log the submit control tag, text, and id/class.",
        "For every required interaction surface, call log_interaction_contract after you inspect the live UI/API "
        "surface. This contract must record actual observed facts, not prose guesses. Use generic surface types "
        "such as web_page, web_modal, web_drawer, rest_endpoint, graphql_operation, grpc_method, cli_command, "
        "or message_event. For web surfaces, include container.kind, a stable container selector or anchor text, "
        "every required visible editable field with selector/id/label/tag/type/options plus validated_locators "
        "when known, and every submit/confirm action with actual selector/tag/text/role. If one action opens a "
        "modal and another action submits it, record opens_surface on the first action and expected_service_calls "
        "or side_effects only on the submitting action. ",
        "For required fields and state-changing actions, validate at least one executable locator with a live "
        "lookup inside the active surface before logging the interaction contract. Do not record impossible "
        "selector/tag combinations, such as an observed div action with a button-only selector.",
        "If you already logged an interaction contract and later discover better executable locators "
        "(for example stable input IDs, scoped selectors, or the real modal submit element), call "
        "log_interaction_contract again for that same surface with the corrected fields/actions and "
        "validated_locators. Corrected locator evidence must be in the structured contract, not only in "
        "a log_action note.",
        "When inspecting pre-action state needed later, call log_baseline_observation with structured "
        "facts such as the selected target record and original field values. Baseline observations are "
        "setup evidence only; they must not be used as final success proof. "
        "After verifying the requested success criteria, call log_success_observation with the exact "
        "proof you used. Include the surface_type, assertion, target value/source when applicable, "
        "and executable locator candidates that were validated live. Prefer scoped or exact locators "
        "over broad text matches, especially when the same text appears in multiple fields. "
        "For repeated records such as table rows, list items, cards, detail panels, API objects, "
        "CLI rows, or message payloads, record observation_kind='record', a scope_locator for the "
        "record/container, and assertions for each important field. If duplicate visible values "
        "appear within the same record, use structural locators inside the scope, not another "
        "text/name lookup.",
        "When creating new records, generate unique values (timestamp/nonce suffix) and log the exact values used, "
        "so retries and generated tests avoid duplicate collisions.",
        "When you observe a confirmation or status message, record its exact text "
        "(preserving capitalisation) in your log_action note. "
        "After clicking any button that triggers an action (login, booking, payment, cancellation), "
        "check the browser console for messages prefixed with [dialog:alert] — "
        "these are JavaScript alerts captured without blocking the page. "
        "Important: console messages are cumulative. A [dialog:alert] message visible after a click "
        "may have been logged at page load, not as a response to your click. "
        "Only treat a [dialog:alert] as a response to your action if it appears AFTER the action completes. "
        "Always also check the DOM state (visible text, status fields) to confirm the actual outcome.",
    ]
    if msa_spec_path:
        sections.append(
            f"Before filling any form that requires account credentials or test data, "
            f"you must call read_spec_file('{msa_spec_path}') first to retrieve the correct "
            f"inputs from the MSA specification. Do not attempt to guess or infer credentials "
            f"from the live UI. This applies to login forms, registration forms, payment fields, "
            f"or any other form requiring specific test data. "
            f"After calling read_spec_file, call log_action to record the credentials and entry "
            f"point URLs you found, so they are available during test generation."
        )
    return "\n\n".join(sections)


def build_test_generation_prompt(
    journey: str,
    filename: str,
    max_retries: int,
    msa_spec: str,
    capture: JourneyCapture,
    browse_network_requests: list[dict[str, str]],
    base_url: str,
    msa_spec_path: str = "",
    journey_contract: JourneyContract | None = None,
    *,
    system_description: str = "",
    use_case_context: str = "",
) -> str:
    observed_requests = [
        f"{str(item.get('method', '')).upper():<5} {str(item.get('path', ''))}"
        for item in browse_network_requests
        if str(item.get("method", "")).strip() and str(item.get("path", "")).strip()
    ]
    observed_requests_block = (
        "\n".join(observed_requests)
        if observed_requests
        else "No backend API requests were captured during exploration."
    )

    execution_brief = build_execution_brief(
        journey=journey,
        msa_spec=msa_spec,
        system_description=system_description,
        use_case_context=use_case_context,
    )
    sections = [
        "Using the execution brief, your logged actions, and your recorded timings below, "
        "write a pytest-playwright test that reproduces the intended successful journey steps exactly "
        "(exclude exploratory detours and failed intermediate attempts). "
        "Derive every assertion from the use case success criteria. "
        "Never assert states observed incidentally during browsing that are not part of the success criteria. "
        "For tests involving delete, update, or similar operations on existing data, "
        "do not hardcode a specific entity name or ID observed during browsing. "
        "Select the first available entity matching the preconditions dynamically at runtime, "
        "capture that target identifier from the chosen row, and use that same identifier for "
        "all post-action checks (network assertion and refreshed-list verification). "
        "Do not switch target rows mid-test. "
        "If a stable destructive target cannot be identified safely, prefer creating a disposable "
        "entity first and deleting that exact entity, or fail fast with a clear precondition assertion. "
        "Use `import os` and define `BASE_URL = os.environ.get(\"BASE_URL\", "
        f"\"{base_url}\")` once near the top of the file. "
        "Always navigate with `page.goto(BASE_URL, ...)` instead of hardcoding the URL.",
        "For create/register flows, generate unique values at runtime (for example time.time_ns() or "
        "a UUID suffix) and reuse those variables for assertions. Avoid hardcoded static "
        "usernames/emails/document numbers that could collide across runs.",
        "Use the observed backend requests to add focused network-aware checks where appropriate. "
        "Prefer `page.expect_request()` or `page.expect_response()` for critical booking and order operations, "
        "and wrap them around the exact action that triggers the request. "
        "You are strictly forbidden from writing custom JavaScript (fetch, XMLHttpRequest, etc.) "
        "to synthesize API requests or bypass the UI. Let the frontend application handle all network communication.",
        "For date fields in booking/search forms, interact through the UI control format (often locale-formatted) and "
        "commit the value with blur/Tab before clicking Search. Do not force backend timestamp text into the input field. "
        "When possible, assert the outbound search request payload contains the expected route/date semantics from the use case.",
        f"Execution brief:\n{execution_brief}",
        "Minimal replay plan derived from browsing:\n"
        f"{_render_replay_plan(capture, journey_contract)}",
        "Exploratory browse actions are archived in the journey guide. Use this replay plan "
        "and the structured journey contract as the default source of truth; consult full "
        "logs only when the replay plan is incomplete.",
        "Use baseline_observations only to choose targets, remember original values, compute changed "
        "values, and compare preserved fields after the action. Never treat baseline observations as "
        "final success assertions. For final assertions, prefer structured success_observations from the contract. "
        "They are the exact evidence verified during browsing. Preserve their scoping and "
        "exactness instead of replacing them with broad page-level text matches. If a success "
        "observation has a scope_locator and field assertions, emit the scope first and then "
        "emit each scoped assertion exactly; do not rewrite structural assertions into text "
        "or accessible-name locators.",
        f"Recorded timings:\n{capture.timing_summary()}",
        "Backend requests observed during exploration:\n"
        f"{observed_requests_block}",
        "Structured journey contract:\n"
        f"{_render_journey_contract_for_prompt(journey_contract)}",
        f"Save it as '{filename}' using create_python_test_file, then run it with run_test_file. "
        f"If it fails, fix and retry at most {max_retries} times.",
        "Locator strategy reminder: use get_by_role over get_by_text for interactive elements. "
        "Strict mode will fail if a locator matches more than one element. "
        "For every locator you write, ask: 'is this word unique on the page?' "
        "For form inputs, never use the field's current value as its locator — "
        "JS-filled values are invisible to CSS attribute selectors. "
        "Prefer id-based locators (#id), positional locators (locator('input').nth(N)), "
        "or get_by_placeholder() only when the placeholder attribute is set in the HTML source. "
        "If you see a pre-filled form during browsing, locate its fields by structure, not by content.",
        "Login submission: always click the actual login form submit control by role "
        "(button or input[type=submit]) scoped to the login form. Do not use get_by_text fallbacks "
        "or body clicks for login.",
        "If the browse logs include element ids for modal fields, prefer id-based locators over role/label "
        "lookups inside the modal. Only use role/label when ids are missing. Always scope modal "
        "field locators to the anchored modal container (for example modal.locator('#add_user_name')).",
        "Locator policy: use validated executable locator candidates first, scoped to their captured "
        "container. If none are validated, use stable executable CSS/test-id candidates, then scoped "
        "role/label candidates, then text candidates. Use positional locators only inside a validated "
        "container. Ignore non-executable snapshot locators such as browser refs, generic[ref=...], "
        "textbox[aria-label=...], combobox[aria-label=...], or button/text=....",
        "If the browse logs include the modal submit control tag/id/class/data attributes, "
        "use that exact selector within the modal. Do not assume the confirm control has a button role; "
        "if it is a span/div, locate it by tag/class/text and click it.",
        "Never use coordinate-based interactions in generated tests (for example page.mouse.click(x, y)); "
        "click explicit locators scoped to the correct container instead.",
        "For any form field that showed autocomplete behaviour during browsing (a dropdown appeared after typing), "
        "use `locator.press_sequentially(value)` instead of `locator.fill(value)` in the generated test. "
        "`fill()` sets the value silently without triggering JavaScript input events, so autocomplete never fires "
        "and the UI submits an unrecognised value — causing empty search results or silent form failures. "
        "After `press_sequentially()`, wait for the dropdown option to appear and click it before continuing: "
        "`page.get_by_role('option', name=value).first.click()` or the equivalent visible suggestion locator.",
        "If the browse logs include select option values, prefer `select_option(value=...)` over labels. "
        "Use label-based selection only when the label is confirmed visible in the control.",
        "For all text content assertions use re.compile('...', re.IGNORECASE) "
        "rather than a plain string — never rely on remembered capitalisation.",
        """
        Modal-scoping helper: when a modal/dialog/overlay is involved, always locate a reliable
        modal anchor (unique heading text or distinctive phrase) and scope subsequent actions
        to that container using Playwright locators. Example:

        modal = page.locator(":has-text('<modal anchor>')").last
        modal.wait_for(state="visible")
        modal.locator("#add_user_name").fill(value)
        modal.locator("[data-am-modal-confirm]").click()
        modal.wait_for(state="hidden")

        This keeps locators unambiguous across UI frameworks and avoids background clicks.
        """,
        "When a modal is open, never use page-level locators for its buttons or fields. "
        "Always use modal-scoped locators anchored to modal text captured during browsing.",
        "For repeated-record success assertions, use the contract's scope locator and field "
        "assertions directly. If two fields can contain the same visible value, assert by "
        "stable child selector or position within the already-matched scope, such as "
        "`row.locator('td').nth(index).to_have_text(value)`, rather than "
        "`row.get_by_role('cell', name=value)`.",
        "Repair rule: use the failure_diagnosis first. If it says the test was blocked before the "
        "required service call, repair that first failing locator/action instead of chasing the "
        "missing network call. Only repair the service trigger when the diagnosis shows the flow "
        "reached the trigger action without emitting the required side effect.",
    ]
    if msa_spec_path:
        sections.append(
            f"If you need credentials or any other specification details not already "
            f"present above, call read_spec_file('{msa_spec_path}')."
        )
    return "\n\n".join(sections)


def _render_replay_plan(
    capture: JourneyCapture,
    contract: JourneyContract | None,
) -> str:
    if contract is None:
        return capture.action_summary()

    lines: list[str] = []
    if not contract.interaction_contracts:
        lines.append(capture.action_summary() if capture is not None else "No interaction surfaces recorded.")
    for index, interaction in enumerate(contract.interaction_contracts, start=1):
        container = interaction.container
        surface = interaction.surface_type
        anchor = container.anchor_text or container.selector or container.url or "unanchored"
        lines.append(f"{index}. Surface {surface}: {anchor}")
        for field in interaction.fields:
            name = field.semantic_name or field.label or field.name or "field"
            locator = _best_locator_for_prompt(field.validated_locators, field.selector)
            value_strategy = f"; value_strategy={field.value_strategy}" if field.value_strategy else ""
            lines.append(f"   - fill/select {name}: {locator or 'no executable locator'}{value_strategy}")
            if field.options:
                options = ", ".join(
                    f"{option.get('label', '')}={option.get('value', '')}"
                    for option in field.options
                )
                lines.append(f"     options: {options}")
        for action in interaction.actions:
            name = action.semantic_name or action.label or action.text or "action"
            locator = _best_action_locator_for_prompt(action)
            suffix = f"; opens={action.opens_surface}" if action.opens_surface else ""
            lines.append(f"   - action {name}: {locator or 'no executable locator'}{suffix}")
            for effect in [*action.side_effects, *action.expected_service_calls]:
                status = f" status={effect.status_code}" if effect.status_code else ""
                purpose = f" purpose={effect.purpose}" if effect.purpose else ""
                lines.append(
                    f"     expects {effect.method} {effect.path}{status}{purpose}"
                )
    if contract.baseline_observations:
        lines.append("Baseline observations for setup/original values:")
        for observation in contract.baseline_observations:
            locator = _best_locator_for_prompt(
                observation.validated_locators,
                observation.locator,
            )
            scope_locator = _best_locator_for_prompt(
                observation.scope_validated_locators,
                observation.scope_locator,
            )
            target = (
                f"; target={observation.target_value}"
                if observation.target_value
                else ""
            )
            lines.append(
                f"- {observation.label or observation.assertion}: "
                f"{observation.assertion}; kind={observation.observation_kind or 'observation'}; "
                f"{locator or 'no executable locator'}{target}"
            )
            if scope_locator:
                lines.append(f"  baseline scope: {scope_locator}")
            for assertion in observation.assertions:
                assertion_locator = _best_locator_for_prompt(
                    assertion.validated_locators,
                    assertion.locator,
                )
                expected = (
                    f"; value={assertion.expected_value}"
                    if assertion.expected_value
                    else ""
                )
                source = (
                    f"; value_source={assertion.expected_value_source}"
                    if assertion.expected_value_source
                    else ""
                )
                lines.append(
                    f"  remember {assertion.field_name or 'field'}: "
                    f"{assertion.assertion}; {assertion_locator or 'no executable locator'}"
                    f"{expected}{source}"
                )
    if contract.success_observations:
        lines.append("Success observations:")
        for observation in contract.success_observations:
            locator = _best_locator_for_prompt(
                observation.validated_locators,
                observation.locator,
            )
            scope_locator = _best_locator_for_prompt(
                observation.scope_validated_locators,
                observation.scope_locator,
            )
            target = (
                f"; target={observation.target_value}"
                if observation.target_value
                else ""
            )
            source = (
                f"; source={observation.target_value_source}"
                if observation.target_value_source
                else ""
            )
            lines.append(
                f"- {observation.label or observation.assertion}: "
                f"{observation.assertion}; kind={observation.observation_kind or 'observation'}; "
                f"{locator or 'no executable locator'}"
                f"{target}{source}"
            )
            if observation.refresh_strategy:
                refresh = ", ".join(
                    f"{key}={value}"
                    for key, value in observation.refresh_strategy.items()
                )
                lines.append(f"  refresh before assertion: {refresh}")
            if scope_locator:
                lines.append(f"  scope: {scope_locator}")
            for assertion in observation.assertions:
                assertion_locator = _best_locator_for_prompt(
                    assertion.validated_locators,
                    assertion.locator,
                )
                expected = (
                    f"; expected={assertion.expected_value}"
                    if assertion.expected_value
                    else ""
                )
                source = (
                    f"; expected_source={assertion.expected_value_source}"
                    if assertion.expected_value_source
                    else ""
                )
                lines.append(
                    f"  assert {assertion.field_name or 'field'}: "
                    f"{assertion.assertion}; {assertion_locator or 'no executable locator'}"
                    f"{expected}{source}"
                )
    if contract.success_checks:
        lines.append("Success checks:")
        lines.extend(f"- {check}" for check in contract.success_checks)
    return "\n".join(lines)


def _best_locator_for_prompt(locators: list, selector: str = "") -> str:
    executable_locators = [
        locator for locator in locators if getattr(locator, "executable", False)
    ]
    if executable_locators:
        locator = sorted(
            executable_locators,
            key=lambda item: (
                getattr(item, "validated", False),
                getattr(item, "strategy", "") in {"css", "test_id"},
                getattr(item, "strategy", "") in {"role", "label"},
            ),
            reverse=True,
        )[0]
        scope = f" scoped to {locator.scope}" if locator.scope else ""
        state = "validated" if locator.validated else "candidate"
        return f"{state} {locator.strategy}={locator.value}{scope}"
    return selector


def _best_action_locator_for_prompt(action) -> str:
    locators = [
        locator
        for locator in getattr(action, "validated_locators", [])
        if not _locator_conflicts_with_action_tag(locator, getattr(action, "tag", ""))
    ]
    selector = getattr(action, "selector", "")
    if _selector_conflicts_with_tag(selector, getattr(action, "tag", "")):
        selector = ""
    return _best_locator_for_prompt(locators, selector)


def _locator_conflicts_with_action_tag(locator, action_tag: str) -> bool:
    return (
        getattr(locator, "strategy", "") == "css"
        and _selector_conflicts_with_tag(getattr(locator, "value", ""), action_tag)
    )


def _selector_conflicts_with_tag(selector: str, tag: str) -> bool:
    selector_tag = _single_target_selector_tag(selector)
    expected_tag = str(tag).strip().lower()
    return bool(selector_tag and expected_tag and selector_tag != expected_tag)


def _single_target_selector_tag(selector: str) -> str:
    cleaned = str(selector).strip()
    if "," in cleaned or re.search(r"\s|[>+~]", cleaned):
        return ""
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*)", cleaned)
    return match.group(1).lower() if match else ""


def _render_journey_contract_for_prompt(
    contract: JourneyContract | None,
) -> str:
    if contract is None:
        return "No structured journey contract was available."

    lines = [
        f"interaction_surface: {contract.interaction_surface}",
        "service_interfaces: "
        + (", ".join(contract.service_interfaces) if contract.service_interfaces else "none observed"),
        f"state_changing: {contract.state_changing}",
        f"complete: {contract.complete}",
    ]
    if contract.completeness_issues:
        lines.append("completeness_issues:")
        lines.extend(f"- {issue}" for issue in contract.completeness_issues)
    if contract.expected_service_calls:
        lines.append("expected_service_calls:")
        for call in contract.expected_service_calls:
            required = "required" if call.required else "observed"
            purpose = f"; purpose={call.purpose}" if call.purpose else ""
            trigger = f"; trigger={call.trigger_action}" if call.trigger_action else ""
            selector = (
                f"; selector_hint={call.trigger_selector_hint}"
                if call.trigger_selector_hint
                else ""
            )
            status = f"; status={call.status_code}" if call.status_code else ""
            lines.append(
                f"- {call.method} {call.path} ({required}{status}{purpose}{trigger}{selector})"
            )
    if contract.interaction_contracts:
        lines.append("interaction_contracts:")
        for index, interaction in enumerate(contract.interaction_contracts, start=1):
            container = interaction.container
            container_bits = [
                f"kind={container.kind or 'unknown'}",
                f"selector={container.selector}" if container.selector else "",
                f"anchor={container.anchor_text}" if container.anchor_text else "",
                f"role={container.role}" if container.role else "",
            ]
            lines.append(
                f"- interaction {index}: surface={interaction.surface_type}; "
                + "; ".join(bit for bit in container_bits if bit)
            )
            for field in interaction.fields:
                field_bits = [
                    f"name={field.semantic_name or field.name or field.label}",
                    f"label={field.label}" if field.label else "",
                    f"selector={field.selector}" if field.selector else "",
                    f"id={field.element_id}" if field.element_id else "",
                    f"tag={field.tag}" if field.tag else "",
                    f"type={field.input_type}" if field.input_type else "",
                    f"role={field.role}" if field.role else "",
                    f"visible={field.visible}",
                    f"editable={field.editable}",
                    f"value_strategy={field.value_strategy}" if field.value_strategy else "",
                ]
                lines.append("  field: " + "; ".join(bit for bit in field_bits if bit))
                for locator in field.validated_locators:
                    state = "validated" if locator.validated else "candidate"
                    executable = "executable" if locator.executable else "non-executable"
                    scope = f"; scope={locator.scope}" if locator.scope else ""
                    lines.append(
                        f"    locator: {state}; {executable}; "
                        f"{locator.strategy}={locator.value}{scope}"
                    )
                if field.options:
                    options = ", ".join(
                        f"{option.get('label', '')}={option.get('value', '')}"
                        for option in field.options
                    )
                    lines.append(f"    options: {options}")
            for action in interaction.actions:
                action_bits = [
                    f"name={action.semantic_name or action.label or action.text}",
                    f"label={action.label}" if action.label else "",
                    f"text={action.text}" if action.text else "",
                    f"selector={action.selector}" if action.selector else "",
                    "selector_tag_mismatch=True"
                    if _selector_conflicts_with_tag(action.selector, action.tag)
                    else "",
                    f"id={action.element_id}" if action.element_id else "",
                    f"tag={action.tag}" if action.tag else "",
                    f"role={action.role or 'none'}",
                    f"opens_surface={action.opens_surface}" if action.opens_surface else "",
                    f"observed_at_step={action.observed_at_step}"
                    if action.observed_at_step is not None
                    else "",
                ]
                lines.append("  action: " + "; ".join(bit for bit in action_bits if bit))
                for locator in action.validated_locators:
                    state = "validated" if locator.validated else "candidate"
                    executable = "executable" if locator.executable else "non-executable"
                    scope = f"; scope={locator.scope}" if locator.scope else ""
                    lines.append(
                        f"    locator: {state}; {executable}; "
                        f"{locator.strategy}={locator.value}{scope}"
                    )
                for effect in [*action.side_effects, *action.expected_service_calls]:
                    lines.append(
                        f"    triggers: {effect.method} {effect.path}"
                        f" status={effect.status_code or '?'}"
                        f" interface={effect.interface}"
                        f" purpose={effect.purpose or 'unspecified'}"
                    )
    if contract.baseline_observations:
        lines.append("baseline_observations:")
        for observation in contract.baseline_observations:
            lines.extend(_render_observation_for_prompt(observation, indent=""))
    if contract.success_observations:
        lines.append("success_observations:")
        for observation in contract.success_observations:
            lines.extend(_render_observation_for_prompt(observation, indent=""))
    if contract.success_checks:
        lines.append("success_checks:")
        lines.extend(f"- {check}" for check in contract.success_checks)
    return "\n".join(lines)


def _render_observation_for_prompt(observation, *, indent: str) -> list[str]:
    lines: list[str] = []
    prefix = indent
    label = observation.label or observation.assertion or "observation"
    bits = [
        f"label={label}",
        f"surface={observation.surface_type}" if observation.surface_type else "",
        f"kind={observation.observation_kind}" if observation.observation_kind else "",
        f"assertion={observation.assertion}",
        f"scope={observation.scope_locator}" if observation.scope_locator else "",
        f"target={observation.target_value}" if observation.target_value else "",
        f"target_source={observation.target_value_source}"
        if observation.target_value_source
        else "",
        f"reason={observation.reason}" if observation.reason else "",
    ]
    lines.append(prefix + "- " + "; ".join(bit for bit in bits if bit))
    for locator in observation.validated_locators:
        state = "validated" if locator.validated else "candidate"
        executable = "executable" if locator.executable else "non-executable"
        scope = f"; scope={locator.scope}" if locator.scope else ""
        lines.append(
            f"{prefix}  locator: {state}; {executable}; "
            f"{locator.strategy}={locator.value}{scope}"
        )
    for locator in observation.scope_validated_locators:
        state = "validated" if locator.validated else "candidate"
        executable = "executable" if locator.executable else "non-executable"
        scope = f"; scope={locator.scope}" if locator.scope else ""
        lines.append(
            f"{prefix}  scope_locator: {state}; {executable}; "
            f"{locator.strategy}={locator.value}{scope}"
        )
    if observation.refresh_strategy:
        refresh = ", ".join(
            f"{key}={value}"
            for key, value in observation.refresh_strategy.items()
        )
        lines.append(f"{prefix}  refresh_strategy: {refresh}")
    for assertion in observation.assertions:
        assertion_bits = [
            f"field={assertion.field_name}" if assertion.field_name else "",
            f"assertion={assertion.assertion}",
            f"locator={assertion.locator}" if assertion.locator else "",
            f"expected={assertion.expected_value}" if assertion.expected_value else "",
            f"expected_source={assertion.expected_value_source}"
            if assertion.expected_value_source
            else "",
            f"reason={assertion.reason}" if assertion.reason else "",
        ]
        lines.append(prefix + "  assertion: " + "; ".join(bit for bit in assertion_bits if bit))
        for locator in assertion.validated_locators:
            state = "validated" if locator.validated else "candidate"
            executable = "executable" if locator.executable else "non-executable"
            scope = f"; scope={locator.scope}" if locator.scope else ""
            lines.append(
                f"{prefix}    locator: {state}; {executable}; "
                f"{locator.strategy}={locator.value}{scope}"
            )
    return lines


def validate_python_test_filename(filename: str) -> None:
    if not filename.endswith(".py"):
        raise ValueError(
            f"Generated test filename must end with '.py': {filename}"
        )
