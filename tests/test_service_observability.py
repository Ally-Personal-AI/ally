import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from ally.attention import AttentionDeliveryRuntime
from ally.events import AttentionClass, EventRecord, EventRuntime, NewEvent
from ally.scheduler import SchedulerRuntime
from ally.service import (
    ProactiveServiceCycle,
    ProactiveServiceRunner,
    SQLiteServiceLeaseStore,
    ServiceRunConflictError,
    service_lease,
)
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteDatabase,
    SQLiteEventStore,
    SQLiteScheduleStore,
    SQLiteServiceCycleRunStore,
    build_sqlite_service_health,
)

OWNER = UUID("00000000-0000-0000-0000-000000000001")


class FailingSink:
    @property
    def id(self) -> str:
        return "failing"

    @property
    def accepted_attention(self) -> tuple[AttentionClass, ...]:
        return ("notify",)

    def deliver(
        self,
        event: EventRecord,
        *,
        delivery_key: str,
    ) -> None:
        raise RuntimeError("synthetic private detail")


def build_runner(
    path: Path,
) -> tuple[SQLiteServiceCycleRunStore, ProactiveServiceRunner]:
    database = SQLiteDatabase(path)
    events = SQLiteEventStore(database)
    cycle = ProactiveServiceCycle(
        SchedulerRuntime(
            SQLiteScheduleStore(database),
            EventRuntime(events),
        ),
        AttentionDeliveryRuntime(
            events,
            SQLiteAttentionDeliveryStore(database),
        ),
    )
    runs = SQLiteServiceCycleRunStore(database)
    return runs, ProactiveServiceRunner(cycle, runs)


