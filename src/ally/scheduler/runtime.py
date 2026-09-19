"""Turn due schedules into idempotent persisted Ally events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import JsonValue

from ally.events import EventRuntime, NewEvent
from ally.scheduler.models import ScheduleRecord, ScheduleTick
from ally.scheduler.store import ScheduleStore


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("tick timestamp must include a timezone offset")
    return value.astimezone(UTC)


def _next_occurrence(
    schedule: ScheduleRecord,
    *,
    as_of: datetime,
) -> tuple[int, datetime | None, bool]:
    scheduled_for = schedule.next_run_at
    if scheduled_for is None:
        raise ValueError("schedule has no next run")

    if schedule.interval_seconds is None:
        return 1, None, False

    interval = timedelta(seconds=schedule.interval_seconds)
    elapsed = as_of - scheduled_for
    occurrences = int(elapsed // interval) + 1
    next_run_at = scheduled_for + (interval * occurrences)
    return occurrences, next_run_at, True


class SchedulerRuntime:
    """Evaluate persisted schedules without owning a background daemon."""

    def __init__(
        self,
        schedules: ScheduleStore,
        events: EventRuntime,
    ) -> None:
        self._schedules = schedules
        self._events = events

    def tick(
        self,
        *,
        as_of: datetime,
        limit: int = 100,
    ) -> tuple[ScheduleTick, ...]:
        observed_at = _as_utc(as_of)
        due = self._schedules.due(as_of=observed_at, limit=limit)

        results: list[ScheduleTick] = []
        for schedule in due:
            scheduled_for = schedule.next_run_at
            if scheduled_for is None:
                continue

            scheduled_for = _as_utc(scheduled_for)
            occurrences, next_run_at, enabled = _next_occurrence(
                schedule,
                as_of=observed_at,
            )

            schedule_metadata: dict[str, JsonValue] = {
                "id": str(schedule.id),
                "name": schedule.name,
                "scheduled_for": scheduled_for.isoformat(),
                "observed_at": observed_at.isoformat(),
                "coalesced_occurrences": occurrences,
            }
            event = self._events.publish(
                NewEvent(
                    type=schedule.event_type,
                    source=f"schedule:{schedule.id}",
                    importance=schedule.importance,
                    payload={
                        "schedule": schedule_metadata,
                        "data": schedule.payload,
                    },
                    dedupe_key=(
                        f"schedule:{schedule.id}:{scheduled_for.isoformat()}"
                    ),
                )
            )

            updated = self._schedules.advance(
                schedule.id,
                expected_next_run_at=scheduled_for,
                next_run_at=next_run_at,
                last_run_at=observed_at,
                enabled=enabled,
            )
            results.append(
                ScheduleTick(
                    schedule_id=schedule.id,
                    event_id=event.id,
                    scheduled_for=scheduled_for,
                    coalesced_occurrences=occurrences,
                    next_run_at=updated.next_run_at,
                )
            )

        return tuple(results)
