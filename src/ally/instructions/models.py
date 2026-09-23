"""User-owned instruction profile models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserInstructions(BaseModel):
    """The current global user instruction profile."""

    model_config = ConfigDict(frozen=True)

    content: str = Field(min_length=1, max_length=100_000)
    created_at: datetime
    updated_at: datetime
