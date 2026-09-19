"""Protocol implemented by external event-source adapters."""

from __future__ import annotations

from typing import Protocol

from ally.sources.models import EventSourcePollResult


class EventSource(Protocol):
    @property
    def id(self) -> str:
        ...

    def poll(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> EventSourcePollResult:
        ...
