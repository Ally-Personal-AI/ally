"""Domain models for persisted time-based event schedules."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from ally.events import EventImportance


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("schedule timestamps must include a timezone offset")
    return value


class NewSchedule(BaseModel):
    """One one-shot or fixed-interval schedule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    event_type: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    importance: EventImportance = "routine"
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    starts_at: datetime
    interval_seconds: int | None = Field(default=None, ge=1)
    enabled: bool = True

    @field_validator("starts_at")
    @classmethod
    def validate_starts_at(cls, value: datetime) -> datetime:
        return _require_aware(value)


class ScheduleRecord(BaseModel):
    """Persisted schedule state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    name: str
    event_type: str
    importance: EventImportance
    payload: dict[str, JsonValue]
    starts_at: datetime
    interval_seconds: int | None
    next_run_at: datetime | None
    last_run_at: datetime | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ScheduleTick(BaseModel):
    """Result of one schedule firing during a deterministic tick."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schedule_id: UUID
    event_id: UUID
    scheduled_for: datetime
    coalesced_occurrences: int = Field(ge=1)
    next_run_at: datetime | None