def test_successful_cycle_persists_payload_free_history(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    runs, runner = build_runner(path)
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    report, run = runner.run(
        as_of=observed_at,
        sinks=(),
    )

    assert report.successful is True
    assert run.status == "succeeded"
    assert run.observed_at == observed_at
    assert run.finished_at is not None
    assert run.scheduled_events == 0
    assert run.delivery_attempts == 0
    assert run.delivery_failures == 0
    assert run.error_class is None
    assert runs.latest() == run
    assert runs.list() == (run,)


def test_delivery_failure_records_degraded_cycle(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    database = SQLiteDatabase(path)
    events = SQLiteEventStore(database)
    event = events.create(
        NewEvent(
            type="synthetic.notify",
            source="test",
            importance="urgent",
        ),
        attention="notify",
    )
    cycle = ProactiveServiceCycle(
        SchedulerRuntime(
            SQLiteScheduleStore(database),
            EventRuntime(events),
        ),
        AttentionDeliveryRuntime(
            events,
            SQLiteAttentionDeliveryStore(database),
        ),
    )
    runs = SQLiteServiceCycleRunStore(database)
    runner = ProactiveServiceRunner(cycle, runs)

    report, run = runner.run(
        as_of=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        sinks=(FailingSink(),),
    )

    assert report.successful is False
    assert run.status == "degraded"
    assert run.delivery_attempts == 1
    assert run.delivery_failures == 1
    assert run.error_class is None

    delivery = SQLiteAttentionDeliveryStore(database).get(event.id, "failing")
    assert delivery is not None
    assert delivery.last_error == "RuntimeError"


def test_cycle_exception_records_only_safe_error_class(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    runs, runner = build_runner(path)
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    class InvalidSink:
        @property
        def id(self) -> str:
            return "Invalid Sink"

        @property
        def accepted_attention(self) -> tuple[AttentionClass, ...]:
            return ("notify",)

        def deliver(
            self,
            event: EventRecord,
            *,
            delivery_key: str,
        ) -> None:
            raise AssertionError("must not deliver")

    with pytest.raises(ValueError, match="invalid attention sink ID"):
        runner.run(
            as_of=observed_at,
            sinks=(InvalidSink(),),
        )

    run = runs.latest()
    assert run is not None
    assert run.status == "failed"
    assert run.error_class == "ValueError"
    assert run.finished_at is not None


def test_new_lease_protected_run_repairs_abandoned_history(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ally.sqlite3"
    runs, runner = build_runner(path)
    old_started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    old = runs.start(
        observed_at=old_started,
        started_at=old_started,
    )

    with service_lease(
        SQLiteServiceLeaseStore(tmp_path / "runtime.sqlite3"),
        name="proactive-cycle",
        ttl_seconds=300,
        owner_id=OWNER,
    ):
        _, current = runner.run(
            as_of=old_started + timedelta(hours=1),
            sinks=(),
        )

    repaired = runs.get(old.id)
    assert repaired is not None
    assert repaired.status == "interrupted"
    assert repaired.error_class == "PreviousProcessInterrupted"
    assert repaired.finished_at is not None
    assert current.status == "succeeded"


def test_direct_double_start_is_rejected_as_history_corruption(
    tmp_path: Path,
) -> None:
    store = SQLiteServiceCycleRunStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    now = datetime.now(UTC)
    first = store.start(observed_at=now, started_at=now)

    with pytest.raises(ServiceRunConflictError, match="running record"):
        store.start(observed_at=now, started_at=now)

    assert store.latest() == first


def test_invalid_terminal_metrics_do_not_mutate_running_history(
    tmp_path: Path,
) -> None:
    store = SQLiteServiceCycleRunStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = store.start(observed_at=started, started_at=started)

    with pytest.raises(
        ValueError,
        match="successful service cycle cannot have delivery failures",
    ):
        store.finish(
            run.id,
            status="succeeded",
            finished_at=started + timedelta(seconds=1),
            delivery_attempts=1,
            delivery_failures=1,
        )

    assert store.get(run.id) == run


def test_terminal_run_cannot_finish_before_start(tmp_path: Path) -> None:
    store = SQLiteServiceCycleRunStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = store.start(observed_at=started, started_at=started)

    with pytest.raises(ValueError, match="cannot finish before"):
        store.finish(
            run.id,
            status="succeeded",
            finished_at=started - timedelta(seconds=1),
        )

    assert store.get(run.id) == run


def test_health_is_uninitialized_without_personal_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "missing.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"

    health = build_sqlite_service_health(
        database_path=database_path,
        runtime_database_path=runtime_path,
    )

    assert health.status == "uninitialized"
    assert health.database_exists is False
    assert health.runtime_database_exists is False
    assert not database_path.exists()
    assert not runtime_path.exists()


def test_health_is_uninitialized_before_first_service_cycle(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ally.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"
    SQLiteDatabase(database_path).migrate()

    health = build_sqlite_service_health(
        database_path=database_path,
        runtime_database_path=runtime_path,
    )

    assert health.status == "uninitialized"
    assert health.database_integrity_ok is True
    assert health.schema_current is True
    assert health.latest_cycle is None
    assert health.runtime_coordination_ok is True


def test_health_is_healthy_after_successful_cycle(tmp_path: Path) -> None:
    database_path = tmp_path / "ally.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"
    _, runner = build_runner(database_path)
    _, run = runner.run(
        as_of=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        sinks=(),
    )

    health = build_sqlite_service_health(
        database_path=database_path,
        runtime_database_path=runtime_path,
        as_of=run.finished_at,
    )

    assert health.status == "healthy"
    assert health.latest_cycle == run
    assert health.proactive_lease_active is False


def test_running_history_is_healthy_while_ephemeral_lease_is_active(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ally.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    runs = SQLiteServiceCycleRunStore(SQLiteDatabase(database_path))
    run = runs.start(observed_at=started, started_at=started)

    lease_store = SQLiteServiceLeaseStore(runtime_path)
    lease = lease_store.acquire(
        name="proactive-cycle",
        owner_id=OWNER,
        now=started,
        ttl_seconds=300,
    )
    assert lease is not None

    health = build_sqlite_service_health(
        database_path=database_path,
        runtime_database_path=runtime_path,
        as_of=started + timedelta(seconds=30),
    )

    assert health.status == "healthy"
    assert health.latest_cycle == run
    assert health.proactive_lease_active is True
    assert health.proactive_lease_expires_at == lease.expires_at


def test_running_history_without_active_lease_is_degraded(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ally.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    runs = SQLiteServiceCycleRunStore(SQLiteDatabase(database_path))
    run = runs.start(observed_at=started, started_at=started)

    health = build_sqlite_service_health(
        database_path=database_path,
        runtime_database_path=runtime_path,
        as_of=started + timedelta(minutes=1),
    )

    assert health.status == "degraded"
    assert health.latest_cycle == run
    assert health.proactive_lease_active is False


def test_expired_lease_does_not_make_running_history_healthy(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ally.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    runs = SQLiteServiceCycleRunStore(SQLiteDatabase(database_path))
    runs.start(observed_at=started, started_at=started)

    lease_store = SQLiteServiceLeaseStore(runtime_path)
    lease_store.acquire(
        name="proactive-cycle",
        owner_id=OWNER,
        now=started,
        ttl_seconds=30,
    )

    health = build_sqlite_service_health(
        database_path=database_path,
        runtime_database_path=runtime_path,
        as_of=started + timedelta(seconds=31),
    )

    assert health.status == "degraded"
    assert health.proactive_lease_active is False


def test_corrupt_runtime_coordination_database_is_degraded(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ally.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"
    _, runner = build_runner(database_path)
    runner.run(
        as_of=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        sinks=(),
    )
    runtime_path.write_bytes(b"not sqlite")

    health = build_sqlite_service_health(
        database_path=database_path,
        runtime_database_path=runtime_path,
    )

    assert health.status == "degraded"
    assert health.runtime_coordination_ok is False


def test_health_is_degraded_for_outdated_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "old.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"
    connection = sqlite3.connect(database_path)
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
        connection.execute(
            """
            INSERT INTO ally_schema_migrations(version, name, applied_at)
            VALUES (1, 'old', '2026-01-01T00:00:00+00:00')
            """
        )
        connection.commit()
    finally:
        connection.close()

    health = build_sqlite_service_health(
        database_path=database_path,
        runtime_database_path=runtime_path,
    )

    assert health.status == "degraded"
    assert health.database_integrity_ok is True
    assert health.schema_current is False
    assert health.applied_schema_versions == (1,)


def test_health_does_not_initialize_either_database(tmp_path: Path) -> None:
    database_path = tmp_path / "empty.sqlite3"
    runtime_path = tmp_path / "runtime.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.close()

    health = build_sqlite_service_health(
        database_path=database_path,
        runtime_database_path=runtime_path,
    )

    assert health.status == "uninitialized"
    assert not runtime_path.exists()

    connection = sqlite3.connect(database_path)
    try:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        connection.close()
    assert tables == []
