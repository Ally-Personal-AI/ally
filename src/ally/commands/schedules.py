"""Human-facing deterministic scheduler commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from ally.commands._storage import build_event_store, build_schedule_store
from ally.events import EventImportance, EventRuntime
from ally.scheduler import (
    NewSchedule,
    ScheduleConflictError,
    SchedulerRuntime,
)


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {value}") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("schedule timestamp must include a timezone offset")
    return parsed.astimezone(UTC)


def _parse_payload(value: str) -> dict[str, JsonValue]:
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"schedule payload must be valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("schedule payload must be a JSON object")
    return cast(dict[str, JsonValue], raw)


def run_create_schedule(
    *,
    name: str,
    event_type: str,
    at: str,
    every_seconds: int | None,
    importance: EventImportance,
    payload_json: str,
    disabled: bool,
) -> int:
    try:
        schedule = NewSchedule(
            name=name,
            event_type=event_type,
            importance=importance,
            payload=_parse_payload(payload_json),
            starts_at=_parse_timestamp(at),
            interval_seconds=every_seconds,
            enabled=not disabled,
        )
        record = build_schedule_store().create(schedule)
    except ValueError as exc:
        print(f"Schedule error: {exc}")
        return 2

    print(record.id)
    return 0


def run_list_schedules(*, limit: int) -> int:
    try:
        records = build_schedule_store().list(limit=limit)
    except ValueError as exc:
        print(f"Schedule error: {exc}")
        return 2

    if not records:
        print("No schedules.")
        return 0

    for record in records:
        state = "enabled" if record.enabled else "disabled"
        recurrence = (
            "once"
            if record.interval_seconds is None
            else f"every {record.interval_seconds}s"
        )
        next_run = (
            "(complete)"
            if record.next_run_at is None
            else record.next_run_at.isoformat()
        )
        print(
            f"{record.id}  {state}  {recurrence}  "
            f"{next_run}  {record.name}"
        )
    return 0


def run_show_schedule(*, schedule_id: str) -> int:
    try:
        identifier = UUID(schedule_id)
    except ValueError:
        print(f"Invalid schedule ID: {schedule_id}")
        return 2

    record = build_schedule_store().get(identifier)
    if record is None:
        print(f"Schedule not found: {identifier}")
        return 2

    print(f"Schedule: {record.id}")
    print(f"Name: {record.name}")
    print(f"Event type: {record.event_type}")
    print(f"Importance: {record.importance}")
    print(f"Enabled: {record.enabled}")
    print(f"Starts: {record.starts_at.isoformat()}")
    print(f"Interval seconds: {record.interval_seconds}")
    print(
        "Next run: "
        + (
            record.next_run_at.isoformat()
            if record.next_run_at is not None
            else "(complete)"
        )
    )
    print(
        "Last run: "
        + (
            record.last_run_at.isoformat()
            if record.last_run_at is not None
            else "(never)"
        )
    )
    print(json.dumps(record.payload, indent=2, sort_keys=True))
    return 0


def run_set_schedule_enabled(
    *,
    schedule_id: str,
    enabled: bool,
) -> int:
    try:
        identifier = UUID(schedule_id)
    except ValueError:
        print(f"Invalid schedule ID: {schedule_id}")
        return 2

    try:
        record = build_schedule_store().set_enabled(
            identifier,
            enabled=enabled,
        )
    except (KeyError, ValueError) as exc:
        print(f"Schedule error: {exc}")
        return 2

    state = "enabled" if record.enabled else "disabled"
    print(f"{record.id}  {state}")
    return 0


def run_tick_schedules(
    *,
    at: str | None,
    limit: int,
) -> int:
    try:
        as_of = datetime.now(UTC) if at is None else _parse_timestamp(at)
        runtime = SchedulerRuntime(
            build_schedule_store(),
            EventRuntime(build_event_store()),
        )
        results = runtime.tick(as_of=as_of, limit=limit)
    except (ScheduleConflictError, ValueError) as exc:
        print(f"Schedule error: {exc}")
        return 2

    if not results:
        print("No schedules due.")
        return 0

    for result in results:
        next_run = (
            "(complete)"
            if result.next_run_at is None
            else result.next_run_at.isoformat()
        )
        print(
            f"{result.schedule_id}  event={result.event_id}  "
            f"coalesced={result.coalesced_occurrences}  next={next_run}"
        )
    return 0
