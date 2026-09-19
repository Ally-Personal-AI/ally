"""Persisted delivery-attempt models for proactive attention."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AttentionDeliveryStatus = Literal["succeeded", "failed"]
AttentionSinkId = Annotated[
    str,
    Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    ),
]
_SINK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def validate_sink_id(value: str) -> str:
    """Validate a stable sink ID before it is used as persistent identity."""

    if _SINK_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid attention sink ID: {value}")
    return value


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

    @model_validator(mode="after")
    def validate_status_state(self) -> AttentionDeliveryRecord:
        if self.status == "succeeded":
            if self.delivered_at is None:
                raise ValueError("successful delivery requires delivered_at")
            if self.last_error is not None:
                raise ValueError("successful delivery cannot retain last_error")
        elif self.delivered_at is not None:
            raise ValueError("failed delivery cannot have delivered_at")
        return self
