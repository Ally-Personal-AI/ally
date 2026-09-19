import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from ally.configuration import AllyConfig, FileConfigStore
from ally.service import (
    HealthCheckResult,
    SQLiteServiceLeaseStore,
    ServiceHealthReport,
    collect_service_health,
)
from ally.storage.sqlite import SQLiteDatabase
from ally.storage.sqlite.schema import MIGRATIONS

OWNER_A = UUID("00000000-0000-0000-0000-000000000001")
OWNER_B = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def check(report: ServiceHealthReport, identifier: str) -> HealthCheckResult:
    return next(item for item in report.checks if item.id == identifier)


def seed_migration_prefix(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE ally_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        for migration in MIGRATIONS[:count]:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                """
                INSERT INTO ally_schema_migrations(version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    NOW.isoformat(),
                ),
            )
        connection.commit()
    finally:
        connection.close()


def test_missing_first_run_state_is_degraded_without_writes(tmp_path: Path) -> None:
    config = tmp_path / "config" / "config.json"
    database = tmp_path / "data" / "ally.sqlite3"
    runtime = tmp_path / "data" / "runtime" / "service.sqlite3"

    report = collect_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        now=NOW,
    )

    assert report.overall == "degraded"
    assert report.has_errors is False
    assert check(report, "config").status == "ok"
    assert check(report, "core_database").status == "warning"
    assert check(report, "runtime_database").status == "ok"
    assert not config.exists()
    assert not database.exists()
    assert not runtime.exists()
    assert not config.parent.exists()
    assert not database.parent.exists()


def test_valid_config_current_database_and_no_runtime_are_healthy(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "ally.sqlite3"
    runtime = tmp_path / "runtime" / "service.sqlite3"

    FileConfigStore(config).initialize(AllyConfig())
    SQLiteDatabase(database).migrate()

    report = collect_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        now=NOW,
    )

    assert report.overall == "healthy"
    assert all(item.status == "ok" for item in report.checks)
    core = check(report, "core_database")
    assert core.details["schema_versions"] == [
        migration.version for migration in MIGRATIONS
    ]


def test_invalid_config_is_unhealthy_and_not_rewritten(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        '{"schema_version":1,"password":"must-not-be-config"}',
        encoding="utf-8",
    )
    database = tmp_path / "ally.sqlite3"
    SQLiteDatabase(database).migrate()
    before = config.read_bytes()

    report = collect_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=tmp_path / "runtime.sqlite3",
        now=NOW,
    )

    assert report.overall == "unhealthy"
    assert check(report, "config").status == "error"
    assert config.read_bytes() == before


def test_older_supported_database_is_warning_and_not_migrated(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ally.sqlite3"
    seed_migration_prefix(database, 3)

    report = collect_service_health(
        config_path=tmp_path / "config.json",
        database_path=database,
        runtime_database_path=tmp_path / "runtime.sqlite3",
        now=NOW,
    )

    core = check(report, "core_database")
    assert core.status == "warning"
    assert core.details["schema_versions"] == [1, 2, 3]

    connection = sqlite3.connect(database)
    try:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM ally_schema_migrations ORDER BY version"
            ).fetchall()
        ]
    finally:
        connection.close()
    assert versions == [1, 2, 3]


def test_invalid_or_future_migration_history_is_unhealthy(tmp_path: Path) -> None:
    database = tmp_path / "ally.sqlite3"
    seed_migration_prefix(database, 1)

    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE ally_schema_migrations SET name = ? WHERE version = 1",
            ("wrong-name",),
        )
        connection.commit()
    finally:
        connection.close()

    report = collect_service_health(
        config_path=tmp_path / "config.json",
        database_path=database,
        runtime_database_path=tmp_path / "runtime.sqlite3",
        now=NOW,
    )
    assert check(report, "core_database").status == "error"

    future = tmp_path / "future.sqlite3"
    seed_migration_prefix(future, len(MIGRATIONS))
    connection = sqlite3.connect(future)
    try:
        connection.execute(
            """
            INSERT INTO ally_schema_migrations(version, name, applied_at)
            VALUES (?, ?, ?)
            """,
            (999, "future", NOW.isoformat()),
        )
        connection.commit()
    finally:
        connection.close()

    future_report = collect_service_health(
        config_path=tmp_path / "config.json",
        database_path=future,
        runtime_database_path=tmp_path / "runtime.sqlite3",
        now=NOW,
    )
    assert check(future_report, "core_database").status == "error"


def test_corrupt_personal_database_is_unhealthy(tmp_path: Path) -> None:
    database = tmp_path / "ally.sqlite3"
    database.write_bytes(b"not a sqlite database")

    report = collect_service_health(
        config_path=tmp_path / "config.json",
        database_path=database,
        runtime_database_path=tmp_path / "runtime.sqlite3",
        now=NOW,
    )

    assert report.overall == "unhealthy"
    assert check(report, "core_database").status == "error"


def test_runtime_database_reports_active_and_expired_leases(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime" / "service.sqlite3"
    store = SQLiteServiceLeaseStore(runtime)
    store.acquire(
        name="active",
        owner_id=OWNER_A,
        now=NOW - timedelta(seconds=10),
        ttl_seconds=60,
    )
    store.acquire(
        name="expired",
        owner_id=OWNER_B,
        now=NOW - timedelta(seconds=60),
        ttl_seconds=30,
    )

    report = collect_service_health(
        config_path=tmp_path / "config.json",
        database_path=tmp_path / "ally.sqlite3",
        runtime_database_path=runtime,
        now=NOW,
    )

    runtime_check = check(report, "runtime_database")
    assert runtime_check.status == "ok"
    assert runtime_check.details["active_leases"] == 1
    assert runtime_check.details["expired_leases"] == 1


def test_corrupt_runtime_database_is_unhealthy(tmp_path: Path) -> None:
    runtime = tmp_path / "service.sqlite3"
    runtime.write_bytes(b"not sqlite")

    report = collect_service_health(
        config_path=tmp_path / "config.json",
        database_path=tmp_path / "ally.sqlite3",
        runtime_database_path=runtime,
        now=NOW,
    )

    assert report.overall == "unhealthy"
    assert check(report, "runtime_database").status == "error"


def test_non_file_paths_are_errors(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "ally.sqlite3"
    runtime = tmp_path / "service.sqlite3"
    config.mkdir()
    database.mkdir()
    runtime.mkdir()

    report = collect_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        now=NOW,
    )

    assert report.overall == "unhealthy"
    assert [item.status for item in report.checks] == [
        "error",
        "error",
        "error",
    ]
