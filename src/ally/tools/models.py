"""Typed tool invocation and execution models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

ToolRisk = Literal[
    "read_only",
    "reversible",
    "external_consequence",
    "high_consequence",
]
ToolStatus = Literal[
    "succeeded",
    "approval_required",
    "denied",
    "failed",
]


class ToolSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    description: str = Field(min_length=1)
    risk: ToolRisk


class ToolInvocation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tool_name: str
    arguments: dict[str, JsonValue]
    approved: bool = False


class ToolExecution(BaseModel):
    model_config = ConfigDict(frozen=True)

    invocation_id: UUID
    tool_name: str
    risk: ToolRisk | None
    status: ToolStatus
    started_at: datetime
    finished_at: datetime
    output: JsonValue | None = None
    error: str | None = None
