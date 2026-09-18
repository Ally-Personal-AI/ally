"""Long-term memory persistence contract."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from ally.memory.models import MemoryKind, MemoryRecord, NewMemory


class MemoryStore(Protocol):
    """Storage contract for inspectable temporal memories."""

    def create(self, memory: NewMemory) -> MemoryRecord:
        ...

    def get(self, memory_id: UUID) -> MemoryRecord | None:
        ...

    def list(
        self,
        *,
        as_of: datetime | None = None,
        kind: MemoryKind | None = None,
        include_inactive: bool = False,
        limit: int = 100,
    ) -> tuple[MemoryRecord, ...]:
        ...

    def search(self, query: str, *, limit: int = 20) -> tuple[MemoryRecord, ...]:
        ...

    def supersede(
        self,
        memory_id: UUID,
        replacement: NewMemory,
    ) -> tuple[MemoryRecord, MemoryRecord]:
        ...

    def retract(self, memory_id: UUID) -> MemoryRecord:
        ...
