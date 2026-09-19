from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import JsonValue

from ally.attention import AttentionDeliveryRuntime
from ally.events import AttentionClass, EventRecord, EventRuntime, NewEvent
from ally.scheduler import SchedulerRuntime
from ally.service import ProactiveServiceCycle
from ally.sources import EventSourceRuntime, FilesystemEventSource
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteDatabase,
    SQLiteEventSourceCheckpointStore,
    SQLiteEventStore,
    SQLiteScheduleStore,
)


class RecordingSink:
    @property
    def id(self) -> str:
        return "recording"

    @property
    def accepted_attention(self) -> tuple[AttentionClass, ...]:
        return ("mention_later",)

    def __init__(self) -> None:
        self.events: list[EventRecord] = []

    def deliver(self, event: EventRecord, *, delivery_key: str) -> None:
        assert delivery_key == f"attention:{self.id}:{event.id}"
        self.events.append(event)


class FailableFilesystemSource(FilesystemEventSource):
    fail = False

    def _scan(self) -> Any:
        if self.fail:
            raise ValueError("synthetic scan failure")
        return super()._scan()


def build_runtime(
    database_path: Path,
) -> tuple[
    SQLiteEventStore,
    SQLiteEventSourceCheckpointStore,
    EventSourceRuntime,
]:
    database = SQLiteDatabase(database_path)
    events = SQLiteEventStore(database)
    checkpoints = SQLiteEventSourceCheckpointStore(database)
    return events, checkpoints, EventSourceRuntime(EventRuntime(events), checkpoints)


def test_filesystem_source_reports_metadata_only_lifecycle(tmp_path: Path) -> None:
    root = tmp_path / "allowlisted"
    root.mkdir()
    seed = root / "seed.txt"
    seed.write_text("PRIVATE-SEED-CONTENT", encoding="utf-8")
    source = FilesystemEventSource(source_id="files.local", root=root)

    baseline = source.poll(cursor=None, limit=10)

    assert baseline.observations == ()
    assert baseline.next_cursor is not None
    assert str(root) not in baseline.next_cursor
    assert "PRIVATE-SEED-CONTENT" not in baseline.next_cursor
    assert json.loads(baseline.next_cursor)["sequence"] == 0

    created = root / "created.txt"
    created.write_text("PRIVATE-CREATED-CONTENT", encoding="utf-8")
    creation = source.poll(cursor=baseline.next_cursor, limit=10)

    assert len(creation.observations) == 1
    created_observation = creation.observations[0]
    assert created_observation.event_type == "filesystem.created"
    assert created_observation.payload["path"] == "created.txt"
    assert "PRIVATE-CREATED-CONTENT" not in json.dumps(created_observation.payload)
    assert "device" not in created_observation.payload
    assert "inode" not in created_observation.payload

    created.write_text("PRIVATE-MODIFIED-CONTENT-LONGER", encoding="utf-8")
    modification = source.poll(cursor=creation.next_cursor, limit=10)

    assert [item.event_type for item in modification.observations] == ["filesystem.modified"]
    assert (
        modification.observations[0].payload["previous_size"]
        != (modification.observations[0].payload["size"])
    )

    moved = root / "moved.txt"
    created.rename(moved)
    movement = source.poll(cursor=modification.next_cursor, limit=10)

    assert [item.event_type for item in movement.observations] == ["filesystem.moved"]
    assert movement.observations[0].payload["previous_path"] == "created.txt"
    assert movement.observations[0].payload["path"] == "moved.txt"

    moved.unlink()
    deletion = source.poll(cursor=movement.next_cursor, limit=10)

    assert [item.event_type for item in deletion.observations] == ["filesystem.deleted"]
    assert deletion.observations[0].payload["path"] == "moved.txt"
    external_ids = {
        created_observation.external_id,
        modification.observations[0].external_id,
        movement.observations[0].external_id,
        deletion.observations[0].external_id,
    }
    assert len(external_ids) == 4


