"""SQLite implementation of versioned personal knowledge."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from ally.knowledge import (
    KnowledgeChunk,
    KnowledgeRevision,
    KnowledgeSource,
    NewKnowledgeChunk,
    NewKnowledgeSource,
)
from ally.storage.sqlite.database import SQLiteDatabase

SourceRow = tuple[str, str, str, str, int, str, str]
RevisionRow = tuple[str, str, int, str, str]
ChunkRow = tuple[str, str, str, int, int, str, int, int, str, str]


class SQLiteKnowledgeStore:
    """Persist versioned knowledge sources and chunks in SQLite."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def ingest(
        self,
        source: NewKnowledgeSource,
        *,
        source_sha256: str,
        chunks: Sequence[NewKnowledgeChunk],
    ) -> tuple[KnowledgeSource, KnowledgeRevision]:
        self._validate_ingest(source_sha256, chunks)
        now = datetime.now(UTC)

        with self._database.connect() as connection:
            source_row = connection.execute(
                """
                SELECT id, uri, title, media_type, current_revision, created_at, updated_at
                FROM knowledge_sources
                WHERE uri = ?
                """,
                (source.uri,),
            ).fetchone()

            if source_row is None:
                source_id = uuid4()
                revision_number = 1
                connection.execute(
                    """
                    INSERT INTO knowledge_sources(
                        id, uri, title, media_type, current_revision, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(source_id),
                        source.uri,
                        source.title,
                        source.media_type,
                        revision_number,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                created_at = now
            else:
                existing = self._source_from_row(cast(SourceRow, source_row))
                source_id = existing.id
                current_revision_row = connection.execute(
                    """
                    SELECT id, source_id, revision, sha256, created_at
                    FROM knowledge_revisions
                    WHERE source_id = ? AND revision = ?
                    """,
                    (str(source_id), existing.current_revision),
                ).fetchone()
                if current_revision_row is None:
                    raise RuntimeError("Knowledge source points to a missing revision.")

                current_revision = self._revision_from_row(
                    cast(RevisionRow, current_revision_row)
                )
                if current_revision.sha256 == source_sha256:
                    connection.execute(
                        """
                        UPDATE knowledge_sources
                        SET title = ?, media_type = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            source.title,
                            source.media_type,
                            now.isoformat(),
                            str(source_id),
                        ),
                    )
                    return (
                        existing.model_copy(
                            update={
                                "title": source.title,
                                "media_type": source.media_type,
                                "updated_at": now,
                            }
                        ),
                        current_revision,
                    )

                revision_number = existing.current_revision + 1
                created_at = existing.created_at
                connection.execute(
                    """
                    UPDATE knowledge_sources
                    SET title = ?, media_type = ?, current_revision = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        source.title,
                        source.media_type,
                        revision_number,
                        now.isoformat(),
                        str(source_id),
                    ),
                )

            revision = KnowledgeRevision(
                id=uuid4(),
                source_id=source_id,
                revision=revision_number,
                sha256=source_sha256,
                created_at=now,
            )
            connection.execute(
                """
                INSERT INTO knowledge_revisions(id, source_id, revision, sha256, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(revision.id),
                    str(revision.source_id),
                    revision.revision,
                    revision.sha256,
                    revision.created_at.isoformat(),
                ),
            )

            for chunk in chunks:
                item = KnowledgeChunk(
                    id=uuid4(),
                    source_id=source_id,
                    revision_id=revision.id,
                    revision=revision_number,
                    ordinal=chunk.ordinal,
                    content=chunk.content,
                    start_char=chunk.start_char,
                    end_char=chunk.end_char,
                    sha256=chunk.sha256,
                    created_at=now,
                )
                connection.execute(
                    """
                    INSERT INTO knowledge_chunks(
                        id, source_id, revision_id, revision, ordinal, content,
                        start_char, end_char, sha256, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(item.id),
                        str(item.source_id),
                        str(item.revision_id),
                        item.revision,
                        item.ordinal,
                        item.content,
                        item.start_char,
                        item.end_char,
                        item.sha256,
                        item.created_at.isoformat(),
                    ),
                )

        return (
            KnowledgeSource(
                id=source_id,
                uri=source.uri,
                title=source.title,
                media_type=source.media_type,
                current_revision=revision_number,
                created_at=created_at,
                updated_at=now,
            ),
            revision,
        )

    def get_source(self, source_id: UUID) -> KnowledgeSource | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, uri, title, media_type, current_revision, created_at, updated_at
                FROM knowledge_sources
                WHERE id = ?
                """,
                (str(source_id),),
            ).fetchone()
        return None if row is None else self._source_from_row(cast(SourceRow, row))

    def find_source_by_uri(self, uri: str) -> KnowledgeSource | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, uri, title, media_type, current_revision, created_at, updated_at
                FROM knowledge_sources
                WHERE uri = ?
                """,
                (uri,),
            ).fetchone()
        return None if row is None else self._source_from_row(cast(SourceRow, row))

    def list_sources(self, *, limit: int = 100) -> tuple[KnowledgeSource, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._database.connect() as connection:
            rows = cast(
                list[SourceRow],
                connection.execute(
                    """
                    SELECT id, uri, title, media_type, current_revision, created_at, updated_at
                    FROM knowledge_sources
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall(),
            )
        return tuple(self._source_from_row(row) for row in rows)

    def list_revisions(self, source_id: UUID) -> tuple[KnowledgeRevision, ...]:
        if self.get_source(source_id) is None:
            raise KeyError(f"Unknown knowledge source: {source_id}")

        with self._database.connect() as connection:
            rows = cast(
                list[RevisionRow],
                connection.execute(
                    """
                    SELECT id, source_id, revision, sha256, created_at
                    FROM knowledge_revisions
                    WHERE source_id = ?
                    ORDER BY revision DESC
                    """,
                    (str(source_id),),
                ).fetchall(),
            )
        return tuple(self._revision_from_row(row) for row in rows)

    def list_current_chunks(self, source_id: UUID) -> tuple[KnowledgeChunk, ...]:
        source = self.get_source(source_id)
        if source is None:
            raise KeyError(f"Unknown knowledge source: {source_id}")

        with self._database.connect() as connection:
            rows = cast(
                list[ChunkRow],
                connection.execute(
                    """
                    SELECT
                        id, source_id, revision_id, revision, ordinal, content,
                        start_char, end_char, sha256, created_at
                    FROM knowledge_chunks
                    WHERE source_id = ? AND revision = ?
                    ORDER BY ordinal
                    """,
                    (str(source_id), source.current_revision),
                ).fetchall(),
            )
        return tuple(self._chunk_from_row(row) for row in rows)

    def list_revision_chunks(self, revision_id: UUID) -> tuple[KnowledgeChunk, ...]:
        with self._database.connect() as connection:
            rows = cast(
                list[ChunkRow],
                connection.execute(
                    """
                    SELECT
                        id, source_id, revision_id, revision, ordinal, content,
                        start_char, end_char, sha256, created_at
                    FROM knowledge_chunks
                    WHERE revision_id = ?
                    ORDER BY ordinal
                    """,
                    (str(revision_id),),
                ).fetchall(),
            )
        return tuple(self._chunk_from_row(row) for row in rows)

    def list_search_candidates(self, *, limit: int = 1000) -> tuple[KnowledgeChunk, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._database.connect() as connection:
            rows = cast(
                list[ChunkRow],
                connection.execute(
                    """
                    SELECT
                        c.id, c.source_id, c.revision_id, c.revision, c.ordinal,
                        c.content, c.start_char, c.end_char, c.sha256, c.created_at
                    FROM knowledge_chunks AS c
                    JOIN knowledge_sources AS s
                      ON s.id = c.source_id
                     AND s.current_revision = c.revision
                    ORDER BY s.updated_at DESC, c.ordinal ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall(),
            )
        return tuple(self._chunk_from_row(row) for row in rows)

    @staticmethod
    def _validate_ingest(
        source_sha256: str,
        chunks: Sequence[NewKnowledgeChunk],
    ) -> None:
        if len(source_sha256) != 64:
            raise ValueError("source_sha256 must be a 64-character SHA-256 digest")
        if not chunks:
            raise ValueError("knowledge ingestion requires at least one chunk")
        ordinals = [chunk.ordinal for chunk in chunks]
        if ordinals != list(range(len(chunks))):
            raise ValueError("knowledge chunk ordinals must be contiguous from zero")

    @staticmethod
    def _source_from_row(row: SourceRow) -> KnowledgeSource:
        identifier, uri, title, media_type, revision, created_at, updated_at = row
        return KnowledgeSource(
            id=UUID(identifier),
            uri=uri,
            title=title,
            media_type=media_type,
            current_revision=revision,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )

    @staticmethod
    def _revision_from_row(row: RevisionRow) -> KnowledgeRevision:
        identifier, source_id, revision, sha256, created_at = row
        return KnowledgeRevision(
            id=UUID(identifier),
            source_id=UUID(source_id),
            revision=revision,
            sha256=sha256,
            created_at=datetime.fromisoformat(created_at),
        )

    @staticmethod
    def _chunk_from_row(row: ChunkRow) -> KnowledgeChunk:
        (
            identifier,
            source_id,
            revision_id,
            revision,
            ordinal,
            content,
            start_char,
            end_char,
            sha256,
            created_at,
        ) = row
        return KnowledgeChunk(
            id=UUID(identifier),
            source_id=UUID(source_id),
            revision_id=UUID(revision_id),
            revision=revision,
            ordinal=ordinal,
            content=content,
            start_char=start_char,
            end_char=end_char,
            sha256=sha256,
            created_at=datetime.fromisoformat(created_at),
        )
