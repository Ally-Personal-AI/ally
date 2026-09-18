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
    Migration(
        version=2,
        name="memory_v1",
        statements=(
            """
            CREATE TABLE memory_records (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL
                    CHECK (
                        kind IN (
                            'episodic',
                            'semantic',
                            'procedural',
                            'preference',
                            'relational'
                        )
                    ),
                content TEXT NOT NULL,
                source_type TEXT NOT NULL
                    CHECK (
                        source_type IN (
                            'user',
                            'conversation',
                            'document',
                            'tool',
                            'system'
                        )
                    ),
                source_id TEXT,
                source_uri TEXT,
                confidence REAL NOT NULL
                    CHECK (confidence >= 0.0 AND confidence <= 1.0),
                importance REAL NOT NULL
                    CHECK (importance >= 0.0 AND importance <= 1.0),
                privacy TEXT NOT NULL
                    CHECK (privacy IN ('private', 'shared', 'public')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                observed_at TEXT,
                valid_from TEXT,
                valid_until TEXT,
                supersedes TEXT REFERENCES memory_records(id),
                superseded_at TEXT,
                superseded_by TEXT REFERENCES memory_records(id),
                retracted_at TEXT
            )
            """,
            """
            CREATE INDEX idx_memory_active
            ON memory_records(superseded_at, retracted_at)
            """,
            """
            CREATE INDEX idx_memory_kind_importance
            ON memory_records(kind, importance DESC)
            """,
            """
            CREATE INDEX idx_memory_validity
            ON memory_records(valid_from, valid_until)
            """,
        ),
    ),
)
