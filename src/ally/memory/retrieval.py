"""Deterministic Memory V1 retrieval and context rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ally.context import ContextBlock
from ally.memory import MemoryRecord, MemoryStore

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "i",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "with",
        "you",
    }
)


def _tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in (match.group(0).lower() for match in _TOKEN_PATTERN.finditer(value))
        if token not in _STOP_WORDS
    )


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
        query_tokens = _tokens(query)
        if not query_tokens:
            return ()

        hits: list[MemoryHit] = []
        for memory in self._store.list(limit=self._candidate_limit):
            memory_tokens = _tokens(memory.content)
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
