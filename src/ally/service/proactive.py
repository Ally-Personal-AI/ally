"""One bounded deterministic proactive service cycle."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ally.attention import (
    AttentionDeliveryRecord,
    AttentionDeliveryRuntime,
    AttentionSink,
)
from ally.attention.models import validate_sink_id
from ally.scheduler import SchedulerRuntime, ScheduleTick


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("service cycle timestamp must include a timezone offset")
    return value.astimezone(UTC)


class SinkDeliverySummary(BaseModel):
    """Delivery outcome for one explicit attention sink."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sink_id: str
    attempts: tuple[AttentionDeliveryRecord, ...] = ()
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)


class ProactiveCycleReport(BaseModel):
    """Structured result from one bounded proactive service cycle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observed_at: datetime
    schedule_ticks: tuple[ScheduleTick, ...] = ()
    deliveries: tuple[SinkDeliverySummary, ...] = ()

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @property
    def scheduled_events(self) -> int:
        return len(self.schedule_ticks)

    @property
    def delivery_attempts(self) -> int:
        return sum(summary.succeeded + summary.failed for summary in self.deliveries)

    @property
    def delivery_failures(self) -> int:
        return sum(summary.failed for summary in self.deliveries)

    @property
    def successful(self) -> bool:
        return self.delivery_failures == 0


class ProactiveServiceCycle:
    """Compose scheduling and attention delivery without owning a daemon."""

    def __init__(
        self,
        scheduler: SchedulerRuntime,
        attention: AttentionDeliveryRuntime,
    ) -> None:
        self._scheduler = scheduler
        self._attention = attention

    def run(
        self,
        *,
        as_of: datetime,
        sinks: tuple[AttentionSink, ...],
        schedule_limit: int = 100,
        delivery_limit: int = 50,
    ) -> ProactiveCycleReport:
        observed_at = _require_aware(as_of)
        if schedule_limit < 1:
            raise ValueError("schedule_limit must be positive")
        if delivery_limit < 1:
            raise ValueError("delivery_limit must be positive")

        sink_ids: list[str] = []
        seen_sinks: set[str] = set()
        for sink in sinks:
            sink_id = validate_sink_id(sink.id)
            if sink_id in seen_sinks:
                raise ValueError(f"duplicate attention sink ID: {sink_id}")
            seen_sinks.add(sink_id)
            sink_ids.append(sink_id)

        schedule_ticks = self._scheduler.tick(
            as_of=observed_at,
            limit=schedule_limit,
        )

        deliveries: list[SinkDeliverySummary] = []
        for sink, sink_id in zip(sinks, sink_ids, strict=True):
            attempts = self._attention.deliver_pending(
                sink,
                limit=delivery_limit,
            )
            succeeded = sum(record.status == "succeeded" for record in attempts)
            failed = sum(record.status == "failed" for record in attempts)
            deliveries.append(
                SinkDeliverySummary(
                    sink_id=sink_id,
                    attempts=attempts,
                    succeeded=succeeded,
                    failed=failed,
                )
            )

        return ProactiveCycleReport(
            observed_at=observed_at,
            schedule_ticks=schedule_ticks,
            deliveries=tuple(deliveries),
        )
