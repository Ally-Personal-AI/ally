"""Persisted delivery-attempt models for proactive attention."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AttentionDeliveryStatus = Literal["succeeded", "failed"]


class AttentionDeliveryRecord(BaseModel):
    """One event's durable delivery state for one sink."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    event_id: UUID
    sink_id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    status: AttentionDeliveryStatus
    attempts: int = Field(ge=1)
    last_error: str | None = Field(default=None, max_length=1000)
    created_at: datetime
    updated_at: datetime
    delivered_at: datetime | None = None
