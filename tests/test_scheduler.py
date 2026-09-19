from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ally.events import EventRuntime, NewEvent
from ally.scheduler import (
    NewSchedule,
    ScheduleConflictError,
    SchedulerRuntime,
)
from ally.storage.sqlite import (
    SQLiteDatabase,
    SQLiteEventStore,
    SQLiteScheduleStore,
)


def build_runtime(
    path: Path,
) -> tuple[SQLiteScheduleStore, SQLiteEventStore, SchedulerRuntime]:
    database = SQLiteDatabase(path)
    schedules = SQLiteScheduleStore(database)
    events = SQLiteEventStore(database)
    runtime = SchedulerRuntime(schedules, EventRuntime(events))
    return schedules, events, runtime


def test_schedule_store_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    schedules, _, _ = build_runtime(path)
    starts_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    created = schedules.create(
        NewSchedule(
            name="Synthetic recurring schedule",
            event_type="synthetic.tick",
            starts_at=starts_at,
            interval_seconds=300,
            payload={"value": 1},
        )
    )

    reopened = SQLiteScheduleStore(SQLiteDatabase(path))
    loaded = reopened.get(created.id)

    assert loaded == created
    assert loaded is not None
    assert loaded.next_run_at == starts_at
    assert loaded.interval_seconds == 300


def test_disabled_schedule_is_not_due(tmp_path: Path) -> None:
    schedules, _, _ = build_runtime(tmp_path / "ally.sqlite3")
    starts_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    disabled = schedules.create(
        NewSchedule(
            name="Disabled",
            event_type="synthetic.disabled",
            starts_at=starts_at,
            enabled=False,
        )
    )
    enabled = schedules.create(
        NewSchedule(
            name="Enabled",
            event_type="synthetic.enabled",
            starts_at=starts_at,
        )
    )

    due = schedules.due(as_of=starts_at)

    assert [record.id for record in due] == [enabled.id]
    assert disabled.id not in {record.id for record in due}


def test_one_shot_tick_emits_once_and_completes(tmp_path: Path) -> None:
    schedules, events, runtime = build_runtime(tmp_path / "ally.sqlite3")
    starts_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    schedule = schedules.create(
        NewSchedule(
            name="One shot",
            event_type="synthetic.once",
            starts_at=starts_at,
            importance="important",
            payload={"message": "synthetic"},
        )
    )

    first = runtime.tick(as_of=starts_at)
    second = runtime.tick(as_of=starts_at + timedelta(hours=1))

    assert len(first) == 1
    assert second == ()
    assert first[0].schedule_id == schedule.id
    assert first[0].coalesced_occurrences == 1
    assert first[0].next_run_at is None

    updated = schedules.get(schedule.id)
    assert updated is not None
    assert updated.enabled is False
    assert updated.next_run_at is None
    assert updated.last_run_at == starts_at

    event = events.get(first[0].event_id)
    assert event is not None
    assert event.type == "synthetic.once"
    assert event.attention == "mention_later"
    assert event.payload["data"] == {"message": "synthetic"}
    assert event.payload["schedule"]["coalesced_occurrences"] == 1


def test_interval_tick_coalesces_missed_occurrences(tmp_path: Path) -> None:
    schedules, events, runtime = build_runtime(tmp_path / "ally.sqlite3")
    starts_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    schedule = schedules.create(
        NewSchedule(
            name="Minute interval",
            event_type="synthetic.interval",
            starts_at=starts_at,
            interval_seconds=60,
        )
    )
    observed_at = starts_at + timedelta(minutes=5, seconds=30)

    results = runtime.tick(as_of=observed_at)

    assert len(results) == 1
    assert results[0].coalesced_occurrences == 6
    assert results[0].scheduled_for == starts_at
    assert results[0].next_run_at == starts_at + timedelta(minutes=6)

    updated = schedules.get(schedule.id)
    assert updated is not None
    assert updated.enabled is True
    assert updated.last_run_at == observed_at
    assert updated.next_run_at == starts_at + timedelta(minutes=6)

    event = events.get(results[0].event_id)
    assert event is not None
    assert event.payload["schedule"]["coalesced_occurrences"] == 6


def test_retry_reuses_event_if_schedule_was_not_advanced(
    tmp_path: Path,
) -> None:
    schedules, events, runtime = build_runtime(tmp_path / "ally.sqlite3")
    starts_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    schedule = schedules.create(
        NewSchedule(
            name="Crash-safe",
            event_type="synthetic.retry",
            starts_at=starts_at,
        )
    )
    dedupe_key = f"schedule:{schedule.id}:{starts_at.isoformat()}"

    already_persisted = EventRuntime(events).publish(
        NewEvent(
            type="synthetic.retry",
            source=f"schedule:{schedule.id}",
            payload={"simulated": "partial-progress"},
            dedupe_key=dedupe_key,
        )
    )

    results = runtime.tick(as_of=starts_at)

    assert len(results) == 1
    assert results[0].event_id == already_persisted.id
    assert len(events.list()) == 1

    updated = schedules.get(schedule.id)
    assert updated is not None
    assert updated.enabled is False
    assert updated.next_run_at is None


def test_stale_schedule_advance_fails_closed(tmp_path: Path) -> None:
    schedules, _, _ = build_runtime(tmp_path / "ally.sqlite3")
    starts_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    schedule = schedules.create(
        NewSchedule(
            name="Concurrent",
            event_type="synthetic.concurrent",
            starts_at=starts_at,
            interval_seconds=60,
        )
    )

    schedules.advance(
        schedule.id,
        expected_next_run_at=starts_at,
        next_run_at=starts_at + timedelta(minutes=1),
        last_run_at=starts_at,
        enabled=True,
    )

    with pytest.raises(ScheduleConflictError, match="changed before advancement"):
        schedules.advance(
            schedule.id,
            expected_next_run_at=starts_at,
            next_run_at=starts_at + timedelta(minutes=2),
            last_run_at=starts_at,
            enabled=True,
        )


def test_completed_one_shot_cannot_be_reenabled(tmp_path: Path) -> None:
    schedules, _, runtime = build_runtime(tmp_path / "ally.sqlite3")
    starts_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    schedule = schedules.create(
        NewSchedule(
            name="Completed",
            event_type="synthetic.complete",
            starts_at=starts_at,
        )
    )
    runtime.tick(as_of=starts_at)

    with pytest.raises(ValueError, match="cannot be re-enabled"):
        schedules.set_enabled(schedule.id, enabled=True)


def test_schedule_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone offset"):
        NewSchedule(
            name="Naive",
            event_type="synthetic.naive",
            starts_at=datetime(2026, 1, 1, 12, 0),
        )
