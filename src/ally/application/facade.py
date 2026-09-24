"""UI-neutral Ally application facade over existing domain/runtime boundaries."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from ally.application.models import (
    AllyBootstrapSnapshot,
    ApplicationNotFoundError,
    ApplicationStateError,
    ApplicationUnavailableError,
    ApproveTaskStepRequest,
    AttentionHistoryBootstrapSection,
    BootstrapLimits,
    ChatTurnRequest,
    ChatTurnResult,
    ConversationBootstrapSection,
    ConversationView,
    KnowledgeIngestResult,
    KnowledgeSearchResult,
    KnowledgeSourceView,
    KnowledgeTextIngestRequest,
    MemoryProposalRequest,
    PendingAttentionBootstrapSection,
    RememberMemoryRequest,
    RunTaskRequest,
    RuntimeInferenceStatus,
    ServiceHealthBootstrapSection,
    ServiceHistoryBootstrapSection,
    SupersedeMemoryRequest,
    TaskBootstrapSection,
    TaskView,
)
from ally.application.operations import ApplicationOperations
from ally.attention import AttentionDeliveryRecord, AttentionDeliveryStatus
from ally.context import CompositeContextProvider, ContextProvider
from ally.conversations import Conversation, ConversationStore
from ally.events import AttentionClass, EventRecord
from ally.instructions import (
    InstructionContext,
    UserInstructionsStore,
    instruction_contributions,
    render_instruction_contributions,
)
from ally.knowledge import KnowledgeSource, KnowledgeStore
from ally.knowledge.ingestion import TextKnowledgeIngestor
from ally.knowledge.retrieval import KnowledgeContextProvider, LexicalKnowledgeRetriever
from ally.memory import (
    MemoryKind,
    MemoryProposalBundle,
    MemoryRecord,
    MemorySource,
    MemoryStore,
    ModelMemoryProposer,
    NewMemory,
)
from ally.memory.retrieval import LexicalMemoryRetriever, MemoryContextProvider
from ally.models import ModelProvider
from ally.runtime import PersistentConversationRuntime
from ally.runtime_profiles import (
    InferenceTargetError,
    ResolvedInferenceTarget,
)
from ally.service import ServiceCycleRunRecord, ServiceHealthReport
from ally.tasks import TaskPlan, TaskRecord, TaskStepRecord

InferenceTargetResolver = Callable[
    [str | None, str | None],
    ResolvedInferenceTarget,
]
ProviderFactory = Callable[
    [ResolvedInferenceTarget],
    AbstractContextManager[ModelProvider],
]


class AllyApplication:
    """Application services shared by CLI and future local UI surfaces."""

    def __init__(
        self,
        *,
        conversations: ConversationStore,
        memories: MemoryStore,
        knowledge: KnowledgeStore,
        instructions: UserInstructionsStore,
        target_resolver: InferenceTargetResolver,
        provider_factory: ProviderFactory,
        operations: ApplicationOperations | None = None,
    ) -> None:
        self._conversations = conversations
        self._memories = memories
        self._knowledge = knowledge
        self._instructions = instructions
        self._target_resolver = target_resolver
        self._provider_factory = provider_factory
        self._operations = operations

    def resolve_inference_target(
        self,
        *,
        development_endpoint: str | None = None,
        development_model: str | None = None,
    ) -> ResolvedInferenceTarget:
        return self._target_resolver(development_endpoint, development_model)

    def runtime_status(self) -> RuntimeInferenceStatus:
        try:
            target = self.resolve_inference_target()
        except InferenceTargetError:
            return RuntimeInferenceStatus(
                state="unavailable",
                error_code="active_profile_unavailable",
            )
        return RuntimeInferenceStatus(state="ready", target=target)

    def bootstrap(
        self,
        *,
        limits: BootstrapLimits | None = None,
    ) -> AllyBootstrapSnapshot:
        """Return bounded best-effort read-only state for initial UI rendering."""

        selected = limits or BootstrapLimits()

        try:
            conversations = ConversationBootstrapSection(
                state="available",
                items=self.list_conversations(limit=selected.conversations),
            )
        except Exception:
            conversations = ConversationBootstrapSection(
                state="error",
                error_code="read_failed",
            )

        try:
            tasks = TaskBootstrapSection(
                state="available",
                items=self.list_tasks(limit=selected.tasks),
            )
        except ApplicationUnavailableError:
            tasks = TaskBootstrapSection(
                state="unavailable",
                error_code="operations_unavailable",
            )
        except Exception:
            tasks = TaskBootstrapSection(
                state="error",
                error_code="read_failed",
            )

        try:
            pending_attention = PendingAttentionBootstrapSection(
                state="available",
                items=self.pending_attention(limit=selected.pending_attention),
            )
        except ApplicationUnavailableError:
            pending_attention = PendingAttentionBootstrapSection(
                state="unavailable",
                error_code="operations_unavailable",
            )
        except Exception:
            pending_attention = PendingAttentionBootstrapSection(
                state="error",
                error_code="read_failed",
            )

        try:
            attention_history = AttentionHistoryBootstrapSection(
                state="available",
                items=self.attention_history(limit=selected.attention_history),
            )
        except ApplicationUnavailableError:
            attention_history = AttentionHistoryBootstrapSection(
                state="unavailable",
                error_code="operations_unavailable",
            )
        except Exception:
            attention_history = AttentionHistoryBootstrapSection(
                state="error",
                error_code="read_failed",
            )

        try:
            service_history = ServiceHistoryBootstrapSection(
                state="available",
                items=self.service_history(limit=selected.service_history),
            )
        except ApplicationUnavailableError:
            service_history = ServiceHistoryBootstrapSection(
                state="unavailable",
                error_code="operations_unavailable",
            )
        except Exception:
            service_history = ServiceHistoryBootstrapSection(
                state="error",
                error_code="read_failed",
            )

        try:
            service_health = ServiceHealthBootstrapSection(
                state="available",
                report=self.service_health(),
            )
        except ApplicationUnavailableError:
            service_health = ServiceHealthBootstrapSection(
                state="unavailable",
                error_code="operations_unavailable",
            )
        except Exception:
            service_health = ServiceHealthBootstrapSection(
                state="error",
                error_code="read_failed",
            )

        return AllyBootstrapSnapshot(
            runtime=self.runtime_status(),
            conversations=conversations,
            tasks=tasks,
            pending_attention=pending_attention,
            attention_history=attention_history,
            service_history=service_history,
            service_health=service_health,
        )

    def create_conversation(self, *, title: str | None = None) -> Conversation:
        return self._conversations.create(title=title)

    def list_conversations(self, *, limit: int = 50) -> tuple[Conversation, ...]:
        return self._conversations.list(limit=limit)

    def conversation(self, conversation_id: UUID) -> ConversationView:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise ApplicationNotFoundError(
                f"Conversation not found: {conversation_id}"
            )
        return ConversationView(
            conversation=conversation,
            messages=self._conversations.list_messages(conversation_id),
        )

    def send_message(self, request: ChatTurnRequest) -> ChatTurnResult:
        """Resolve inference before touching conversation/private context state."""

        target = self.resolve_inference_target(
            development_endpoint=request.development_endpoint,
            development_model=request.development_model,
        )

        if request.conversation_id is None:
            conversation = self._conversations.create(
                title=_title_for_message(request.message)
            )
        else:
            conversation = self._conversations.get(request.conversation_id)
            if conversation is None:
                raise ApplicationNotFoundError(
                    f"Conversation not found: {request.conversation_id}"
                )

        instructions = self._render_instructions(
            conversation_id=conversation.id,
            project_key=request.project_key,
            task_key=request.task_key,
            session_instructions=request.session_instructions,
        )
        context = self._private_context_provider()

        with self._provider_factory(target) as provider:
            response = PersistentConversationRuntime(
                provider,
                self._conversations,
                conversation.id,
                user_instructions=instructions,
                context_provider=context,
            ).respond(request.message)

        refreshed = self._conversations.get(conversation.id)
        if refreshed is None:
            raise ApplicationNotFoundError(
                f"Conversation not found after response: {conversation.id}"
            )
        return ChatTurnResult(
            conversation=refreshed,
            response=response,
            target=target,
        )

    def propose_memories(
        self,
        request: MemoryProposalRequest,
    ) -> MemoryProposalBundle:
        """Generate reviewable memory candidates without durable writes."""

        target = self.resolve_inference_target(
            development_endpoint=request.development_endpoint,
            development_model=request.development_model,
        )
        source = MemorySource(
            type=request.source_type,
            id=request.source_id,
            uri=request.source_uri,
        )
        with self._provider_factory(target) as provider:
            return ModelMemoryProposer(provider).propose(
                text=request.text,
                source=source,
                privacy=request.privacy,
            )

    def accept_memory_proposals(
        self,
        bundle: MemoryProposalBundle,
        *,
        indices: tuple[int, ...],
    ) -> tuple[MemoryRecord, ...]:
        """Persist only explicitly selected reviewable memory candidates."""

        if not indices:
            raise ValueError("at least one proposal index is required")
        if len(indices) != len(set(indices)):
            raise ValueError("proposal indices must be unique")
        selected = tuple(bundle.accepted_memory(index) for index in indices)
        return tuple(self._memories.create(memory) for memory in selected)

    def list_memories(
        self,
        *,
        kind: MemoryKind | None = None,
        include_inactive: bool = False,
        limit: int = 100,
    ) -> tuple[MemoryRecord, ...]:
        return self._memories.list(
            kind=kind,
            include_inactive=include_inactive,
            limit=limit,
        )

    def search_memories(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> tuple[MemoryRecord, ...]:
        return self._memories.search(query, limit=limit)

    def memory(self, memory_id: UUID) -> MemoryRecord:
        record = self._memories.get(memory_id)
        if record is None:
            raise ApplicationNotFoundError(f"Memory not found: {memory_id}")
        return record

    def remember(self, request: RememberMemoryRequest) -> MemoryRecord:
        return self._memories.create(
            NewMemory(
                kind=request.kind,
                content=request.content,
                source=MemorySource(type="user"),
                confidence=request.confidence,
                importance=request.importance,
                privacy=request.privacy,
                observed_at=datetime.now(UTC),
            )
        )

    def supersede_memory(
        self,
        request: SupersedeMemoryRequest,
    ) -> MemoryRecord:
        existing = self.memory(request.memory_id)
        _, replacement = self._memories.supersede(
            existing.id,
            NewMemory(
                kind=existing.kind,
                content=request.content,
                source=MemorySource(type="user"),
                confidence=1.0,
                importance=existing.importance,
                privacy=existing.privacy,
                observed_at=datetime.now(UTC),
                valid_from=existing.valid_from,
                valid_until=existing.valid_until,
            ),
        )
        return replacement

    def retract_memory(self, memory_id: UUID) -> MemoryRecord:
        try:
            return self._memories.retract(memory_id)
        except KeyError as exc:
            raise ApplicationNotFoundError(
                f"memory not found: {memory_id}"
            ) from exc

    def list_knowledge_sources(
        self,
        *,
        limit: int = 100,
    ) -> tuple[KnowledgeSource, ...]:
        return self._knowledge.list_sources(limit=limit)

    def knowledge_source(self, source_id: UUID) -> KnowledgeSourceView:
        source = self._knowledge.get_source(source_id)
        if source is None:
            raise ApplicationNotFoundError(
                f"Knowledge source not found: {source_id}"
            )
        return KnowledgeSourceView(
            source=source,
            revisions=self._knowledge.list_revisions(source_id),
            current_chunks=self._knowledge.list_current_chunks(source_id),
        )

    def search_knowledge(
        self,
        query: str,
        *,
        limit: int = 8,
    ) -> tuple[KnowledgeSearchResult, ...]:
        hits = LexicalKnowledgeRetriever(
            self._knowledge,
            limit=limit,
        ).retrieve(query)
        return tuple(
            KnowledgeSearchResult(
                source=hit.source,
                chunk=hit.chunk,
                score=hit.score,
            )
            for hit in hits
        )

    def ingest_knowledge_text(
        self,
        request: KnowledgeTextIngestRequest,
    ) -> KnowledgeIngestResult:
        source, revision = TextKnowledgeIngestor(self._knowledge).ingest_text(
            uri=request.uri,
            title=request.title,
            text=request.text,
            media_type=request.media_type,
        )
        return KnowledgeIngestResult(source=source, revision=revision)

    def ingest_knowledge_file(self, path: Path) -> KnowledgeIngestResult:
        source, revision = TextKnowledgeIngestor(self._knowledge).ingest_file(path)
        return KnowledgeIngestResult(source=source, revision=revision)

    def create_task(self, plan: TaskPlan) -> TaskView:
        operations = self._require_operations()
        task, steps = operations.tasks.create(plan)
        return TaskView(task=task, steps=steps)

    def list_tasks(self, *, limit: int = 50) -> tuple[TaskRecord, ...]:
        return self._require_operations().tasks.list(limit=limit)

    def task(self, task_id: UUID) -> TaskView:
        operations = self._require_operations()
        task = operations.tasks.get(task_id)
        if task is None:
            raise ApplicationNotFoundError(f"Task not found: {task_id}")
        return TaskView(
            task=task,
            steps=operations.tasks.list_steps(task_id),
        )

    def run_task(self, request: RunTaskRequest) -> TaskView:
        operations = self._require_operations()
        try:
            operations.task_runner.run(
                request.task_id,
                approved_steps=request.approved_steps,
            )
        except KeyError as exc:
            raise ApplicationNotFoundError(
                f"Task not found: {request.task_id}"
            ) from exc
        return self.task(request.task_id)

    def approve_task_step(self, request: ApproveTaskStepRequest) -> TaskView:
        """Approve one exact currently-paused step and continue deterministically."""

        view = self.task(request.task_id)
        step = next((item for item in view.steps if item.id == request.step_id), None)
        if step is None:
            raise ApplicationNotFoundError(
                f"Task step not found: {request.task_id}/{request.step_id}"
            )
        if step.status != "approval_required":
            raise ApplicationStateError(
                "task step is not currently waiting for explicit approval"
            )
        return self.run_task(
            RunTaskRequest(
                task_id=request.task_id,
                approved_steps=(request.step_id,),
            )
        )

    def retry_task_step(
        self,
        *,
        task_id: UUID,
        step_id: UUID,
    ) -> TaskStepRecord:
        operations = self._require_operations()
        try:
            return operations.tasks.retry_failed_step(task_id, step_id)
        except KeyError as exc:
            raise ApplicationNotFoundError(
                f"Task or step not found: {task_id}/{step_id}"
            ) from exc
        except ValueError as exc:
            raise ApplicationStateError(
                "task step is not currently eligible for retry"
            ) from exc

    def pending_attention(
        self,
        *,
        limit: int = 50,
    ) -> tuple[EventRecord, ...]:
        attentions: tuple[AttentionClass, ...] = (
            "interrupt",
            "notify",
            "mention_later",
        )
        return self._require_operations().events.pending_attention(
            attentions=attentions,
            limit=limit,
        )

    def attention_history(
        self,
        *,
        limit: int = 50,
        status: AttentionDeliveryStatus | None = None,
    ) -> tuple[AttentionDeliveryRecord, ...]:
        return self._require_operations().attention_deliveries.list(
            limit=limit,
            status=status,
        )

    def service_history(
        self,
        *,
        limit: int = 50,
    ) -> tuple[ServiceCycleRunRecord, ...]:
        return self._require_operations().service_runs.list(limit=limit)

    def service_health(self) -> ServiceHealthReport:
        return self._require_operations().service_health()

    def _require_operations(self) -> ApplicationOperations:
        if self._operations is None:
            raise ApplicationUnavailableError(
                "operational application services are not composed"
            )
        return self._operations

    def _private_context_provider(self) -> ContextProvider:
        return CompositeContextProvider(
            (
                MemoryContextProvider(LexicalMemoryRetriever(self._memories)),
                KnowledgeContextProvider(
                    LexicalKnowledgeRetriever(self._knowledge)
                ),
            ),
            limit=12,
        )

    def _render_instructions(
        self,
        *,
        conversation_id: UUID,
        project_key: str | None,
        task_key: str | None,
        session_instructions: str | None,
    ) -> str | None:
        context = InstructionContext(
            project_key=project_key,
            conversation_key=str(conversation_id),
            task_key=task_key,
            session_instructions=session_instructions,
        )
        profiles = self._instructions.resolve(context)
        contributions = instruction_contributions(
            profiles,
            session_instructions=context.session_instructions,
        )
        return render_instruction_contributions(contributions) or None


def _title_for_message(message: str) -> str | None:
    compact = " ".join(message.split())
    return None if not compact else compact[:80]
