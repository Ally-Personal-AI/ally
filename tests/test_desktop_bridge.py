from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from io import StringIO
from pathlib import Path

from ally.application import AllyApplication
from ally.desktop.bridge import MAX_REQUEST_BYTES, handle_request_json, serve
from ally.models import ChatRequest, ChatResponse, ModelProvider
from ally.runtime_profiles import InferenceTargetError, ResolvedInferenceTarget
from ally.storage.sqlite import (
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
    SQLiteUserInstructionsStore,
)


class CapturingProvider:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.requests: list[ChatRequest] = []

    @property
    def name(self) -> str:
        return "synthetic-desktop"

    def __enter__(self) -> CapturingProvider:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            content=self.responses.pop(0),
            model="synthetic-model",
            provider=self.name,
        )


def _target(
    endpoint: str | None,
    model: str | None,
) -> ResolvedInferenceTarget:
    if endpoint is not None or model is not None:
        raise AssertionError("desktop bridge must not request development inference")
    return ResolvedInferenceTarget(
        source="validated_profile",
        endpoint="http://127.0.0.1:8080/v1",
        model="synthetic-model",
        profile_id="a" * 64,
        runtime_name="synthetic-runtime",
        runtime_version="1",
    )


def _application(
    tmp_path: Path,
    *,
    provider: CapturingProvider,
    resolver: Callable[
        [str | None, str | None],
        ResolvedInferenceTarget,
    ] = _target,
) -> AllyApplication:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")

    def provider_factory(
        target: ResolvedInferenceTarget,
    ) -> AbstractContextManager[ModelProvider]:
        assert target.model == "synthetic-model"
        return provider

    return AllyApplication(
        conversations=SQLiteConversationStore(database),
        memories=SQLiteMemoryStore(database),
        knowledge=SQLiteKnowledgeStore(database),
        instructions=SQLiteUserInstructionsStore(database),
        target_resolver=resolver,
        provider_factory=provider_factory,
    )


def _request(method: str, params: dict[str, object] | None = None) -> str:
    return json.dumps(
        {
            "id": "synthetic-request",
            "method": method,
            "params": params or {},
        }
    )


def test_bridge_bootstrap_is_read_only_and_serializable(tmp_path: Path) -> None:
    provider = CapturingProvider([])
    app = _application(tmp_path, provider=provider)

    response = handle_request_json(app, _request("bootstrap"))

    assert response.ok
    assert response.error is None
    assert isinstance(response.result, dict)
    runtime = response.result["runtime"]
    assert isinstance(runtime, dict)
    assert runtime["state"] == "ready"
    assert provider.requests == []


def test_bridge_conversation_round_trip_uses_application_facade(tmp_path: Path) -> None:
    provider = CapturingProvider(["SYNTHETIC_REPLY"])
    app = _application(tmp_path, provider=provider)

    created = handle_request_json(app, _request("conversation.create"))
    assert created.ok
    assert isinstance(created.result, dict)
    conversation_id = created.result["id"]
    assert isinstance(conversation_id, str)

    sent = handle_request_json(
        app,
        _request(
            "conversation.send",
            {
                "conversation_id": conversation_id,
                "message": "Synthetic local-only message.",
            },
        ),
    )
    assert sent.ok
    assert isinstance(sent.result, dict)
    response = sent.result["response"]
    assert isinstance(response, dict)
    assert response["content"] == "SYNTHETIC_REPLY"
    assert len(provider.requests) == 1

    loaded = handle_request_json(
        app,
        _request("conversation.get", {"conversation_id": conversation_id}),
    )
    assert loaded.ok
    assert isinstance(loaded.result, dict)
    messages = loaded.result["messages"]
    assert isinstance(messages, list)
    assert [message["role"] for message in messages if isinstance(message, dict)] == [
        "user",
        "assistant",
    ]


def test_bridge_rejects_raw_runtime_coordinates(tmp_path: Path) -> None:
    provider = CapturingProvider([])
    app = _application(tmp_path, provider=provider)
    created = app.create_conversation(title="Synthetic")

    response = handle_request_json(
        app,
        _request(
            "conversation.send",
            {
                "conversation_id": str(created.id),
                "message": "Synthetic private message.",
                "development_endpoint": "http://127.0.0.1:9999/v1",
                "development_model": "unvalidated-model",
            },
        ),
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "invalid_request"
    assert provider.requests == []


def test_bridge_sanitizes_inference_selection_failures(tmp_path: Path) -> None:
    provider = CapturingProvider([])

    def unavailable(
        endpoint: str | None,
        model: str | None,
    ) -> ResolvedInferenceTarget:
        raise InferenceTargetError("PRIVATE-PATH-AND-RUNTIME-DETAIL")

    app = _application(tmp_path, provider=provider, resolver=unavailable)
    created = app.create_conversation(title="Synthetic")

    response = handle_request_json(
        app,
        _request(
            "conversation.send",
            {
                "conversation_id": str(created.id),
                "message": "Synthetic private message.",
            },
        ),
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "inference_unavailable"
    rendered = response.model_dump_json()
    assert "PRIVATE-PATH" not in rendered
    assert "Synthetic private message" not in rendered


def test_bridge_bounds_stdio_requests_without_echoing_payload(tmp_path: Path) -> None:
    provider = CapturingProvider([])
    app = _application(tmp_path, provider=provider)
    input_stream = StringIO("X" * (MAX_REQUEST_BYTES + 10) + "\n")
    output_stream = StringIO()

    exit_code = serve(
        app,
        input_stream=input_stream,
        output_stream=output_stream,
        once=True,
    )

    assert exit_code == 2
    response = output_stream.getvalue()
    assert "request_too_large" in response
    assert "XXXXX" not in response
