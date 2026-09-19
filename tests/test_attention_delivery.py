from pathlib import Path

import pytest

from ally.attention import AttentionDeliveryRuntime, delivery_key
from ally.events import AttentionClass, EventRecord, NewEvent
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteDatabase,
    SQLiteEventStore,
)


class RecordingSink:
    def __init__(
        self,
        *,
        sink_id: str = "recording",
        accepted: tuple[AttentionClass, ...] = (
            "mention_later",
            "notify",
            "interrupt",
        ),
    ) -> None:
        self._id = sink_id
        self._accepted = accepted
        self.event_ids: list[str] = []

    @property
    def id(self) -> str:
        return self._id

    @property
    def accepted_attention(self) -> tuple[AttentionClass, ...]:
        return self._accepted

    def deliver(
        self,
        event: EventRecord,
        *,
        delivery_key: str,
    ) -> None:
        assert delivery_key == (
            f"attention:{self.id}:{event.id}"
        )
        self.event_ids.append(str(event.id))


class FlakySink(RecordingSink):
    def __init__(self) -> None:
        super().__init__(sink_id="flaky", accepted=("notify",))
        self.calls = 0

    def deliver(
        self,
        event: EventRecord,
        *,
        delivery_key: str,
    ) -> None:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("synthetic delivery failure: secret=must-not-persist")
        super().deliver(event, delivery_key=delivery_key)


def build_runtime(
    path: Path,
) -> tuple[
    SQLiteEventStore,
    SQLiteAttentionDeliveryStore,
    AttentionDeliveryRuntime,
]:
    database = SQLiteDatabase(path)
    events = SQLiteEventStore(database)
    deliveries = SQLiteAttentionDeliveryStore(database)
    return events, deliveries, AttentionDeliveryRuntime(events, deliveries)


def create_event(
    events: SQLiteEventStore,
    *,
    name: str,
    attention: AttentionClass,
) -> EventRecord:
    return events.create(
        NewEvent(
            type=f"synthetic.{name}",
            source="test",
            payload={"name": name},
        ),
        attention=attention,
    )


def test_pending_attention_excludes_handled_and_non_delivery_classes(
    tmp_path: Path,
) -> None:
    events, _, _ = build_runtime(tmp_path / "ally.sqlite3")
    remembered = create_event(events, name="remembered", attention="remember")
    later = create_event(events, name="later", attention="mention_later")
    notify = create_event(events, name="notify", attention="notify")
    interrupt = create_event(events, name="interrupt", attention="interrupt")
    acted = create_event(events, name="acted", attention="act")
    events.mark_handled(notify.id)

    pending = events.pending_attention(
        attentions=("mention_later", "notify", "interrupt"),
    )

    assert [record.id for record in pending] == [interrupt.id, later.id]
    assert remembered.id not in {record.id for record in pending}
    assert notify.id not in {record.id for record in pending}
    assert acted.id not in {record.id for record in pending}


def test_successful_delivery_is_idempotent_and_not_handled(
    tmp_path: Path,
) -> None:
    events, deliveries, runtime = build_runtime(tmp_path / "ally.sqlite3")
    event = create_event(events, name="notify", attention="notify")
    sink = RecordingSink(accepted=("notify",))

    first = runtime.deliver_pending(sink)
    second = runtime.deliver_pending(sink)

    assert len(first) == 1
    assert first[0].status == "succeeded"
    assert first[0].attempts == 1
    assert second == ()
    assert sink.event_ids == [str(event.id)]

    persisted = deliveries.get(event.id, sink.id)
    assert persisted == first[0]

    stored_event = events.get(event.id)
    assert stored_event is not None
    assert stored_event.handled_at is None


def test_failed_delivery_retries_and_can_transition_to_success(
    tmp_path: Path,
) -> None:
    events, deliveries, runtime = build_runtime(tmp_path / "ally.sqlite3")
    event = create_event(events, name="retry", attention="notify")
    sink = FlakySink()

    first = runtime.deliver_pending(sink)
    second = runtime.deliver_pending(sink)
    third = runtime.deliver_pending(sink)

    assert len(first) == 1
    assert first[0].status == "failed"
    assert first[0].attempts == 1
    assert first[0].last_error == "RuntimeError"

    assert len(second) == 1
    assert second[0].status == "succeeded"
    assert second[0].attempts == 2
    assert second[0].last_error is None
    assert second[0].delivered_at is not None
    assert third == ()
    assert sink.calls == 2

    persisted = deliveries.get(event.id, sink.id)
    assert persisted == second[0]


