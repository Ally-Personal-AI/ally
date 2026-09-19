"""Reliable delivery of persisted attention events to explicit sinks."""

from __future__ import annotations

from ally.attention.models import AttentionDeliveryRecord, validate_sink_id
from ally.attention.sinks import (
    DELIVERABLE_ATTENTION_CLASSES,
    AttentionSink,
)
from ally.attention.store import AttentionDeliveryStore
from ally.events import AttentionClass, EventStore


def delivery_key(*, sink_id: str, event_id: str) -> str:
    """Return stable identity a sink may use for external idempotency."""

    return f"attention:{sink_id}:{event_id}"


def _safe_error(exc: Exception) -> str:
    """Persist only the exception class; arbitrary messages may contain secrets."""

    return type(exc).__name__


class AttentionDeliveryRuntime:
    """Deliver pending attention without changing user-handled event state."""

    def __init__(
        self,
        events: EventStore,
        deliveries: AttentionDeliveryStore,
    ) -> None:
        self._events = events
        self._deliveries = deliveries

    def deliver_pending(
        self,
        sink: AttentionSink,
        *,
        limit: int = 50,
    ) -> tuple[AttentionDeliveryRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")

        sink_id = validate_sink_id(sink.id)
        accepted_items: list[AttentionClass] = []
        for attention in sink.accepted_attention:
            if attention in DELIVERABLE_ATTENTION_CLASSES:
                accepted_items.append(attention)
        accepted = tuple(accepted_items)
        if not accepted:
            return ()

        page_size = max(50, limit)
        offset = 0
        attempts: list[AttentionDeliveryRecord] = []

        while len(attempts) < limit:
            events = self._events.pending_attention(
                attentions=accepted,
                limit=page_size,
                offset=offset,
            )
            if not events:
                break
            offset += len(events)

            for event in events:
                existing = self._deliveries.get(event.id, sink_id)
                if existing is not None and existing.status == "succeeded":
                    continue

                key = delivery_key(
                    sink_id=sink_id,
                    event_id=str(event.id),
                )
                try:
                    sink.deliver(event, delivery_key=key)
                except Exception as exc:
                    attempts.append(
                        self._deliveries.record_attempt(
                            event_id=event.id,
                            sink_id=sink_id,
                            succeeded=False,
                            error=_safe_error(exc),
                        )
                    )
                else:
                    attempts.append(
                        self._deliveries.record_attempt(
                            event_id=event.id,
                            sink_id=sink_id,
                            succeeded=True,
                        )
                    )

                if len(attempts) >= limit:
                    break

            if len(events) < page_size:
                break

        return tuple(attempts)
