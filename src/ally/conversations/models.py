"""Conversation domain models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ally.models import ChatRole


class Conversation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class NewConversationMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: ChatRole
    content: str = Field(min_length=1)


class ConversationMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    conversation_id: UUID
    position: int = Field(ge=0)
    role: ChatRole
    content: str
    created_at: datetime
