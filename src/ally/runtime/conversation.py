"""Stateless conversation orchestration."""

from __future__ import annotations

from collections.abc import Sequence

from ally.models import ChatMessage, ChatRequest, ChatResponse, ModelProvider

DEFAULT_SYSTEM_PROMPT = (
    "You are Ally, a private, user-owned personal AI assistant. "
    "Be accurate, useful, direct, and explicit about uncertainty. "
    "Follow the user's instructions and engage with legitimate requests without "
    "unnecessary refusal, unsolicited moralizing, or viewpoint favoritism. "
    "Do not pretend to know facts you cannot verify or claim capabilities you do not have. "
    "Reasoning and discussion do not grant authority to take external actions; "
    "Ally's deterministic capability and privacy policies remain authoritative."
)


def compose_system_prompt(
    base_prompt: str = DEFAULT_SYSTEM_PROMPT,
    *,
    user_instructions: str | None = None,
) -> str:
    """Compose fixed Ally behavior with private user-owned instructions."""

    instructions = (user_instructions or "").strip()
    if not instructions:
        return base_prompt
    if not base_prompt:
        return f"User instructions:\n{instructions}"
    return f"{base_prompt}\n\nUser instructions:\n{instructions}"


class ConversationRuntime:
    """Build model requests without coupling conversation logic to a provider."""

    def __init__(
        self,
        provider: ModelProvider,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        user_instructions: str | None = None,
    ) -> None:
        self._provider = provider
        self._system_prompt = compose_system_prompt(
            system_prompt,
            user_instructions=user_instructions,
        )

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
