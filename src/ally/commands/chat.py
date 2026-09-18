"""Local interactive chat command."""

from __future__ import annotations

from uuid import UUID

from ally.commands._storage import build_conversation_store
from ally.models.errors import ModelProviderError
from ally.models.providers import OpenAICompatibleProvider
from ally.runtime import PersistentConversationRuntime


def _parse_conversation_id(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid conversation ID: {value}") from exc


def _title_for_prompt(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    compact = " ".join(prompt.split())
    if not compact:
        return None
    return compact[:80]


def run_chat(
    *,
    endpoint: str,
    model: str,
    prompt: str | None,
    allow_remote: bool,
    conversation_id: str | None,
) -> int:
    try:
        store = build_conversation_store()
        identifier = _parse_conversation_id(conversation_id)

        if identifier is None:
            conversation = store.create(title=_title_for_prompt(prompt))
        else:
            conversation = store.get(identifier)
            if conversation is None:
                raise ValueError(f"Conversation not found: {identifier}")

        with OpenAICompatibleProvider(
            base_url=endpoint,
            model=model,
            allow_remote=allow_remote,
        ) as provider:
            runtime = PersistentConversationRuntime(
                provider,
                store,
                conversation.id,
            )

            if prompt is not None:
                response = runtime.respond(prompt)
                print(response.content)
                return 0

            print(f"Conversation: {conversation.id}")
            print("Ally local chat. Type /exit to quit.")
            while True:
                try:
                    user_input = input("You: ").strip()
                except EOFError:
                    print()
                    return 0

                if user_input in {"/exit", "/quit"}:
                    return 0
                if not user_input:
                    continue

                response = runtime.respond(user_input)
                print(f"Ally: {response.content}")
    except (KeyError, ModelProviderError, ValueError) as exc:
        print(f"Ally error: {exc}")
        return 2
