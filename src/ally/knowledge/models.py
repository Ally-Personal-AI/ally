"""Personal knowledge domain models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NewKnowledgeSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    uri: str = Field(min_length=1)
    title: str = Field(min_length=1)
    media_type: str = Field(default="text/plain", min_length=1)


class NewKnowledgeChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    ordinal: int = Field(ge=0)
    content: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    uri: str
    title: str
    media_type: str
    current_revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class KnowledgeRevision(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    source_id: UUID
    revision: int = Field(ge=1)
    sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime


class KnowledgeChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    source_id: UUID
    revision_id: UUID
    revision: int = Field(ge=1)
    ordinal: int = Field(ge=0)
    content: str
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime
