"""Stateless conversation orchestration."""

from __future__ import annotations

from collections.abc import Sequence

from ally.models import ChatMessage, ChatRequest, ChatResponse, ModelProvider


DEFAULT_SYSTEM_PROMPT = (
    "You are Ally, a local-first personal AI assistant. "
    "Be accurate, useful, concise, and explicit about uncertainty."
)


class ConversationRuntime:
    """Build model requests without coupling conversation logic to a provider."""

    def __init__(
        self,
        provider: ModelProvider,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._provider = provider
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
        messages.extend(history)
        messages.append(ChatMessage(role="user", content=user_input))

        return self._provider.chat(ChatRequest(messages=tuple(messages)))
