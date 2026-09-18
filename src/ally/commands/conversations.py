"""Conversation inspection commands."""

from __future__ import annotations

from uuid import UUID

from ally.commands._storage import build_conversation_store


def run_list_conversations(*, limit: int) -> int:
    store = build_conversation_store()
    conversations = store.list(limit=limit)

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

    store = build_conversation_store()
    conversation = store.get(identifier)
    if conversation is None:
        print(f"Conversation not found: {identifier}")
        return 2

    print(f"Conversation: {conversation.id}")
    print(f"Title: {conversation.title or '(untitled)'}")
    print()

    for message in store.list_messages(identifier):
        print(f"{message.role}: {message.content}")
    return 0
