"""Persistence contract for user-owned instructions."""

from __future__ import annotations

from typing import Protocol

from ally.instructions.models import (
    InstructionContext,
    InstructionScope,
    UserInstructions,
)


class UserInstructionsStore(Protocol):
    """Store and resolve scoped private user instruction profiles."""

    def get(
        self,
        *,
        scope: InstructionScope = "global",
        scope_key: str | None = None,
    ) -> UserInstructions | None:
        ...

    def set(
        self,
        content: str,
        *,
        scope: InstructionScope = "global",
        scope_key: str | None = None,
        enabled: bool = True,
    ) -> UserInstructions:
        ...

    def set_enabled(
        self,
        enabled: bool,
        *,
        scope: InstructionScope = "global",
        scope_key: str | None = None,
    ) -> UserInstructions:
        ...

    def clear(
        self,
        *,
        scope: InstructionScope = "global",
        scope_key: str | None = None,
    ) -> bool:
        ...

    def list(self, *, include_disabled: bool = True) -> tuple[UserInstructions, ...]:
        ...

    def resolve(self, context: InstructionContext) -> tuple[UserInstructions, ...]:
        ...
