"""SQLite persistence for scoped Ally user instructions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from ally.instructions import InstructionContext, InstructionScope, UserInstructions
from ally.storage.sqlite.database import SQLiteDatabase

InstructionRow = tuple[str, str, str, int, str, str]


def _scope_key(scope: InstructionScope, scope_key: str | None) -> str:
    compact = (scope_key or "").strip()
    if scope == "global":
        if compact:
            raise ValueError("global instructions cannot have a scope key")
        return ""
    if not compact:
        raise ValueError(f"{scope} instructions require a scope key")
    if len(compact) > 512:
        raise ValueError("instruction scope key cannot exceed 512 characters")
    return compact


class SQLiteUserInstructionsStore:
    """Persist and resolve private instruction profiles in local SQLite."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def get(
        self,
        *,
        scope: InstructionScope = "global",
        scope_key: str | None = None,
    ) -> UserInstructions | None:
        key = _scope_key(scope, scope_key)
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT scope, scope_key, content, enabled, created_at, updated_at
                FROM user_instruction_profiles
                WHERE scope = ? AND scope_key = ?
                """,
                (scope, key),
            ).fetchone()
        if row is None:
            return None
        return self._from_row(cast(InstructionRow, row))

    def set(
        self,
        content: str,
        *,
        scope: InstructionScope = "global",
        scope_key: str | None = None,
        enabled: bool = True,
    ) -> UserInstructions:
        compact = content.strip()
        if not compact:
            raise ValueError("instructions cannot be empty")
        if len(compact) > 100_000:
            raise ValueError("instructions cannot exceed 100000 characters")
        key = _scope_key(scope, scope_key)

        now = datetime.now(UTC)
        existing = self.get(scope=scope, scope_key=key)
        created_at = existing.created_at if existing is not None else now

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO user_instruction_profiles(
                    scope, scope_key, content, enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, scope_key) DO UPDATE SET
                    content = excluded.content,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    scope,
                    key,
                    compact,
                    int(enabled),
                    created_at.isoformat(),
                    now.isoformat(),
                ),
            )
        return UserInstructions(
            scope=scope,
            scope_key=key,
            content=compact,
            enabled=enabled,
            created_at=created_at,
            updated_at=now,
        )

    def set_enabled(
        self,
        enabled: bool,
        *,
        scope: InstructionScope = "global",
        scope_key: str | None = None,
    ) -> UserInstructions:
        key = _scope_key(scope, scope_key)
        existing = self.get(scope=scope, scope_key=key)
        if existing is None:
            raise KeyError(f"No {scope} instruction profile for {key or 'global'}")

        now = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE user_instruction_profiles
                SET enabled = ?, updated_at = ?
                WHERE scope = ? AND scope_key = ?
                """,
                (int(enabled), now.isoformat(), scope, key),
            )
        return existing.model_copy(update={"enabled": enabled, "updated_at": now})

    def clear(
        self,
        *,
        scope: InstructionScope = "global",
        scope_key: str | None = None,
    ) -> bool:
        key = _scope_key(scope, scope_key)
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM user_instruction_profiles
                WHERE scope = ? AND scope_key = ?
                """,
                (scope, key),
            )
        return cursor.rowcount > 0

    def list(self, *, include_disabled: bool = True) -> tuple[UserInstructions, ...]:
        where = "" if include_disabled else "WHERE enabled = 1"
        with self._database.connect() as connection:
            rows = cast(
                list[InstructionRow],
                connection.execute(
                    f"""
                    SELECT scope, scope_key, content, enabled, created_at, updated_at
                    FROM user_instruction_profiles
                    {where}
                    ORDER BY
                        CASE scope
                            WHEN 'global' THEN 0
                            WHEN 'project' THEN 1
                            WHEN 'conversation' THEN 2
                            WHEN 'task' THEN 3
                        END,
                        scope_key
                    """
                ).fetchall(),
            )
        return tuple(self._from_row(row) for row in rows)

    def resolve(self, context: InstructionContext) -> tuple[UserInstructions, ...]:
        selectors: list[tuple[InstructionScope, str | None]] = [("global", None)]
        if context.project_key:
            selectors.append(("project", context.project_key))
        if context.conversation_key:
            selectors.append(("conversation", context.conversation_key))
        if context.task_key:
            selectors.append(("task", context.task_key))

        profiles: list[UserInstructions] = []
        for scope, key in selectors:
            profile = self.get(scope=scope, scope_key=key)
            if profile is not None and profile.enabled:
                profiles.append(profile)
        return tuple(profiles)

    @staticmethod
    def _from_row(row: InstructionRow) -> UserInstructions:
        scope, scope_key, content, enabled, created_at, updated_at = row
        return UserInstructions(
            scope=cast(InstructionScope, scope),
            scope_key=scope_key,
            content=content,
            enabled=bool(enabled),
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )
