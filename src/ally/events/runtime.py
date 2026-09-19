"""Persist then dispatch proactive events."""

from __future__ import annotations

from ally.events.attention import DefaultAttentionPolicy
from ally.events.dispatch import EventDispatcher
from ally.events.models import EventRecord, NewEvent
from ally.events.store import EventStore


class EventRuntime:
    """Classify, persist, and optionally dispatch one observed event."""

    def __init__(
        self,
        store: EventStore,
        *,
        policy: DefaultAttentionPolicy | None = None,
        dispatcher: EventDispatcher | None = None,
    ) -> None:
        self._store = store
        self._policy = policy or DefaultAttentionPolicy()
        self._dispatcher = dispatcher

    def publish(self, event: NewEvent) -> EventRecord:
        attention = self._policy.classify(event)
        record = self._store.create(event, attention=attention)

        if self._dispatcher is not None and attention != "ignore":
            self._dispatcher.dispatch(record)

        return record
