"""Local chat presentation adapter over Ally application services."""

from __future__ import annotations

from ally.application import (
    ApplicationNotFoundError,
    ChatTurnRequest,
)
from ally.composition import build_default_application
from ally.models.errors import ModelProviderError
from ally.runtime_profiles import InferenceTargetError


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
    app = build_default_application()

    try:
        if prompt is not None:
            identifier = _conversation_id(conversation_id)
            result = app.send_message(
                ChatTurnRequest(
                    message=prompt,
                    conversation_id=identifier,
                    project_key=instruction_project,
                    task_key=instruction_task,
                    session_instructions=session_instructions,
                    development_endpoint=development_endpoint,
                    development_model=development_model,
                )
            )
            print(result.response.content)
            return 0

        # Preserve the historical interactive behavior of creating the
        # conversation before the first prompt, but resolve inference first so
        # invalid/tampered runtime selection cannot mutate private state.
        app.resolve_inference_target(
            development_endpoint=development_endpoint,
            development_model=development_model,
        )
        conversation = app.create_conversation()
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

            result = app.send_message(
                ChatTurnRequest(
                    message=user_input,
                    conversation_id=conversation.id,
                    project_key=instruction_project,
                    task_key=instruction_task,
                    session_instructions=session_instructions,
                    development_endpoint=development_endpoint,
                    development_model=development_model,
                )
            )
            print(f"Ally: {result.response.content}")
    except InferenceTargetError as exc:
        print(f"Inference target error: {exc}")
        return 2
    except ModelProviderError as exc:
        print(f"Ally provider error: {exc}")
        return 2
    except (ApplicationNotFoundError, ValueError) as exc:
        print(f"Ally error: {exc}")
        return 2


def _conversation_id(value: str | None):
    if value is None:
        return None

    from uuid import UUID

    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid conversation ID: {value}") from exc
