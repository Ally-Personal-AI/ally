"""Human-facing proactive attention delivery commands."""

from __future__ import annotations

import json
import sys

from ally.attention import (
    AttentionDeliveryRuntime,
    AttentionDeliveryStatus,
    AttentionSinkName,
    MacOSNotificationError,
    build_attention_sink,
    macos_notification_status,
)
from ally.commands._storage import (
    build_attention_delivery_store,
    build_event_store,
)
from ally.events import AttentionClass

_PENDING_ATTENTION: tuple[AttentionClass, ...] = (
    "interrupt",
    "notify",
    "mention_later",
)


def run_list_pending_attention(*, limit: int) -> int:
    try:
        events = build_event_store().pending_attention(
            attentions=_PENDING_ATTENTION,
            limit=limit,
        )
    except ValueError as exc:
        print(f"Attention error: {exc}")
        return 2

    if not events:
        print("No pending attention.")
        return 0

    for event in events:
        print(
            f"{event.id}  {event.attention}  "
            f"{event.type}  {event.source}"
        )
    return 0


def run_deliver_attention(
    *,
    sink_name: AttentionSinkName,
    limit: int,
) -> int:
    runtime = AttentionDeliveryRuntime(
        build_event_store(),
        build_attention_delivery_store(),
    )
    try:
        sink = build_attention_sink(sink_name)
        attempts = runtime.deliver_pending(
            sink,
            limit=limit,
        )
    except (MacOSNotificationError, ValueError) as exc:
        print(f"Attention error: {exc}")
        return 2

    succeeded = sum(record.status == "succeeded" for record in attempts)
    failed = sum(record.status == "failed" for record in attempts)
    print(f"Delivery attempts: {len(attempts)}")
    print(f"Succeeded: {succeeded}")
    print(f"Failed: {failed}")
    return 2 if failed else 0


def run_attention_sink_health(
    *,
    sink_name: AttentionSinkName,
    json_output: bool,
) -> int:
    selected = (
        "macos"
        if sink_name == "auto" and sys.platform == "darwin"
        else "console"
        if sink_name == "auto"
        else sink_name
    )

    if selected == "console":
        report: dict[str, bool | str] = {
            "requested_sink": sink_name,
            "selected_sink": selected,
            "status": "ready",
            "supported": True,
            "api_available": True,
            "authorization": "not_required",
            "action": "none",
        }
        exit_code = 0
    else:
        status = macos_notification_status()
        if not status.supported or not status.api_available:
            state = "unavailable"
            action = "Native macOS Notification Center is unavailable."
            exit_code = 2
        elif status.authorization == "denied":
            state = "unavailable"
            action = (
                "Enable notifications for Ally in macOS System Settings, "
                "then retry the health check."
            )
            exit_code = 2
        elif status.authorization == "not_determined":
            state = "degraded"
            action = (
                "Notification authorization has not been decided; complete "
                "the dedicated-machine notification acceptance flow."
            )
            exit_code = 1
        elif status.authorization == "unobservable":
            state = "degraded"
            action = (
                "The CLI-native notification API cannot read authorization "
                "state; verify Ally notifications in macOS System Settings "
                "and complete dedicated-machine acceptance."
            )
            exit_code = 1
        else:
            state = "ready"
            action = "none"
            exit_code = 0

        report = {
            "requested_sink": sink_name,
            "selected_sink": selected,
            "status": state,
            "supported": status.supported,
            "api_available": status.api_available,
            "authorization": status.authorization,
            "backend": status.backend,
            "action": action,
        }

    if json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Sink: {report['selected_sink']}")
        print(f"Status: {report['status']}")
        print(f"Authorization: {report['authorization']}")
        if report["action"] != "none":
            print(f"Action: {report['action']}")
    return exit_code


def run_list_attention_history(
    *,
    limit: int,
    status: AttentionDeliveryStatus | None,
) -> int:
    try:
        records = build_attention_delivery_store().list(
            limit=limit,
            status=status,
        )
    except ValueError as exc:
        print(f"Attention error: {exc}")
        return 2

    if not records:
        print("No attention delivery history.")
        return 0

    for record in records:
        delivered = (
            record.delivered_at.isoformat()
            if record.delivered_at is not None
            else "(not delivered)"
        )
        print(
            f"{record.event_id}  sink={record.sink_id}  "
            f"{record.status}  attempts={record.attempts}  "
            f"delivered={delivered}"
        )
        if record.last_error is not None:
            print(f"  error={record.last_error}")

    return 0
