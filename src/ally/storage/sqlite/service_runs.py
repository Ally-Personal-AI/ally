"""SQLite persistence for portable proactive service lifecycle history."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from ally.service.models import ServiceCycleRunRecord, ServiceCycleRunStatus
from ally.service.store import ServiceRunConflictError
from ally.storage.sqlite.database import SQLiteDatabase

ServiceRunRow = tuple[
    str,
    str,
    str,
    str,
    str | None,
    int,
    int,
    int,
    str | None,
]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("service lifecycle timestamp must include a timezone offset")
    return value.astimezone(UTC)


class SQLiteServiceCycleRunStore:
    """Persist payload-free lifecycle history in Ally's user-owned database."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def interrupt_running(
        self,
        *,
        finished_at: datetime,
        error_class: str = "PreviousProcessInterrupted",
    ) -> int:
        finished = _as_utc(finished_at)
        if not error_class or len(error_class) > 256:
            raise ValueError("error_class must contain 1 to 256 characters")

        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE service_cycle_runs
                SET
                    status = 'interrupted',
                    finished_at = ?,
                    error_class = ?
                WHERE status = 'running'
                  AND started_at <= ?
                """,
                (
                    finished.isoformat(),
                    error_class,
                    finished.isoformat(),
                ),
            )
            return cursor.rowcount

    def start(
        self,
        *,
        observed_at: datetime,
        started_at: datetime,
        run_id: UUID | None = None,
    ) -> ServiceCycleRunRecord:
        observed = _as_utc(observed_at)
        started = _as_utc(started_at)
        record = ServiceCycleRunRecord(
            id=run_id or uuid4(),
            status="running",
            observed_at=observed,
            started_at=started,
        )

        with self._database.connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO service_cycle_runs(
                        id,
                        status,
                        observed_at,
                        started_at,
                        finished_at,
                        scheduled_events,
                        delivery_attempts,
                        delivery_failures,
                        error_class
                    )
                    VALUES (?, 'running', ?, ?, NULL, 0, 0, 0, NULL)
                    """,
                    (
                        str(record.id),
                        record.observed_at.isoformat(),
                        record.started_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ServiceRunConflictError(
                    "portable service lifecycle already has a running record"
                ) from exc

        return record

    def update_running_progress(
        self,
        run_id: UUID,
        *,
        scheduled_events: int | None = None,
        delivery_attempts_delta: int = 0,
        delivery_failures_delta: int = 0,
    ) -> ServiceCycleRunRecord:
        if scheduled_events is not None and scheduled_events < 0:
            raise ValueError("scheduled_events cannot be negative")
        if delivery_attempts_delta < 0 or delivery_failures_delta < 0:
            raise ValueError("delivery progress deltas cannot be negative")
        if delivery_failures_delta > delivery_attempts_delta:
            raise ValueError(
                "delivery failure delta cannot exceed attempt delta"
            )

        current = self.get(run_id)
        if current is None:
            raise KeyError(f"Unknown service cycle run: {run_id}")
        if current.status != "running":
            raise ServiceRunConflictError(
                f"service cycle is no longer running: {run_id}"
            )

        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE service_cycle_runs
                SET
                    scheduled_events = COALESCE(?, scheduled_events),
                    delivery_attempts = delivery_attempts + ?,
                    delivery_failures = delivery_failures + ?
                WHERE id = ?
                  AND status = 'running'
                """,
                (
                    scheduled_events,
                    delivery_attempts_delta,
                    delivery_failures_delta,
                    str(run_id),
                ),
            )
            if cursor.rowcount != 1:
                raise ServiceRunConflictError(
                    f"service cycle is no longer running: {run_id}"
                )

        loaded = self.get(run_id)
        assert loaded is not None
        return loaded

    def finish(
        self,
        run_id: UUID,
        *,
        status: ServiceCycleRunStatus,
        finished_at: datetime,
        scheduled_events: int = 0,
        delivery_attempts: int = 0,
        delivery_failures: int = 0,
        error_class: str | None = None,
    ) -> ServiceCycleRunRecord:
        if status == "running":
            raise ValueError("cannot finish a service cycle as running")
        finished = _as_utc(finished_at)

        current = self.get(run_id)
        if current is None:
            raise KeyError(f"Unknown service cycle run: {run_id}")
        if current.status != "running":
            raise ServiceRunConflictError(
                f"service cycle is no longer running: {run_id}"
            )

        candidate = ServiceCycleRunRecord(
            id=current.id,
            status=status,
            observed_at=current.observed_at,
            started_at=current.started_at,
            finished_at=finished,
            scheduled_events=scheduled_events,
            delivery_attempts=delivery_attempts,
            delivery_failures=delivery_failures,
            error_class=error_class,
        )

        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE service_cycle_runs
                SET
                    status = ?,
                    finished_at = ?,
                    scheduled_events = ?,
                    delivery_attempts = ?,
                    delivery_failures = ?,
                    error_class = ?
                WHERE id = ?
                  AND status = 'running'
                """,
                (
                    candidate.status,
                    finished.isoformat(),
                    candidate.scheduled_events,
                    candidate.delivery_attempts,
                    candidate.delivery_failures,
                    candidate.error_class,
                    str(run_id),
                ),
            )
            if cursor.rowcount != 1:
                raise ServiceRunConflictError(
                    f"service cycle is no longer running: {run_id}"
                )

        loaded = self.get(run_id)
        assert loaded is not None
        return loaded

    def get(self, run_id: UUID) -> ServiceCycleRunRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    status,
                    observed_at,
                    started_at,
                    finished_at,
                    scheduled_events,
                    delivery_attempts,
                    delivery_failures,
                    error_class
                FROM service_cycle_runs
                WHERE id = ?
                """,
                (str(run_id),),
            ).fetchone()

        if row is None:
            return None
        return self._from_row(cast(ServiceRunRow, row))

    def latest(self) -> ServiceCycleRunRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    status,
                    observed_at,
                    started_at,
                    finished_at,
                    scheduled_events,
                    delivery_attempts,
                    delivery_failures,
                    error_class
                FROM service_cycle_runs
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None
        return self._from_row(cast(ServiceRunRow, row))

    def list(self, *, limit: int = 50) -> tuple[ServiceCycleRunRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        with self._database.connect() as connection:
            rows = cast(
                list[ServiceRunRow],
                connection.execute(
                    """
                    SELECT
                        id,
                        status,
                        observed_at,
                        started_at,
                        finished_at,
                        scheduled_events,
                        delivery_attempts,
                        delivery_failures,
                        error_class
                    FROM service_cycle_runs
                    ORDER BY started_at DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall(),
            )

        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(row: ServiceRunRow) -> ServiceCycleRunRecord:
        (
            identifier,
            status,
            observed_at,
            started_at,
            finished_at,
            scheduled_events,
            delivery_attempts,
            delivery_failures,
            error_class,
        ) = row
        return ServiceCycleRunRecord(
            id=UUID(identifier),
            status=cast(ServiceCycleRunStatus, status),
            observed_at=datetime.fromisoformat(observed_at),
            started_at=datetime.fromisoformat(started_at),
            finished_at=(
                None if finished_at is None else datetime.fromisoformat(finished_at)
            ),
            scheduled_events=scheduled_events,
            delivery_attempts=delivery_attempts,
            delivery_failures=delivery_failures,
            error_class=error_class,
        )
