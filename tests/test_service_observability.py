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
    ServiceRunConflictError,
    SQLiteServiceLeaseStore,
    service_lease,
)
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteDatabase,
    SQLiteEventStore,
    SQLiteScheduleStore,
    SQLiteServiceCycleRunStore,
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

    report, run = runner.run(as_of=observed_at, sinks=())

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
    runner = ProactiveServiceRunner(
        ProactiveServiceCycle(
            SchedulerRuntime(
                SQLiteScheduleStore(database),
                EventRuntime(events),
            ),
            AttentionDeliveryRuntime(
                events,
                SQLiteAttentionDeliveryStore(database),
            ),
        ),
        SQLiteServiceCycleRunStore(database),
    )

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
    runs, runner = build_runner(tmp_path / "ally.sqlite3")

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
            as_of=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
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


def test_running_service_progress_is_payload_free_and_monotonic(
    tmp_path: Path,
) -> None:
    store = SQLiteServiceCycleRunStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = store.start(observed_at=started, started_at=started)

    progressed = store.update_running_progress(
        run.id,
        scheduled_events=2,
        delivery_attempts_delta=1,
        delivery_failures_delta=1,
    )

    assert progressed.status == "running"
    assert progressed.scheduled_events == 2
    assert progressed.delivery_attempts == 1
    assert progressed.delivery_failures == 1
    assert progressed.finished_at is None

    progressed_again = store.update_running_progress(
        run.id,
        delivery_attempts_delta=1,
    )
    assert progressed_again.scheduled_events == 2
    assert progressed_again.delivery_attempts == 2
    assert progressed_again.delivery_failures == 1


def test_running_service_progress_rejects_invalid_or_terminal_updates(
    tmp_path: Path,
) -> None:
    store = SQLiteServiceCycleRunStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    )
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = store.start(observed_at=started, started_at=started)

    with pytest.raises(ValueError, match="failure delta"):
        store.update_running_progress(
            run.id,
            delivery_attempts_delta=0,
            delivery_failures_delta=1,
        )

    finished = store.finish(
        run.id,
        status="succeeded",
        finished_at=started + timedelta(seconds=1),
    )
    assert finished.status == "succeeded"

    with pytest.raises(ServiceRunConflictError, match="no longer running"):
        store.update_running_progress(
            run.id,
            delivery_attempts_delta=1,
        )


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
