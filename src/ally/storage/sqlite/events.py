"""SQLite persistence for proactive events."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import JsonValue

from ally.events.models import AttentionClass, EventImportance, EventRecord, NewEvent
from ally.storage.sqlite.database import SQLiteDatabase

EventRow = tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str | None,
    str,
    str | None,
]


class SQLiteEventStore:
    """Persist proactive events in Ally's local database."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def create(
        self,
        event: NewEvent,
        *,
        attention: AttentionClass,
    ) -> EventRecord:
        record = EventRecord(
            id=uuid4(),
            type=event.type,
            source=event.source,
            importance=event.importance,
            attention=attention,
            payload=event.payload,
            dedupe_key=event.dedupe_key,
            created_at=datetime.now(UTC),
        )

        with self._database.connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO event_records(
                        id,
                        type,
                        source,
                        importance,
                        attention,
                        payload_json,
                        dedupe_key,
                        created_at,
                        handled_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(record.id),
                        record.type,
                        record.source,
                        record.importance,
                        record.attention,
                        json.dumps(record.payload, sort_keys=True),
                        record.dedupe_key,
                        record.created_at.isoformat(),
                        None,
                    ),
                )
            except sqlite3.IntegrityError:
                if event.dedupe_key is None:
                    raise
                row = connection.execute(
                    """
                    SELECT
                        id,
                        type,
                        source,
                        importance,
                        attention,
                        payload_json,
                        dedupe_key,
                        created_at,
                        handled_at
                    FROM event_records
                    WHERE dedupe_key = ?
                    """,
                    (event.dedupe_key,),
                ).fetchone()
                if row is None:
                    raise
                return self._from_row(cast(EventRow, row))

        return record

    def get(self, event_id: UUID) -> EventRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    type,
                    source,
                    importance,
                    attention,
                    payload_json,
                    dedupe_key,
                    created_at,
                    handled_at
                FROM event_records
                WHERE id = ?
                """,
                (str(event_id),),
            ).fetchone()

        if row is None:
            return None
        return self._from_row(cast(EventRow, row))

    def list(
        self,
        *,
        limit: int = 50,
        attention: AttentionClass | None = None,
        handled: bool | None = None,
    ) -> tuple[EventRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        clauses: list[str] = []
        params: list[object] = []

        if attention is not None:
            clauses.append("attention = ?")
            params.append(attention)

        if handled is True:
            clauses.append("handled_at IS NOT NULL")
        elif handled is False:
            clauses.append("handled_at IS NULL")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        query = f"""
            SELECT
                id,
                type,
                source,
                importance,
                attention,
                payload_json,
                dedupe_key,
                created_at,
                handled_at
            FROM event_records
            {where}
            ORDER BY created_at DESC
            LIMIT ?
        """

        with self._database.connect() as connection:
            rows = cast(
                list[EventRow],
                connection.execute(query, tuple(params)).fetchall(),
            )

        return tuple(self._from_row(row) for row in rows)

    def pending_attention(
        self,
        *,
        attentions: tuple[AttentionClass, ...],
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[EventRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset cannot be negative")
        if not attentions:
            return ()

        placeholders = ", ".join("?" for _ in attentions)
        query = f"""
            SELECT
                id,
                type,
                source,
                importance,
                attention,
                payload_json,
                dedupe_key,
                created_at,
                handled_at
            FROM event_records
            WHERE handled_at IS NULL
              AND attention IN ({placeholders})
            ORDER BY
                CASE attention
                    WHEN 'interrupt' THEN 0
                    WHEN 'notify' THEN 1
                    WHEN 'mention_later' THEN 2
                    ELSE 3
                END,
                created_at ASC,
                id ASC
            LIMIT ? OFFSET ?
        """
        params: tuple[object, ...] = (*attentions, limit, offset)

        with self._database.connect() as connection:
            rows = cast(
                list[EventRow],
                connection.execute(query, params).fetchall(),
            )

        return tuple(self._from_row(row) for row in rows)

    def mark_handled(self, event_id: UUID) -> EventRecord:
        handled_at = datetime.now(UTC)
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE event_records
                SET handled_at = COALESCE(handled_at, ?)
                WHERE id = ?
                """,
                (handled_at.isoformat(), str(event_id)),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown event: {event_id}")

        loaded = self.get(event_id)
        assert loaded is not None
        return loaded

    @staticmethod
    def _from_row(row: EventRow) -> EventRecord:
        (
            identifier,
            event_type,
            source,
            importance,
            attention,
            payload_json,
            dedupe_key,
            created_at,
            handled_at,
        ) = row
        return EventRecord(
            id=UUID(identifier),
            type=event_type,
            source=source,
            importance=cast(EventImportance, importance),
            attention=cast(AttentionClass, attention),
            payload=cast(dict[str, JsonValue], json.loads(payload_json)),
            dedupe_key=dedupe_key,
            created_at=datetime.fromisoformat(created_at),
            handled_at=(
                None if handled_at is None else datetime.fromisoformat(handled_at)
            ),
        )
