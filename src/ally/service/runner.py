"""Persisted lifecycle wrapper around one proactive service cycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ally.attention import AttentionSink
from ally.service.models import ServiceCycleRunRecord
from ally.service.proactive import ProactiveCycleReport, ProactiveServiceCycle
from ally.service.store import ServiceCycleRunStore

DEFAULT_STALE_RUN_AFTER = timedelta(hours=1)


class ProactiveServiceRunner:
    """Run one cycle while persisting payload-free lifecycle metadata."""

    def __init__(
        self,
        cycle: ProactiveServiceCycle,
        runs: ServiceCycleRunStore,
    ) -> None:
        self._cycle = cycle
        self._runs = runs

    def run(
        self,
        *,
        as_of: datetime,
        sinks: tuple[AttentionSink, ...],
        schedule_limit: int = 100,
        delivery_limit: int = 50,
        stale_after: timedelta = DEFAULT_STALE_RUN_AFTER,
    ) -> tuple[ProactiveCycleReport, ServiceCycleRunRecord]:
        started_at = datetime.now(UTC)
        if stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive")

        self._runs.recover_stale(
            before=started_at - stale_after,
            finished_at=started_at,
        )
        run = self._runs.start(
            observed_at=as_of,
            started_at=started_at,
        )

        try:
            report = self._cycle.run(
                as_of=as_of,
                sinks=sinks,
                schedule_limit=schedule_limit,
                delivery_limit=delivery_limit,
            )
        except Exception as exc:
            self._runs.finish(
                run.id,
                status="failed",
                finished_at=datetime.now(UTC),
                error_class=type(exc).__name__,
            )
            raise

        status = "succeeded" if report.successful else "degraded"
        finished = self._runs.finish(
            run.id,
            status=status,
            finished_at=datetime.now(UTC),
            scheduled_events=report.scheduled_events,
            delivery_attempts=report.delivery_attempts,
            delivery_failures=report.delivery_failures,
        )
        return report, finished
