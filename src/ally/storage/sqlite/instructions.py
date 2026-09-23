"""SQLite persistence for Ally user instructions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from ally.instructions import UserInstructions
from ally.storage.sqlite.database import SQLiteDatabase

InstructionRow = tuple[str, str, str]


class SQLiteUserInstructionsStore:
    """Persist the current global user instruction profile locally."""

    PROFILE_ID = "global"

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def get(self) -> UserInstructions | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT content, created_at, updated_at
                FROM user_instruction_profiles
                WHERE id = ?
                """,
                (self.PROFILE_ID,),
            ).fetchone()
        if row is None:
            return None
        return self._from_row(cast(InstructionRow, row))

    def set(self, content: str) -> UserInstructions:
        compact = content.strip()
        if not compact:
            raise ValueError("instructions cannot be empty")
        if len(compact) > 100_000:
            raise ValueError("instructions cannot exceed 100000 characters")

        now = datetime.now(UTC)
        existing = self.get()
        created_at = existing.created_at if existing is not None else now

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO user_instruction_profiles(
                    id, content, created_at, updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    content = excluded.content,
                    updated_at = excluded.updated_at
                """,
                (
                    self.PROFILE_ID,
                    compact,
                    created_at.isoformat(),
                    now.isoformat(),
                ),
            )
        return UserInstructions(
            content=compact,
            created_at=created_at,
            updated_at=now,
        )

    def clear(self) -> bool:
        with self._database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM user_instruction_profiles WHERE id = ?",
                (self.PROFILE_ID,),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _from_row(row: InstructionRow) -> UserInstructions:
        content, created_at, updated_at = row
        return UserInstructions(
            content=content,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )
