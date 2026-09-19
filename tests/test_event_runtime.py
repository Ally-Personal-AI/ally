from datetime import UTC, datetime
from uuid import UUID, uuid4

from ally.events import (
    AttentionClass,
    EventDispatcher,
    EventRuntime,
    NewEvent,
)
from ally.events.models import EventRecord


class RecordingStore:
    def __init__(self) -> None:
        self.records: list[EventRecord] = []

    def create(
        self,
        event: NewEvent,
        *,
        attention: AttentionClass,
    ) -> EventRecord:
        record = EventRecord(
            id=uuid4(),
            type=event.type,
            source=event.source,
            importance=event.importance,
            attention=attention,
            payload=event.payload,
            created_at=datetime.now(UTC),
        )
        self.records.append(record)
        return record

    def get(self, event_id: UUID) -> EventRecord | None:
        return next(
            (record for record in self.records if record.id == event_id),
            None,
        )

    def list(
        self,
        *,
        limit: int = 50,
        attention: AttentionClass | None = None,
        handled: bool | None = None,
    ) -> tuple[EventRecord, ...]:
        records = self.records
        if attention is not None:
            records = [record for record in records if record.attention == attention]
        if handled is True:
            records = [record for record in records if record.handled_at is not None]
        elif handled is False:
            records = [record for record in records if record.handled_at is None]
        return tuple(records[-limit:])

    def pending_attention(
        self,
        *,
        attentions: tuple[AttentionClass, ...],
        limit: int = 50,
    ) -> tuple[EventRecord, ...]:
        records = [
            record
            for record in self.records
            if record.handled_at is None and record.attention in attentions
        ]
        return tuple(records[:limit])

    def mark_handled(self, event_id: UUID) -> EventRecord:
        raise NotImplementedError


class RecordingHandler:
    def __init__(self) -> None:
        self.records: list[EventRecord] = []

    def handle(self, event: EventRecord) -> None:
        self.records.append(event)


def test_runtime_persists_before_dispatch() -> None:
    store = RecordingStore()
    dispatcher = EventDispatcher()
    handler = RecordingHandler()
    dispatcher.register("calendar.changed", handler)
    runtime = EventRuntime(store, dispatcher=dispatcher)

    record = runtime.publish(
        NewEvent(
            type="calendar.changed",
            source="synthetic",
            importance="urgent",
        )
    )

    assert store.records == [record]
    assert handler.records == [record]
    assert record.attention == "notify"


def test_ignored_event_is_persisted_but_not_dispatched() -> None:
    store = RecordingStore()
    dispatcher = EventDispatcher()
    handler = RecordingHandler()
    dispatcher.register("noise.event", handler)
    runtime = EventRuntime(store, dispatcher=dispatcher)

    record = runtime.publish(
        NewEvent(
            type="noise.event",
            source="synthetic",
            importance="noise",
        )
    )

    assert store.records == [record]
    assert record.attention == "ignore"
    assert handler.records == []
