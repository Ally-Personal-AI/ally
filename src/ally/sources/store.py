"""Persistence contract for source checkpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ally.sources.models import EventSourceCheckpoint


class EventSourceConflictError(RuntimeError):
    """Raised when a source cursor changed before checkpoint advancement."""


class EventSourceCheckpointStore(Protocol):
    def get(self, source_id: str) -> EventSourceCheckpoint | None:
        ...

    def advance(
        self,
        *,
        source_id: str,
        expected_cursor: str | None,
        next_cursor: str | None,
        published: int,
        polled_at: datetime,
    ) -> EventSourceCheckpoint:
        ...

    def list(self, *, limit: int = 50) -> tuple[EventSourceCheckpoint, ...]:
        ...
