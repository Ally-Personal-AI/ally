"""Portable lifecycle wrapper around one proactive service cycle."""

from __future__ import annotations

from datetime import UTC, datetime

from ally.attention import AttentionSink
from ally.service.models import ServiceCycleRunRecord
from ally.service.proactive import ProactiveCycleReport, ProactiveServiceCycle
from ally.service.store import ServiceCycleRunStore


class ProactiveServiceRunner:
    """Record one lease-protected cycle as portable lifecycle history.

    The caller must acquire the ephemeral proactive service lease before invoking
    this runner. Coordination belongs to the runtime lease subsystem; this class
    records only user-owned operational history.
    """

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
    ) -> tuple[ProactiveCycleReport, ServiceCycleRunRecord]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("service cycle timestamp must include a timezone offset")
        observed_at = as_of.astimezone(UTC)
        started_at = datetime.now(UTC)

        self._runs.interrupt_running(finished_at=started_at)
        run = self._runs.start(
            observed_at=observed_at,
            started_at=started_at,
        )

        try:
            report = self._cycle.run(
                as_of=observed_at,
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
