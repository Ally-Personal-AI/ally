"""Deterministic Memory V1 retrieval and context rendering."""

from __future__ import annotations

from dataclasses import dataclass

from ally.context import ContextBlock
from ally.context.lexical import lexical_tokens
from ally.memory import MemoryRecord, MemoryStore


@dataclass(frozen=True)
class MemoryHit:
    memory: MemoryRecord
    score: float


class LexicalMemoryRetriever:
    """Rank active memories with deterministic lexical overlap."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        limit: int = 8,
        candidate_limit: int = 500,
    ) -> None:
        if limit < 1 or candidate_limit < 1:
            raise ValueError("retrieval limits must be positive")
        self._store = store
        self._limit = limit
        self._candidate_limit = candidate_limit

    def retrieve(self, query: str) -> tuple[MemoryHit, ...]:
        query_tokens = lexical_tokens(query)
        if not query_tokens:
            return ()

        hits: list[MemoryHit] = []
        for memory in self._store.list(limit=self._candidate_limit):
            memory_tokens = lexical_tokens(memory.content)
            overlap = len(query_tokens & memory_tokens)
            if overlap == 0:
                continue
            lexical_score = overlap / len(query_tokens)
            score = lexical_score + (memory.importance * 0.2)
            hits.append(MemoryHit(memory=memory, score=score))

        hits.sort(
            key=lambda hit: (
                hit.score,
                hit.memory.importance,
                hit.memory.updated_at,
            ),
            reverse=True,
        )
        return tuple(hits[: self._limit])


class MemoryContextProvider:
    """Expose retrieved memories as provenance-labelled reference context."""

    def __init__(self, retriever: LexicalMemoryRetriever) -> None:
        self._retriever = retriever

    def retrieve(self, query: str) -> tuple[ContextBlock, ...]:
        blocks: list[ContextBlock] = []
        for hit in self._retriever.retrieve(query):
            memory = hit.memory
            source_detail = memory.source.type
            if memory.source.id is not None:
                source_detail = f"{source_detail}:{memory.source.id}"

            blocks.append(
                ContextBlock(
                    source=f"memory:{memory.id}",
                    content=(
                        f"kind={memory.kind}; confidence={memory.confidence:.2f}; "
                        f"importance={memory.importance:.2f}; provenance={source_detail}\n"
                        f"{memory.content}"
                    ),
                )
            )
        return tuple(blocks)
