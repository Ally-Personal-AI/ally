"""In-process event dispatch for explicit handlers."""

from __future__ import annotations

from typing import Protocol

from ally.events.models import EventRecord


class EventHandler(Protocol):
    def handle(self, event: EventRecord) -> None:
        ...


class EventDispatcher:
    """Dispatch exact event types to explicitly registered handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def register(self, event_type: str, handler: EventHandler) -> None:
        if not event_type.strip():
            raise ValueError("event_type cannot be empty")
        self._handlers.setdefault(event_type, []).append(handler)

    def dispatch(self, event: EventRecord) -> None:
        for handler in self._handlers.get(event.type, ()):
            handler.handle(event)
