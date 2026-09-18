"""Versioned SQLite schema migrations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="conversations",
        statements=(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE conversation_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                role TEXT NOT NULL
                    CHECK (role IN ('system', 'user', 'assistant', 'tool')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (conversation_id, position)
            )
            """,
            """
            CREATE INDEX idx_conversation_messages_conversation
            ON conversation_messages(conversation_id, position)
            """,
            """
            CREATE INDEX idx_conversations_updated_at
            ON conversations(updated_at DESC)
            """,
        ),
    ),
)
