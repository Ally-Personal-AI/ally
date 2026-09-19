"""Task and step domain models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

TaskStatus = Literal[
    "pending",
    "running",
    "waiting_approval",
    "succeeded",
    "failed",
    "cancelled",
]
TaskStepStatus = Literal[
    "pending",
    "running",
    "approval_required",
    "succeeded",
    "failed",
]


class NewTaskStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class TaskPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    goal: str = Field(min_length=1)
    steps: tuple[NewTaskStep, ...] = Field(min_length=1)


class TaskRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    goal: str
    status: TaskStatus
    failure: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskStepRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    task_id: UUID
    position: int = Field(ge=0)
    tool_name: str
    arguments: dict[str, JsonValue]
    status: TaskStepStatus
    attempts: int = Field(ge=0)
    last_output: JsonValue | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
