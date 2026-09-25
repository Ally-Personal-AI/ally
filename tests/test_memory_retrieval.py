from datetime import UTC, datetime
from uuid import UUID, uuid4

from ally.memory import MemoryKind, MemoryRecord, MemorySource, NewMemory
from ally.memory.retrieval import LexicalMemoryRetriever, MemoryContextProvider


class MemoryStoreStub:
    def __init__(self, memories: tuple[MemoryRecord, ...]) -> None:
        self._memories = memories

    def create(self, memory: NewMemory) -> MemoryRecord:
        raise NotImplementedError

    def get(self, memory_id: UUID) -> MemoryRecord | None:
        raise NotImplementedError

    def list(
        self,
        *,
        as_of: datetime | None = None,
        kind: MemoryKind | None = None,
        include_inactive: bool = False,
        limit: int = 100,
    ) -> tuple[MemoryRecord, ...]:
        del as_of, kind, include_inactive
        return self._memories[:limit]

    def search(self, query: str, *, limit: int = 20) -> tuple[MemoryRecord, ...]:
        raise NotImplementedError

    def supersede(
        self,
        memory_id: UUID,
        replacement: NewMemory,
    ) -> tuple[MemoryRecord, MemoryRecord]:
        raise NotImplementedError

    def retract(self, memory_id: UUID) -> MemoryRecord:
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


def test_memory_relevance_outranks_importance_when_terms_are_more_specific() -> None:
    specific = memory("The orchard irrigation controller uses zone seven.", importance=0.1)
    broad = memory("The orchard has seasonal maintenance tasks.", importance=1.0)
    retriever = LexicalMemoryRetriever(
        MemoryStoreStub((broad, specific)),
        limit=2,
    )

    hits = retriever.retrieve("orchard irrigation controller")

    assert [hit.memory.id for hit in hits] == [specific.id, broad.id]
    assert hits[0].score > hits[1].score
