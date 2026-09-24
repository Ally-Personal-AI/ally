"""Desktop-owned proactive cycle and notification-delivery reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ally.attention import DELIVERABLE_ATTENTION_CLASSES, AttentionDeliveryRecord
from ally.attention.notifications import render_notification
from ally.attention.runtime import delivery_key
from ally.attention.store import AttentionDeliveryStore
from ally.events import AttentionClass, EventStore
from ally.scheduler import SchedulerRuntime
from ally.service.leases import (
    ServiceLeaseUnavailableError,
    SQLiteServiceLeaseStore,
)
from ally.service.models import ServiceCycleRunRecord
from ally.service.store import ServiceCycleRunStore, ServiceRunConflictError

DESKTOP_NOTIFICATION_SINK_ID = "macos.notification"
DESKTOP_PROACTIVE_LEASE_NAME = "proactive-cycle"
DESKTOP_PROACTIVE_LEASE_SECONDS = 55
_NATIVE_DELIVERY_ERROR = "NativeUserNotificationDeliveryError"


class DesktopNotificationCandidate(BaseModel):
    """Payload-minimized app-owned notification request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    delivery_key: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=500)
    attention: AttentionClass
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("notification candidate timestamp must include a timezone")
        return value.astimezone(UTC)


class DesktopProactivePreparation(BaseModel):
    """One bounded scheduler preparation plus app-owned notification candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run: ServiceCycleRunRecord
    candidates: tuple[DesktopNotificationCandidate, ...] = ()


class DesktopProactiveCoordinator:
    """Prepare proactive work without delivering OS notifications itself."""

    def __init__(
        self,
        *,
        scheduler: SchedulerRuntime,
        events: EventStore,
        deliveries: AttentionDeliveryStore,
        runs: ServiceCycleRunStore,
        leases: SQLiteServiceLeaseStore,
    ) -> None:
        self._scheduler = scheduler
        self._events = events
        self._deliveries = deliveries
        self._runs = runs
        self._leases = leases

    def prepare(
        self,
        *,
        as_of: datetime | None = None,
        schedule_limit: int = 100,
        delivery_limit: int = 50,
    ) -> DesktopProactivePreparation:
        if schedule_limit < 1:
            raise ValueError("schedule_limit must be positive")
        if delivery_limit < 1:
            raise ValueError("delivery_limit must be positive")

        observed_at = datetime.now(UTC) if as_of is None else as_of
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("service timestamp must include a timezone offset")
        observed_at = observed_at.astimezone(UTC)

        run_id = uuid4()
        lease = self._leases.acquire(
            name=DESKTOP_PROACTIVE_LEASE_NAME,
            owner_id=run_id,
            now=datetime.now(UTC),
            ttl_seconds=DESKTOP_PROACTIVE_LEASE_SECONDS,
        )
        if lease is None:
            raise ServiceLeaseUnavailableError(
                "service lease is already held: proactive-cycle"
            )

        started_at = datetime.now(UTC)
        run: ServiceCycleRunRecord | None = None
        try:
            self._runs.interrupt_running(finished_at=started_at)
            run = self._runs.start(
                observed_at=observed_at,
                started_at=started_at,
                run_id=run_id,
            )
            ticks = self._scheduler.tick(
                as_of=observed_at,
                limit=schedule_limit,
            )
            candidates = self._candidates(limit=delivery_limit)
            run = self._runs.update_running_progress(
                run.id,
                scheduled_events=len(ticks),
            )
            if not candidates:
                run = self._runs.finish(
                    run.id,
                    status="succeeded",
                    finished_at=datetime.now(UTC),
                    scheduled_events=run.scheduled_events,
                    delivery_attempts=run.delivery_attempts,
                    delivery_failures=run.delivery_failures,
                )
                self._leases.release(
                    name=DESKTOP_PROACTIVE_LEASE_NAME,
                    owner_id=run_id,
                )
            return DesktopProactivePreparation(
                run=run,
                candidates=candidates,
            )
        except Exception as exc:
            try:
                if run is not None and run.status == "running":
                    self._runs.finish(
                        run.id,
                        status="failed",
                        finished_at=datetime.now(UTC),
                        scheduled_events=run.scheduled_events,
                        delivery_attempts=run.delivery_attempts,
                        delivery_failures=run.delivery_failures,
                        error_class=type(exc).__name__,
                    )
            finally:
                self._leases.release(
                    name=DESKTOP_PROACTIVE_LEASE_NAME,
                    owner_id=run_id,
                )
            raise

    def _candidates(
        self,
        *,
        limit: int,
    ) -> tuple[DesktopNotificationCandidate, ...]:
        page_size = max(50, limit)
        offset = 0
        selected: list[DesktopNotificationCandidate] = []

        while len(selected) < limit:
            events = self._events.pending_attention(
                attentions=DELIVERABLE_ATTENTION_CLASSES,
                limit=page_size,
                offset=offset,
            )
            if not events:
                break
            offset += len(events)

            for event in events:
                existing = self._deliveries.get(
                    event.id,
                    DESKTOP_NOTIFICATION_SINK_ID,
                )
                if existing is not None and existing.status == "succeeded":
                    continue

                title, body = render_notification(event)
                selected.append(
                    DesktopNotificationCandidate(
                        event_id=event.id,
                        delivery_key=delivery_key(
                            sink_id=DESKTOP_NOTIFICATION_SINK_ID,
                            event_id=str(event.id),
                        ),
                        title=title,
                        body=body,
                        attention=event.attention,
                        created_at=event.created_at,
                    )
                )
                if len(selected) >= limit:
                    break

            if len(events) < page_size:
                break

        return tuple(selected)

    def record_delivery_result(
        self,
        *,
        run_id: UUID,
        event_id: UUID,
        delivery_key_value: str,
        succeeded: bool,
    ) -> AttentionDeliveryRecord:
        event = self._events.get(event_id)
        if event is None:
            raise KeyError(f"Unknown event: {event_id}")
        if event.attention not in DELIVERABLE_ATTENTION_CLASSES:
            raise ValueError("event is not eligible for desktop notification delivery")

        expected = delivery_key(
            sink_id=DESKTOP_NOTIFICATION_SINK_ID,
            event_id=str(event.id),
        )
        if delivery_key_value != expected:
            raise ValueError("notification delivery key does not match event identity")

        existing = self._deliveries.get(
            event.id,
            DESKTOP_NOTIFICATION_SINK_ID,
        )
        if existing is not None and existing.status == "succeeded":
            return existing

        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"Unknown service cycle run: {run_id}")
        if run.status != "running":
            raise ServiceRunConflictError(
                f"service cycle is no longer running: {run_id}"
            )

        recorded = self._deliveries.record_attempt(
            event_id=event.id,
            sink_id=DESKTOP_NOTIFICATION_SINK_ID,
            succeeded=succeeded,
            error=None if succeeded else _NATIVE_DELIVERY_ERROR,
        )
        renewed = self._leases.renew(
            name=DESKTOP_PROACTIVE_LEASE_NAME,
            owner_id=run_id,
            now=datetime.now(UTC),
            ttl_seconds=DESKTOP_PROACTIVE_LEASE_SECONDS,
        )
        if renewed is None:
            raise ServiceLeaseUnavailableError(
                "desktop proactive lease expired before delivery acknowledgement"
            )
        self._runs.update_running_progress(
            run_id,
            delivery_attempts_delta=1,
            delivery_failures_delta=0 if succeeded else 1,
        )
        return recorded

    def complete(self, run_id: UUID) -> ServiceCycleRunRecord:
        """Finish one prepared cycle using only server-owned progress counters."""

        current = self._runs.get(run_id)
        if current is None:
            raise KeyError(f"Unknown service cycle run: {run_id}")
        if current.status != "running":
            self._leases.release(
                name=DESKTOP_PROACTIVE_LEASE_NAME,
                owner_id=run_id,
            )
            return current

        renewed = self._leases.renew(
            name=DESKTOP_PROACTIVE_LEASE_NAME,
            owner_id=run_id,
            now=datetime.now(UTC),
            ttl_seconds=DESKTOP_PROACTIVE_LEASE_SECONDS,
        )
        if renewed is None:
            raise ServiceLeaseUnavailableError(
                "desktop proactive lease is no longer active"
            )

        finished = self._runs.finish(
            run_id,
            status="degraded" if current.delivery_failures else "succeeded",
            finished_at=datetime.now(UTC),
            scheduled_events=current.scheduled_events,
            delivery_attempts=current.delivery_attempts,
            delivery_failures=current.delivery_failures,
        )
        self._leases.release(
            name=DESKTOP_PROACTIVE_LEASE_NAME,
            owner_id=run_id,
        )
        return finished
