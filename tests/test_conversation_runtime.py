import pytest

from ally.models import ChatMessage, ChatRequest, ChatResponse
from ally.runtime import ConversationRuntime


class RecordingProvider:
    def __init__(self) -> None:
        self.last_request: ChatRequest | None = None

    @property
    def name(self) -> str:
        return "recording"

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.last_request = request
        return ChatResponse(
            content="answer",
            model="synthetic",
            provider=self.name,
        )


def test_runtime_builds_system_history_and_user_messages() -> None:
    provider = RecordingProvider()
    runtime = ConversationRuntime(provider, system_prompt="system")

    response = runtime.respond(
        "new question",
        history=(
            ChatMessage(role="user", content="old question"),
            ChatMessage(role="assistant", content="old answer"),
        ),
    )

    assert response.content == "answer"
    assert provider.last_request is not None
    assert provider.last_request.messages == (
        ChatMessage(role="system", content="system"),
        ChatMessage(role="user", content="old question"),
        ChatMessage(role="assistant", content="old answer"),
        ChatMessage(role="user", content="new question"),
    )


def test_runtime_rejects_empty_user_input() -> None:
    runtime = ConversationRuntime(RecordingProvider())

    with pytest.raises(ValueError, match="cannot be empty"):
        runtime.respond("   ")
