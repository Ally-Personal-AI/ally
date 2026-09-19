import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ally.events import EventRuntime, NewEvent
from ally.sources import (
    EventSourceConflictError,
    EventSourceObservation,
    EventSourcePollResult,
    EventSourceRuntime,
    JsonlEventSource,
)
from ally.storage.sqlite import (
    SQLiteDatabase,
    SQLiteEventSourceCheckpointStore,
    SQLiteEventStore,
)


class StaticSource:
    def __init__(
        self,
        *,
        source_id: str = "synthetic.source",
        result: EventSourcePollResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._id = source_id
        self._result = result or EventSourcePollResult()
        self._error = error
        self.cursors: list[str | None] = []
        self.limits: list[int] = []

    @property
    def id(self) -> str:
        return self._id

    def poll(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> EventSourcePollResult:
        self.cursors.append(cursor)
        self.limits.append(limit)
        if self._error is not None:
            raise self._error
        return self._result


def build_runtime(
    path: Path,
) -> tuple[
    SQLiteEventStore,
    SQLiteEventSourceCheckpointStore,
    EventSourceRuntime,
]:
    database = SQLiteDatabase(path)
    events = SQLiteEventStore(database)
    checkpoints = SQLiteEventSourceCheckpointStore(database)
    return (
        events,
        checkpoints,
        EventSourceRuntime(EventRuntime(events), checkpoints),
    )


def write_jsonl(path: Path, count: int) -> None:
    lines = []
    for index in range(count):
        lines.append(
            json.dumps(
                {
                    "external_id": f"obs-{index}",
                    "event_type": "synthetic.changed",
                    "importance": "important",
                    "payload": {"index": index},
                },
                sort_keys=True,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_jsonl_source_pages_and_resumes_from_checkpoint(tmp_path: Path) -> None:
    database_path = tmp_path / "ally.sqlite3"
    source_path = tmp_path / "events.jsonl"
    write_jsonl(source_path, 3)
    events, checkpoints, runtime = build_runtime(database_path)
    source = JsonlEventSource(source_id="jsonl.synthetic", path=source_path)
    first_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    first = runtime.poll(
        source,
        limit=2,
        polled_at=first_at,
    )

    assert first.from_cursor is None
    assert first.to_cursor == "2"
    assert first.published == 2
    assert source.id == "jsonl.synthetic"
    assert [event.payload["data"] for event in first.events] == [
        {"index": 0},
        {"index": 1},
    ]
    assert all(event.attention == "mention_later" for event in first.events)

    reopened = EventSourceRuntime(
        EventRuntime(SQLiteEventStore(SQLiteDatabase(database_path))),
        SQLiteEventSourceCheckpointStore(SQLiteDatabase(database_path)),
    )
    second = reopened.poll(
        source,
        limit=2,
        polled_at=first_at,
    )

    assert second.from_cursor == "2"
    assert second.to_cursor == "3"
    assert second.published == 1

    checkpoint = checkpoints.get("jsonl.synthetic")
    assert checkpoint is not None
    assert checkpoint.cursor == "3"
    assert checkpoint.successful_polls == 2
    assert checkpoint.observations_published == 3
    assert len(events.list(limit=10)) == 3


def test_empty_poll_still_records_successful_checkpoint(tmp_path: Path) -> None:
    _, checkpoints, runtime = build_runtime(tmp_path / "ally.sqlite3")
    source_path = tmp_path / "empty.jsonl"
    source_path.write_text("", encoding="utf-8")
    source = JsonlEventSource(source_id="jsonl.empty", path=source_path)

    first = runtime.poll(source)
    second = runtime.poll(source)

    assert first.published == 0
    assert first.to_cursor == "0"
    assert second.from_cursor == "0"
    assert second.to_cursor == "0"
    checkpoint = checkpoints.get("jsonl.empty")
    assert checkpoint is not None
    assert checkpoint.successful_polls == 2
    assert checkpoint.observations_published == 0


def test_replay_reuses_event_after_partial_progress(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    events, checkpoints, runtime = build_runtime(path)
    source = StaticSource(
        source_id="synthetic.replay",
        result=EventSourcePollResult(
            observations=(
                EventSourceObservation(
                    external_id="external-1",
                    event_type="synthetic.replayed",
                    importance="urgent",
                    payload={"value": 1},
                ),
            ),
            next_cursor="cursor-1",
        ),
    )

    existing = EventRuntime(events).publish(
        NewEvent(
            type="synthetic.replayed",
            source="source:synthetic.replay",
            importance="urgent",
            payload={
                "source": {
                    "id": "synthetic.replay",
                    "external_id": "external-1",
                },
                "data": {"value": 1},
            },
            dedupe_key="source:synthetic.replay:external-1",
        )
    )

    report = runtime.poll(source)

    assert report.event_ids == (existing.id,)
    assert len(events.list()) == 1
    checkpoint = checkpoints.get("synthetic.replay")
    assert checkpoint is not None
    assert checkpoint.cursor == "cursor-1"


def test_source_failure_does_not_advance_checkpoint(tmp_path: Path) -> None:
    events, checkpoints, runtime = build_runtime(tmp_path / "ally.sqlite3")
    source = StaticSource(
        source_id="synthetic.failure",
        error=RuntimeError("synthetic failure"),
    )

    with pytest.raises(RuntimeError, match="synthetic failure"):
        runtime.poll(source)

    assert checkpoints.get("synthetic.failure") is None
    assert events.list() == ()


def test_duplicate_external_ids_are_rejected_before_publish(tmp_path: Path) -> None:
    events, checkpoints, runtime = build_runtime(tmp_path / "ally.sqlite3")
    observation = EventSourceObservation(
        external_id="duplicate",
        event_type="synthetic.duplicate",
    )
    source = StaticSource(
        result=EventSourcePollResult(
            observations=(observation, observation),
            next_cursor="2",
        )
    )

    with pytest.raises(ValueError, match="duplicate external IDs"):
        runtime.poll(source)

    assert events.list() == ()
    assert checkpoints.get(source.id) is None


def test_nonadvancing_cursor_with_observations_is_rejected(
    tmp_path: Path,
) -> None:
    events, checkpoints, runtime = build_runtime(tmp_path / "ally.sqlite3")
    source = StaticSource(
        result=EventSourcePollResult(
            observations=(
                EventSourceObservation(
                    external_id="one",
                    event_type="synthetic.one",
                ),
            ),
            next_cursor=None,
        )
    )

    with pytest.raises(ValueError, match="must advance its cursor"):
        runtime.poll(source)

    assert events.list() == ()
    assert checkpoints.get(source.id) is None


def test_source_cannot_return_more_than_requested(tmp_path: Path) -> None:
    events, checkpoints, runtime = build_runtime(tmp_path / "ally.sqlite3")
    source = StaticSource(
        result=EventSourcePollResult(
            observations=(
                EventSourceObservation(
                    external_id="one",
                    event_type="synthetic.one",
                ),
                EventSourceObservation(
                    external_id="two",
                    event_type="synthetic.two",
                ),
            ),
            next_cursor="2",
        )
    )

    with pytest.raises(ValueError, match="more observations"):
        runtime.poll(source, limit=1)

    assert events.list() == ()
    assert checkpoints.get(source.id) is None


def test_checkpoint_store_rejects_stale_cursor(tmp_path: Path) -> None:
    store = SQLiteEventSourceCheckpointStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    polled_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    first = store.advance(
        source_id="synthetic.source",
        expected_cursor=None,
        next_cursor="cursor-1",
        published=1,
        polled_at=polled_at,
    )

    assert first.cursor == "cursor-1"

    with pytest.raises(EventSourceConflictError, match="checkpoint changed"):
        store.advance(
            source_id="synthetic.source",
            expected_cursor=None,
            next_cursor="cursor-2",
            published=1,
            polled_at=polled_at,
        )

    loaded = store.get("synthetic.source")
    assert loaded is not None
    assert loaded.cursor == "cursor-1"
    assert loaded.successful_polls == 1


def test_jsonl_source_rejects_blank_invalid_and_out_of_range_cursor(
    tmp_path: Path,
) -> None:
    blank = tmp_path / "blank.jsonl"
    blank.write_text("\n", encoding="utf-8")
    source = JsonlEventSource(source_id="jsonl.blank", path=blank)
    with pytest.raises(ValueError, match="blank line"):
        source.poll(cursor=None, limit=10)

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text("not-json\n", encoding="utf-8")
    invalid_source = JsonlEventSource(
        source_id="jsonl.invalid",
        path=invalid,
    )
    with pytest.raises(ValueError, match="invalid JSONL"):
        invalid_source.poll(cursor=None, limit=10)

    valid = tmp_path / "valid.jsonl"
    write_jsonl(valid, 1)
    valid_source = JsonlEventSource(source_id="jsonl.valid", path=valid)
    with pytest.raises(ValueError, match="beyond the current file length"):
        valid_source.poll(cursor="2", limit=10)


def test_invalid_source_id_fails_before_source_poll(tmp_path: Path) -> None:
    _, checkpoints, runtime = build_runtime(tmp_path / "ally.sqlite3")
    source = StaticSource(source_id="Invalid Source")

    with pytest.raises(ValueError, match="invalid event source ID"):
        runtime.poll(source)

    assert source.cursors == []
    assert checkpoints.list() == ()
