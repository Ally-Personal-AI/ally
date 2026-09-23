"""User-owned instruction profile models and scope semantics."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

InstructionScope = Literal["global", "project", "conversation", "task"]
INSTRUCTION_SCOPES: tuple[InstructionScope, ...] = (
    "global",
    "project",
    "conversation",
    "task",
)
INSTRUCTION_SCOPE_ORDER: dict[InstructionScope, int] = {
    scope: index for index, scope in enumerate(INSTRUCTION_SCOPES)
}


class UserInstructions(BaseModel):
    """One durable user-owned instruction profile."""

    model_config = ConfigDict(frozen=True)

    scope: InstructionScope = "global"
    scope_key: str = ""
    content: str = Field(min_length=1, max_length=100_000)
    enabled: bool = True
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_scope_key(self) -> UserInstructions:
        if self.scope == "global" and self.scope_key:
            raise ValueError("global instructions cannot have a scope key")
        if self.scope != "global" and not self.scope_key:
            raise ValueError(f"{self.scope} instructions require a scope key")
        return self


class InstructionContext(BaseModel):
    """Selectors used to resolve durable instruction scopes for one request."""

    model_config = ConfigDict(frozen=True)

    project_key: str | None = None
    conversation_key: str | None = None
    task_key: str | None = None
    session_instructions: str | None = Field(default=None, max_length=100_000)


class InstructionContribution(BaseModel):
    """One inspectable contribution to a composed instruction prompt."""

    model_config = ConfigDict(frozen=True)

    scope: str
    scope_key: str = ""
    content: str
