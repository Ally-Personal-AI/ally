"""Human-facing bounded service operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from ally.attention import (
    AttentionDeliveryRuntime,
    AttentionSinkName,
    MacOSNotificationError,
    build_attention_sink,
)
from ally.commands._storage import (
    build_attention_delivery_store,
    build_event_store,
    build_schedule_store,
    build_service_cycle_run_store,
    build_service_lease_store,
)
from ally.composition import build_default_application
from ally.events import EventRuntime
from ally.scheduler import ScheduleConflictError, SchedulerRuntime
from ally.service import (
    ProactiveServiceCycle,
    ProactiveServiceRunner,
    ServiceLeaseUnavailableError,
    ServiceRunConflictError,
    service_lease,
)


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
    sink_name: AttentionSinkName,
    lease_seconds: int,
    json_output: bool,
) -> int:
    try:
        sink = build_attention_sink(sink_name)
        observed_at = datetime.now(UTC) if at is None else _parse_timestamp(at)
        with service_lease(
            build_service_lease_store(),
            name="proactive-cycle",
            ttl_seconds=lease_seconds,
        ):
            event_store = build_event_store()
            runner = ProactiveServiceRunner(
                ProactiveServiceCycle(
                    SchedulerRuntime(
                        build_schedule_store(),
                        EventRuntime(event_store),
                    ),
                    AttentionDeliveryRuntime(
                        event_store,
                        build_attention_delivery_store(),
                    ),
                ),
                build_service_cycle_run_store(),
            )
            report, run = runner.run(
                as_of=observed_at,
                sinks=(sink,),
                schedule_limit=schedule_limit,
                delivery_limit=delivery_limit,
            )
    except (
        MacOSNotificationError,
        ScheduleConflictError,
        ServiceLeaseUnavailableError,
        ServiceRunConflictError,
        ValueError,
    ) as exc:
        print(f"Service error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                {
                    "cycle": report.model_dump(mode="json"),
                    "run": run.model_dump(mode="json"),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Run: {run.id}")
        print(f"Status: {run.status}")
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


def run_service_history(
    *,
    limit: int,
    json_output: bool,
) -> int:
    try:
        records = build_default_application().service_history(limit=limit)
    except ValueError as exc:
        print(f"Service error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                [record.model_dump(mode="json") for record in records],
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not records:
        print("No service cycle history.")
        return 0

    for record in records:
        finished = (
            record.finished_at.isoformat()
            if record.finished_at is not None
            else "(running)"
        )
        print(
            f"{record.id}  {record.status}  "
            f"started={record.started_at.isoformat()}  "
            f"finished={finished}  "
            f"scheduled={record.scheduled_events}  "
            f"deliveries={record.delivery_attempts}  "
            f"failures={record.delivery_failures}"
        )
        if record.error_class is not None:
            print(f"  error_class={record.error_class}")

    return 0


def run_service_health(*, json_output: bool) -> int:
    try:
        report = build_default_application().service_health()
    except ValueError as exc:
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
        print(f"Status: {report.status}")
        for check in report.checks:
            print(
                f"[{check.severity.upper()}] "
                f"{check.id}: {check.summary}"
            )
        print(f"Database exists: {report.database_exists}")
        print(f"Database integrity: {report.database_integrity_ok}")
        print(f"Schema current: {report.schema_current}")
        print(f"Runtime coordination: {report.runtime_coordination_ok}")
        print(f"Proactive lease active: {report.proactive_lease_active}")
        if report.latest_cycle is None:
            print("Latest cycle: (none)")
        else:
            print(
                f"Latest cycle: {report.latest_cycle.id} "
                f"{report.latest_cycle.status}"
            )

    if report.status == "healthy":
        return 0
    if report.status == "degraded":
        return 1
    return 2
