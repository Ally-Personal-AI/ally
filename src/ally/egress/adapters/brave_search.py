"""Brave Search transport behind Ally's controlled-egress boundary."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast
from urllib.parse import urlsplit

import httpx
from pydantic import JsonValue, ValidationError

from ally.egress import EgressFieldSpec, EgressOperationSpec
from ally.research import (
    WEB_SEARCH_OPERATION,
    WebSearchPayload,
    WebSearchRequest,
    WebSearchResult,
)
from ally.secrets import SecretRef, SecretStore, SecretStoreError, resolve_secret
from ally.security.network import is_loopback_http_url

BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
BRAVE_SEARCH_SECRET_REF = "research.brave.api-key"
MAX_BRAVE_RESPONSE_BYTES = 2 * 1024 * 1024

SecretStoreFactory = Callable[[], SecretStore]


class BraveSearchAdapterError(RuntimeError):
    """Safe base error for Brave Search transport failures."""


class BraveSearchCredentialError(BraveSearchAdapterError):
    """Raised when the configured API credential is unavailable."""


class BraveSearchResponseError(BraveSearchAdapterError):
    """Raised when the remote response cannot be safely normalized."""


class BraveSearchAdapter:
    """Send an approved exact query to Brave Search and normalize public results."""

    def __init__(
        self,
        *,
        secret_store_factory: SecretStoreFactory,
        endpoint: str = BRAVE_SEARCH_ENDPOINT,
        timeout_seconds: float = 10.0,
    ) -> None:
        if endpoint != BRAVE_SEARCH_ENDPOINT and not is_loopback_http_url(endpoint):
            raise ValueError(
                "Brave Search endpoint overrides are restricted to loopback testing"
            )
        if timeout_seconds <= 0.0 or timeout_seconds > 60.0:
            raise ValueError("Brave Search timeout must be between 0 and 60 seconds")
        self._secret_store_factory = secret_store_factory
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    @property
    def service(self) -> str:
        return "brave.search"

    @property
    def operations(self) -> tuple[EgressOperationSpec, ...]:
        return (
            EgressOperationSpec(
                operation=WEB_SEARCH_OPERATION,
                fields=(
                    EgressFieldSpec(
                        name="query",
                        classification="explicit_outbound",
                    ),
                    EgressFieldSpec(
                        name="count",
                        classification="public",
                    ),
                ),
            ),
        )

    def send(
        self,
        operation: str,
        payload: dict[str, JsonValue],
    ) -> JsonValue:
        if operation != WEB_SEARCH_OPERATION:
            raise BraveSearchAdapterError("unsupported Brave Search operation")
        try:
            request = WebSearchRequest.model_validate(payload)
        except ValidationError as exc:
            raise BraveSearchAdapterError("invalid Brave Search request") from exc

        token = self._credential()
        raw = self._request(request, token)
        normalized = self._normalize(raw, count=request.count)
        return cast(JsonValue, normalized.model_dump(mode="json"))

    def _credential(self) -> str:
        try:
            store = self._secret_store_factory()
            secret = resolve_secret(SecretRef(name=BRAVE_SEARCH_SECRET_REF), store)
        except (KeyError, SecretStoreError):
            raise BraveSearchCredentialError(
                "Brave Search credential is unavailable"
            ) from None
        value = secret.get_secret_value()
        if not value:
            raise BraveSearchCredentialError(
                "Brave Search credential is unavailable"
            )
        return value

    def _request(self, request: WebSearchRequest, token: str) -> object:
        chunks: list[bytes] = []
        try:
            with httpx.Client(
                trust_env=False,
                timeout=self._timeout_seconds,
                follow_redirects=False,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": token,
                },
            ) as client, client.stream(
                "GET",
                self._endpoint,
                params={
                    "q": request.query,
                    "count": request.count,
                },
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    raise BraveSearchResponseError(
                        "Brave Search returned a non-success status"
                    )
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BRAVE_RESPONSE_BYTES:
                        raise BraveSearchResponseError(
                            "Brave Search response exceeds the size limit"
                        )
                    chunks.append(chunk)
        except BraveSearchResponseError:
            raise
        except httpx.HTTPError:
            raise BraveSearchAdapterError("Brave Search transport failed") from None

        try:
            return json.loads(b"".join(chunks))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BraveSearchResponseError(
                "Brave Search returned malformed JSON"
            ) from None

    @classmethod
    def _normalize(cls, raw: object, *, count: int) -> WebSearchPayload:
        if not isinstance(raw, dict):
            raise BraveSearchResponseError("Brave Search response is not an object")
        response = cast(dict[str, object], raw)
        web = response.get("web")
        if not isinstance(web, dict):
            results_raw: list[object] = []
        else:
            web_object = cast(dict[str, object], web)
            candidate_results = web_object.get("results", [])
            if not isinstance(candidate_results, list):
                raise BraveSearchResponseError(
                    "Brave Search results have an invalid shape"
                )
            results_raw = cast(list[object], candidate_results)

        results: list[WebSearchResult] = []
        for candidate in results_raw[:count]:
            normalized = cls._normalize_result(candidate)
            if normalized is not None:
                results.append(normalized)

        query = response.get("query")
        more_results_available = False
        if isinstance(query, dict):
            query_object = cast(dict[str, object], query)
            more = query_object.get("more_results_available")
            more_results_available = more if isinstance(more, bool) else False

        return WebSearchPayload(
            results=tuple(results),
            more_results_available=more_results_available,
        )

    @staticmethod
    def _normalize_result(raw: object) -> WebSearchResult | None:
        if not isinstance(raw, dict):
            return None
        item = cast(dict[str, object], raw)
        title = _bounded_text(item.get("title"), 500)
        url = _bounded_text(item.get("url"), 4_000)
        description = _bounded_text(item.get("description"), 2_000) or ""
        if title is None or url is None:
            return None
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return WebSearchResult(
            title=title,
            url=url,
            description=description,
        )


def _bounded_text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    if not normalized:
        return None
    return normalized[:limit]
