"""Persistence contract for restart-safe tasks."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import JsonValue

from ally.tasks.models import (
    TaskPlan,
    TaskRecord,
    TaskStatus,
    TaskStepRecord,
    TaskStepStatus,
)


class TaskStore(Protocol):
    def create(self, plan: TaskPlan) -> tuple[TaskRecord, tuple[TaskStepRecord, ...]]:
        ...

    def get(self, task_id: UUID) -> TaskRecord | None:
        ...

    def list(self, *, limit: int = 50) -> tuple[TaskRecord, ...]:
        ...

    def list_steps(self, task_id: UUID) -> tuple[TaskStepRecord, ...]:
        ...

    def set_task_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        *,
        failure: str | None = None,
    ) -> TaskRecord:
        ...

    def set_step_status(
        self,
        step_id: UUID,
        status: TaskStepStatus,
        *,
        output: JsonValue | None = None,
        error: str | None = None,
        increment_attempts: bool = False,
    ) -> TaskStepRecord:
        ...

    def retry_failed_step(self, task_id: UUID, step_id: UUID) -> TaskStepRecord:
        ...
