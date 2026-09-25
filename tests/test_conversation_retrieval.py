from pathlib import Path

import pytest

from ally.conversations import (
    LexicalConversationRetriever,
    NewConversationMessage,
    conversation_snippet,
)
from ally.storage.sqlite import SQLiteConversationStore, SQLiteDatabase


def build_store(path: Path) -> SQLiteConversationStore:
    return SQLiteConversationStore(SQLiteDatabase(path))


def test_conversation_retrieval_finds_title_without_messages(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    conversation = store.create(title="Synthetic greenhouse planning")

    hits = LexicalConversationRetriever(store).retrieve("greenhouse")

    assert len(hits) == 1
    assert hits[0].conversation.id == conversation.id
    assert hits[0].message is None
    assert hits[0].score > 0.0


def test_conversation_retrieval_returns_one_best_hit_per_conversation(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    conversation = store.create(title="Synthetic thread")
    store.append_messages(
        conversation.id,
        (
            NewConversationMessage(
                role="user",
                content="The orchard marker is CEDAR-812.",
            ),
            NewConversationMessage(
                role="assistant",
                content="CEDAR-812 is the synthetic orchard marker.",
            ),
        ),
    )

    hits = LexicalConversationRetriever(store).retrieve("CEDAR-812")

    assert len(hits) == 1
    assert hits[0].conversation.id == conversation.id
    assert hits[0].message is not None


def test_conversation_snippet_is_bounded_and_centers_matching_text() -> None:
    text = (
        "prefix " * 80
        + "distinctive-marker "
        + "suffix " * 80
    )

    snippet = conversation_snippet(
        "distinctive marker",
        text,
        max_chars=90,
    )

    assert len(snippet) <= 90
    assert "distinctive-marker" in snippet
    assert snippet.startswith("…")
    assert snippet.endswith("…")


def test_conversation_retrieval_honors_conversation_and_result_limits(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    first = store.create(title="Synthetic alpha archive")
    second = store.create(title="Synthetic alpha notes")
    third = store.create(title="Synthetic alpha newest")
    store.append_messages(
        third.id,
        (NewConversationMessage(role="user", content="touch newest"),),
    )

    hits = LexicalConversationRetriever(
        store,
        limit=1,
        conversation_candidate_limit=2,
    ).retrieve("alpha")

    assert len(hits) == 1
    assert hits[0].conversation.id in {second.id, third.id}
    assert hits[0].conversation.id != first.id


def test_conversation_retrieval_honors_recent_message_bound(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    conversation = store.create(title="Synthetic thread")
    store.append_messages(
        conversation.id,
        (
            NewConversationMessage(
                role="user",
                content="ARCHIVE-991 appears only in the old message.",
            ),
            NewConversationMessage(
                role="assistant",
                content="A newer unrelated response.",
            ),
        ),
    )

    hits = LexicalConversationRetriever(
        store,
        messages_per_conversation=1,
    ).retrieve("ARCHIVE-991")

    assert hits == ()


def test_conversation_retrieval_honors_message_character_bound(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    conversation = store.create(title="Synthetic thread")
    store.append_messages(
        conversation.id,
        (
            NewConversationMessage(
                role="user",
                content=("x" * 80) + " TAIL-552",
            ),
        ),
    )

    hits = LexicalConversationRetriever(
        store,
        message_character_limit=40,
    ).retrieve("TAIL-552")

    assert hits == ()


def test_conversation_retrieval_stopword_only_query_returns_no_hits(
    tmp_path: Path,
) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    conversation = store.create(title="The synthetic conversation")
    store.append_messages(
        conversation.id,
        (NewConversationMessage(role="user", content="And this is a message."),),
    )

    assert LexicalConversationRetriever(store).retrieve("the and is") == ()


@pytest.mark.parametrize(
    "overrides",
    (
        {"limit": 0},
        {"conversation_candidate_limit": 0},
        {"messages_per_conversation": 0},
        {"message_candidate_limit": 0},
        {"message_character_limit": 0},
    ),
)
def test_conversation_retrieval_rejects_non_positive_bounds(
    tmp_path: Path,
    overrides: dict[str, int],
) -> None:
    store = build_store(tmp_path / "ally.sqlite3")

    with pytest.raises(ValueError, match="bounds must be positive"):
        LexicalConversationRetriever(store, **overrides)
