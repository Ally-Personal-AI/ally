"""SQLite implementation of Ally long-term memory."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from ally.memory import (
    MemoryKind,
    MemoryPrivacy,
    MemoryRecord,
    MemorySource,
    MemorySourceType,
    NewMemory,
)
from ally.storage.sqlite.database import SQLiteDatabase

MemoryRow = tuple[
    str,
    str,
    str,
    str,
    str | None,
    str | None,
    float,
    float,
    str,
    str,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _optional_utc_iso(value: datetime | None) -> str | None:
    return None if value is None else _utc_iso(value)


class SQLiteMemoryStore:
    """Persist temporal memories in Ally's local SQLite database."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def create(self, memory: NewMemory) -> MemoryRecord:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            record = self._insert(
                connection,
                memory,
                created_at=now,
                supersedes=None,
            )
        return record

    def get(self, memory_id: UUID) -> MemoryRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                self._select_sql("WHERE id = ?"),
                (str(memory_id),),
            ).fetchone()
        if row is None:
            return None
        return self._from_row(cast(MemoryRow, row))

    def list(
        self,
        *,
        as_of: datetime | None = None,
        kind: MemoryKind | None = None,
        include_inactive: bool = False,
        limit: int = 100,
    ) -> tuple[MemoryRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        conditions: list[str] = []
        parameters: list[object] = []

        if not include_inactive:
            moment = as_of or datetime.now(UTC)
            moment_iso = _utc_iso(moment)
            conditions.extend(
                (
                    "created_at <= ?",
                    "(superseded_at IS NULL OR superseded_at > ?)",
                    "(retracted_at IS NULL OR retracted_at > ?)",
                    "(valid_from IS NULL OR valid_from <= ?)",
                    "(valid_until IS NULL OR valid_until > ?)",
                )
            )
            parameters.extend([moment_iso] * 5)

        if kind is not None:
            conditions.append("kind = ?")
            parameters.append(kind)

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        parameters.append(limit)
        with self._database.connect() as connection:
            rows = cast(
                list[MemoryRow],
                connection.execute(
                    self._select_sql(
                        f"{where} ORDER BY importance DESC, updated_at DESC LIMIT ?"
                    ),
                    tuple(parameters),
                ).fetchall(),
            )
        return tuple(self._from_row(row) for row in rows)

    def search(self, query: str, *, limit: int = 20) -> tuple[MemoryRecord, ...]:
        compact = query.strip()
        if not compact:
            return ()
        if limit < 1:
            raise ValueError("limit must be positive")

        now = datetime.now(UTC).isoformat()
        pattern = f"%{compact}%"
        with self._database.connect() as connection:
            rows = cast(
                list[MemoryRow],
                connection.execute(
                    self._select_sql(
                        """
                        WHERE content LIKE ? COLLATE NOCASE
                          AND created_at <= ?
                          AND (superseded_at IS NULL OR superseded_at > ?)
                          AND (retracted_at IS NULL OR retracted_at > ?)
                          AND (valid_from IS NULL OR valid_from <= ?)
                          AND (valid_until IS NULL OR valid_until > ?)
                        ORDER BY importance DESC, updated_at DESC
                        LIMIT ?
                        """
                    ),
                    (pattern, now, now, now, now, now, limit),
                ).fetchall(),
            )
        return tuple(self._from_row(row) for row in rows)

    def supersede(
        self,
        memory_id: UUID,
        replacement: NewMemory,
    ) -> tuple[MemoryRecord, MemoryRecord]:
        now = datetime.now(UTC)

        with self._database.connect() as connection:
            old_row = connection.execute(
                self._select_sql("WHERE id = ?"),
                (str(memory_id),),
            ).fetchone()
            if old_row is None:
                raise KeyError(f"Unknown memory: {memory_id}")

            old = self._from_row(cast(MemoryRow, old_row))
            if old.superseded_at is not None or old.retracted_at is not None:
                raise ValueError("Only an active memory can be superseded")

            new = self._insert(
                connection,
                replacement,
                created_at=now,
                supersedes=old.id,
            )
            connection.execute(
                """
                UPDATE memory_records
                SET updated_at = ?, superseded_at = ?, superseded_by = ?
                WHERE id = ?
                """,
                (now.isoformat(), now.isoformat(), str(new.id), str(old.id)),
            )

        updated_old = old.model_copy(
            update={
                "updated_at": now,
                "superseded_at": now,
                "superseded_by": new.id,
            }
        )
        return updated_old, new

    def retract(self, memory_id: UUID) -> MemoryRecord:
        existing = self.get(memory_id)
        if existing is None:
            raise KeyError(f"Unknown memory: {memory_id}")
        if existing.retracted_at is not None:
            return existing

        now = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE memory_records
                SET updated_at = ?, retracted_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), now.isoformat(), str(memory_id)),
            )
        return existing.model_copy(
            update={"updated_at": now, "retracted_at": now}
        )

    def _insert(
        self,
        connection: sqlite3.Connection,
        memory: NewMemory,
        *,
        created_at: datetime,
        supersedes: UUID | None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            id=uuid4(),
            kind=memory.kind,
            content=memory.content,
            source=memory.source,
            confidence=memory.confidence,
            importance=memory.importance,
            privacy=memory.privacy,
            created_at=created_at,
            updated_at=created_at,
            observed_at=memory.observed_at,
            valid_from=memory.valid_from,
            valid_until=memory.valid_until,
            supersedes=supersedes,
        )
        connection.execute(
            """
            INSERT INTO memory_records(
                id, kind, content, source_type, source_id, source_uri,
                confidence, importance, privacy, created_at, updated_at,
                observed_at, valid_from, valid_until, supersedes,
                superseded_at, superseded_by, retracted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(record.id),
                record.kind,
                record.content,
                record.source.type,
                record.source.id,
                record.source.uri,
                record.confidence,
                record.importance,
                record.privacy,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
                _optional_utc_iso(record.observed_at),
                _optional_utc_iso(record.valid_from),
                _optional_utc_iso(record.valid_until),
                str(record.supersedes) if record.supersedes is not None else None,
                None,
                None,
                None,
            ),
        )
        return record

    @staticmethod
    def _select_sql(suffix: str) -> str:
        return f"""
            SELECT
                id, kind, content, source_type, source_id, source_uri,
                confidence, importance, privacy, created_at, updated_at,
                observed_at, valid_from, valid_until, supersedes,
                superseded_at, superseded_by, retracted_at
            FROM memory_records
            {suffix}
        """

    @staticmethod
    def _from_row(row: MemoryRow) -> MemoryRecord:
        (
            identifier,
            kind,
            content,
            source_type,
            source_id,
            source_uri,
            confidence,
            importance,
            privacy,
            created_at,
            updated_at,
            observed_at,
            valid_from,
            valid_until,
            supersedes,
            superseded_at,
            superseded_by,
            retracted_at,
        ) = row

        return MemoryRecord(
            id=UUID(identifier),
            kind=cast(MemoryKind, kind),
            content=content,
            source=MemorySource(
                type=cast(MemorySourceType, source_type),
                id=source_id,
                uri=source_uri,
            ),
            confidence=confidence,
            importance=importance,
            privacy=cast(MemoryPrivacy, privacy),
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
            observed_at=(
                datetime.fromisoformat(observed_at)
                if observed_at is not None
                else None
            ),
            valid_from=(
                datetime.fromisoformat(valid_from)
                if valid_from is not None
                else None
            ),
            valid_until=(
                datetime.fromisoformat(valid_until)
                if valid_until is not None
                else None
            ),
            supersedes=UUID(supersedes) if supersedes is not None else None,
            superseded_at=(
                datetime.fromisoformat(superseded_at)
                if superseded_at is not None
                else None
            ),
            superseded_by=(
                UUID(superseded_by) if superseded_by is not None else None
            ),
            retracted_at=(
                datetime.fromisoformat(retracted_at)
                if retracted_at is not None
                else None
            ),
        )
