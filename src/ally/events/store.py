"""Persistence contract for proactive events."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from ally.events.models import AttentionClass, EventRecord, NewEvent


class EventStore(Protocol):
    def create(
        self,
        event: NewEvent,
        *,
        attention: AttentionClass,
    ) -> EventRecord:
        ...

    def get(self, event_id: UUID) -> EventRecord | None:
        ...

    def list(
        self,
        *,
        limit: int = 50,
        attention: AttentionClass | None = None,
        handled: bool | None = None,
    ) -> tuple[EventRecord, ...]:
        ...

    def mark_handled(self, event_id: UUID) -> EventRecord:
        ...
