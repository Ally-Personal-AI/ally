"""SQLite persistence for deterministic schedules."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import JsonValue

from ally.events import EventImportance
from ally.scheduler import (
    NewSchedule,
    ScheduleConflictError,
    ScheduleRecord,
)
from ally.storage.sqlite.database import SQLiteDatabase

ScheduleRow = tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    int | None,
    str | None,
    str | None,
    int,
    str,
    str,
]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("schedule timestamps must include a timezone offset")
    return value.astimezone(UTC)


class SQLiteScheduleStore:
    """Persist one-shot and fixed-interval schedules."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def create(self, schedule: NewSchedule) -> ScheduleRecord:
        starts_at = _utc(schedule.starts_at)
        now = datetime.now(UTC)
        record = ScheduleRecord(
            id=uuid4(),
            name=schedule.name,
            event_type=schedule.event_type,
            importance=schedule.importance,
            payload=schedule.payload,
            starts_at=starts_at,
            interval_seconds=schedule.interval_seconds,
            next_run_at=starts_at,
            last_run_at=None,
            enabled=schedule.enabled,
            created_at=now,
            updated_at=now,
        )

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO schedules(
                    id,
                    name,
                    event_type,
                    importance,
                    payload_json,
                    starts_at,
                    interval_seconds,
                    next_run_at,
                    last_run_at,
                    enabled,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.id),
                    record.name,
                    record.event_type,
                    record.importance,
                    json.dumps(record.payload, sort_keys=True),
                    record.starts_at.isoformat(),
                    record.interval_seconds,
                    record.next_run_at.isoformat()
                    if record.next_run_at is not None
                    else None,
                    None,
                    int(record.enabled),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )

        return record

    def get(self, schedule_id: UUID) -> ScheduleRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    name,
                    event_type,
                    importance,
                    payload_json,
                    starts_at,
                    interval_seconds,
                    next_run_at,
                    last_run_at,
                    enabled,
                    created_at,
                    updated_at
                FROM schedules
                WHERE id = ?
                """,
                (str(schedule_id),),
            ).fetchone()

        if row is None:
            return None
        return self._from_row(cast(ScheduleRow, row))

    def list(self, *, limit: int = 50) -> tuple[ScheduleRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        with self._database.connect() as connection:
            rows = cast(
                list[ScheduleRow],
                connection.execute(
                    """
                    SELECT
                        id,
                        name,
                        event_type,
                        importance,
                        payload_json,
                        starts_at,
                        interval_seconds,
                        next_run_at,
                        last_run_at,
                        enabled,
                        created_at,
                        updated_at
                    FROM schedules
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall(),
            )

        return tuple(self._from_row(row) for row in rows)

    def due(
        self,
        *,
        as_of: datetime,
        limit: int = 100,
    ) -> tuple[ScheduleRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        cutoff = _utc(as_of).isoformat()
        with self._database.connect() as connection:
            rows = cast(
                list[ScheduleRow],
                connection.execute(
                    """
                    SELECT
                        id,
                        name,
                        event_type,
                        importance,
                        payload_json,
                        starts_at,
                        interval_seconds,
                        next_run_at,
                        last_run_at,
                        enabled,
                        created_at,
                        updated_at
                    FROM schedules
                    WHERE enabled = 1
                      AND next_run_at IS NOT NULL
                      AND next_run_at <= ?
                    ORDER BY next_run_at ASC, id ASC
                    LIMIT ?
                    """,
                    (cutoff, limit),
                ).fetchall(),
            )

        return tuple(self._from_row(row) for row in rows)

    def set_enabled(
        self,
        schedule_id: UUID,
        *,
        enabled: bool,
    ) -> ScheduleRecord:
        current = self.get(schedule_id)
        if current is None:
            raise KeyError(f"Unknown schedule: {schedule_id}")
        if enabled and current.next_run_at is None:
            raise ValueError("completed one-shot schedule cannot be re-enabled")

        updated_at = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE schedules
                SET enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    int(enabled),
                    updated_at.isoformat(),
                    str(schedule_id),
                ),
            )

        loaded = self.get(schedule_id)
        assert loaded is not None
        return loaded

    def advance(
        self,
        schedule_id: UUID,
        *,
        expected_next_run_at: datetime,
        next_run_at: datetime | None,
        last_run_at: datetime,
        enabled: bool,
    ) -> ScheduleRecord:
        expected = _utc(expected_next_run_at)
        next_value = None if next_run_at is None else _utc(next_run_at)
        last_value = _utc(last_run_at)
        updated_at = datetime.now(UTC)

        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE schedules
                SET
                    next_run_at = ?,
                    last_run_at = ?,
                    enabled = ?,
                    updated_at = ?
                WHERE id = ?
                  AND enabled = 1
                  AND next_run_at = ?
                """,
                (
                    None if next_value is None else next_value.isoformat(),
                    last_value.isoformat(),
                    int(enabled),
                    updated_at.isoformat(),
                    str(schedule_id),
                    expected.isoformat(),
                ),
            )
            if cursor.rowcount != 1:
                raise ScheduleConflictError(
                    f"schedule changed before advancement: {schedule_id}"
                )

        loaded = self.get(schedule_id)
        assert loaded is not None
        return loaded

    @staticmethod
    def _from_row(row: ScheduleRow) -> ScheduleRecord:
        (
            identifier,
            name,
            event_type,
            importance,
            payload_json,
            starts_at,
            interval_seconds,
            next_run_at,
            last_run_at,
            enabled,
            created_at,
            updated_at,
        ) = row
        return ScheduleRecord(
            id=UUID(identifier),
            name=name,
            event_type=event_type,
            importance=cast(EventImportance, importance),
            payload=cast(dict[str, JsonValue], json.loads(payload_json)),
            starts_at=datetime.fromisoformat(starts_at),
            interval_seconds=interval_seconds,
            next_run_at=(
                None if next_run_at is None else datetime.fromisoformat(next_run_at)
            ),
            last_run_at=(
                None if last_run_at is None else datetime.fromisoformat(last_run_at)
            ),
            enabled=bool(enabled),
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )
