from pathlib import Path

import pytest

from ally.events import NewEvent
from ally.storage.sqlite import SQLiteDatabase, SQLiteEventStore


def build_store(path: Path) -> SQLiteEventStore:
    return SQLiteEventStore(SQLiteDatabase(path))


def test_event_store_round_trips_and_filters(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    store = build_store(path)

    quiet = store.create(
        NewEvent(
            type="file.changed",
            source="synthetic",
            importance="routine",
            payload={"path": "synthetic.txt"},
        ),
        attention="remember",
    )
    loud = store.create(
        NewEvent(
            type="weather.warning",
            source="synthetic",
            importance="urgent",
        ),
        attention="notify",
    )

    handled = store.mark_handled(quiet.id)

    reopened = build_store(path)
    assert reopened.get(quiet.id) == handled
    assert [record.id for record in reopened.list(attention="notify")] == [loud.id]
    assert [record.id for record in reopened.list(handled=True)] == [quiet.id]
    assert [record.id for record in reopened.list(handled=False)] == [loud.id]


def test_mark_handled_is_idempotent(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    record = store.create(
        NewEvent(type="test.event", source="synthetic"),
        attention="remember",
    )

    first = store.mark_handled(record.id)
    second = store.mark_handled(record.id)

    assert first.handled_at is not None
    assert second.handled_at == first.handled_at


def test_event_store_rejects_non_positive_limit(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")

    with pytest.raises(ValueError, match="positive"):
        store.list(limit=0)


def test_event_store_dedupe_key_returns_existing_record(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")

    first = store.create(
        NewEvent(
            type="schedule.synthetic",
            source="schedule:test",
            payload={"value": 1},
            dedupe_key="schedule:test:2026-01-01T00:00:00+00:00",
        ),
        attention="remember",
    )
    second = store.create(
        NewEvent(
            type="schedule.synthetic",
            source="schedule:test",
            payload={"value": 999},
            dedupe_key="schedule:test:2026-01-01T00:00:00+00:00",
        ),
        attention="notify",
    )

    assert second == first
    records = store.list()
    assert len(records) == 1
    assert records[0].payload == {"value": 1}
    assert records[0].attention == "remember"
    assert records[0].dedupe_key == "schedule:test:2026-01-01T00:00:00+00:00"
