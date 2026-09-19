"""Read-only readiness diagnostics for Ally's proactive service."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from ally.configuration import ConfigFileError, FileConfigStore
from ally.service import (
    ServiceCycleRunRecord,
    ServiceCycleRunStatus,
    ServiceHealthCheck,
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
MigrationRow = tuple[int, str]
LeaseRow = tuple[str, str]


def _readonly_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
    )


def _check(
    check_id: str,
    severity: str,
    summary: str,
) -> ServiceHealthCheck:
    return ServiceHealthCheck(
        id=check_id,
        severity=cast("HealthCheckSeverity", severity),
        summary=summary,
    )


def _overall_status(
    checks: tuple[ServiceHealthCheck, ...],
) -> ServiceHealthStatus:
    severities = {check.severity for check in checks}
    if "error" in severities:
        return "unhealthy"
    if "warning" in severities:
        return "degraded"
    return "healthy"


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


def _inspect_config(path: Path) -> tuple[ServiceHealthCheck, bool, bool]:
    if not path.exists():
        return (
            _check(
                "config.file",
                "warning",
                "Configuration file is not initialized; safe defaults will apply.",
            ),
            False,
            False,
        )

    try:
        FileConfigStore(path).load()
    except ConfigFileError:
        return (
            _check(
                "config.file",
                "error",
                "Configuration file exists but is invalid or unreadable.",
            ),
            True,
            False,
        )

    return (
        _check("config.file", "ok", "Configuration file is valid."),
        True,
        True,
    )


def _inspect_core_database(
    path: Path,
) -> tuple[
    tuple[ServiceHealthCheck, ...],
    bool,
    bool,
    bool,
    tuple[int, ...],
    ServiceCycleRunRecord | None,
]:
    expected = tuple((item.version, item.name) for item in MIGRATIONS)
    expected_versions = tuple(item[0] for item in expected)

    if not path.exists():
        return (
            (
                _check(
                    "database.core",
                    "warning",
                    "Core database is not initialized.",
                ),
                _check(
                    "database.schema",
                    "warning",
                    "Core database schema is not initialized.",
                ),
                _check(
                    "service.lifecycle",
                    "warning",
                    "No proactive service lifecycle history is available.",
                ),
            ),
            False,
            False,
            False,
            (),
            None,
        )

    try:
        connection = _readonly_connection(path)
        try:
            quick = cast(
                tuple[str] | None,
                connection.execute("PRAGMA quick_check").fetchone(),
            )
            integrity_ok = bool(quick is not None and quick[0] == "ok")
            if not integrity_ok:
                return (
                    (
                        _check(
                            "database.core",
                            "error",
                            "Core database failed SQLite integrity checking.",
                        ),
                        _check(
                            "database.schema",
                            "error",
                            "Core schema cannot be trusted while integrity fails.",
                        ),
                        _check(
                            "service.lifecycle",
                            "warning",
                            "Service lifecycle state could not be inspected.",
                        ),
                    ),
                    True,
                    False,
                    False,
                    (),
                    None,
                )

            table_rows = cast(
                list[tuple[str]],
                connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                    """
                ).fetchall(),
            )
            tables = {row[0] for row in table_rows}
            core_check = _check(
                "database.core",
                "ok",
                "Core database passed SQLite integrity checking.",
            )

            if "ally_schema_migrations" not in tables:
                if not tables:
                    schema_check = _check(
                        "database.schema",
                        "warning",
                        "Core database exists but has not been initialized.",
                    )
                    lifecycle_check = _check(
                        "service.lifecycle",
                        "warning",
                        "No proactive service lifecycle history is available.",
                    )
                    return (
                        (core_check, schema_check, lifecycle_check),
                        True,
                        True,
                        False,
                        (),
                        None,
                    )

                schema_check = _check(
                    "database.schema",
                    "error",
                    "Core database has tables but no Ally migration history.",
                )
                lifecycle_check = _check(
                    "service.lifecycle",
                    "warning",
                    "Service lifecycle state could not be inspected.",
                )
                return (
                    (core_check, schema_check, lifecycle_check),
                    True,
                    True,
                    False,
                    (),
                    None,
                )

            migration_rows = cast(
                list[MigrationRow],
                connection.execute(
                    """
                    SELECT version, name
                    FROM ally_schema_migrations
                    ORDER BY version
                    """
                ).fetchall(),
            )
            applied = tuple(migration_rows)
            applied_versions = tuple(item[0] for item in applied)
            is_prefix = applied == expected[: len(applied)]

            latest: ServiceCycleRunRecord | None = None
            if applied == expected:
                schema_check = _check(
                    "database.schema",
                    "ok",
                    "Core database schema is current.",
                )
                schema_current = True

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
            elif is_prefix:
                schema_check = _check(
                    "database.schema",
                    "warning",
                    "Core database uses an older supported Ally schema.",
                )
                schema_current = False
            else:
                schema_check = _check(
                    "database.schema",
                    "error",
                    "Core database migration history is unsupported.",
                )
                schema_current = False

            if latest is None:
                lifecycle_check = _check(
                    "service.lifecycle",
                    "warning",
                    "No current proactive service lifecycle result is available.",
                )
            elif latest.status == "succeeded":
                lifecycle_check = _check(
                    "service.lifecycle",
                    "ok",
                    "Latest proactive service cycle completed successfully.",
                )
            elif latest.status == "running":
                lifecycle_check = _check(
                    "service.lifecycle",
                    "ok",
                    "A proactive service cycle is currently recorded as running.",
                )
            else:
                lifecycle_check = _check(
                    "service.lifecycle",
                    "warning",
                    "Latest proactive service cycle did not complete cleanly.",
                )

            return (
                (core_check, schema_check, lifecycle_check),
                True,
                True,
                schema_current,
                applied_versions,
                latest,
            )
        finally:
            connection.close()
    except (sqlite3.DatabaseError, ValueError):
        return (
            (
                _check(
                    "database.core",
                    "error",
                    "Core database is unreadable or invalid.",
                ),
                _check(
                    "database.schema",
                    "error",
                    "Core database schema could not be inspected safely.",
                ),
                _check(
                    "service.lifecycle",
                    "warning",
                    "Service lifecycle state could not be inspected.",
                ),
            ),
            True,
            False,
            False,
            (),
            None,
        )