def test_delivery_pages_past_terminal_successes(tmp_path: Path) -> None:
    events, deliveries, runtime = build_runtime(tmp_path / "ally.sqlite3")
    for index in range(60):
        create_event(events, name=f"event-{index:02d}", attention="notify")

    ordered = events.pending_attention(attentions=("notify",), limit=100)
    assert len(ordered) == 60
    for event in ordered[:50]:
        deliveries.record_attempt(
            event_id=event.id,
            sink_id="recording",
            succeeded=True,
        )

    sink = RecordingSink(accepted=("notify",))
    attempts = runtime.deliver_pending(sink, limit=10)

    assert len(attempts) == 10
    assert all(record.status == "succeeded" for record in attempts)
    assert sink.event_ids == [str(event.id) for event in ordered[50:60]]


def test_sink_attention_scope_is_respected(tmp_path: Path) -> None:
    events, _, runtime = build_runtime(tmp_path / "ally.sqlite3")
    later = create_event(events, name="later", attention="mention_later")
    interrupt = create_event(events, name="interrupt", attention="interrupt")
    sink = RecordingSink(accepted=("interrupt",))

    attempts = runtime.deliver_pending(sink)

    assert len(attempts) == 1
    assert sink.event_ids == [str(interrupt.id)]
    assert str(later.id) not in sink.event_ids


def test_invalid_sink_id_fails_before_external_delivery(tmp_path: Path) -> None:
    events, _, runtime = build_runtime(tmp_path / "ally.sqlite3")
    create_event(events, name="notify", attention="notify")
    sink = RecordingSink(sink_id="Invalid Sink", accepted=("notify",))

    with pytest.raises(ValueError):
        runtime.deliver_pending(sink)

    assert sink.event_ids == []


def test_success_is_terminal_in_delivery_store(tmp_path: Path) -> None:
    events, deliveries, _ = build_runtime(tmp_path / "ally.sqlite3")
    event = create_event(events, name="terminal", attention="notify")

    first = deliveries.record_attempt(
        event_id=event.id,
        sink_id="recording",
        succeeded=True,
    )
    second = deliveries.record_attempt(
        event_id=event.id,
        sink_id="recording",
        succeeded=False,
        error="must not replace success",
    )

    assert second == first
    assert second.status == "succeeded"
    assert second.attempts == 1
    assert second.last_error is None


def test_delivery_history_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    events, deliveries, _ = build_runtime(path)
    event = create_event(events, name="persisted", attention="notify")
    created = deliveries.record_attempt(
        event_id=event.id,
        sink_id="recording",
        succeeded=False,
        error="synthetic",
    )

    reopened = SQLiteAttentionDeliveryStore(SQLiteDatabase(path))

    assert reopened.get(event.id, "recording") == created
    assert reopened.list(status="failed") == (created,)


def test_act_attention_cannot_be_delivered_by_user_attention_runtime(
    tmp_path: Path,
) -> None:
    events, _, runtime = build_runtime(tmp_path / "ally.sqlite3")
    create_event(events, name="act", attention="act")
    sink = RecordingSink(accepted=("act",))

    attempts = runtime.deliver_pending(sink)

    assert attempts == ()
    assert sink.event_ids == []


def test_delivery_key_is_stable() -> None:
    assert delivery_key(
        sink_id="console",
        event_id="00000000-0000-0000-0000-000000000001",
    ) == (
        "attention:console:"
        "00000000-0000-0000-0000-000000000001"
    )


def test_delivery_record_rejects_inconsistent_terminal_state() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from ally.attention import AttentionDeliveryRecord

    now = datetime.now(UTC)

    with pytest.raises(ValueError, match="requires delivered_at"):
        AttentionDeliveryRecord(
            id=uuid4(),
            event_id=uuid4(),
            sink_id="recording",
            status="succeeded",
            attempts=1,
            created_at=now,
            updated_at=now,
        )

    with pytest.raises(ValueError, match="failed delivery cannot"):
        AttentionDeliveryRecord(
            id=uuid4(),
            event_id=uuid4(),
            sink_id="recording",
            status="failed",
            attempts=1,
            created_at=now,
            updated_at=now,
            delivered_at=now,
        )
