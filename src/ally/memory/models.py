"""Long-term memory domain models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MemoryKind = Literal[
    "episodic",
    "semantic",
    "procedural",
    "preference",
    "relational",
]
MemoryPrivacy = Literal["private", "shared", "public"]
MemorySourceType = Literal["user", "conversation", "document", "tool", "system"]


class MemorySource(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: MemorySourceType
    id: str | None = None
    uri: str | None = None


class NewMemory(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: MemoryKind
    content: str = Field(min_length=1)
    source: MemorySource
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    privacy: MemoryPrivacy = "private"
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        for value in (self.observed_at, self.valid_from, self.valid_until):
            if value is not None and value.tzinfo is None:
                raise ValueError("memory timestamps must be timezone-aware")
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise ValueError("valid_until must be later than valid_from")
        return self


class MemoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    kind: MemoryKind
    content: str
    source: MemorySource
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)
    privacy: MemoryPrivacy
    created_at: datetime
    updated_at: datetime
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    supersedes: UUID | None = None
    superseded_at: datetime | None = None
    superseded_by: UUID | None = None
    retracted_at: datetime | None = None
