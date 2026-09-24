"""UI-neutral Ally application facade over existing domain/runtime boundaries."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from ally.application.models import (
    ApplicationNotFoundError,
    ChatTurnRequest,
    ChatTurnResult,
    ConversationView,
    KnowledgeIngestResult,
    KnowledgeSearchResult,
    KnowledgeSourceView,
    KnowledgeTextIngestRequest,
    MemoryProposalRequest,
    RememberMemoryRequest,
    RuntimeInferenceStatus,
    SupersedeMemoryRequest,
)
from ally.context import CompositeContextProvider, ContextProvider
from ally.conversations import Conversation, ConversationStore
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
    ) -> None:
        self._conversations = conversations
        self._memories = memories
        self._knowledge = knowledge
        self._instructions = instructions
        self._target_resolver = target_resolver
        self._provider_factory = provider_factory

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
