"""Deterministic Memory V1 retrieval and context rendering."""

from __future__ import annotations

from dataclasses import dataclass

from ally.context import ContextBlock
from ally.context.lexical import bm25_scores
from ally.memory import MemoryRecord, MemoryStore


@dataclass(frozen=True)
class MemoryHit:
    memory: MemoryRecord
    score: float


class LexicalMemoryRetriever:
    """Rank active memories with deterministic BM25 lexical relevance."""

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
        candidates = self._store.list(limit=self._candidate_limit)
        scores = bm25_scores(
            query,
            tuple(memory.content for memory in candidates),
        )

        hits = [
            MemoryHit(memory=memory, score=score)
            for memory, score in zip(candidates, scores, strict=True)
            if score > 0.0
        ]
        hits.sort(
            key=lambda hit: (
                hit.score,
                hit.memory.importance,
                hit.memory.confidence,
                hit.memory.updated_at,
                str(hit.memory.id),
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
