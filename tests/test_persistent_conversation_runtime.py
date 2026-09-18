from pathlib import Path

from ally.models import ChatRequest, ChatResponse
from ally.runtime import PersistentConversationRuntime
from ally.storage.sqlite import SQLiteConversationStore, SQLiteDatabase


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    @property
    def name(self) -> str:
        return "recording"

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            content=f"answer-{len(self.requests)}",
            model="synthetic",
            provider=self.name,
        )


def test_runtime_reloads_history_and_persists_successful_exchanges(
    tmp_path: Path,
) -> None:
    store = SQLiteConversationStore(SQLiteDatabase(tmp_path / "ally.sqlite3"))
    conversation = store.create()
    provider = RecordingProvider()
    runtime = PersistentConversationRuntime(provider, store, conversation.id)

    first = runtime.respond("first")
    second = runtime.respond("second")

    assert first.content == "answer-1"
    assert second.content == "answer-2"
    assert provider.requests[1].messages[-3].content == "first"
    assert provider.requests[1].messages[-2].content == "answer-1"
    assert provider.requests[1].messages[-1].content == "second"

    persisted = store.list_messages(conversation.id)
    assert [message.content for message in persisted] == [
        "first",
        "answer-1",
        "second",
        "answer-2",
    ]
