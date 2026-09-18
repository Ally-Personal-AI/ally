"""Local interactive chat command."""

from __future__ import annotations

from ally.models import ChatMessage
from ally.models.errors import ModelProviderError
from ally.models.providers import OpenAICompatibleProvider
from ally.runtime import ConversationRuntime


def run_chat(
    *,
    endpoint: str,
    model: str,
    prompt: str | None,
    allow_remote: bool,
) -> int:
    history: list[ChatMessage] = []

    try:
        with OpenAICompatibleProvider(
            base_url=endpoint,
            model=model,
            allow_remote=allow_remote,
        ) as provider:
            runtime = ConversationRuntime(provider)

            if prompt is not None:
                response = runtime.respond(prompt)
                print(response.content)
                return 0

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

                response = runtime.respond(user_input, history=history)
                print(f"Ally: {response.content}")
                history.extend(
                    (
                        ChatMessage(role="user", content=user_input),
                        ChatMessage(role="assistant", content=response.content),
                    )
                )
    except (ModelProviderError, ValueError) as exc:
        print(f"Ally error: {exc}")
        return 2