def _inspect_runtime_database(
    path: Path,
    *,
    observed_at: datetime,
) -> tuple[
    tuple[ServiceHealthCheck, ...],
    bool,
    bool,
    int,
    int,
    bool,
    datetime | None,
]:
    if not path.exists():
        return (
            (
                _check(
                    "database.runtime",
                    "warning",
                    "Runtime coordination database is not initialized.",
                ),
                _check(
                    "runtime.leases",
                    "ok",
                    "No runtime leases are present.",
                ),
            ),
            False,
            True,
            0,
            0,
            False,
            None,
        )

    try:
        connection = _readonly_connection(path)
        try:
            quick = cast(
                tuple[str] | None,
                connection.execute("PRAGMA quick_check").fetchone(),
            )
            if quick is None or quick[0] != "ok":
                raise sqlite3.DatabaseError("runtime integrity failure")

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
                return (
                    (
                        _check(
                            "database.runtime",
                            "error",
                            "Runtime database is missing the lease table.",
                        ),
                        _check(
                            "runtime.leases",
                            "error",
                            "Runtime leases could not be inspected.",
                        ),
                    ),
                    True,
                    False,
                    0,
                    0,
                    False,
                    None,
                )

            rows = cast(
                list[LeaseRow],
                connection.execute(
                    """
                    SELECT name, expires_at
                    FROM service_leases
                    ORDER BY name
                    """
                ).fetchall(),
            )
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return (
            (
                _check(
                    "database.runtime",
                    "error",
                    "Runtime coordination database is unreadable or invalid.",
                ),
                _check(
                    "runtime.leases",
                    "error",
                    "Runtime leases could not be inspected.",
                ),
            ),
            True,
            False,
            0,
            0,
            False,
            None,
        )

    active = 0
    expired = 0
    proactive_active = False
    proactive_expires: datetime | None = None
    try:
        for name, raw_expires_at in rows:
            expires_at = datetime.fromisoformat(raw_expires_at)
            if expires_at.tzinfo is None or expires_at.utcoffset() is None:
                raise ValueError("naive lease timestamp")
            expires_at = expires_at.astimezone(UTC)
            is_active = expires_at > observed_at
            if is_active:
                active += 1
            else:
                expired += 1
            if name == "proactive-cycle":
                proactive_active = is_active
                proactive_expires = expires_at
    except ValueError:
        return (
            (
                _check(
                    "database.runtime",
                    "error",
                    "Runtime coordination database contains invalid lease state.",
                ),
                _check(
                    "runtime.leases",
                    "error",
                    "Runtime leases could not be interpreted safely.",
                ),
            ),
            True,
            False,
            0,
            0,
            False,
            None,
        )

    return (
        (
            _check(
                "database.runtime",
                "ok",
                "Runtime coordination database is valid.",
            ),
            _check(
                "runtime.leases",
                "ok",
                f"Runtime leases: {active} active, {expired} expired.",
            ),
        ),
        True,
        True,
        active,
        expired,
        proactive_active,
        proactive_expires,
    )


