"""Conversation runtime grounded by provider-neutral retrieved context."""

from __future__ import annotations

from collections.abc import Sequence

from ally.context import ContextProvider
from ally.context.render import render_context
from ally.models import ChatMessage, ChatRequest, ChatResponse, ModelProvider
from ally.runtime.conversation import DEFAULT_SYSTEM_PROMPT


class GroundedConversationRuntime:
    """Retrieve reference context before each model request."""

    def __init__(
        self,
        provider: ModelProvider,
        context_provider: ContextProvider,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._provider = provider
        self._context_provider = context_provider
        self._system_prompt = system_prompt

    def respond(
        self,
        user_input: str,
        *,
        history: Sequence[ChatMessage] = (),
    ) -> ChatResponse:
        if not user_input.strip():
            raise ValueError("user_input cannot be empty")

        messages: list[ChatMessage] = []
        if self._system_prompt:
            messages.append(ChatMessage(role="system", content=self._system_prompt))

        context_text = render_context(self._context_provider.retrieve(user_input))
        if context_text:
            messages.append(ChatMessage(role="system", content=context_text))

        messages.extend(history)
        messages.append(ChatMessage(role="user", content=user_input))
        return self._provider.chat(ChatRequest(messages=tuple(messages)))
