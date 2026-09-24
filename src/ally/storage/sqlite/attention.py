"""SQLite persistence for proactive attention delivery attempts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from ally.attention.models import (
    AttentionDeliveryRecord,
    AttentionDeliveryStatus,
    validate_sink_id,
)
from ally.storage.sqlite.database import SQLiteDatabase

DeliveryRow = tuple[
    str,
    str,
    str,
    str,
    int,
    str | None,
    str,
    str,
    str | None,
]


class SQLiteAttentionDeliveryStore:
    """Persist terminal-success delivery state per event and sink."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def get(
        self,
        event_id: UUID,
        sink_id: str,
    ) -> AttentionDeliveryRecord | None:
        validated_sink = validate_sink_id(sink_id)
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    event_id,
                    sink_id,
                    status,
                    attempts,
                    last_error,
                    created_at,
                    updated_at,
                    delivered_at
                FROM attention_deliveries
                WHERE event_id = ? AND sink_id = ?
                """,
                (str(event_id), validated_sink),
            ).fetchone()

        if row is None:
            return None
        return self._from_row(cast(DeliveryRow, row))

    def list_for_event(
        self,
        event_id: UUID,
    ) -> tuple[AttentionDeliveryRecord, ...]:
        with self._database.connect() as connection:
            rows = cast(
                list[DeliveryRow],
                connection.execute(
                    """
                    SELECT
                        id,
                        event_id,
                        sink_id,
                        status,
                        attempts,
                        last_error,
                        created_at,
                        updated_at,
                        delivered_at
                    FROM attention_deliveries
                    WHERE event_id = ?
                    ORDER BY updated_at DESC, sink_id ASC
                    """,
                    (str(event_id),),
                ).fetchall(),
            )
        return tuple(self._from_row(row) for row in rows)

    def record_attempt(
        self,
        *,
        event_id: UUID,
        sink_id: str,
        succeeded: bool,
        error: str | None = None,
    ) -> AttentionDeliveryRecord:
        validated_sink = validate_sink_id(sink_id)
        current = self.get(event_id, validated_sink)
        if current is not None and current.status == "succeeded":
            return current

        now = datetime.now(UTC)
        status: AttentionDeliveryStatus = "succeeded" if succeeded else "failed"
        last_error = None if succeeded else (None if error is None else error[:1000])
        delivered_at = now if succeeded else None

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO attention_deliveries(
                    id,
                    event_id,
                    sink_id,
                    status,
                    attempts,
                    last_error,
                    created_at,
                    updated_at,
                    delivered_at
                )
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(event_id, sink_id) DO UPDATE SET
                    status = excluded.status,
                    attempts = attention_deliveries.attempts + 1,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at,
                    delivered_at = excluded.delivered_at
                WHERE attention_deliveries.status != 'succeeded'
                """,
                (
                    str(uuid4()),
                    str(event_id),
                    validated_sink,
                    status,
                    last_error,
                    now.isoformat(),
                    now.isoformat(),
                    None if delivered_at is None else delivered_at.isoformat(),
                ),
            )

        loaded = self.get(event_id, validated_sink)
        assert loaded is not None
        return loaded

    def list(
        self,
        *,
        limit: int = 50,
        status: AttentionDeliveryStatus | None = None,
    ) -> tuple[AttentionDeliveryRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        query = """
            SELECT
                id,
                event_id,
                sink_id,
                status,
                attempts,
                last_error,
                created_at,
                updated_at,
                delivered_at
            FROM attention_deliveries
        """
        params: tuple[object, ...]
        if status is None:
            query += " ORDER BY updated_at DESC, id ASC LIMIT ?"
            params = (limit,)
        else:
            query += " WHERE status = ? ORDER BY updated_at DESC, id ASC LIMIT ?"
            params = (status, limit)

        with self._database.connect() as connection:
            rows = cast(
                list[DeliveryRow],
                connection.execute(query, params).fetchall(),
            )

        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(row: DeliveryRow) -> AttentionDeliveryRecord:
        (
            identifier,
            event_id,
            sink_id,
            status,
            attempts,
            last_error,
            created_at,
            updated_at,
            delivered_at,
        ) = row
        return AttentionDeliveryRecord(
            id=UUID(identifier),
            event_id=UUID(event_id),
            sink_id=sink_id,
            status=cast(AttentionDeliveryStatus, status),
            attempts=attempts,
            last_error=last_error,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
            delivered_at=(
                None if delivered_at is None else datetime.fromisoformat(delivered_at)
            ),
        )