def test_filesystem_source_pages_deterministically_and_replays_stably(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    source = FilesystemEventSource(source_id="files.paged", root=root)
    baseline = source.poll(cursor=None, limit=2)

    for name in ("c.txt", "a.txt", "b.txt"):
        (root / name).write_text(name, encoding="utf-8")

    first = source.poll(cursor=baseline.next_cursor, limit=2)
    replay = source.poll(cursor=baseline.next_cursor, limit=2)
    second = source.poll(cursor=first.next_cursor, limit=2)

    assert [item.payload["path"] for item in first.observations] == [
        "a.txt",
        "b.txt",
    ]
    assert replay == first
    assert [item.payload["path"] for item in second.observations] == ["c.txt"]
    assert set(item.external_id for item in first.observations).isdisjoint(
        item.external_id for item in second.observations
    )


def test_replay_after_event_publish_reuses_record_and_advances_checkpoint(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    database_path = tmp_path / "ally.sqlite3"
    events, checkpoints, runtime = build_runtime(database_path)
    source = FilesystemEventSource(source_id="files.replay", root=root)
    baseline = runtime.poll(source)
    assert baseline.to_cursor is not None

    (root / "new.txt").write_text("private", encoding="utf-8")
    pending = source.poll(cursor=baseline.to_cursor, limit=10)
    observation = pending.observations[0]
    existing = EventRuntime(events).publish(
        NewEvent(
            type=observation.event_type,
            source="source:files.replay",
            importance=observation.importance,
            payload={
                "source": {
                    "id": "files.replay",
                    "external_id": observation.external_id,
                },
                "data": observation.payload,
            },
            dedupe_key=f"source:files.replay:{observation.external_id}",
        )
    )

    reopened = EventSourceRuntime(
        EventRuntime(SQLiteEventStore(SQLiteDatabase(database_path))),
        SQLiteEventSourceCheckpointStore(SQLiteDatabase(database_path)),
    )
    report = reopened.poll(source)

    assert report.event_ids == (existing.id,)
    assert len(events.list()) == 1
    checkpoint = checkpoints.get(source.id)
    assert checkpoint is not None
    assert checkpoint.cursor == pending.next_cursor


def test_scan_failure_keeps_checkpoint_and_next_poll_recovers(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _, checkpoints, runtime = build_runtime(tmp_path / "ally.sqlite3")
    source = FailableFilesystemSource(source_id="files.failure", root=root)
    baseline = runtime.poll(source)
    (root / "new.txt").write_text("private", encoding="utf-8")

    source.fail = True
    with pytest.raises(ValueError, match="synthetic scan failure"):
        runtime.poll(source)

    unchanged = checkpoints.get(source.id)
    assert unchanged is not None
    assert unchanged.cursor == baseline.to_cursor
    assert unchanged.observations_published == 0

    source.fail = False
    recovered = runtime.poll(source)
    assert recovered.published == 1


def test_hidden_symlink_special_and_root_escape_behavior(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "private.txt").write_text("OUTSIDE-PRIVATE-CONTENT", encoding="utf-8")
    source = FilesystemEventSource(source_id="files.safe", root=root)
    baseline = source.poll(cursor=None, limit=10)

    (root / ".hidden.txt").write_text("HIDDEN-PRIVATE-CONTENT", encoding="utf-8")
    (root / "outside-link").symlink_to(outside, target_is_directory=True)
    (root / "visible.txt").write_text("VISIBLE-PRIVATE-CONTENT", encoding="utf-8")
    report = source.poll(cursor=baseline.next_cursor, limit=10)

    assert [item.payload["path"] for item in report.observations] == ["visible.txt"]
    rendered = json.dumps(report.model_dump(mode="json"))
    assert "HIDDEN-PRIVATE-CONTENT" not in rendered
    assert "OUTSIDE-PRIVATE-CONTENT" not in rendered

    root_link = tmp_path / "root-link"
    root_link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="cannot be a symbolic link"):
        FilesystemEventSource(source_id="files.escape", root=root_link)

    hidden_source = FilesystemEventSource(
        source_id="files.hidden",
        root=root,
        include_hidden=True,
    )
    hidden_baseline = hidden_source.poll(cursor=None, limit=10)
    (root / ".another-hidden.txt").write_text("private", encoding="utf-8")
    hidden_report = hidden_source.poll(cursor=hidden_baseline.next_cursor, limit=10)
    assert [item.payload["path"] for item in hidden_report.observations] == [".another-hidden.txt"]


def test_source_rejects_unbounded_scan_and_malformed_cursor(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "one.txt").write_text("one", encoding="utf-8")
    (root / "two.txt").write_text("two", encoding="utf-8")
    bounded = FilesystemEventSource(
        source_id="files.bounded",
        root=root,
        max_entries=1,
    )

    with pytest.raises(ValueError, match="max_entries"):
        bounded.poll(cursor=None, limit=10)

    source = FilesystemEventSource(source_id="files.cursor", root=root)
    bad_cursor = json.dumps(
        {
            "version": 1,
            "sequence": 0,
            "entries": [
                {
                    "path": "../outside.txt",
                    "device": 1,
                    "inode": 1,
                    "size": 1,
                    "modified_ns": 1,
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="invalid relative path"):
        source.poll(cursor=bad_cursor, limit=10)


def test_filesystem_events_flow_through_existing_proactive_cycle(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
    events = SQLiteEventStore(database)
    checkpoints = SQLiteEventSourceCheckpointStore(database)
    source_runtime = EventSourceRuntime(EventRuntime(events), checkpoints)
    source = FilesystemEventSource(
        source_id="files.proactive",
        root=root,
        importance="important",
    )
    source_runtime.poll(source)
    (root / "new.txt").write_text("private", encoding="utf-8")
    polled_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    source_report = source_runtime.poll(source, polled_at=polled_at)

    sink = RecordingSink()
    cycle = ProactiveServiceCycle(
        SchedulerRuntime(SQLiteScheduleStore(database), EventRuntime(events)),
        AttentionDeliveryRuntime(events, SQLiteAttentionDeliveryStore(database)),
    )
    cycle_report = cycle.run(as_of=polled_at, sinks=(sink,))

    assert source_report.published == 1
    assert cycle_report.delivery_attempts == 1
    assert sink.events[0].type == "filesystem.created"
    data = cast(dict[str, JsonValue], sink.events[0].payload["data"])
    assert data["path"] == "new.txt"
