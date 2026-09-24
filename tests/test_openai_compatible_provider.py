import httpx
import pytest

from ally.models import ChatMessage, ChatRequest
from ally.models.errors import ProviderConnectionError, ProviderResponseError
from ally.models.providers import (
    OpenAICompatibleProvider,
    OpenAICompatiblePublicProvider,
)


def test_provider_posts_to_versioned_chat_completions_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/chat/completions"
        assert b'"model":"test-model"' in request.content
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"message": {"content": "hello"}}],
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:8080/v1",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )
    try:
        response = provider.chat(
            ChatRequest(messages=(ChatMessage(role="user", content="hi"),))
        )
    finally:
        provider.close()

    assert response.content == "hello"
    assert response.model == "test-model"
    assert response.provider == "openai-compatible"


def test_private_provider_rejects_remote_endpoint_without_override() -> None:
    with pytest.raises(ValueError, match="loopback-only"):
        OpenAICompatibleProvider(
            base_url="https://example.com/v1",
            model="test-model",
        )


def test_public_provider_requires_explicit_remote_public_opt_in() -> None:
    with pytest.raises(ValueError, match="allow_remote_public"):
        OpenAICompatiblePublicProvider(
            base_url="https://example.com/v1",
            model="test-model",
        )


def test_public_provider_can_explicitly_use_remote_for_public_data() -> None:
    provider = OpenAICompatiblePublicProvider(
        base_url="https://example.com/v1",
        model="test-model",
        allow_remote_public=True,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "model": "test-model",
                    "choices": [{"message": {"content": "ok"}}],
                },
            )
        ),
    )
    provider.close()


def test_provider_normalizes_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    provider = OpenAICompatibleProvider(
        base_url="http://localhost:8080/v1",
        model="test-model",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ProviderConnectionError, match="Could not reach"):
            provider.chat(
                ChatRequest(messages=(ChatMessage(role="user", content="hi"),))
            )
    finally:
        provider.close()


def test_provider_rejects_empty_choices() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://localhost:8080/v1",
        model="test-model",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": []})
        ),
    )
    try:
        with pytest.raises(ProviderResponseError, match="no choices"):
            provider.chat(
                ChatRequest(messages=(ChatMessage(role="user", content="hi"),))
            )
    finally:
        provider.close()
