"""Conversation persistence contract."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from ally.conversations.models import (
    Conversation,
    ConversationMessage,
    NewConversationMessage,
)


class ConversationStore(Protocol):
    """Storage contract for persistent conversations."""

    def create(self, *, title: str | None = None) -> Conversation:
        ...

    def get(self, conversation_id: UUID) -> Conversation | None:
        ...

    def list(self, *, limit: int = 50) -> tuple[Conversation, ...]:
        ...

    def delete(self, conversation_id: UUID) -> bool:
        ...

    def list_messages(self, conversation_id: UUID) -> tuple[ConversationMessage, ...]:
        ...

    def append_messages(
        self,
        conversation_id: UUID,
        messages: Sequence[NewConversationMessage],
    ) -> tuple[ConversationMessage, ...]:
        ...
