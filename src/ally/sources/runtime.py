"""Restart-safe publication of external observations into Ally events."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from pydantic import JsonValue

from ally.events import EventRecord, EventRuntime, NewEvent
from ally.sources.models import EventSourcePollReport
from ally.sources.store import EventSourceCheckpointStore
from ally.sources.types import EventSource

_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def validate_source_id(value: str) -> str:
    if _SOURCE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid event source ID: {value}")
    return value


class EventSourceRuntime:
    """Poll one source, publish idempotent events, then advance its cursor."""

    def __init__(
        self,
        events: EventRuntime,
        checkpoints: EventSourceCheckpointStore,
    ) -> None:
        self._events = events
        self._checkpoints = checkpoints

    def poll(
        self,
        source: EventSource,
        *,
        limit: int = 100,
        polled_at: datetime | None = None,
    ) -> EventSourcePollReport:
        if limit < 1:
            raise ValueError("limit must be positive")

        source_id = validate_source_id(source.id)
        observed_at = polled_at or datetime.now(UTC)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("poll timestamp must include a timezone offset")
        observed_at = observed_at.astimezone(UTC)

        previous = self._checkpoints.get(source_id)
        cursor = None if previous is None else previous.cursor
        result = source.poll(cursor=cursor, limit=limit)

        if len(result.observations) > limit:
            raise ValueError("event source returned more observations than requested")

        external_ids = [observation.external_id for observation in result.observations]
        if len(external_ids) != len(set(external_ids)):
            raise ValueError("event source returned duplicate external IDs")

        if result.observations and (
            result.next_cursor is None or result.next_cursor == cursor
        ):
            raise ValueError(
                "event source must advance its cursor when observations are returned"
            )

        events: list[EventRecord] = []
        for observation in result.observations:
            source_metadata: dict[str, JsonValue] = {
                "id": source_id,
                "external_id": observation.external_id,
            }
            event = self._events.publish(
                NewEvent(
                    type=observation.event_type,
                    source=f"source:{source_id}",
                    importance=observation.importance,
                    payload={
                        "source": source_metadata,
                        "data": observation.payload,
                    },
                    dedupe_key=(
                        f"source:{source_id}:{observation.external_id}"
                    ),
                )
            )
            events.append(event)

        checkpoint = self._checkpoints.advance(
            source_id=source_id,
            expected_cursor=cursor,
            next_cursor=result.next_cursor,
            published=len(events),
            polled_at=observed_at,
        )

        return EventSourcePollReport(
            source_id=source_id,
            from_cursor=cursor,
            to_cursor=checkpoint.cursor,
            events=tuple(events),
            checkpoint=checkpoint,
        )
