import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ally.attention import AttentionDeliveryRuntime
from ally.events import AttentionClass, EventRecord, EventRuntime, NewEvent
from ally.scheduler import SchedulerRuntime
from ally.service import (
    ProactiveServiceCycle,
    ProactiveServiceRunner,
    ServiceRunConflictError,
)
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteDatabase,
    SQLiteEventStore,
    SQLiteScheduleStore,
    SQLiteServiceCycleRunStore,
    build_sqlite_service_health,
)


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


def test_cycle_exception_records_safe_error_class(tmp_path: Path) -> None:
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


def test_fresh_running_cycle_blocks_second_start(tmp_path: Path) -> None:
    store = SQLiteServiceCycleRunStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    now = datetime.now(UTC)
    first = store.start(observed_at=now, started_at=now)

    with pytest.raises(ServiceRunConflictError, match="already running"):
        store.start(observed_at=now, started_at=now)

    assert store.latest() == first


def test_stale_running_cycle_can_be_recovered(tmp_path: Path) -> None:
    store = SQLiteServiceCycleRunStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = store.start(observed_at=started, started_at=started)
    finished = started + timedelta(hours=2)

    recovered = store.recover_stale(
        before=started + timedelta(hours=1),
        finished_at=finished,
    )

    assert recovered == 1
    loaded = store.get(run.id)
    assert loaded is not None
    assert loaded.status == "interrupted"
    assert loaded.error_class == "StaleLeaseExpired"
    assert loaded.finished_at == finished


def test_nonstale_running_cycle_is_not_recovered(tmp_path: Path) -> None:
    store = SQLiteServiceCycleRunStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = store.start(observed_at=started, started_at=started)

    recovered = store.recover_stale(
        before=started,
        finished_at=started + timedelta(minutes=1),
    )

    assert recovered == 0
    assert store.get(run.id) == run


def test_health_is_uninitialized_without_database(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"

    health = build_sqlite_service_health(database_path=path)

    assert health.status == "uninitialized"
    assert health.database_exists is False
    assert health.database_integrity_ok is False
    assert health.schema_current is False
    assert not path.exists()


def test_health_is_uninitialized_before_first_service_cycle(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ally.sqlite3"
    SQLiteDatabase(path).migrate()

    health = build_sqlite_service_health(database_path=path)

    assert health.status == "uninitialized"
    assert health.database_exists is True
    assert health.database_integrity_ok is True
    assert health.schema_current is True
    assert health.latest_cycle is None


def test_health_is_healthy_after_successful_cycle(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    _, runner = build_runner(path)
    observed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    _, run = runner.run(as_of=observed_at, sinks=())

    health = build_sqlite_service_health(
        database_path=path,
        as_of=run.started_at + timedelta(minutes=1),
    )

    assert health.status == "healthy"
    assert health.latest_cycle == run
    assert health.database_integrity_ok is True
    assert health.schema_current is True


def test_health_is_degraded_for_stale_running_cycle(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    store = SQLiteServiceCycleRunStore(SQLiteDatabase(path))
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = store.start(observed_at=started, started_at=started)

    health = build_sqlite_service_health(
        database_path=path,
        as_of=started + timedelta(hours=2),
        stale_after=timedelta(hours=1),
    )

    assert health.status == "degraded"
    assert health.latest_cycle == run


def test_health_is_degraded_for_outdated_schema(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
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
        connection.execute(
            """
            INSERT INTO ally_schema_migrations(version, name, applied_at)
            VALUES (1, 'old', '2026-01-01T00:00:00+00:00')
            """
        )
        connection.commit()
    finally:
        connection.close()

    health = build_sqlite_service_health(database_path=path)

    assert health.status == "degraded"
    assert health.database_integrity_ok is True
    assert health.schema_current is False
    assert health.applied_schema_versions == (1,)


def test_health_does_not_mutate_uninitialized_sqlite_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "empty.sqlite3"
    connection = sqlite3.connect(path)
    connection.close()

    health = build_sqlite_service_health(database_path=path)

    assert health.status == "uninitialized"
    connection = sqlite3.connect(path)
    try:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        connection.close()
    assert tables == []


def test_invalid_terminal_metrics_do_not_mutate_running_cycle(
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


def test_stale_recovery_rejects_inverted_time_window(tmp_path: Path) -> None:
    store = SQLiteServiceCycleRunStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    cutoff = datetime(2026, 1, 1, 13, 0, tzinfo=UTC)

    with pytest.raises(ValueError, match="cannot precede cutoff"):
        store.recover_stale(
            before=cutoff,
            finished_at=cutoff - timedelta(seconds=1),
        )
