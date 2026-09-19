"""Deterministic read-only local service health reporting."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

from ally.service.models import (
    ServiceCycleRunRecord,
    ServiceCycleRunStatus,
    ServiceHealthReport,
    ServiceHealthStatus,
)
from ally.storage.sqlite.schema import MIGRATIONS

DEFAULT_STALE_HEALTH_AFTER = timedelta(hours=1)

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


def _from_run_row(row: ServiceRunRow) -> ServiceCycleRunRecord:
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


def build_sqlite_service_health(
    *,
    database_path: Path,
    as_of: datetime | None = None,
    stale_after: timedelta = DEFAULT_STALE_HEALTH_AFTER,
) -> ServiceHealthReport:
    """Inspect local service health without migrating or mutating state."""

    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")

    observed_at = datetime.now(UTC) if as_of is None else as_of
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("health timestamp must include a timezone offset")
    observed_at = observed_at.astimezone(UTC)

    expected = tuple(migration.version for migration in MIGRATIONS)
    if not database_path.exists():
        return ServiceHealthReport(
            status="uninitialized",
            database_exists=False,
            database_integrity_ok=False,
            schema_current=False,
            expected_schema_versions=expected,
        )

    integrity_ok = False
    versions: tuple[int, ...] = ()
    latest: ServiceCycleRunRecord | None = None

    try:
        connection = sqlite3.connect(
            f"{database_path.resolve().as_uri()}?mode=ro",
            uri=True,
        )
        try:
            quick_check_row = cast(
                tuple[str] | None,
                connection.execute("PRAGMA quick_check").fetchone(),
            )
            integrity_ok = bool(
                quick_check_row and quick_check_row[0] == "ok"
            )

            migration_table = cast(
                tuple[int] | None,
                connection.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'ally_schema_migrations'
                """
                ).fetchone(),
            )
            if migration_table is not None:
                migration_rows = cast(
                    list[tuple[int]],
                    connection.execute(
                    """
                    SELECT version
                    FROM ally_schema_migrations
                    ORDER BY version
                    """
                    ).fetchall(),
                )
                versions = tuple(item[0] for item in migration_rows)

            if integrity_ok and versions == expected:
                run_row = cast(
                    ServiceRunRow | None,
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
                    LIMIT 1
                    """
                    ).fetchone(),
                )
                if run_row is not None:
                    latest = _from_run_row(run_row)
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        integrity_ok = False

    schema_current = versions == expected
    status: ServiceHealthStatus
    if not integrity_ok:
        status = "degraded"
    elif not versions:
        status = "uninitialized"
    elif not schema_current:
        status = "degraded"
    elif latest is None:
        status = "uninitialized"
    elif latest.status in ("failed", "degraded", "interrupted"):
        status = "degraded"
    elif (
        latest.status == "running"
        and latest.started_at < observed_at - stale_after
    ):
        status = "degraded"
    else:
        status = "healthy"

    return ServiceHealthReport(
        status=status,
        database_exists=True,
        database_integrity_ok=integrity_ok,
        schema_current=schema_current,
        applied_schema_versions=versions,
        expected_schema_versions=expected,
        latest_cycle=latest,
    )
