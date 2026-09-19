"""Human-facing external event-source commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ally.commands._storage import (
    build_event_source_checkpoint_store,
    build_event_store,
)
from ally.events import EventImportance, EventRuntime
from ally.sources import (
    EventSourceConflictError,
    EventSourceRuntime,
    FilesystemEventSource,
    JsonlEventSource,
)
from ally.sources.runtime import validate_source_id


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {value}") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("source poll timestamp must include a timezone offset")
    return parsed.astimezone(UTC)


def run_poll_jsonl_source(
    *,
    source_id: str,
    path: str,
    limit: int,
    at: str | None,
    json_output: bool,
) -> int:
    try:
        polled_at = None if at is None else _parse_timestamp(at)
        runtime = EventSourceRuntime(
            EventRuntime(build_event_store()),
            build_event_source_checkpoint_store(),
        )
        report = runtime.poll(
            JsonlEventSource(
                source_id=source_id,
                path=Path(path),
            ),
            limit=limit,
            polled_at=polled_at,
        )
    except (EventSourceConflictError, ValueError) as exc:
        print(f"Source error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                report.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Source: {report.source_id}")
        print(f"From cursor: {report.from_cursor or '(start)'}")
        print(f"To cursor: {report.to_cursor or '(none)'}")
        print(f"Published: {report.published}")

    return 0


def run_poll_filesystem_source(
    *,
    source_id: str,
    root: str,
    limit: int,
    max_entries: int,
    include_hidden: bool,
    importance: EventImportance,
    at: str | None,
    json_output: bool,
) -> int:
    try:
        polled_at = None if at is None else _parse_timestamp(at)
        runtime = EventSourceRuntime(
            EventRuntime(build_event_store()),
            build_event_source_checkpoint_store(),
        )
        report = runtime.poll(
            FilesystemEventSource(
                source_id=source_id,
                root=Path(root),
                max_entries=max_entries,
                include_hidden=include_hidden,
                importance=importance,
            ),
            limit=limit,
            polled_at=polled_at,
        )
    except (EventSourceConflictError, ValueError) as exc:
        print(f"Source error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                report.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Source: {report.source_id}")
        print(f"Published: {report.published}")
        print(f"Snapshot cursor bytes: {len(report.to_cursor or '')}")

    return 0


def run_list_source_checkpoints(*, limit: int) -> int:
    try:
        records = build_event_source_checkpoint_store().list(limit=limit)
    except ValueError as exc:
        print(f"Source error: {exc}")
        return 2

    if not records:
        print("No event-source checkpoints.")
        return 0

    for record in records:
        cursor = record.cursor if record.cursor is not None else "(none)"
        print(
            f"{record.source_id}  cursor={cursor}  "
            f"polls={record.successful_polls}  "
            f"published={record.observations_published}"
        )
    return 0


def run_show_source_checkpoint(*, source_id: str) -> int:
    try:
        validated = validate_source_id(source_id)
    except ValueError as exc:
        print(f"Source error: {exc}")
        return 2

    record = build_event_source_checkpoint_store().get(validated)
    if record is None:
        print(f"Event-source checkpoint not found: {validated}")
        return 2

    print(f"Source: {record.source_id}")
    print(f"Cursor: {record.cursor or '(none)'}")
    print(f"Successful polls: {record.successful_polls}")
    print(f"Observations published: {record.observations_published}")
    print(f"Last polled: {record.last_polled_at.isoformat()}")
    print(f"Created: {record.created_at.isoformat()}")
    print(f"Updated: {record.updated_at.isoformat()}")
    return 0
