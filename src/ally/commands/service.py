"""Human-facing bounded service operations."""

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
    build_service_lease_store,
)
from ally.configuration import default_config_path
from ally.events import EventRuntime
from ally.scheduler import ScheduleConflictError, SchedulerRuntime
from ally.service import (
    ProactiveServiceCycle,
    collect_service_health,
    ServiceLeaseUnavailableError,
    service_lease,
)
from ally.storage import default_database_path, default_runtime_database_path


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
    lease_seconds: int,
    json_output: bool,
) -> int:
    if sink_name != "console":
        print(f"Service error: unknown attention sink: {sink_name}")
        return 2

    try:
        observed_at = datetime.now(UTC) if at is None else _parse_timestamp(at)
        with service_lease(
            build_service_lease_store(),
            name="proactive-cycle",
            ttl_seconds=lease_seconds,
        ):
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
    except (
        ScheduleConflictError,
        ServiceLeaseUnavailableError,
        ValueError,
    ) as exc:
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


def run_list_service_leases() -> int:
    now = datetime.now(UTC)
    records = build_service_lease_store().list()
    if not records:
        print("No service leases.")
        return 0

    for record in records:
        state = "active" if record.expires_at > now else "expired"
        print(
            f"{record.name}  {state}  "
            f"owner={record.owner_id}  expires={record.expires_at.isoformat()}"
        )
    return 0


def run_service_health(*, json_output: bool) -> int:
    report = collect_service_health(
        config_path=default_config_path(),
        database_path=default_database_path(),
        runtime_database_path=default_runtime_database_path(),
    )

    if json_output:
        print(
            json.dumps(
                report.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Overall: {report.overall}")
        for check in report.checks:
            print(f"{check.id}: {check.status} — {check.message}")

    return 2 if report.has_errors else 0
