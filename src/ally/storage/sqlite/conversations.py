"""SQLite implementation of conversation persistence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from ally.conversations import (
    Conversation,
    ConversationMessage,
    NewConversationMessage,
)
from ally.models import ChatRole
from ally.storage.sqlite.database import SQLiteDatabase


class SQLiteConversationStore:
    """Persist conversations in Ally's local SQLite database."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def create(self, *, title: str | None = None) -> Conversation:
        now = datetime.now(UTC)
        conversation = Conversation(
            id=uuid4(),
            title=title,
            created_at=now,
            updated_at=now,
        )
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations(id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(conversation.id),
                    conversation.title,
                    conversation.created_at.isoformat(),
                    conversation.updated_at.isoformat(),
                ),
            )
        return conversation

    def get(self, conversation_id: UUID) -> Conversation | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (str(conversation_id),),
            ).fetchone()
        if row is None:
            return None
        return self._conversation_from_row(
            cast(tuple[str, str | None, str, str], row)
        )

    def list(self, *, limit: int = 50) -> tuple[Conversation, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._database.connect() as connection:
            rows = cast(
                list[tuple[str, str | None, str, str]],
                connection.execute(
                    """
                    SELECT id, title, created_at, updated_at
                    FROM conversations
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall(),
            )
        return tuple(self._conversation_from_row(row) for row in rows)

    def list_messages(self, conversation_id: UUID) -> tuple[ConversationMessage, ...]:
        with self._database.connect() as connection:
            rows = cast(
                list[tuple[str, str, int, str, str, str]],
                connection.execute(
                    """
                    SELECT id, conversation_id, position, role, content, created_at
                    FROM conversation_messages
                    WHERE conversation_id = ?
                    ORDER BY position ASC
                    """,
                    (str(conversation_id),),
                ).fetchall(),
            )
        return tuple(self._message_from_row(row) for row in rows)

    def append_messages(
        self,
        conversation_id: UUID,
        messages: Sequence[NewConversationMessage],
    ) -> tuple[ConversationMessage, ...]:
        if not messages:
            return ()

        now = datetime.now(UTC)
        stored: list[ConversationMessage] = []

        with self._database.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM conversations WHERE id = ?",
                (str(conversation_id),),
            ).fetchone()
            if exists is None:
                raise KeyError(f"Unknown conversation: {conversation_id}")

            position_row = connection.execute(
                """
                SELECT COALESCE(MAX(position) + 1, 0)
                FROM conversation_messages
                WHERE conversation_id = ?
                """,
                (str(conversation_id),),
            ).fetchone()
            assert position_row is not None
            position = cast(tuple[int], position_row)[0]

            for offset, message in enumerate(messages):
                item = ConversationMessage(
                    id=uuid4(),
                    conversation_id=conversation_id,
                    position=position + offset,
                    role=message.role,
                    content=message.content,
                    created_at=now,
                )
                connection.execute(
                    """
                    INSERT INTO conversation_messages(
                        id, conversation_id, position, role, content, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(item.id),
                        str(item.conversation_id),
                        item.position,
                        item.role,
                        item.content,
                        item.created_at.isoformat(),
                    ),
                )
                stored.append(item)

            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now.isoformat(), str(conversation_id)),
            )

        return tuple(stored)

    @staticmethod
    def _conversation_from_row(
        row: tuple[str, str | None, str, str],
    ) -> Conversation:
        identifier, title, created_at, updated_at = row
        return Conversation(
            id=UUID(identifier),
            title=title,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )

    @staticmethod
    def _message_from_row(
        row: tuple[str, str, int, str, str, str],
    ) -> ConversationMessage:
        identifier, conversation_id, position, role, content, created_at = row
        return ConversationMessage(
            id=UUID(identifier),
            conversation_id=UUID(conversation_id),
            position=position,
            role=cast(ChatRole, role),
            content=content,
            created_at=datetime.fromisoformat(created_at),
        )
