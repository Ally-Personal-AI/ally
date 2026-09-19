"""Persisted delivery-attempt models for proactive attention."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

AttentionDeliveryStatus = Literal["succeeded", "failed"]
AttentionSinkId = Annotated[
    str,
    Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    ),
]
_SINK_ID_ADAPTER = TypeAdapter(AttentionSinkId)


def validate_sink_id(value: str) -> str:
    """Validate a stable sink ID before it is used as persistent identity."""

    return _SINK_ID_ADAPTER.validate_python(value)


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("delivery timestamps must include a timezone offset")
    return value


class AttentionDeliveryRecord(BaseModel):
    """One event's durable delivery state for one sink."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    event_id: UUID
    sink_id: AttentionSinkId
    status: AttentionDeliveryStatus
    attempts: int = Field(ge=1)
    last_error: str | None = Field(default=None, max_length=1000)
    created_at: datetime
    updated_at: datetime
    delivered_at: datetime | None = None

    @field_validator("created_at", "updated_at", "delivered_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _require_aware(value)
