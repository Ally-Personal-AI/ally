from ally.events import EventDispatcher, EventRuntime, NewEvent
from ally.events.models import EventRecord


class RecordingStore:
    def __init__(self) -> None:
        self.records: list[EventRecord] = []

    def create(self, event: NewEvent, *, attention: str) -> EventRecord:
        from datetime import UTC, datetime
        from uuid import uuid4

        record = EventRecord(
            id=uuid4(),
            type=event.type,
            source=event.source,
            importance=event.importance,
            attention=attention,  # type: ignore[arg-type]
            payload=event.payload,
            created_at=datetime.now(UTC),
        )
        self.records.append(record)
        return record

    def get(self, event_id):  # pragma: no cover - unused protocol surface
        return None

    def list(self, *, limit=50, attention=None, handled=None):  # pragma: no cover
        return tuple(self.records[-limit:])

    def mark_handled(self, event_id):  # pragma: no cover
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
