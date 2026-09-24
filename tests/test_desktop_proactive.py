from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ally.attention import DESKTOP_NOTIFICATION_SINK_ID
from ally.events import EventRuntime, NewEvent
from ally.scheduler import SchedulerRuntime
from ally.service import DesktopProactiveCoordinator, SQLiteServiceLeaseStore
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteDatabase,
    SQLiteEventStore,
    SQLiteScheduleStore,
    SQLiteServiceCycleRunStore,
)


def _coordinator(
    tmp_path: Path,
) -> tuple[
    DesktopProactiveCoordinator,
    SQLiteEventStore,
    SQLiteAttentionDeliveryStore,
]:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
    events = SQLiteEventStore(database)
    deliveries = SQLiteAttentionDeliveryStore(database)
    return (
        DesktopProactiveCoordinator(
            scheduler=SchedulerRuntime(
                SQLiteScheduleStore(database),
                EventRuntime(events),
            ),
            events=events,
            deliveries=deliveries,
            runs=SQLiteServiceCycleRunStore(database),
            leases=SQLiteServiceLeaseStore(tmp_path / "runtime.sqlite3"),
        ),
        events,
        deliveries,
    )


def test_prepare_exposes_only_rendered_notification_text(tmp_path: Path) -> None:
    coordinator, events, _ = _coordinator(tmp_path)
    event = events.create(
        NewEvent(
            type="synthetic.private-event",
            source="desktop-proactive-test",
            importance="urgent",
            payload={
                "summary": "Synthetic user-facing summary.",
                "private_detail": "must not leave the bridge candidate",
                "nested": {"secret": "synthetic-secret"},
            },
        ),
        attention="notify",
    )

    prepared = coordinator.prepare(
        as_of=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )

    assert prepared.run.status == "succeeded"
    assert prepared.run.scheduled_events == 0
    assert prepared.run.delivery_attempts == 0
    assert len(prepared.candidates) == 1
    candidate = prepared.candidates[0]
    assert candidate.event_id == event.id
    assert candidate.title == "Ally"
    assert candidate.body == "Synthetic user-facing summary."
    assert candidate.delivery_key == (
        f"attention:{DESKTOP_NOTIFICATION_SINK_ID}:{event.id}"
    )
    rendered = candidate.model_dump_json()
    assert "private_detail" not in rendered
    assert "synthetic-secret" not in rendered


def test_successful_native_result_removes_future_candidate(tmp_path: Path) -> None:
    coordinator, events, deliveries = _coordinator(tmp_path)
    event = events.create(
        NewEvent(
            type="synthetic.notify",
            source="desktop-proactive-test",
            importance="important",
            payload={"message": "Synthetic delivery."},
        ),
        attention="notify",
    )
    first = coordinator.prepare()
    candidate = first.candidates[0]

    recorded = coordinator.record_delivery_result(
        event_id=event.id,
        delivery_key_value=candidate.delivery_key,
        succeeded=True,
    )

    assert recorded.status == "succeeded"
    assert recorded.sink_id == DESKTOP_NOTIFICATION_SINK_ID
    assert coordinator.prepare().candidates == ()
    assert deliveries.get(event.id, DESKTOP_NOTIFICATION_SINK_ID) == recorded

    duplicate_ack = coordinator.record_delivery_result(
        event_id=event.id,
        delivery_key_value=candidate.delivery_key,
        succeeded=True,
    )
    assert duplicate_ack == recorded
    assert duplicate_ack.attempts == 1


def test_failed_native_result_remains_retryable(tmp_path: Path) -> None:
    coordinator, events, _ = _coordinator(tmp_path)
    event = events.create(
        NewEvent(
            type="synthetic.notify",
            source="desktop-proactive-test",
            importance="important",
            payload={"summary": "Synthetic retry."},
        ),
        attention="notify",
    )
    candidate = coordinator.prepare().candidates[0]

    failed = coordinator.record_delivery_result(
        event_id=event.id,
        delivery_key_value=candidate.delivery_key,
        succeeded=False,
    )

    assert failed.status == "failed"
    assert failed.last_error == "NativeUserNotificationDeliveryError"
    retry = coordinator.prepare().candidates
    assert len(retry) == 1
    assert retry[0].delivery_key == candidate.delivery_key


def test_native_result_rejects_wrong_key_and_non_deliverable_event(
    tmp_path: Path,
) -> None:
    coordinator, events, _ = _coordinator(tmp_path)
    event = events.create(
        NewEvent(
            type="synthetic.notify",
            source="desktop-proactive-test",
            importance="important",
        ),
        attention="notify",
    )

    with pytest.raises(ValueError, match="delivery key"):
        coordinator.record_delivery_result(
            event_id=event.id,
            delivery_key_value="attention:macos.notification:wrong",
            succeeded=True,
        )

    ignored = events.create(
        NewEvent(
            type="synthetic.ignore",
            source="desktop-proactive-test",
            importance="noise",
        ),
        attention="ignore",
    )
    with pytest.raises(ValueError, match="not eligible"):
        coordinator.record_delivery_result(
            event_id=ignored.id,
            delivery_key_value=(
                f"attention:{DESKTOP_NOTIFICATION_SINK_ID}:{ignored.id}"
            ),
            succeeded=True,
        )
