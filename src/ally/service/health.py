"""Read-only health diagnostics for Ally service wrappers."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from ally.configuration import ConfigFileError, FileConfigStore
from ally.storage.sqlite.schema import MIGRATIONS

HealthStatus = Literal["ok", "warning", "error"]
OverallHealth = Literal["healthy", "degraded", "unhealthy"]


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("health timestamp must include a timezone offset")
    return value.astimezone(UTC)


class HealthCheckResult(BaseModel):
    """One safe, structured readiness check."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    status: HealthStatus
    message: str = Field(min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ServiceHealthReport(BaseModel):
    """Read-only aggregate health report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_at: datetime
    overall: OverallHealth
    checks: tuple[HealthCheckResult, ...]

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @property
    def has_errors(self) -> bool:
        return any(check.status == "error" for check in self.checks)


def _overall(checks: tuple[HealthCheckResult, ...]) -> OverallHealth:
    if any(check.status == "error" for check in checks):
        return "unhealthy"
    if any(check.status == "warning" for check in checks):
        return "degraded"
    return "healthy"


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = f"{path.expanduser().resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2.0)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _config_health(path: Path) -> HealthCheckResult:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return HealthCheckResult(
            id="config",
            status="ok",
            message="Config file is absent; safe built-in defaults will be used.",
            details={"present": False},
        )
    if not resolved.is_file():
        return HealthCheckResult(
            id="config",
            status="error",
            message="Config path exists but is not a regular file.",
            details={"present": True},
        )

    try:
        config = FileConfigStore(resolved).load()
    except ConfigFileError:
        return HealthCheckResult(
            id="config",
            status="error",
            message="Existing Ally config is invalid or unreadable.",
            details={"present": True},
        )

    return HealthCheckResult(
        id="config",
        status="ok",
        message="Existing Ally config is valid.",
        details={
            "present": True,
            "schema_version": config.schema_version,
        },
    )


def _sqlite_integrity(connection: sqlite3.Connection) -> bool:
    rows = cast(
        list[tuple[str]],
        connection.execute("PRAGMA quick_check").fetchall(),
    )
    if rows != [("ok",)]:
        return False

    foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    return not foreign_key_rows


def _core_database_health(path: Path) -> HealthCheckResult:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return HealthCheckResult(
            id="core_database",
            status="warning",
            message="Personal database is not initialized yet.",
            details={"present": False},
        )
    if not resolved.is_file():
        return HealthCheckResult(
            id="core_database",
            status="error",
            message="Personal database path is not a regular file.",
            details={"present": True},
        )

    try:
        connection = _connect_read_only(resolved)
        try:
            if not _sqlite_integrity(connection):
                return HealthCheckResult(
                    id="core_database",
                    status="error",
                    message="Personal database failed SQLite integrity checks.",
                    details={"present": True},
                )

            rows = cast(
                list[tuple[int, str]],
                connection.execute(
                    """
                    SELECT version, name
                    FROM ally_schema_migrations
                    ORDER BY version
                    """
                ).fetchall(),
            )
        finally:
            connection.close()
    except (OSError, sqlite3.DatabaseError):
        return HealthCheckResult(
            id="core_database",
            status="error",
            message="Personal database is unreadable or missing Ally schema metadata.",
            details={"present": True},
        )

    actual = tuple(rows)
    supported = tuple((migration.version, migration.name) for migration in MIGRATIONS)
    expected_prefix = supported[: len(actual)]
    versions = [version for version, _ in actual]

    if actual != expected_prefix:
        return HealthCheckResult(
            id="core_database",
            status="error",
            message="Personal database migration history is unsupported.",
            details={
                "present": True,
                "schema_versions": versions,
                "latest_supported": supported[-1][0],
            },
        )

    if len(actual) < len(supported):
        return HealthCheckResult(
            id="core_database",
            status="warning",
            message="Personal database uses an older supported schema.",
            details={
                "present": True,
                "schema_versions": versions,
                "latest_supported": supported[-1][0],
            },
        )

    return HealthCheckResult(
        id="core_database",
        status="ok",
        message="Personal database is healthy and schema-current.",
        details={
            "present": True,
            "schema_versions": versions,
            "latest_supported": supported[-1][0],
        },
    )


def _runtime_database_health(
    path: Path,
    *,
    now: datetime,
) -> HealthCheckResult:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return HealthCheckResult(
            id="runtime_database",
            status="ok",
            message="Runtime coordination database is not initialized.",
            details={
                "present": False,
                "active_leases": 0,
                "expired_leases": 0,
            },
        )
    if not resolved.is_file():
        return HealthCheckResult(
            id="runtime_database",
            status="error",
            message="Runtime database path is not a regular file.",
            details={"present": True},
        )

    try:
        connection = _connect_read_only(resolved)
        try:
            if not _sqlite_integrity(connection):
                return HealthCheckResult(
                    id="runtime_database",
                    status="error",
                    message="Runtime database failed SQLite integrity checks.",
                    details={"present": True},
                )
            rows = cast(
                list[tuple[str]],
                connection.execute(
                    "SELECT expires_at FROM service_leases"
                ).fetchall(),
            )
        finally:
            connection.close()
    except (OSError, sqlite3.DatabaseError):
        return HealthCheckResult(
            id="runtime_database",
            status="error",
            message="Runtime database is unreadable or has an invalid service schema.",
            details={"present": True},
        )

    active = 0
    expired = 0
    try:
        for (expires_at,) in rows:
            parsed = datetime.fromisoformat(expires_at)
            expires = _require_aware(parsed)
            if expires > now:
                active += 1
            else:
                expired += 1
    except ValueError:
        return HealthCheckResult(
            id="runtime_database",
            status="error",
            message="Runtime database contains invalid lease timestamps.",
            details={"present": True},
        )

    return HealthCheckResult(
        id="runtime_database",
        status="ok",
        message="Runtime coordination database is healthy.",
        details={
            "present": True,
            "active_leases": active,
            "expired_leases": expired,
        },
    )


def collect_service_health(
    *,
    config_path: Path,
    database_path: Path,
    runtime_database_path: Path,
    now: datetime | None = None,
) -> ServiceHealthReport:
    """Inspect service readiness without creating or migrating local state."""

    observed_at = _require_aware(now or datetime.now(UTC))
    checks = (
        _config_health(config_path),
        _core_database_health(database_path),
        _runtime_database_health(runtime_database_path, now=observed_at),
    )
    return ServiceHealthReport(
        generated_at=observed_at,
        overall=_overall(checks),
        checks=checks,
    )
