"""Reliable delivery of persisted attention events to explicit sinks."""

from __future__ import annotations

from ally.attention.models import AttentionDeliveryRecord
from ally.attention.sinks import AttentionSink
from ally.attention.store import AttentionDeliveryStore
from ally.events import EventStore


def _bounded_error(exc: Exception) -> str:
    rendered = f"{type(exc).__name__}: {exc}"
    return rendered[:1000]


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

        accepted = sink.accepted_attention
        if not accepted:
            return ()

        events = self._events.pending_attention(
            attentions=accepted,
            limit=limit,
        )

        attempts: list[AttentionDeliveryRecord] = []
        for event in events:
            existing = self._deliveries.get(event.id, sink.id)
            if existing is not None and existing.status == "succeeded":
                continue

            try:
                sink.deliver(event)
            except Exception as exc:
                attempts.append(
                    self._deliveries.record_attempt(
                        event_id=event.id,
                        sink_id=sink.id,
                        succeeded=False,
                        error=_bounded_error(exc),
                    )
                )
                continue

            attempts.append(
                self._deliveries.record_attempt(
                    event_id=event.id,
                    sink_id=sink.id,
                    succeeded=True,
                )
            )

        return tuple(attempts)
