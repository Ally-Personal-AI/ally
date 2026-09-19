"""SQLite persistence for payload-free skill execution audit."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from ally.skills.models import (
    SkillExecutionAuditRecord,
    SkillExecutionResult,
    SkillExecutionStatus,
)
from ally.storage.sqlite.database import SQLiteDatabase

SkillAuditRow = tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    int,
    int | None,
    str | None,
]


class SQLiteSkillExecutionAuditStore:
    """Persist skill execution metadata without request/result/output payloads."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def record(
        self,
        *,
        installation_id: UUID,
        result: SkillExecutionResult,
    ) -> SkillExecutionAuditRecord:
        record = SkillExecutionAuditRecord(
            id=uuid4(),
            installation_id=installation_id,
            skill_id=result.skill_id,
            version=result.version,
            status=result.status,
            started_at=result.started_at,
            finished_at=result.finished_at,
            duration_ms=result.duration_ms,
            exit_code=result.exit_code,
            error_class=result.error_class,
        )

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO skill_execution_audit(
                    id,
                    installation_id,
                    skill_id,
                    version,
                    status,
                    started_at,
                    finished_at,
                    duration_ms,
                    exit_code,
                    error_class
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.id),
                    str(record.installation_id),
                    record.skill_id,
                    record.version,
                    record.status,
                    record.started_at.isoformat(),
                    record.finished_at.isoformat(),
                    record.duration_ms,
                    record.exit_code,
                    record.error_class,
                ),
            )

        return record

    def list(
        self,
        *,
        limit: int = 50,
    ) -> tuple[SkillExecutionAuditRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        with self._database.connect() as connection:
            rows = cast(
                list[SkillAuditRow],
                connection.execute(
                    """
                    SELECT
                        id,
                        installation_id,
                        skill_id,
                        version,
                        status,
                        started_at,
                        finished_at,
                        duration_ms,
                        exit_code,
                        error_class
                    FROM skill_execution_audit
                    ORDER BY started_at DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall(),
            )

        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(row: SkillAuditRow) -> SkillExecutionAuditRecord:
        (
            identifier,
            installation_id,
            skill_id,
            version,
            status,
            started_at,
            finished_at,
            duration_ms,
            exit_code,
            error_class,
        ) = row
        return SkillExecutionAuditRecord(
            id=UUID(identifier),
            installation_id=UUID(installation_id),
            skill_id=skill_id,
            version=version,
            status=cast(SkillExecutionStatus, status),
            started_at=datetime.fromisoformat(started_at),
            finished_at=datetime.fromisoformat(finished_at),
            duration_ms=duration_ms,
            exit_code=exit_code,
            error_class=error_class,
        )
