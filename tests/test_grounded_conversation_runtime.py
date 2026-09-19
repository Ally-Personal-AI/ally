from ally.context import ContextBlock
from ally.models import ChatRequest, ChatResponse
from ally.runtime.grounded_conversation import GroundedConversationRuntime


class RecordingProvider:
    def __init__(self) -> None:
        self.request: ChatRequest | None = None

    @property
    def name(self) -> str:
        return "recording"

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.request = request
        return ChatResponse(
            content="answer",
            model="synthetic",
            provider=self.name,
        )


class ContextStub:
    def retrieve(self, query: str) -> tuple[ContextBlock, ...]:
        return (
            ContextBlock(
                source="memory:synthetic",
                content="Relevant synthetic context.",
            ),
        )


def test_grounded_runtime_places_context_before_user_message() -> None:
    provider = RecordingProvider()
    runtime = GroundedConversationRuntime(
        provider,
        ContextStub(),
        system_prompt="base system",
    )

    response = runtime.respond("question")

    assert response.content == "answer"
    assert provider.request is not None
    assert provider.request.messages[0].content == "base system"
    assert "REFERENCE CONTEXT" in provider.request.messages[1].content
    assert provider.request.messages[-1].role == "user"
    assert provider.request.messages[-1].content == "question"
