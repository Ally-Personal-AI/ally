from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ally.attention import AttentionDeliveryRuntime
from ally.events import AttentionClass, EventRecord, EventRuntime
from ally.scheduler import NewSchedule, SchedulerRuntime
from ally.service import ProactiveServiceCycle
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteDatabase,
    SQLiteEventStore,
    SQLiteScheduleStore,
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
        fail: bool = False,
    ) -> None:
        self._id = sink_id
        self._accepted = accepted
        self._fail = fail
        self.events: list[EventRecord] = []

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
        assert delivery_key == f"attention:{self.id}:{event.id}"
        if self._fail:
            raise RuntimeError("synthetic")
        self.events.append(event)


def build_cycle(path: Path) -> tuple[
    SQLiteScheduleStore,
    SQLiteEventStore,
    SQLiteAttentionDeliveryStore,
    ProactiveServiceCycle,
]:
    database = SQLiteDatabase(path)
    schedules = SQLiteScheduleStore(database)
    events = SQLiteEventStore(database)
    deliveries = SQLiteAttentionDeliveryStore(database)
    cycle = ProactiveServiceCycle(
        SchedulerRuntime(schedules, EventRuntime(events)),
        AttentionDeliveryRuntime(events, deliveries),
    )
    return schedules, events, deliveries, cycle


def test_empty_service_cycle_is_successful(tmp_path: Path) -> None:
    _, _, _, cycle = build_cycle(tmp_path / "ally.sqlite3")
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    report = cycle.run(
        as_of=observed_at,
        sinks=(RecordingSink(),),
    )

    assert report.observed_at == observed_at
    assert report.schedule_ticks == ()
    assert report.deliveries[0].attempts == ()
    assert report.scheduled_events == 0
    assert report.delivery_attempts == 0
    assert report.delivery_failures == 0
    assert report.successful is True


def test_due_schedule_is_delivered_in_same_cycle(tmp_path: Path) -> None:
    schedules, events, deliveries, cycle = build_cycle(tmp_path / "ally.sqlite3")
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    schedule = schedules.create(
        NewSchedule(
            name="Same cycle",
            event_type="synthetic.same-cycle",
            starts_at=observed_at,
            importance="urgent",
            payload={"message": "synthetic"},
        )
    )
    sink = RecordingSink(accepted=("notify",))

    report = cycle.run(
        as_of=observed_at,
        sinks=(sink,),
    )

    assert report.scheduled_events == 1
    assert report.delivery_attempts == 1
    assert report.delivery_failures == 0
    assert report.successful is True
    assert report.schedule_ticks[0].schedule_id == schedule.id
    assert len(sink.events) == 1

    event = sink.events[0]
    assert event.id == report.schedule_ticks[0].event_id
    assert event.type == "synthetic.same-cycle"
    assert event.attention == "notify"

    delivery = deliveries.get(event.id, sink.id)
    assert delivery is not None
    assert delivery.status == "succeeded"

    persisted = events.get(event.id)
    assert persisted is not None
    assert persisted.handled_at is None


def test_delivery_limit_is_applied_per_sink(tmp_path: Path) -> None:
    schedules, _, _, cycle = build_cycle(tmp_path / "ally.sqlite3")
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    for index in range(3):
        schedules.create(
            NewSchedule(
                name=f"Bounded {index}",
                event_type=f"synthetic.bounded-{index}",
                starts_at=observed_at,
                importance="urgent",
            )
        )

    sink = RecordingSink(accepted=("notify",))
    report = cycle.run(
        as_of=observed_at,
        sinks=(sink,),
        schedule_limit=3,
        delivery_limit=2,
    )

    assert report.scheduled_events == 3
    assert report.delivery_attempts == 2
    assert len(sink.events) == 2


def test_schedule_limit_defers_excess_due_schedules(tmp_path: Path) -> None:
    schedules, _, _, cycle = build_cycle(tmp_path / "ally.sqlite3")
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    for index in range(3):
        schedules.create(
            NewSchedule(
                name=f"Limited {index}",
                event_type=f"synthetic.limited-{index}",
                starts_at=observed_at,
                importance="urgent",
            )
        )

    first = cycle.run(
        as_of=observed_at,
        sinks=(),
        schedule_limit=2,
    )
    second = cycle.run(
        as_of=observed_at + timedelta(seconds=1),
        sinks=(),
        schedule_limit=2,
    )

    assert first.scheduled_events == 2
    assert second.scheduled_events == 1


def test_failed_sink_delivery_is_reported_and_persisted(tmp_path: Path) -> None:
    schedules, _, deliveries, cycle = build_cycle(tmp_path / "ally.sqlite3")
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    schedules.create(
        NewSchedule(
            name="Failure",
            event_type="synthetic.failure",
            starts_at=observed_at,
            importance="urgent",
        )
    )
    sink = RecordingSink(sink_id="failing", accepted=("notify",), fail=True)

    report = cycle.run(
        as_of=observed_at,
        sinks=(sink,),
    )

    assert report.delivery_attempts == 1
    assert report.delivery_failures == 1
    assert report.successful is False
    record = report.deliveries[0].attempts[0]
    assert record.status == "failed"
    assert record.last_error == "RuntimeError"
    assert deliveries.get(record.event_id, sink.id) == record


def test_duplicate_sink_ids_are_rejected_before_second_delivery(
    tmp_path: Path,
) -> None:
    schedules, _, _, cycle = build_cycle(tmp_path / "ally.sqlite3")
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    schedules.create(
        NewSchedule(
            name="Duplicate sink",
            event_type="synthetic.duplicate",
            starts_at=observed_at,
            importance="urgent",
        )
    )
    first = RecordingSink(sink_id="same", accepted=("notify",))
    second = RecordingSink(sink_id="same", accepted=("notify",))

    with pytest.raises(ValueError, match="duplicate attention sink ID"):
        cycle.run(
            as_of=observed_at,
            sinks=(first, second),
        )

    assert len(first.events) == 1
    assert second.events == []


def test_cycle_rejects_naive_timestamp_and_non_positive_limits(
    tmp_path: Path,
) -> None:
    _, _, _, cycle = build_cycle(tmp_path / "ally.sqlite3")
    aware = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="timezone offset"):
        cycle.run(as_of=datetime(2026, 1, 1, 12, 0), sinks=())

    with pytest.raises(ValueError, match="schedule_limit"):
        cycle.run(as_of=aware, sinks=(), schedule_limit=0)

    with pytest.raises(ValueError, match="delivery_limit"):
        cycle.run(as_of=aware, sinks=(), delivery_limit=0)
