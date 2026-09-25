"""Personal knowledge persistence contract."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from ally.knowledge.models import (
    KnowledgeChunk,
    KnowledgeRevision,
    KnowledgeSource,
    NewKnowledgeChunk,
    NewKnowledgeSource,
)


class KnowledgeStore(Protocol):
    """Storage contract for versioned personal knowledge."""

    def ingest(
        self,
        source: NewKnowledgeSource,
        *,
        source_sha256: str,
        chunks: Sequence[NewKnowledgeChunk],
    ) -> tuple[KnowledgeSource, KnowledgeRevision]:
        ...

    def get_source(self, source_id: UUID) -> KnowledgeSource | None:
        ...

    def find_source_by_uri(self, uri: str) -> KnowledgeSource | None:
        ...

    def list_sources(self, *, limit: int = 100) -> tuple[KnowledgeSource, ...]:
        ...

    def delete_source(self, source_id: UUID) -> bool:
        ...

    def list_revisions(self, source_id: UUID) -> tuple[KnowledgeRevision, ...]:
        ...

    def list_current_chunks(self, source_id: UUID) -> tuple[KnowledgeChunk, ...]:
        ...

    def list_revision_chunks(self, revision_id: UUID) -> tuple[KnowledgeChunk, ...]:
        ...

    def list_search_candidates(self, *, limit: int = 1000) -> tuple[KnowledgeChunk, ...]:
        ...
