import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

TEST_RESULTS_DIR = Path("test-results")


@pytest.fixture(autouse=True)
def capture_frontend_api_calls(page, request):
    requests: list[dict[str, str]] = []

    def on_request(playwright_request) -> None:
        parsed = urlparse(playwright_request.url)
        if "/api/" not in parsed.path:
            return
        requests.append(
            {
                "method": playwright_request.method.upper(),
                "url": playwright_request.url,
                "path": parsed.path,
            }
        )

    page.context.on("request", on_request)
    yield

    TEST_RESULTS_DIR.mkdir(exist_ok=True)
    test_path = Path(str(getattr(request.node, "path", request.node.fspath)))
    network_path = TEST_RESULTS_DIR / f"{test_path.stem}.network.json"
    network_path.write_text(
        json.dumps(
            {
                "filename": test_path.name,
                "requests": requests,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
