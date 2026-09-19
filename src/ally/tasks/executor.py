"""Deterministic, restart-safe task execution lifecycle."""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

from ally.tasks.models import TaskRecord
from ally.tasks.store import TaskStore
from ally.tasks.verification import ExecutionSucceededVerifier, StepVerifier
from ally.tools.executor import ToolExecutor


class TaskRunner:
    """Advance a persisted task until it finishes or requires human input."""

    def __init__(
        self,
        store: TaskStore,
        tool_executor: ToolExecutor,
        *,
        verifier: StepVerifier | None = None,
    ) -> None:
        self._store = store
        self._tool_executor = tool_executor
        self._verifier = verifier or ExecutionSucceededVerifier()

    def run(
        self,
        task_id: UUID,
        *,
        approved_steps: Collection[UUID] = (),
    ) -> TaskRecord:
        task = self._store.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task: {task_id}")
        if task.status in {"succeeded", "cancelled"}:
            return task

        approvals = set(approved_steps)
        self._store.set_task_status(task_id, "running")

        for step in self._store.list_steps(task_id):
            if step.status == "succeeded":
                continue
            if step.status == "failed":
                return self._store.set_task_status(
                    task_id,
                    "failed",
                    failure=step.last_error or "A task step previously failed.",
                )
            if step.status == "approval_required" and step.id not in approvals:
                return self._store.set_task_status(task_id, "waiting_approval")

            step = self._store.set_step_status(
                step.id,
                "running",
                increment_attempts=True,
            )
            execution = self._tool_executor.invoke(
                step.tool_name,
                step.arguments,
                approved=step.id in approvals,
            )

            if execution.status == "approval_required":
                self._store.set_step_status(
                    step.id,
                    "approval_required",
                    error=execution.error,
                )
                return self._store.set_task_status(task_id, "waiting_approval")

            if execution.status in {"denied", "failed"}:
                error = execution.error or f"Tool execution ended as {execution.status}."
                self._store.set_step_status(step.id, "failed", error=error)
                return self._store.set_task_status(
                    task_id,
                    "failed",
                    failure=error,
                )

            verification = self._verifier.verify(step, execution)
            if not verification.passed:
                self._store.set_step_status(
                    step.id,
                    "failed",
                    output=execution.output,
                    error=verification.detail,
                )
                return self._store.set_task_status(
                    task_id,
                    "failed",
                    failure=verification.detail,
                )

            self._store.set_step_status(
                step.id,
                "succeeded",
                output=execution.output,
            )

        return self._store.set_task_status(task_id, "succeeded")
