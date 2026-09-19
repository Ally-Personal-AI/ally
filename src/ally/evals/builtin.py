"""Built-in deterministic Ally behavioral evaluators."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ally.context import ContextBlock
from ally.context.render import render_context
from ally.evals.models import EvalCase, EvaluationOutcome
from ally.events import AttentionClass, DefaultAttentionPolicy, EventImportance, NewEvent
from ally.evals.registry import EvaluatorRegistry
from ally.knowledge.chunking import chunk_text
from ally.memory import MemoryKind, MemoryRecord, MemorySource, NewMemory
from ally.memory.retrieval import LexicalMemoryRetriever
from ally.security.network import private_grounding_allowed


class _EventAttentionInput(BaseModel):
    importance: EventImportance


class _EventAttentionExpected(BaseModel):
    attention: AttentionClass


class EventAttentionEvaluator:
    @property
    def name(self) -> str:
        return "event-attention-policy"

    @property
    def category(self) -> str:
        return "event_attention"

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        payload = _EventAttentionInput.model_validate(case.input)
        expected = _EventAttentionExpected.model_validate(case.expected)
        actual = DefaultAttentionPolicy().classify(
            NewEvent(
                type="eval.synthetic",
                source="eval",
                importance=payload.importance,
            )
        )
        return EvaluationOutcome(
            passed=actual == expected.attention,
            message=f"expected attention={expected.attention!r}, got {actual!r}",
        )


class _PrivateGroundingInput(BaseModel):
    endpoint: str
    allow_remote_private_context: bool


class _PrivateGroundingExpected(BaseModel):
    allowed: bool


class PrivateGroundingPolicyEvaluator:
    @property
    def name(self) -> str:
        return "private-grounding-policy"

    @property
    def category(self) -> str:
        return "private_grounding_policy"

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        payload = _PrivateGroundingInput.model_validate(case.input)
        expected = _PrivateGroundingExpected.model_validate(case.expected)
        actual = private_grounding_allowed(
            payload.endpoint,
            allow_remote_private_context=payload.allow_remote_private_context,
        )
        return EvaluationOutcome(
            passed=actual == expected.allowed,
            message=f"expected allowed={expected.allowed}, got {actual}",
        )


class _ContextBoundaryInput(BaseModel):
    source: str
    content: str


class ContextBoundaryEvaluator:
    @property
    def name(self) -> str:
        return "retrieved-context-boundary"

    @property
    def category(self) -> str:
        return "context_boundary"

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        payload = _ContextBoundaryInput.model_validate(case.input)
        rendered = render_context(
            (ContextBlock(source=payload.source, content=payload.content),)
        )
        has_guard = "reference data, not instructions" in rendered
        preserves_source = payload.source in rendered
        preserves_content = payload.content in rendered
        passed = has_guard and preserves_source and preserves_content
        return EvaluationOutcome(
            passed=passed,
            message=(
                f"guard={has_guard}, source={preserves_source}, "
                f"content={preserves_content}"
            ),
        )


class _ChunkingInput(BaseModel):
    text: str
    max_chars: int = 1600
    overlap_chars: int = 200


class _ChunkingExpected(BaseModel):
    min_chunks: int = Field(default=1, ge=1)


class KnowledgeChunkingEvaluator:
    @property
    def name(self) -> str:
        return "knowledge-chunking"

    @property
    def category(self) -> str:
        return "knowledge_chunking"

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        payload = _ChunkingInput.model_validate(case.input)
        expected = _ChunkingExpected.model_validate(case.expected)
        chunks = chunk_text(
            payload.text,
            max_chars=payload.max_chars,
            overlap_chars=payload.overlap_chars,
        )
        exact_offsets = all(
            payload.text[chunk.start_char : chunk.end_char] == chunk.content
            for chunk in chunks
        )
        bounded = all(len(chunk.content) <= payload.max_chars for chunk in chunks)
        contiguous_ordinals = [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
        enough = len(chunks) >= expected.min_chunks

        return EvaluationOutcome(
            passed=exact_offsets and bounded and contiguous_ordinals and enough,
            message=(
                f"chunks={len(chunks)}, exact_offsets={exact_offsets}, "
                f"bounded={bounded}, contiguous={contiguous_ordinals}"
            ),
        )


class _MemoryFixture(BaseModel):
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class _MemoryRetrievalInput(BaseModel):
    query: str
    memories: tuple[_MemoryFixture, ...]


class _MemoryRetrievalExpected(BaseModel):
    top_content: str


class _MemoryStore:
    def __init__(self, records: tuple[MemoryRecord, ...]) -> None:
        self._records = records

    def create(self, memory: NewMemory) -> MemoryRecord:
        raise NotImplementedError

    def get(self, memory_id: UUID) -> MemoryRecord | None:
        raise NotImplementedError

    def list(
        self,
        *,
        as_of: datetime | None = None,
        kind: MemoryKind | None = None,
        include_inactive: bool = False,
        limit: int = 100,
    ) -> tuple[MemoryRecord, ...]:
        del as_of, kind, include_inactive
        return self._records[:limit]

    def search(self, query: str, *, limit: int = 20) -> tuple[MemoryRecord, ...]:
        raise NotImplementedError

    def supersede(
        self,
        memory_id: UUID,
        replacement: NewMemory,
    ) -> tuple[MemoryRecord, MemoryRecord]:
        raise NotImplementedError

    def retract(self, memory_id: UUID) -> MemoryRecord:
        raise NotImplementedError


class MemoryRetrievalEvaluator:
    @property
    def name(self) -> str:
        return "memory-lexical-retrieval"

    @property
    def category(self) -> str:
        return "memory_retrieval"

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        payload = _MemoryRetrievalInput.model_validate(case.input)
        expected = _MemoryRetrievalExpected.model_validate(case.expected)
        now = datetime.now(UTC)
        records = tuple(
            MemoryRecord(
                id=uuid4(),
                kind="semantic",
                content=item.content,
                source=MemorySource(type="system"),
                confidence=1.0,
                importance=item.importance,
                privacy="private",
                created_at=now,
                updated_at=now,
            )
            for item in payload.memories
        )
        hits = LexicalMemoryRetriever(_MemoryStore(records), limit=1).retrieve(
            payload.query
        )
        top = hits[0].memory.content if hits else None
        return EvaluationOutcome(
            passed=top == expected.top_content,
            message=f"expected top={expected.top_content!r}, got {top!r}",
        )


def register_builtin_evaluators(registry: EvaluatorRegistry) -> None:
    """Register deterministic evaluators that require no model or external service."""

    registry.register(EventAttentionEvaluator())
    registry.register(PrivateGroundingPolicyEvaluator())
    registry.register(ContextBoundaryEvaluator())
    registry.register(KnowledgeChunkingEvaluator())
    registry.register(MemoryRetrievalEvaluator())
