"""Event domain models for proactive Ally."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

EventImportance = Literal["noise", "routine", "important", "urgent", "critical"]
AttentionClass = Literal[
    "ignore",
    "remember",
    "mention_later",
    "notify",
    "interrupt",
    "act",
]

EVENT_IMPORTANCE_LEVELS: tuple[EventImportance, ...] = (
    "noise",
    "routine",
    "important",
    "urgent",
    "critical",
)
ATTENTION_CLASSES: tuple[AttentionClass, ...] = (
    "ignore",
    "remember",
    "mention_later",
    "notify",
    "interrupt",
    "act",
)


class NewEvent(BaseModel):
    """One observed event before attention policy is applied."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    source: str = Field(min_length=1)
    importance: EventImportance = "routine"
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    dedupe_key: str | None = Field(default=None, min_length=1)


class EventRecord(BaseModel):
    """Persisted event plus Ally's deterministic attention decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    type: str
    source: str
    importance: EventImportance
    attention: AttentionClass
    payload: dict[str, JsonValue]
    dedupe_key: str | None = None
    created_at: datetime
    handled_at: datetime | None = None
