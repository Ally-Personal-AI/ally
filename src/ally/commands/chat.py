"""Local interactive chat command."""

from __future__ import annotations

from uuid import UUID

from ally.commands._storage import (
    build_conversation_store,
    build_knowledge_store,
    build_memory_store,
    build_user_instructions_store,
)
from ally.context import CompositeContextProvider, ContextProvider
from ally.instructions import (
    InstructionContext,
    instruction_contributions,
    render_instruction_contributions,
)
from ally.knowledge.retrieval import KnowledgeContextProvider, LexicalKnowledgeRetriever
from ally.memory.retrieval import LexicalMemoryRetriever, MemoryContextProvider
from ally.models.errors import ModelProviderError
from ally.models.providers import OpenAICompatibleProvider
from ally.runtime import PersistentConversationRuntime
from ally.runtime_profiles import InferenceTargetError, resolve_inference_target


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


def run_chat(
    *,
    development_endpoint: str | None,
    development_model: str | None,
    prompt: str | None,
    conversation_id: str | None,
    instruction_project: str | None = None,
    instruction_task: str | None = None,
    session_instructions: str | None = None,
) -> int:
    try:
        target = resolve_inference_target(
            development_endpoint=development_endpoint,
            development_model=development_model,
        )
    except InferenceTargetError as exc:
        print(f"Inference target error: {exc}")
        return 2

    try:
        conversation_store = build_conversation_store()

        context_provider: ContextProvider | None = _build_private_context_provider()

        identifier = _parse_conversation_id(conversation_id)

        if identifier is None:
            conversation = conversation_store.create(title=_title_for_prompt(prompt))
        else:
            conversation = conversation_store.get(identifier)
            if conversation is None:
                raise ValueError(f"Conversation not found: {identifier}")

        instruction_context = InstructionContext(
            project_key=instruction_project,
            conversation_key=str(conversation.id),
            task_key=instruction_task,
            session_instructions=session_instructions,
        )
        profiles = build_user_instructions_store().resolve(instruction_context)
        contributions = instruction_contributions(
            profiles,
            session_instructions=instruction_context.session_instructions,
        )
        rendered_instructions = render_instruction_contributions(contributions) or None

        with OpenAICompatibleProvider(
            base_url=target.endpoint,
            model=target.model,
        ) as provider:
            runtime = PersistentConversationRuntime(
                provider,
                conversation_store,
                conversation.id,
                user_instructions=rendered_instructions,
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
    except ModelProviderError as exc:
        print(f"Ally provider error: {exc}")
        return 2
    except (KeyError, ValueError) as exc:
        print(f"Ally error: {exc}")
        return 2
