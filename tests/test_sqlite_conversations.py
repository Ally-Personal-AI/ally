from pathlib import Path
from uuid import uuid4

import pytest

from ally.conversations import NewConversationMessage
from ally.storage.sqlite import SQLiteConversationStore, SQLiteDatabase


def build_store(path: Path) -> SQLiteConversationStore:
    return SQLiteConversationStore(SQLiteDatabase(path))


def test_store_persists_conversations_and_ordered_messages(tmp_path: Path) -> None:
    database_path = tmp_path / "ally.sqlite3"
    store = build_store(database_path)
    conversation = store.create(title="Synthetic conversation")

    stored = store.append_messages(
        conversation.id,
        (
            NewConversationMessage(role="user", content="hello"),
            NewConversationMessage(role="assistant", content="hi"),
        ),
    )

    assert [message.position for message in stored] == [0, 1]

    reopened = build_store(database_path)
    loaded = reopened.get(conversation.id)
    messages = reopened.list_messages(conversation.id)

    assert loaded is not None
    assert loaded.id == conversation.id
    assert loaded.title == "Synthetic conversation"
    assert [message.role for message in messages] == ["user", "assistant"]
    assert [message.content for message in messages] == ["hello", "hi"]


def test_store_migrations_are_idempotent(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")

    database.migrate()
    database.migrate()

    store = SQLiteConversationStore(database)
    assert store.list() == ()


def test_store_rejects_non_positive_list_limit(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")

    with pytest.raises(ValueError, match="positive"):
        store.list(limit=0)


def test_store_rejects_append_to_unknown_conversation(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")

    with pytest.raises(KeyError, match="Unknown conversation"):
        store.append_messages(
            uuid4(),
            (NewConversationMessage(role="user", content="hello"),),
        )


def test_store_delete_removes_conversation_and_messages(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    conversation = store.create(title="Synthetic delete target")
    stored = store.append_messages(
        conversation.id,
        (
            NewConversationMessage(role="user", content="delete me"),
            NewConversationMessage(role="assistant", content="deleted"),
        ),
    )
    assert len(stored) == 2

    assert store.delete(conversation.id) is True
    assert store.get(conversation.id) is None
    assert store.list_messages(conversation.id) == ()
    assert store.delete(conversation.id) is False
