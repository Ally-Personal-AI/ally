import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from ally.configuration import FileConfigStore
from ally.diagnostics import build_service_health
from ally.service import SQLiteServiceLeaseStore
from ally.storage.sqlite import (
    SQLiteDatabase,
    SQLiteServiceCycleRunStore,
)
from ally.storage.sqlite.schema import MIGRATIONS

OWNER = UUID("00000000-0000-0000-0000-000000000001")
BASE_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def initialize_config(path: Path) -> None:
    FileConfigStore(path).initialize()


def initialize_runtime(path: Path) -> SQLiteServiceLeaseStore:
    return SQLiteServiceLeaseStore(path)


def record_success(path: Path) -> None:
    store = SQLiteServiceCycleRunStore(SQLiteDatabase(path))
    run = store.start(observed_at=BASE_TIME, started_at=BASE_TIME)
    store.finish(
        run.id,
        status="succeeded",
        finished_at=BASE_TIME + timedelta(seconds=1),
    )


def check_map(report) -> dict[str, str]:
    return {check.id: check.severity for check in report.checks}


def create_schema_prefix(path: Path, count: int) -> None:
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
                    BASE_TIME.isoformat(),
                ),
            )
        connection.commit()
    finally:
        connection.close()


def test_missing_state_is_degraded_without_creating_files(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "ally.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME,
    )

    assert report.status == "degraded"
    assert check_map(report) == {
        "config.file": "warning",
        "database.core": "warning",
        "database.schema": "warning",
        "service.lifecycle": "warning",
        "database.runtime": "warning",
        "runtime.leases": "ok",
    }
    assert not config.exists()
    assert not database.exists()
    assert not runtime.exists()


def test_invalid_config_is_unhealthy_without_exposing_contents(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        '{"schema_version":1,"password":"TOP-SECRET-VALUE"}',
        encoding="utf-8",
    )

    report = build_service_health(
        config_path=config,
        database_path=tmp_path / "missing.sqlite3",
        runtime_database_path=tmp_path / "missing-runtime.sqlite3",
        as_of=BASE_TIME,
    )

    assert report.status == "unhealthy"
    assert check_map(report)["config.file"] == "error"
    rendered = report.model_dump_json()
    assert "TOP-SECRET-VALUE" not in rendered
    assert "password" not in rendered


def test_fully_initialized_successful_state_is_healthy(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "ally.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    record_success(database)
    initialize_runtime(runtime)

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME + timedelta(minutes=1),
    )

    assert report.status == "healthy"
    assert all(check.severity == "ok" for check in report.checks)
    assert report.config_valid is True
    assert report.database_integrity_ok is True
    assert report.schema_current is True
    assert report.runtime_coordination_ok is True


def test_exact_older_schema_prefix_is_warning_not_error(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "old.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    create_schema_prefix(database, len(MIGRATIONS) - 1)
    initialize_runtime(runtime)

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME,
    )

    assert report.status == "degraded"
    assert check_map(report)["database.schema"] == "warning"
    assert report.applied_schema_versions == tuple(
        migration.version for migration in MIGRATIONS[:-1]
    )
    assert report.schema_current is False


def test_wrong_migration_name_is_unhealthy(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "wrong-name.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    create_schema_prefix(database, 1)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE ally_schema_migrations SET name = 'wrong' WHERE version = 1"
        )
        connection.commit()
    finally:
        connection.close()
    initialize_runtime(runtime)

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME,
    )

    assert report.status == "unhealthy"
    assert check_map(report)["database.schema"] == "error"


def test_future_migration_history_is_unhealthy(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "future.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    create_schema_prefix(database, len(MIGRATIONS))
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            INSERT INTO ally_schema_migrations(version, name, applied_at)
            VALUES (?, 'future', ?)
            """,
            (MIGRATIONS[-1].version + 1, BASE_TIME.isoformat()),
        )
        connection.commit()
    finally:
        connection.close()
    initialize_runtime(runtime)

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME,
    )

    assert report.status == "unhealthy"
    assert check_map(report)["database.schema"] == "error"


def test_core_database_with_tables_but_no_history_is_unhealthy(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "unknown.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE unknown_state(id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()
    initialize_runtime(runtime)

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME,
    )

    assert report.status == "unhealthy"
    assert check_map(report)["database.schema"] == "error"


def test_corrupt_core_database_is_unhealthy(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "corrupt.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    database.write_bytes(b"not sqlite")
    initialize_runtime(runtime)

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME,
    )

    assert report.status == "unhealthy"
    assert check_map(report)["database.core"] == "error"


def test_corrupt_runtime_database_is_unhealthy(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "ally.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    record_success(database)
    runtime.write_bytes(b"not sqlite")

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME,
    )

    assert report.status == "unhealthy"
    assert check_map(report)["database.runtime"] == "error"


def test_runtime_database_without_lease_table_is_unhealthy(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "ally.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    record_success(database)
    connection = sqlite3.connect(runtime)
    connection.close()

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME,
    )

    assert report.status == "unhealthy"
    assert check_map(report)["database.runtime"] == "error"


def test_lease_counts_are_informational(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "ally.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    record_success(database)
    leases = initialize_runtime(runtime)
    leases.acquire(
        name="expired",
        owner_id=OWNER,
        now=BASE_TIME,
        ttl_seconds=10,
    )
    leases.acquire(
        name="proactive-cycle",
        owner_id=OWNER,
        now=BASE_TIME + timedelta(seconds=20),
        ttl_seconds=60,
    )

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME + timedelta(seconds=30),
    )

    assert report.status == "healthy"
    assert report.active_lease_count == 1
    assert report.expired_lease_count == 1
    assert report.proactive_lease_active is True
    assert check_map(report)["runtime.leases"] == "ok"


def test_running_history_requires_active_proactive_lease(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "ally.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    runs = SQLiteServiceCycleRunStore(SQLiteDatabase(database))
    runs.start(observed_at=BASE_TIME, started_at=BASE_TIME)
    initialize_runtime(runtime)

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME + timedelta(seconds=30),
    )

    assert report.status == "unhealthy"
    assert check_map(report)["service.lifecycle"] == "error"

    leases = SQLiteServiceLeaseStore(runtime)
    leases.acquire(
        name="proactive-cycle",
        owner_id=OWNER,
        now=BASE_TIME,
        ttl_seconds=60,
    )
    with_lease = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME + timedelta(seconds=30),
    )

    assert with_lease.status == "healthy"
    assert check_map(with_lease)["service.lifecycle"] == "ok"


def test_failed_latest_cycle_is_degraded_not_structurally_unhealthy(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "ally.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    initialize_config(config)
    runs = SQLiteServiceCycleRunStore(SQLiteDatabase(database))
    run = runs.start(observed_at=BASE_TIME, started_at=BASE_TIME)
    runs.finish(
        run.id,
        status="failed",
        finished_at=BASE_TIME + timedelta(seconds=1),
        error_class="RuntimeError",
    )
    initialize_runtime(runtime)

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME + timedelta(minutes=1),
    )

    assert report.status == "degraded"
    assert check_map(report)["service.lifecycle"] == "warning"


def test_health_does_not_mutate_empty_existing_databases(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    database = tmp_path / "empty.sqlite3"
    runtime = tmp_path / "runtime.sqlite3"
    sqlite3.connect(database).close()

    report = build_service_health(
        config_path=config,
        database_path=database,
        runtime_database_path=runtime,
        as_of=BASE_TIME,
    )

    assert report.status == "degraded"
    assert not config.exists()
    assert not runtime.exists()

    connection = sqlite3.connect(database)
    try:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        connection.close()
    assert tables == []
