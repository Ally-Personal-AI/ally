"""Read-only SQLite health reporting for the proactive service."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
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
LeaseExpiryRow = tuple[str]


def _readonly_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
    )


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


def _runtime_lease_state(
    *,
    runtime_database_path: Path,
    observed_at: datetime,
) -> tuple[bool, bool, bool, datetime | None]:
    if not runtime_database_path.exists():
        return False, True, False, None

    try:
        connection = _readonly_connection(runtime_database_path)
        try:
            quick_check_row = cast(
                tuple[str] | None,
                connection.execute("PRAGMA quick_check").fetchone(),
            )
            if quick_check_row is None or quick_check_row[0] != "ok":
                return True, False, False, None

            lease_table = cast(
                tuple[int] | None,
                connection.execute(
                    """
                    SELECT 1
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name = 'service_leases'
                    """
                ).fetchone(),
            )
            if lease_table is None:
                return True, True, False, None

            lease_row = cast(
                LeaseExpiryRow | None,
                connection.execute(
                    """
                    SELECT expires_at
                    FROM service_leases
                    WHERE name = 'proactive-cycle'
                    """
                ).fetchone(),
            )
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return True, False, False, None

    if lease_row is None:
        return True, True, False, None

    expires_at = datetime.fromisoformat(lease_row[0])
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        return True, False, False, None
    expires_at = expires_at.astimezone(UTC)
    return True, True, expires_at > observed_at, expires_at


def build_sqlite_service_health(
    *,
    database_path: Path,
    runtime_database_path: Path,
    as_of: datetime | None = None,
) -> ServiceHealthReport:
    """Inspect durable and ephemeral service state without mutating either."""

    observed_at = datetime.now(UTC) if as_of is None else as_of
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("health timestamp must include a timezone offset")
    observed_at = observed_at.astimezone(UTC)

    (
        runtime_exists,
        runtime_ok,
        lease_active,
        lease_expires_at,
    ) = _runtime_lease_state(
        runtime_database_path=runtime_database_path,
        observed_at=observed_at,
    )

    expected = tuple(migration.version for migration in MIGRATIONS)
    if not database_path.exists():
        return ServiceHealthReport(
            status="uninitialized",
            database_exists=False,
            database_integrity_ok=False,
            schema_current=False,
            expected_schema_versions=expected,
            runtime_database_exists=runtime_exists,
            runtime_coordination_ok=runtime_ok,
            proactive_lease_active=lease_active,
            proactive_lease_expires_at=lease_expires_at,
        )

    integrity_ok = False
    versions: tuple[int, ...] = ()
    latest: ServiceCycleRunRecord | None = None

    try:
        connection = _readonly_connection(database_path)
        try:
            quick_check_row = cast(
                tuple[str] | None,
                connection.execute("PRAGMA quick_check").fetchone(),
            )
            integrity_ok = bool(
                quick_check_row is not None
                and quick_check_row[0] == "ok"
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
    if not integrity_ok or not runtime_ok:
        status = "degraded"
    elif not versions:
        status = "uninitialized"
    elif not schema_current:
        status = "degraded"
    elif latest is None:
        status = "uninitialized"
    elif latest.status in ("failed", "degraded", "interrupted"):
        status = "degraded"
    elif latest.status == "running" and not lease_active:
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
        runtime_database_exists=runtime_exists,
        runtime_coordination_ok=runtime_ok,
        proactive_lease_active=lease_active,
        proactive_lease_expires_at=lease_expires_at,
    )
