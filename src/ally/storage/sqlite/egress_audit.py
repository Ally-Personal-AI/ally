"""SQLite persistence for payload-free egress audit records."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast
from uuid import UUID

from ally.egress import (
    EgressAuditRecord,
    EgressDecision,
    EgressFieldManifest,
    EgressStatus,
)
from ally.storage.sqlite.database import SQLiteDatabase

EgressAuditRow = tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    int,
    str,
    str | None,
    str,
    str,
]


class SQLiteEgressAuditStore:
    """Persist disclosure metadata without payload values or remote responses."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def append(self, record: EgressAuditRecord) -> None:
        field_manifest = [
            item.model_dump(mode="json")
            for item in record.fields
        ]
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO egress_audit_records(
                    id,
                    request_id,
                    service,
                    operation,
                    decision,
                    status,
                    approved,
                    fields_json,
                    error_class,
                    started_at,
                    finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.id),
                    str(record.request_id),
                    record.service,
                    record.operation,
                    record.decision,
                    record.status,
                    int(record.approved),
                    json.dumps(field_manifest, sort_keys=True),
                    record.error_class,
                    record.started_at.isoformat(),
                    record.finished_at.isoformat(),
                ),
            )

    def list(self, *, limit: int = 100) -> tuple[EgressAuditRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        with self._database.connect() as connection:
            rows = cast(
                list[EgressAuditRow],
                connection.execute(
                    """
                    SELECT
                        id,
                        request_id,
                        service,
                        operation,
                        decision,
                        status,
                        approved,
                        fields_json,
                        error_class,
                        started_at,
                        finished_at
                    FROM egress_audit_records
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall(),
            )
        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(row: EgressAuditRow) -> EgressAuditRecord:
        (
            identifier,
            request_id,
            service,
            operation,
            decision,
            status,
            approved,
            fields_json,
            error_class,
            started_at,
            finished_at,
        ) = row
        raw_fields = cast(list[object], json.loads(fields_json))
        fields = tuple(
            EgressFieldManifest.model_validate(item)
            for item in raw_fields
        )
        return EgressAuditRecord(
            id=UUID(identifier),
            request_id=UUID(request_id),
            service=service,
            operation=operation,
            decision=cast(EgressDecision, decision),
            status=cast(EgressStatus, status),
            approved=bool(approved),
            fields=fields,
            error_class=error_class,
            started_at=datetime.fromisoformat(started_at),
            finished_at=datetime.fromisoformat(finished_at),
        )
