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
    AttentionEventView,
    AttentionHistoryBootstrapSection,
    BootstrapLimits,
    ChatTurnRequest,
    ChatTurnResult,
    CompleteDesktopProactiveRequest,
    ConversationBootstrapSection,
    ConversationView,
    DesktopNotificationResultRequest,
    InstructionResolutionView,
    InstructionSelectorRequest,
    KnowledgeIngestResult,
    KnowledgeSearchResult,
    KnowledgeSourceView,
    KnowledgeTextIngestRequest,
    LegacyManagedServiceView,
    MemoryProposalRequest,
    PendingAttentionBootstrapSection,
    RememberMemoryRequest,
    ResolveUserInstructionsRequest,
    RunTaskRequest,
    RuntimeInferenceStatus,
    RuntimeProfileCatalogView,
    RuntimeProfileSummary,
    SelectRuntimeProfileRequest,
    SetUserInstructionsEnabledRequest,
    SetUserInstructionsRequest,
    ServiceHealthBootstrapSection,
    ServiceHistoryBootstrapSection,
    SupersedeMemoryRequest,
    TaskBootstrapSection,
    TaskView,
)
from ally.application.operations import ApplicationOperations
from ally.attention import (
    DELIVERABLE_ATTENTION_CLASSES,
    AttentionDeliveryRecord,
    AttentionDeliveryStatus,
)
from ally.context import CompositeContextProvider, ContextProvider
from ally.conversations import Conversation, ConversationStore
from ally.egress import EgressInspection
from ally.events import AttentionClass, EventRecord
from ally.instructions import (
    InstructionContext,
    UserInstructions,
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
from ally.research import (
    ResearchService,
    WebResearchExecution,
    WebSearchRequest,
)
from ally.runtime import PersistentConversationRuntime
from ally.runtime_profiles import (
    InferenceTargetError,
    ResolvedInferenceTarget,
    RuntimeProfileCatalog,
    RuntimeProfileCatalogError,
    ValidatedRuntimeProfile,
)
from ally.service import (
    DesktopProactivePreparation,
    ServiceCycleRunRecord,
    ServiceHealthReport,
    ServiceLeaseUnavailableError,
    ServiceRunConflictError,
)
from ally.service.macos_launchd import ManagedServiceError
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
        runtime_profiles: RuntimeProfileCatalog | None = None,
    ) -> None:
        self._conversations = conversations
        self._memories = memories
        self._knowledge = knowledge
        self._instructions = instructions
        self._target_resolver = target_resolver
        self._provider_factory = provider_factory
        self._operations = operations
        self._runtime_profiles = runtime_profiles

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

    def runtime_profile_catalog(self) -> RuntimeProfileCatalogView:
        """Return only installed evidence-backed profiles and exact active state."""

        catalog = self._require_runtime_profiles()
        try:
            selection = catalog.selection()
            active_profile_id: str | None = None
            if selection is not None:
                active_profile_id = catalog.active().profile_id
            profiles = catalog.list()
        except RuntimeProfileCatalogError as exc:
            raise ApplicationStateError(
                "validated runtime profile catalog is unavailable or invalid"
            ) from exc

        return RuntimeProfileCatalogView(
            items=tuple(
                self._runtime_profile_summary(
                    profile,
                    active=profile.profile_id == active_profile_id,
                )
                for profile in profiles
            ),
            active_profile_id=active_profile_id,
        )

    def select_runtime_profile(
        self,
        request: SelectRuntimeProfileRequest,
    ) -> RuntimeProfileCatalogView:
        """Select one exact installed profile; never accept raw runtime coordinates."""

        catalog = self._require_runtime_profiles()
        try:
            catalog.select(request.profile_id)
        except RuntimeProfileCatalogError as exc:
            raise ApplicationStateError(
                "validated runtime profile selection failed"
            ) from exc
        return self.runtime_profile_catalog()

    def deselect_runtime_profile(self) -> RuntimeProfileCatalogView:
        """Clear active inference selection without deleting installed evidence."""

        catalog = self._require_runtime_profiles()
        try:
            catalog.deselect()
        except RuntimeProfileCatalogError as exc:
            raise ApplicationStateError(
                "validated runtime profile selection could not be cleared"
            ) from exc
        return self.runtime_profile_catalog()

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

    def list_user_instructions(
        self,
        *,
        include_disabled: bool = True,
    ) -> tuple[UserInstructions, ...]:
        """List private user-owned instruction profiles in deterministic scope order."""

        return self._instructions.list(include_disabled=include_disabled)

    def user_instructions(
        self,
        request: InstructionSelectorRequest,
    ) -> UserInstructions:
        """Return one exact instruction profile or a presentation-safe not-found error."""

        profile = self._instructions.get(
            scope=request.scope,
            scope_key=request.scope_key,
        )
        if profile is None:
            raise ApplicationNotFoundError(
                f"instruction profile not found: {request.scope}"
            )
        return profile

    def set_user_instructions(
        self,
        request: SetUserInstructionsRequest,
    ) -> UserInstructions:
        """Create or replace one private instruction profile."""

        return self._instructions.set(
            request.content,
            scope=request.scope,
            scope_key=request.scope_key,
            enabled=request.enabled,
        )

    def set_user_instructions_enabled(
        self,
        request: SetUserInstructionsEnabledRequest,
    ) -> UserInstructions:
        """Toggle one exact existing instruction profile without deleting content."""

        try:
            return self._instructions.set_enabled(
                request.enabled,
                scope=request.scope,
                scope_key=request.scope_key,
            )
        except KeyError as exc:
            raise ApplicationNotFoundError(
                f"instruction profile not found: {request.scope}"
            ) from exc

    def clear_user_instructions(
        self,
        request: InstructionSelectorRequest,
    ) -> bool:
        """Delete one exact instruction profile while leaving unrelated scopes intact."""

        return self._instructions.clear(
            scope=request.scope,
            scope_key=request.scope_key,
        )

    def resolve_user_instructions(
        self,
        request: ResolveUserInstructionsRequest,
    ) -> InstructionResolutionView:
        """Preview the exact enabled instruction contributions for a local context."""

        context = InstructionContext(
            project_key=request.project_key,
            conversation_key=request.conversation_key,
            task_key=request.task_key,
            session_instructions=request.session_instructions,
        )
        profiles = self._instructions.resolve(context)
        contributions = instruction_contributions(
            profiles,
            session_instructions=context.session_instructions,
        )
        return InstructionResolutionView(
            profiles=profiles,
            contributions=contributions,
            rendered=render_instruction_contributions(contributions) or None,
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
        try:
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
        except ValueError as exc:
            raise ApplicationStateError(
                "only an active memory can be corrected"
            ) from exc
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

    def inspect_web_research(self, request: WebSearchRequest) -> EgressInspection:
        """Inspect exact outbound search fields without network access."""

        research = self._require_research()
        return research.inspect_search(request)

    def search_web(
        self,
        request: WebSearchRequest,
        *,
        approved: bool = False,
    ) -> WebResearchExecution:
        """Run one exact-query web search through controlled egress."""

        research = self._require_research()
        return research.search(request, approved=approved)

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
        if view.task.status != "waiting_approval" or step.status != "approval_required":
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

    def list_attention_events(
        self,
        *,
        limit: int = 100,
        handled: bool | None = None,
    ) -> tuple[EventRecord, ...]:
        """List user-facing attention events, including handled history."""

        if limit < 1:
            raise ValueError("limit must be positive")
        operations = self._require_operations()
        collected: list[EventRecord] = []
        for attention in DELIVERABLE_ATTENTION_CLASSES:
            collected.extend(
                operations.events.list(
                    limit=limit,
                    attention=attention,
                    handled=handled,
                )
            )
        collected.sort(
            key=lambda event: (event.created_at, str(event.id)),
            reverse=True,
        )
        return tuple(collected[:limit])

    def attention_event(self, event_id: UUID) -> AttentionEventView:
        """Return one durable event with every delivery record for inspection."""

        operations = self._require_operations()
        event = operations.events.get(event_id)
        if event is None:
            raise ApplicationNotFoundError(f"Attention event not found: {event_id}")
        return AttentionEventView(
            event=event,
            deliveries=operations.attention_deliveries.list_for_event(event_id),
        )

    def mark_attention_handled(self, event_id: UUID) -> AttentionEventView:
        """Explicitly mark one event handled without changing delivery history."""

        operations = self._require_operations()
        try:
            operations.events.mark_handled(event_id)
        except KeyError as exc:
            raise ApplicationNotFoundError(
                f"Attention event not found: {event_id}"
            ) from exc
        return self.attention_event(event_id)

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

    def prepare_desktop_proactive(
        self,
        *,
        schedule_limit: int = 100,
        delivery_limit: int = 50,
    ) -> DesktopProactivePreparation:
        """Prepare one bounded proactive cycle for app-owned notification delivery."""

        operations = self._require_operations()
        coordinator = operations.desktop_proactive
        if coordinator is None:
            raise ApplicationUnavailableError(
                "desktop proactive coordinator is not available"
            )
        try:
            return coordinator.prepare(
                schedule_limit=schedule_limit,
                delivery_limit=delivery_limit,
            )
        except (ServiceLeaseUnavailableError, ServiceRunConflictError) as exc:
            raise ApplicationStateError(
                "desktop proactive cycle is already active or stale"
            ) from exc

    def record_desktop_notification_result(
        self,
        request: DesktopNotificationResultRequest,
    ) -> AttentionDeliveryRecord:
        """Record one exact app-owned notification result without accepting payload."""

        operations = self._require_operations()
        coordinator = operations.desktop_proactive
        if coordinator is None:
            raise ApplicationUnavailableError(
                "desktop proactive coordinator is not available"
            )
        try:
            return coordinator.record_delivery_result(
                run_id=request.run_id,
                event_id=request.event_id,
                delivery_key_value=request.delivery_key,
                succeeded=request.succeeded,
            )
        except KeyError as exc:
            raise ApplicationNotFoundError(
                "Attention event or proactive run was not found"
            ) from exc
        except (ServiceLeaseUnavailableError, ServiceRunConflictError) as exc:
            raise ApplicationStateError(
                "desktop notification acknowledgement is stale"
            ) from exc

    def complete_desktop_proactive(
        self,
        request: CompleteDesktopProactiveRequest,
    ) -> ServiceCycleRunRecord:
        """Finish one prepared desktop proactive run using durable counters."""

        operations = self._require_operations()
        coordinator = operations.desktop_proactive
        if coordinator is None:
            raise ApplicationUnavailableError(
                "desktop proactive coordinator is not available"
            )
        try:
            return coordinator.complete(request.run_id)
        except KeyError as exc:
            raise ApplicationNotFoundError(
                f"Service run not found: {request.run_id}"
            ) from exc
        except (ServiceLeaseUnavailableError, ServiceRunConflictError) as exc:
            raise ApplicationStateError(
                "desktop proactive completion is stale"
            ) from exc

    def service_history(
        self,
        *,
        limit: int = 50,
    ) -> tuple[ServiceCycleRunRecord, ...]:
        return self._require_operations().service_runs.list(limit=limit)

    def service_health(self) -> ServiceHealthReport:
        return self._require_operations().service_health()

    def legacy_managed_service_status(self) -> LegacyManagedServiceView:
        """Inspect the historical launchd service without exposing local paths."""

        operations = self._require_operations()
        service = operations.legacy_managed_service
        if service is None:
            raise ApplicationUnavailableError(
                "legacy managed-service migration is not available"
            )
        status = service.migration_status()
        return LegacyManagedServiceView(
            supported=status.supported,
            configured=status.configured,
            definition_state=status.definition_state,
            loaded=status.loaded,
            running=status.running,
            label=status.label,
            can_retire=status.can_retire,
        )

    def retire_legacy_managed_service(self) -> LegacyManagedServiceView:
        """Retire only a recognized Ally-owned historical launchd service."""

        operations = self._require_operations()
        service = operations.legacy_managed_service
        if service is None:
            raise ApplicationUnavailableError(
                "legacy managed-service migration is not available"
            )
        try:
            service.retire_legacy()
        except ManagedServiceError as exc:
            raise ApplicationStateError(
                "legacy managed-service retirement is not safe in the current state"
            ) from exc
        return self.legacy_managed_service_status()

    def _require_research(self) -> ResearchService:
        operations = self._require_operations()
        if operations.research is None:
            raise ApplicationUnavailableError("web research is not available")
        return operations.research

    def _require_runtime_profiles(self) -> RuntimeProfileCatalog:
        if self._runtime_profiles is None:
            raise ApplicationUnavailableError(
                "validated runtime profile catalog is not available"
            )
        return self._runtime_profiles

    @staticmethod
    def _runtime_profile_summary(
        profile: ValidatedRuntimeProfile,
        *,
        active: bool,
    ) -> RuntimeProfileSummary:
        return RuntimeProfileSummary(
            profile_id=profile.profile_id,
            generated_at=profile.generated_at,
            ally_version=profile.ally_version,
            model=profile.model,
            runtime_name=profile.runtime.name,
            runtime_version=profile.runtime.version,
            model_source=profile.runtime.model_source,
            quantization=profile.runtime.quantization,
            precision=profile.runtime.precision,
            model_size_bytes=profile.runtime.model_size_bytes,
            context_length=profile.runtime.context_length,
            apple_model=profile.hardware.apple_model,
            apple_chip=profile.hardware.apple_chip,
            total_memory_bytes=profile.hardware.total_memory_bytes,
            time_to_first_token_ms=profile.observations.time_to_first_token_ms,
            generation_tokens_per_second=(
                profile.observations.generation_tokens_per_second
            ),
            maximum_tested_context_tokens=(
                profile.observations.maximum_tested_context_tokens
            ),
            capability_evidence_name=profile.capability_evidence.name,
            capability_evidence_sha256=profile.capability_evidence.sha256,
            privacy_evidence_name=profile.privacy_evidence.name,
            privacy_evidence_sha256=profile.privacy_evidence.sha256,
            workflow_evidence_name=profile.workflow_evidence.name,
            workflow_evidence_sha256=profile.workflow_evidence.sha256,
            active=active,
        )

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
