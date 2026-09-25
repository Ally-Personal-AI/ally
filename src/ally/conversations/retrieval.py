"""Deterministic local conversation-history retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ally.context.lexical import bm25_scores, lexical_terms
from ally.conversations.models import Conversation, ConversationMessage
from ally.conversations.store import ConversationStore

DEFAULT_CONVERSATION_CANDIDATE_LIMIT = 250
DEFAULT_MESSAGES_PER_CONVERSATION = 50
DEFAULT_MESSAGE_CANDIDATE_LIMIT = 5_000
DEFAULT_MESSAGE_CHARACTER_LIMIT = 4_000
DEFAULT_SNIPPET_CHARACTER_LIMIT = 360


@dataclass(frozen=True)
class ConversationHit:
    """One best lexical hit for a conversation."""

    conversation: Conversation
    message: ConversationMessage | None
    score: float


@dataclass(frozen=True)
class _Candidate:
    conversation: Conversation
    message: ConversationMessage | None
    document: str


class LexicalConversationRetriever:
    """Rank recent local conversations with deterministic bounded BM25."""

    def __init__(
        self,
        store: ConversationStore,
        *,
        limit: int = 20,
        conversation_candidate_limit: int = DEFAULT_CONVERSATION_CANDIDATE_LIMIT,
        messages_per_conversation: int = DEFAULT_MESSAGES_PER_CONVERSATION,
        message_candidate_limit: int = DEFAULT_MESSAGE_CANDIDATE_LIMIT,
        message_character_limit: int = DEFAULT_MESSAGE_CHARACTER_LIMIT,
    ) -> None:
        bounds = (
            limit,
            conversation_candidate_limit,
            messages_per_conversation,
            message_candidate_limit,
            message_character_limit,
        )
        if any(value < 1 for value in bounds):
            raise ValueError("conversation retrieval bounds must be positive")

        self._store = store
        self._limit = limit
        self._conversation_candidate_limit = conversation_candidate_limit
        self._messages_per_conversation = messages_per_conversation
        self._message_candidate_limit = message_candidate_limit
        self._message_character_limit = message_character_limit

    def retrieve(self, query: str) -> tuple[ConversationHit, ...]:
        conversations = self._store.list(
            limit=self._conversation_candidate_limit,
        )
        candidates: list[_Candidate] = []
        message_candidates = 0

        for conversation in conversations:
            title = (conversation.title or "").strip()
            if title:
                candidates.append(
                    _Candidate(
                        conversation=conversation,
                        message=None,
                        document=title,
                    )
                )

            if message_candidates >= self._message_candidate_limit:
                continue

            messages = self._store.list_messages(conversation.id)
            recent_messages = messages[-self._messages_per_conversation :]
            for message in recent_messages:
                if message_candidates >= self._message_candidate_limit:
                    break
                candidates.append(
                    _Candidate(
                        conversation=conversation,
                        message=message,
                        document=message.content[: self._message_character_limit],
                    )
                )
                message_candidates += 1

        scores = bm25_scores(
            query,
            tuple(candidate.document for candidate in candidates),
        )

        best_by_conversation: dict[UUID, ConversationHit] = {}
        for candidate, score in zip(candidates, scores, strict=True):
            if score <= 0.0:
                continue
            hit = ConversationHit(
                conversation=candidate.conversation,
                message=candidate.message,
                score=score,
            )
            existing = best_by_conversation.get(candidate.conversation.id)
            if existing is None or _hit_candidate_key(hit) > _hit_candidate_key(
                existing
            ):
                best_by_conversation[candidate.conversation.id] = hit

        hits = list(best_by_conversation.values())
        hits.sort(
            key=lambda hit: (
                hit.score,
                hit.conversation.updated_at,
                str(hit.conversation.id),
            ),
            reverse=True,
        )
        return tuple(hits[: self._limit])


def conversation_snippet(
    query: str,
    text: str,
    *,
    max_chars: int = DEFAULT_SNIPPET_CHARACTER_LIMIT,
) -> str:
    """Return a bounded display snippet around the earliest lexical query match."""

    if max_chars < 8:
        raise ValueError("conversation snippet limit must be at least 8")

    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized

    lowered = normalized.lower()
    positions = [
        position
        for term in lexical_terms(query)
        if (position := lowered.find(term)) >= 0
    ]
    anchor = min(positions) if positions else 0

    content_budget = max_chars - 2
    start = max(0, anchor - content_budget // 3)
    end = min(len(normalized), start + content_budget)
    if end == len(normalized):
        start = max(0, end - content_budget)

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(normalized) else ""
    available = max_chars - len(prefix) - len(suffix)
    return f"{prefix}{normalized[start : start + available]}{suffix}"


def _hit_candidate_key(hit: ConversationHit) -> tuple[float, int, int, str]:
    if hit.message is None:
        return (hit.score, 1, -1, "")
    return (
        hit.score,
        0,
        hit.message.position,
        str(hit.message.id),
    )
