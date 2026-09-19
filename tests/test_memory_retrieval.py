from datetime import UTC, datetime
from uuid import uuid4

from ally.memory import MemoryRecord, MemorySource
from ally.memory.retrieval import LexicalMemoryRetriever, MemoryContextProvider


class MemoryStoreStub:
    def __init__(self, memories: tuple[MemoryRecord, ...]) -> None:
        self._memories = memories

    def create(self, memory):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def get(self, memory_id):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def list(
        self,
        *,
        as_of=None,  # type: ignore[no-untyped-def]
        kind=None,  # type: ignore[no-untyped-def]
        include_inactive=False,
        limit=100,
    ):  # type: ignore[no-untyped-def]
        return self._memories[:limit]

    def search(self, query, *, limit=20):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def supersede(self, memory_id, replacement):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def retract(self, memory_id):  # type: ignore[no-untyped-def]
        raise NotImplementedError


def memory(content: str, *, importance: float = 0.5) -> MemoryRecord:
    now = datetime.now(UTC)
    return MemoryRecord(
        id=uuid4(),
        kind="semantic",
        content=content,
        source=MemorySource(type="user"),
        confidence=1.0,
        importance=importance,
        privacy="private",
        created_at=now,
        updated_at=now,
    )


def test_lexical_retriever_ranks_relevant_memory() -> None:
    relevant = memory("The greenhouse uses drip irrigation.", importance=0.7)
    irrelevant = memory("The truck needs an oil change.", importance=1.0)
    retriever = LexicalMemoryRetriever(
        MemoryStoreStub((irrelevant, relevant)),
        limit=3,
    )

    hits = retriever.retrieve("What irrigation system does the greenhouse use?")

    assert [hit.memory.id for hit in hits] == [relevant.id]


def test_memory_context_preserves_provenance_label() -> None:
    record = memory("Synthetic preference.")
    provider = MemoryContextProvider(
        LexicalMemoryRetriever(MemoryStoreStub((record,)))
    )

    blocks = provider.retrieve("synthetic preference")

    assert len(blocks) == 1
    assert blocks[0].source == f"memory:{record.id}"
    assert "provenance=user" in blocks[0].content
