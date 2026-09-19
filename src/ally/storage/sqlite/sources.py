"""SQLite persistence for external event-source checkpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from ally.sources import EventSourceCheckpoint, EventSourceConflictError
from ally.sources.runtime import validate_source_id
from ally.storage.sqlite.database import SQLiteDatabase

CheckpointRow = tuple[
    str,
    str | None,
    int,
    int,
    str,
    str,
    str,
]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("checkpoint timestamp must include a timezone offset")
    return value.astimezone(UTC)


class SQLiteEventSourceCheckpointStore:
    """Persist successful opaque cursors with compare-and-set advancement."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def get(self, source_id: str) -> EventSourceCheckpoint | None:
        validated = validate_source_id(source_id)
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    source_id,
                    cursor,
                    successful_polls,
                    observations_published,
                    last_polled_at,
                    created_at,
                    updated_at
                FROM event_source_checkpoints
                WHERE source_id = ?
                """,
                (validated,),
            ).fetchone()

        if row is None:
            return None
        return self._from_row(cast(CheckpointRow, row))

    def advance(
        self,
        *,
        source_id: str,
        expected_cursor: str | None,
        next_cursor: str | None,
        published: int,
        polled_at: datetime,
    ) -> EventSourceCheckpoint:
        if published < 0:
            raise ValueError("published cannot be negative")

        validated = validate_source_id(source_id)
        observed_at = _as_utc(polled_at)
        now = datetime.now(UTC)

        with self._database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT
                    source_id,
                    cursor,
                    successful_polls,
                    observations_published,
                    last_polled_at,
                    created_at,
                    updated_at
                FROM event_source_checkpoints
                WHERE source_id = ?
                """,
                (validated,),
            ).fetchone()

            if row is None:
                if expected_cursor is not None:
                    raise EventSourceConflictError(
                        f"event source checkpoint changed: {validated}"
                    )

                connection.execute(
                    """
                    INSERT INTO event_source_checkpoints(
                        source_id,
                        cursor,
                        successful_polls,
                        observations_published,
                        last_polled_at,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        validated,
                        next_cursor,
                        published,
                        observed_at.isoformat(),
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
            else:
                current = self._from_row(cast(CheckpointRow, row))
                if current.cursor != expected_cursor:
                    raise EventSourceConflictError(
                        f"event source checkpoint changed: {validated}"
                    )

                connection.execute(
                    """
                    UPDATE event_source_checkpoints
                    SET
                        cursor = ?,
                        successful_polls = successful_polls + 1,
                        observations_published = observations_published + ?,
                        last_polled_at = ?,
                        updated_at = ?
                    WHERE source_id = ?
                    """,
                    (
                        next_cursor,
                        published,
                        observed_at.isoformat(),
                        now.isoformat(),
                        validated,
                    ),
                )

        loaded = self.get(validated)
        assert loaded is not None
        return loaded

    def list(self, *, limit: int = 50) -> tuple[EventSourceCheckpoint, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        with self._database.connect() as connection:
            rows = cast(
                list[CheckpointRow],
                connection.execute(
                    """
                    SELECT
                        source_id,
                        cursor,
                        successful_polls,
                        observations_published,
                        last_polled_at,
                        created_at,
                        updated_at
                    FROM event_source_checkpoints
                    ORDER BY updated_at DESC, source_id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall(),
            )

        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(row: CheckpointRow) -> EventSourceCheckpoint:
        (
            source_id,
            cursor,
            successful_polls,
            observations_published,
            last_polled_at,
            created_at,
            updated_at,
        ) = row
        return EventSourceCheckpoint(
            source_id=source_id,
            cursor=cursor,
            successful_polls=successful_polls,
            observations_published=observations_published,
            last_polled_at=datetime.fromisoformat(last_polled_at),
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )
