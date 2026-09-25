from __future__ import annotations

import json
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import ClassVar
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr

from ally.egress.adapters import (
    BRAVE_SEARCH_SECRET_REF,
    BraveSearchAdapter,
    BraveSearchResponseError,
)
from ally.research import WEB_SEARCH_OPERATION
from ally.secrets import InMemorySecretStore


class SearchHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list[dict[str, object]]] = []
    status_code = 200
    response_payload: object = {
        "web": {
            "results": [
                {
                    "title": "Synthetic public result",
                    "url": "https://example.test/public",
                    "description": "Synthetic snippet",
                }
            ]
        },
        "query": {"more_results_available": True},
    }

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        self.__class__.requests.append(
            {
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "token": self.headers.get("X-Subscription-Token"),
            }
        )
        body = json.dumps(self.__class__.response_payload).encode("utf-8")
        self.send_response(self.__class__.status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def search_server() -> Generator[tuple[str, type[SearchHandler]], None, None]:
    SearchHandler.requests = []
    SearchHandler.status_code = 200
    SearchHandler.response_payload = {
        "web": {
            "results": [
                {
                    "title": "Synthetic public result",
                    "url": "https://example.test/public",
                    "description": "Synthetic snippet",
                }
            ]
        },
        "query": {"more_results_available": True},
    }
    server = HTTPServer(("127.0.0.1", 0), SearchHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/res/v1/web/search"
    try:
        yield endpoint, SearchHandler
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _store() -> InMemorySecretStore:
    store = InMemorySecretStore()
    store.set(BRAVE_SEARCH_SECRET_REF, SecretStr("synthetic-token"))
    return store


def test_brave_adapter_uses_keychain_boundary_and_ignores_proxy_environment(
    search_server: tuple[str, type[SearchHandler]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint, handler = search_server
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")

    store = _store()
    adapter = BraveSearchAdapter(
        secret_store_factory=lambda: store,
        endpoint=endpoint,
    )

    output = adapter.send(
        WEB_SEARCH_OPERATION,
        {"query": "synthetic public topic", "count": 4},
    )

    assert handler.requests == [
        {
            "path": "/res/v1/web/search",
            "query": {"q": ["synthetic public topic"], "count": ["4"]},
            "token": "synthetic-token",
        }
    ]
    assert isinstance(output, dict)
    results = output["results"]
    assert isinstance(results, list)
    assert results
    first = results[0]
    assert isinstance(first, dict)
    assert first["title"] == "Synthetic public result"
    assert output["more_results_available"] is True


def test_brave_adapter_does_not_expose_remote_error_body(
    search_server: tuple[str, type[SearchHandler]],
) -> None:
    endpoint, handler = search_server
    handler.status_code = 500
    marker = "REMOTE-SENSITIVE-ERROR-MARKER"
    handler.response_payload = {"error": marker}
    store = _store()
    adapter = BraveSearchAdapter(
        secret_store_factory=lambda: store,
        endpoint=endpoint,
    )

    with pytest.raises(BraveSearchResponseError) as captured:
        adapter.send(
            WEB_SEARCH_OPERATION,
            {"query": "synthetic public topic", "count": 1},
        )

    assert marker not in str(captured.value)


def test_brave_adapter_rejects_arbitrary_remote_endpoint_override() -> None:
    store = _store()

    with pytest.raises(ValueError, match="loopback"):
        BraveSearchAdapter(
            secret_store_factory=lambda: store,
            endpoint="https://example.test/search",
        )
