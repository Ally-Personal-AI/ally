from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from ally.attention import (
    AttentionDeliveryRuntime,
    MacOSNotificationError,
    MacOSNotificationSink,
    MacOSNotificationStatus,
    NativeMacOSNotificationBackend,
    delivery_key,
    render_macos_notification,
)
from ally.commands import attention as attention_commands
from ally.events import EventRecord, EventRuntime, NewEvent
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteDatabase,
    SQLiteEventStore,
)


class RecordingBackend:
    def __init__(
        self,
        *,
        existing: set[str] | None = None,
        fail: bool = False,
        status: MacOSNotificationStatus | None = None,
    ) -> None:
        self.existing = set(existing or ())
        self.fail = fail
        self.deliveries: list[tuple[str, str, str]] = []
        self._status = status or MacOSNotificationStatus(
            supported=True,
            api_available=True,
            authorization="unobservable",
        )

    def contains(self, identifier: str) -> bool:
        return identifier in self.existing

    def deliver(self, *, identifier: str, title: str, body: str) -> None:
        if self.fail:
            raise MacOSNotificationError("PRIVATE-DETAIL-MUST-NOT-PERSIST")
        self.deliveries.append((identifier, title, body))
        self.existing.add(identifier)

    def status(self) -> MacOSNotificationStatus:
        return self._status


def event(
    *,
    attention: str = "notify",
    payload: dict[str, object] | None = None,
) -> EventRecord:
    return EventRecord.model_validate(
        {
            "id": uuid4(),
            "type": "synthetic.changed",
            "source": "synthetic",
            "importance": "urgent",
            "attention": attention,
            "payload": payload or {},
            "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        }
    )


def test_notification_render_uses_only_explicit_user_facing_summary() -> None:
    record = event(
        payload={
            "summary": "Meeting moved to 4 PM",
            "private_blob": "PRIVATE-CONTENT-MUST-NOT-APPEAR",
            "nested": {"secret": "also-private"},
        }
    )

    title, body = render_macos_notification(record)

    assert title == "Ally"
    assert body == "Meeting moved to 4 PM"
    assert "PRIVATE-CONTENT" not in body
    assert "also-private" not in body


def test_notification_render_falls_back_to_event_type_and_bounds_text() -> None:
    fallback = event(payload={"private_blob": "never render this"})
    _, fallback_body = render_macos_notification(fallback)
    assert fallback_body == "synthetic.changed"

    long_summary = event(payload={"summary": "x" * 1000})
    _, long_body = render_macos_notification(long_summary)
    assert len(long_body) == 500
    assert long_body.endswith("…")


def test_interrupt_uses_more_prominent_title() -> None:
    record = event(attention="interrupt", payload={"message": "Synthetic alert"})

    title, body = render_macos_notification(record)

    assert title == "Ally — Important"
    assert body == "Synthetic alert"


def test_sink_uses_stable_delivery_key_and_suppresses_native_duplicate() -> None:
    record = event(payload={"summary": "Synthetic"})
    key = delivery_key(sink_id="macos.notification", event_id=str(record.id))
    backend = RecordingBackend(existing={key})
    sink = MacOSNotificationSink(backend)

    sink.deliver(record, delivery_key=key)

    assert backend.deliveries == []


def test_sink_delivers_identifier_title_and_bounded_body() -> None:
    record = event(payload={"summary": "Synthetic notification"})
    key = delivery_key(sink_id="macos.notification", event_id=str(record.id))
    backend = RecordingBackend()
    sink = MacOSNotificationSink(backend)

    sink.deliver(record, delivery_key=key)

    assert backend.deliveries == [
        (key, "Ally", "Synthetic notification"),
    ]


def test_runtime_persists_only_error_class_for_native_failure(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
    events = SQLiteEventStore(database)
    deliveries = SQLiteAttentionDeliveryStore(database)
    record = EventRuntime(events).publish(
        NewEvent(
            type="synthetic.failure",
            source="synthetic",
            importance="urgent",
            payload={"summary": "PRIVATE-NOTIFICATION-TEXT"},
        )
    )
    sink = MacOSNotificationSink(RecordingBackend(fail=True))

    attempts = AttentionDeliveryRuntime(events, deliveries).deliver_pending(sink)

    assert len(attempts) == 1
    assert attempts[0].status == "failed"
    assert attempts[0].last_error == "MacOSNotificationError"
    assert "PRIVATE" not in attempts[0].model_dump_json()
    assert deliveries.get(record.id, sink.id) == attempts[0]


def test_native_backend_fails_closed_off_macos() -> None:
    with pytest.raises(MacOSNotificationError, match="only on macOS"):
        NativeMacOSNotificationBackend(platform_name="linux")


@pytest.mark.parametrize(
    ("authorization", "expected_code", "expected_status"),
    [
        ("authorized", 0, "ready"),
        ("denied", 2, "unavailable"),
        ("not_determined", 1, "degraded"),
        ("unobservable", 1, "degraded"),
    ],
)
def test_attention_health_is_payload_free_and_actionable(
    authorization: str,
    expected_code: int,
    expected_status: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = MacOSNotificationStatus.model_construct if False else None
    del status
    monkeypatch.setattr(
        attention_commands,
        "macos_notification_status",
        lambda: MacOSNotificationStatus(
            supported=True,
            api_available=True,
            authorization=authorization,  # type: ignore[arg-type]
        ),
    )

    result = attention_commands.run_attention_sink_health(
        sink_name="macos",
        json_output=True,
    )
    output = capsys.readouterr().out

    assert result == expected_code
    assert f'"status": "{expected_status}"' in output
    assert f'"authorization": "{authorization}"' in output
    assert "PRIVATE" not in output


def test_attention_health_reports_safe_unavailable_state(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        attention_commands,
        "macos_notification_status",
        lambda: MacOSNotificationStatus(
            supported=False,
            api_available=False,
            authorization="unobservable",
        ),
    )

    result = attention_commands.run_attention_sink_health(
        sink_name="macos",
        json_output=False,
    )
    output = capsys.readouterr().out

    assert result == 2
    assert "Status: unavailable" in output
    assert "Notification Center" in output
