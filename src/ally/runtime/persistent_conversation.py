"""Conversation runtime backed by durable storage."""

from __future__ import annotations

from uuid import UUID

from ally.context import ContextProvider
from ally.conversations import ConversationStore, NewConversationMessage
from ally.models import ChatMessage, ChatResponse, ModelProvider
from ally.runtime.conversation import DEFAULT_SYSTEM_PROMPT, ConversationRuntime
from ally.runtime.grounded_conversation import GroundedConversationRuntime


class PersistentConversationRuntime:
    """Run a conversation while storing successful user/assistant exchanges."""

    def __init__(
        self,
        provider: ModelProvider,
        store: ConversationStore,
        conversation_id: UUID,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        context_provider: ContextProvider | None = None,
    ) -> None:
        if store.get(conversation_id) is None:
            raise KeyError(f"Unknown conversation: {conversation_id}")

        self._store = store
        self._conversation_id = conversation_id
        if context_provider is None:
            self._runtime: ConversationRuntime | GroundedConversationRuntime = (
                ConversationRuntime(provider, system_prompt=system_prompt)
            )
        else:
            self._runtime = GroundedConversationRuntime(
                provider,
                context_provider,
                system_prompt=system_prompt,
            )

    @property
    def conversation_id(self) -> UUID:
        return self._conversation_id

    def respond(self, user_input: str) -> ChatResponse:
        history = tuple(
            ChatMessage(role=message.role, content=message.content)
            for message in self._store.list_messages(self._conversation_id)
        )
        response = self._runtime.respond(user_input, history=history)
        self._store.append_messages(
            self._conversation_id,
            (
                NewConversationMessage(role="user", content=user_input),
                NewConversationMessage(role="assistant", content=response.content),
            ),
        )
        return response
