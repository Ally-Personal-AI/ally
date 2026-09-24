"""Typed UI-neutral application request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ally.attention import AttentionDeliveryRecord
from ally.conversations import Conversation, ConversationMessage
from ally.events import EventRecord
from ally.knowledge import KnowledgeChunk, KnowledgeRevision, KnowledgeSource
from ally.memory import (
    MemoryKind,
    MemoryPrivacy,
    MemorySourceType,
)
from ally.models import ChatResponse
from ally.runtime_profiles import ResolvedInferenceTarget
from ally.service import ServiceCycleRunRecord, ServiceHealthReport
from ally.tasks import TaskRecord, TaskStepRecord


class ApplicationError(ValueError):
    """Base error for UI-neutral Ally application operations."""


class ApplicationNotFoundError(ApplicationError):
    """Requested Ally-owned state does not exist."""


class ApplicationUnavailableError(ApplicationError):
    """Requested application capability is not composed in this instance."""


class ApplicationStateError(ApplicationError):
    """Requested action is not valid for the current durable state."""


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


class RuntimeProfileSummary(BaseModel):
    """Path-free presentation summary for one installed validated runtime profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime
    ally_version: str
    model: str
    runtime_name: str
    runtime_version: str
    model_source: str | None = None
    quantization: str | None = None
    precision: str | None = None
    model_size_bytes: int | None = None
    context_length: int | None = None
    apple_model: str | None = None
    apple_chip: str | None = None
    total_memory_bytes: int | None = None
    time_to_first_token_ms: float | None = None
    generation_tokens_per_second: float | None = None
    maximum_tested_context_tokens: int | None = None
    capability_evidence_name: str
    capability_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    privacy_evidence_name: str
    privacy_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    workflow_evidence_name: str
    workflow_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    active: bool = False


class RuntimeProfileCatalogView(BaseModel):
    """Installed validated profiles plus the exact active selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: tuple[RuntimeProfileSummary, ...]
    active_profile_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class SelectRuntimeProfileRequest(BaseModel):
    """Select exactly one already-installed validated runtime profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = Field(pattern=r"^[0-9a-f]{64}$")


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


class AttentionEventView(BaseModel):
    """One proactive event plus all durable delivery state for presentation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event: EventRecord
    deliveries: tuple[AttentionDeliveryRecord, ...]


class DesktopNotificationResultRequest(BaseModel):
    """Record only the result for one exact app-owned notification candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    delivery_key: str = Field(min_length=1, max_length=512)
    succeeded: bool


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


class ApproveTaskStepRequest(BaseModel):
    """Approve exactly one task step that is currently waiting for approval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID
    step_id: UUID


BootstrapSectionState = Literal["available", "unavailable", "error"]
BootstrapSectionErrorCode = Literal["operations_unavailable", "read_failed"]


class BootstrapLimits(BaseModel):
    """Bounded startup/dashboard collection limits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    conversations: int = Field(default=20, ge=1, le=100)
    tasks: int = Field(default=20, ge=1, le=100)
    pending_attention: int = Field(default=20, ge=1, le=100)
    attention_history: int = Field(default=20, ge=1, le=100)
    service_history: int = Field(default=10, ge=1, le=100)


class ConversationBootstrapSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: BootstrapSectionState
    items: tuple[Conversation, ...] = ()
    error_code: BootstrapSectionErrorCode | None = None


class TaskBootstrapSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: BootstrapSectionState
    items: tuple[TaskRecord, ...] = ()
    error_code: BootstrapSectionErrorCode | None = None


class PendingAttentionBootstrapSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: BootstrapSectionState
    items: tuple[EventRecord, ...] = ()
    error_code: BootstrapSectionErrorCode | None = None


class AttentionHistoryBootstrapSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: BootstrapSectionState
    items: tuple[AttentionDeliveryRecord, ...] = ()
    error_code: BootstrapSectionErrorCode | None = None


class ServiceHistoryBootstrapSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: BootstrapSectionState
    items: tuple[ServiceCycleRunRecord, ...] = ()
    error_code: BootstrapSectionErrorCode | None = None


class ServiceHealthBootstrapSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: BootstrapSectionState
    report: ServiceHealthReport | None = None
    error_code: BootstrapSectionErrorCode | None = None


class AllyBootstrapSnapshot(BaseModel):
    """Read-only bounded state for the first desktop/dashboard render."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime: RuntimeInferenceStatus
    conversations: ConversationBootstrapSection
    tasks: TaskBootstrapSection
    pending_attention: PendingAttentionBootstrapSection
    attention_history: AttentionHistoryBootstrapSection
    service_history: ServiceHistoryBootstrapSection
    service_health: ServiceHealthBootstrapSection
