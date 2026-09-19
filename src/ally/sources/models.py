"""Validated data models for external event-source polling."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
)

from ally.events import EventImportance, EventRecord


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("event-source timestamps must include a timezone offset")
    return value


class EventSourceObservation(BaseModel):
    """One stable external observation before it becomes an Ally event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    external_id: str = Field(min_length=1, max_length=512)
    event_type: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    importance: EventImportance = "routine"
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class EventSourcePollResult(BaseModel):
    """One bounded source response from an opaque cursor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    observations: tuple[EventSourceObservation, ...] = ()
    next_cursor: str | None = Field(default=None, max_length=4096)


class EventSourceCheckpoint(BaseModel):
    """Persisted successful cursor state for one source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    cursor: str | None = Field(default=None, max_length=4096)
    successful_polls: int = Field(ge=1)
    observations_published: int = Field(ge=0)
    last_polled_at: datetime
    created_at: datetime
    updated_at: datetime

    @field_validator("last_polled_at", "created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return _require_aware(value)


class EventSourcePollReport(BaseModel):
    """Structured result from one successful source poll."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    from_cursor: str | None
    to_cursor: str | None
    events: tuple[EventRecord, ...] = ()
    checkpoint: EventSourceCheckpoint

    @property
    def published(self) -> int:
        return len(self.events)

    @property
    def event_ids(self) -> tuple[UUID, ...]:
        return tuple(event.id for event in self.events)
