"""SQLite tool-execution audit storage."""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from ally.security.tool_policy import PolicyDecision
from ally.storage.sqlite.database import SQLiteDatabase
from ally.tools.audit import ToolAuditRecord
from ally.tools.models import ToolRisk, ToolStatus


class SQLiteToolAuditStore:
    """Append-only local audit log for tool attempts."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def append(self, record: ToolAuditRecord) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO tool_audit_records(
                    id,
                    invocation_id,
                    tool_name,
                    risk,
                    decision,
                    status,
                    arguments_json,
                    output_json,
                    error,
                    started_at,
                    finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.id),
                    str(record.invocation_id),
                    record.tool_name,
                    record.risk,
                    record.decision,
                    record.status,
                    json.dumps(record.arguments, sort_keys=True),
                    None
                    if record.output is None
                    else json.dumps(record.output, sort_keys=True),
                    record.error,
                    record.started_at.isoformat(),
                    record.finished_at.isoformat(),
                ),
            )

    def list(self, *, limit: int = 100) -> tuple[ToolAuditRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        with self._database.connect() as connection:
            rows = cast(
                list[
                    tuple[
                        str,
                        str,
                        str,
                        str | None,
                        str | None,
                        str,
                        str,
                        str | None,
                        str | None,
                        str,
                        str,
                    ]
                ],
                connection.execute(
                    """
                    SELECT
                        id,
                        invocation_id,
                        tool_name,
                        risk,
                        decision,
                        status,
                        arguments_json,
                        output_json,
                        error,
                        started_at,
                        finished_at
                    FROM tool_audit_records
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall(),
            )

        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(
        row: tuple[
            str,
            str,
            str,
            str | None,
            str | None,
            str,
            str,
            str | None,
            str | None,
            str,
            str,
        ],
    ) -> ToolAuditRecord:
        (
            identifier,
            invocation_id,
            tool_name,
            risk,
            decision,
            status,
            arguments_json,
            output_json,
            error,
            started_at,
            finished_at,
        ) = row

        arguments = cast(dict[str, JsonValue], json.loads(arguments_json))
        output = (
            None
            if output_json is None
            else cast(JsonValue, json.loads(output_json))
        )

        return ToolAuditRecord(
            id=UUID(identifier),
            invocation_id=UUID(invocation_id),
            tool_name=tool_name,
            risk=cast(ToolRisk | None, risk),
            decision=cast(PolicyDecision | None, decision),
            status=cast(ToolStatus, status),
            arguments=arguments,
            output=output,
            error=error,
            started_at=datetime.fromisoformat(started_at),
            finished_at=datetime.fromisoformat(finished_at),
        )
