"""Typed UI-neutral application request and response models."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ally.conversations import Conversation, ConversationMessage
from ally.tasks import TaskRecord, TaskStepRecord
from ally.knowledge import KnowledgeChunk, KnowledgeRevision, KnowledgeSource
from ally.memory import (
    MemoryKind,
    MemoryPrivacy,
    MemorySourceType,
)
from ally.models import ChatResponse
from ally.runtime_profiles import ResolvedInferenceTarget


class ApplicationError(ValueError):
    """Base error for UI-neutral Ally application operations."""


class ApplicationNotFoundError(ApplicationError):
    """Requested Ally-owned state does not exist."""


class ApplicationUnavailableError(ApplicationError):
    """Requested application capability is not composed in this instance."""


class ChatTurnRequest(BaseModel):
    """One private conversational turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message: str = Field(min_length=1)
    conversation_id: UUID | None = None
    project_key: str | None = None
    task_key: str | None = None
    session_instructions: str | None = Field(default=None, max_length=100_000)
    development_endpoint: str | None = None
    development_model: str | None = None


class ChatTurnResult(BaseModel):
    """Persisted conversation result with explicit inference provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    conversation: Conversation
    response: ChatResponse
    target: ResolvedInferenceTarget


class ConversationView(BaseModel):
    """Conversation metadata plus ordered durable messages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    conversation: Conversation
    messages: tuple[ConversationMessage, ...]


class RuntimeInferenceStatus(BaseModel):
    """Read-only readiness of daily private model inference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: Literal["ready", "unavailable"]
    target: ResolvedInferenceTarget | None = None
    error_code: Literal["active_profile_unavailable"] | None = None


class RememberMemoryRequest(BaseModel):
    """Explicit user-authorized memory creation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(min_length=1)
    kind: MemoryKind = "semantic"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    privacy: MemoryPrivacy = "private"


class MemoryProposalRequest(BaseModel):
    """Reviewable model memory-extraction request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    source_type: MemorySourceType = "user"
    source_id: str | None = None
    source_uri: str | None = None
    privacy: MemoryPrivacy = "private"
    development_endpoint: str | None = None
    development_model: str | None = None


class SupersedeMemoryRequest(BaseModel):
    """Explicit correction of one durable memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: UUID
    content: str = Field(min_length=1)


class KnowledgeTextIngestRequest(BaseModel):
    """In-memory text ingestion for desktop/mobile presentation layers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uri: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    media_type: str = Field(default="text/plain", min_length=1)


class KnowledgeIngestResult(BaseModel):
    """Result of deterministic personal-knowledge ingestion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: KnowledgeSource
    revision: KnowledgeRevision


class KnowledgeSourceView(BaseModel):
    """One source with revision history and current chunks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: KnowledgeSource
    revisions: tuple[KnowledgeRevision, ...]
    current_chunks: tuple[KnowledgeChunk, ...]


class KnowledgeSearchResult(BaseModel):
    """Serializable knowledge retrieval hit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: KnowledgeSource
    chunk: KnowledgeChunk
    score: float = Field(ge=0.0)


class TaskView(BaseModel):
    """Persisted task plus ordered step state for presentation surfaces."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: TaskRecord
    steps: tuple[TaskStepRecord, ...]


class RunTaskRequest(BaseModel):
    """Advance a task with explicit approvals for named step IDs only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID
    approved_steps: tuple[UUID, ...] = ()