def build_service_health(
    *,
    config_path: Path,
    database_path: Path,
    runtime_database_path: Path,
    as_of: datetime | None = None,
) -> ServiceHealthReport:
    """Build a fully read-only service readiness report."""

    observed_at = datetime.now(UTC) if as_of is None else as_of
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("health timestamp must include a timezone offset")
    observed_at = observed_at.astimezone(UTC)

    config_check, config_exists, config_valid = _inspect_config(config_path)
    (
        core_checks,
        database_exists,
        database_integrity_ok,
        schema_current,
        applied_versions,
        latest_cycle,
    ) = _inspect_core_database(database_path)
    (
        runtime_checks,
        runtime_database_exists,
        runtime_coordination_ok,
        active_lease_count,
        expired_lease_count,
        proactive_lease_active,
        proactive_lease_expires_at,
    ) = _inspect_runtime_database(
        runtime_database_path,
        observed_at=observed_at,
    )

    checks = (config_check, *core_checks, *runtime_checks)

    if latest_cycle is not None and latest_cycle.status == "running":
        lifecycle_index = next(
            index
            for index, check in enumerate(checks)
            if check.id == "service.lifecycle"
        )
        replacement = (
            _check(
                "service.lifecycle",
                "ok",
                "Proactive service cycle is running under an active lease.",
            )
            if proactive_lease_active
            else _check(
                "service.lifecycle",
                "error",
                "Proactive service cycle is running without an active lease.",
            )
        )
        mutable_checks = list(checks)
        mutable_checks[lifecycle_index] = replacement
        checks = tuple(mutable_checks)

    expected_versions = tuple(item.version for item in MIGRATIONS)
    return ServiceHealthReport(
        status=_overall_status(checks),
        checks=checks,
        config_exists=config_exists,
        config_valid=config_valid,
        database_exists=database_exists,
        database_integrity_ok=database_integrity_ok,
        schema_current=schema_current,
        applied_schema_versions=applied_versions,
        expected_schema_versions=expected_versions,
        latest_cycle=latest_cycle,
        runtime_database_exists=runtime_database_exists,
        runtime_coordination_ok=runtime_coordination_ok,
        active_lease_count=active_lease_count,
        expired_lease_count=expired_lease_count,
        proactive_lease_active=proactive_lease_active,
        proactive_lease_expires_at=proactive_lease_expires_at,
    )
