"""Deterministic Knowledge V1 retrieval and context rendering."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ally.context import ContextBlock
from ally.context.lexical import bm25_scores
from ally.knowledge import KnowledgeChunk, KnowledgeSource, KnowledgeStore


@dataclass(frozen=True)
class KnowledgeHit:
    chunk: KnowledgeChunk
    source: KnowledgeSource
    score: float


class LexicalKnowledgeRetriever:
    """Rank current knowledge chunks with deterministic BM25 lexical relevance."""

    def __init__(
        self,
        store: KnowledgeStore,
        *,
        limit: int = 8,
        candidate_limit: int = 1000,
    ) -> None:
        if limit < 1 or candidate_limit < 1:
            raise ValueError("retrieval limits must be positive")
        self._store = store
        self._limit = limit
        self._candidate_limit = candidate_limit

    def retrieve(self, query: str) -> tuple[KnowledgeHit, ...]:
        candidates = self._store.list_search_candidates(limit=self._candidate_limit)
        scores = bm25_scores(
            query,
            tuple(chunk.content for chunk in candidates),
        )

        hits: list[KnowledgeHit] = []
        source_cache: dict[UUID, KnowledgeSource] = {}
        for chunk, score in zip(candidates, scores, strict=True):
            if score <= 0.0:
                continue

            source = source_cache.get(chunk.source_id)
            if source is None:
                loaded = self._store.get_source(chunk.source_id)
                if loaded is None:
                    continue
                source_cache[chunk.source_id] = loaded
                source = loaded

            hits.append(KnowledgeHit(chunk=chunk, source=source, score=score))

        hits.sort(
            key=lambda hit: (
                hit.score,
                hit.source.updated_at,
                -hit.chunk.ordinal,
                str(hit.chunk.id),
            ),
            reverse=True,
        )
        return tuple(hits[: self._limit])


class KnowledgeContextProvider:
    """Expose retrieved document chunks as provenance-labelled context."""

    def __init__(self, retriever: LexicalKnowledgeRetriever) -> None:
        self._retriever = retriever

    def retrieve(self, query: str) -> tuple[ContextBlock, ...]:
        blocks: list[ContextBlock] = []

        for hit in self._retriever.retrieve(query):
            chunk = hit.chunk
            source = hit.source
            blocks.append(
                ContextBlock(
                    source=(
                        f"knowledge:{source.id}:"
                        f"r{chunk.revision}:c{chunk.ordinal}"
                    ),
                    content=(
                        f"title={source.title}; media_type={source.media_type}; "
                        f"revision={chunk.revision}; chars={chunk.start_char}-{chunk.end_char}\n"
                        f"{chunk.content}"
                    ),
                )
            )

        return tuple(blocks)
