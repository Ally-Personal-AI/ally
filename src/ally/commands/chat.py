"""Local interactive chat command."""

from __future__ import annotations

import sys
from uuid import UUID

from ally.commands._storage import (
    build_conversation_store,
    build_knowledge_store,
    build_memory_store,
)
from ally.context import CompositeContextProvider, ContextProvider
from ally.knowledge.retrieval import KnowledgeContextProvider, LexicalKnowledgeRetriever
from ally.memory.retrieval import LexicalMemoryRetriever, MemoryContextProvider
from ally.models.errors import ModelProviderError
from ally.models.providers import OpenAICompatibleProvider
from ally.runtime import PersistentConversationRuntime
from ally.security.network import is_loopback_http_url


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


def _build_private_context_provider() -> ContextProvider:
    return CompositeContextProvider(
        (
            MemoryContextProvider(LexicalMemoryRetriever(build_memory_store())),
            KnowledgeContextProvider(LexicalKnowledgeRetriever(build_knowledge_store())),
        ),
        limit=12,
    )


def _private_context_allowed(
    endpoint: str,
    *,
    allow_private_context_remote: bool,
) -> bool:
    return is_loopback_http_url(endpoint) or allow_private_context_remote


def run_chat(
    *,
    endpoint: str,
    model: str,
    prompt: str | None,
    allow_remote: bool,
    allow_private_context_remote: bool,
    conversation_id: str | None,
) -> int:
    try:
        conversation_store = build_conversation_store()
        is_remote = not is_loopback_http_url(endpoint)

        context_provider: ContextProvider | None = None
        if _private_context_allowed(
            endpoint,
            allow_private_context_remote=allow_private_context_remote,
        ):
            context_provider = _build_private_context_provider()
        elif allow_remote:
            print(
                "Private memory/document grounding is disabled for remote inference. "
                "Use --allow-private-context-remote to opt in.",
                file=sys.stderr,
            )

        identifier = _parse_conversation_id(conversation_id)

        if identifier is None:
            conversation = conversation_store.create(title=_title_for_prompt(prompt))
        else:
            conversation = conversation_store.get(identifier)
            if conversation is None:
                raise ValueError(f"Conversation not found: {identifier}")

        with OpenAICompatibleProvider(
            base_url=endpoint,
            model=model,
            allow_remote=allow_remote,
        ) as provider:
            runtime = PersistentConversationRuntime(
                provider,
                conversation_store,
                conversation.id,
                context_provider=context_provider,
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
