"""Human-facing proactive attention delivery commands."""

from __future__ import annotations

from ally.attention import (
    AttentionDeliveryRuntime,
    AttentionDeliveryStatus,
    ConsoleAttentionSink,
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
    sink_name: str,
    limit: int,
) -> int:
    if sink_name != "console":
        print(f"Attention error: unknown sink: {sink_name}")
        return 2

    runtime = AttentionDeliveryRuntime(
        build_event_store(),
        build_attention_delivery_store(),
    )
    try:
        attempts = runtime.deliver_pending(
            ConsoleAttentionSink(),
            limit=limit,
        )
    except ValueError as exc:
        print(f"Attention error: {exc}")
        return 2

    succeeded = sum(record.status == "succeeded" for record in attempts)
    failed = sum(record.status == "failed" for record in attempts)
    print(f"Delivery attempts: {len(attempts)}")
    print(f"Succeeded: {succeeded}")
    print(f"Failed: {failed}")
    return 2 if failed else 0


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
