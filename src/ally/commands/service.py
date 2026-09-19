"""Human-facing bounded proactive service-cycle command."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from ally.attention import (
    AttentionDeliveryRuntime,
    ConsoleAttentionSink,
)
from ally.commands._storage import (
    build_attention_delivery_store,
    build_event_store,
    build_schedule_store,
)
from ally.events import EventRuntime
from ally.scheduler import ScheduleConflictError, SchedulerRuntime
from ally.service import ProactiveServiceCycle


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {value}") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("service timestamp must include a timezone offset")
    return parsed.astimezone(UTC)


def run_proactive_cycle(
    *,
    at: str | None,
    schedule_limit: int,
    delivery_limit: int,
    sink_name: str,
    json_output: bool,
) -> int:
    if sink_name != "console":
        print(f"Service error: unknown attention sink: {sink_name}")
        return 2

    try:
        observed_at = datetime.now(UTC) if at is None else _parse_timestamp(at)
        event_store = build_event_store()
        cycle = ProactiveServiceCycle(
            SchedulerRuntime(
                build_schedule_store(),
                EventRuntime(event_store),
            ),
            AttentionDeliveryRuntime(
                event_store,
                build_attention_delivery_store(),
            ),
        )
        report = cycle.run(
            as_of=observed_at,
            sinks=(ConsoleAttentionSink(),),
            schedule_limit=schedule_limit,
            delivery_limit=delivery_limit,
        )
    except (ScheduleConflictError, ValueError) as exc:
        print(f"Service error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                report.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Observed at: {report.observed_at.isoformat()}")
        print(f"Scheduled events: {report.scheduled_events}")
        print(f"Delivery attempts: {report.delivery_attempts}")
        print(f"Delivery failures: {report.delivery_failures}")

    return 0 if report.successful else 2
