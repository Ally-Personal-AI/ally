"""Conversation presentation adapter over Ally application services."""

from __future__ import annotations

from uuid import UUID

from ally.application import ApplicationNotFoundError
from ally.composition import build_default_application


def run_list_conversations(*, limit: int) -> int:
    try:
        conversations = build_default_application().list_conversations(limit=limit)
    except ValueError as exc:
        print(f"Conversation error: {exc}")
        return 2

    if not conversations:
        print("No conversations.")
        return 0

    for conversation in conversations:
        title = conversation.title or "(untitled)"
        print(f"{conversation.id}  {conversation.updated_at.isoformat()}  {title}")
    return 0


def run_show_conversation(*, conversation_id: str) -> int:
    try:
        identifier = UUID(conversation_id)
    except ValueError:
        print(f"Invalid conversation ID: {conversation_id}")
        return 2

    try:
        view = build_default_application().conversation(identifier)
    except ApplicationNotFoundError as exc:
        print(exc)
        return 2

    print(f"Conversation: {view.conversation.id}")
    print(f"Title: {view.conversation.title or '(untitled)'}")
    print()

    for message in view.messages:
        print(f"{message.role}: {message.content}")
    return 0
