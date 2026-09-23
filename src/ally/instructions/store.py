"""Persistence contract for user-owned instructions."""

from __future__ import annotations

from typing import Protocol

from ally.instructions.models import UserInstructions


class UserInstructionsStore(Protocol):
    """Store the current global user instruction profile."""

    def get(self) -> UserInstructions | None:
        ...

    def set(self, content: str) -> UserInstructions:
        ...

    def clear(self) -> bool:
        ...
