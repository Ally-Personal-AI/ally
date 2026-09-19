"""SQLite persistence for restart-safe tasks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import JsonValue

from ally.storage.sqlite.database import SQLiteDatabase
from ally.tasks import (
    TaskPlan,
    TaskRecord,
    TaskStatus,
    TaskStepRecord,
    TaskStepStatus,
)


class SQLiteTaskStore:
    """Persist task plans and execution state in Ally's local database."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._database.migrate()

    def create(self, plan: TaskPlan) -> tuple[TaskRecord, tuple[TaskStepRecord, ...]]:
        now = datetime.now(UTC)
        task = TaskRecord(
            id=uuid4(),
            goal=plan.goal,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        steps = tuple(
            TaskStepRecord(
                id=uuid4(),
                task_id=task.id,
                position=position,
                tool_name=step.tool_name,
                arguments=step.arguments,
                status="pending",
                attempts=0,
                created_at=now,
                updated_at=now,
            )
            for position, step in enumerate(plan.steps)
        )

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks(id, goal, status, failure, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(task.id),
                    task.goal,
                    task.status,
                    task.failure,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )
            for step in steps:
                connection.execute(
                    """
                    INSERT INTO task_steps(
                        id,
                        task_id,
                        position,
                        tool_name,
                        arguments_json,
                        status,
                        attempts,
                        last_output_json,
                        last_error,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(step.id),
                        str(step.task_id),
                        step.position,
                        step.tool_name,
                        json.dumps(step.arguments, sort_keys=True),
                        step.status,
                        step.attempts,
                        None,
                        None,
                        step.created_at.isoformat(),
                        step.updated_at.isoformat(),
                    ),
                )
        return task, steps

    def get(self, task_id: UUID) -> TaskRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, goal, status, failure, created_at, updated_at
                FROM tasks
                WHERE id = ?
                """,
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        return self._task_from_row(
            cast(tuple[str, str, str, str | None, str, str], row)
        )

    def list(self, *, limit: int = 50) -> tuple[TaskRecord, ...]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._database.connect() as connection:
            rows = cast(
                list[tuple[str, str, str, str | None, str, str]],
                connection.execute(
                    """
                    SELECT id, goal, status, failure, created_at, updated_at
                    FROM tasks
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall(),
            )
        return tuple(self._task_from_row(row) for row in rows)

    def list_steps(self, task_id: UUID) -> tuple[TaskStepRecord, ...]:
        with self._database.connect() as connection:
            rows = cast(
                list[
                    tuple[
                        str,
                        str,
                        int,
                        str,
                        str,
                        str,
                        int,
                        str | None,
                        str | None,
                        str,
                        str,
                    ]
                ],
                connection.execute(
                    """
                    SELECT
                        id,
                        task_id,
                        position,
                        tool_name,
                        arguments_json,
                        status,
                        attempts,
                        last_output_json,
                        last_error,
                        created_at,
                        updated_at
                    FROM task_steps
                    WHERE task_id = ?
                    ORDER BY position ASC
                    """,
                    (str(task_id),),
                ).fetchall(),
            )
        return tuple(self._step_from_row(row) for row in rows)

    def set_task_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        *,
        failure: str | None = None,
    ) -> TaskRecord:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET status = ?, failure = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, failure, now.isoformat(), str(task_id)),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown task: {task_id}")
        loaded = self.get(task_id)
        assert loaded is not None
        return loaded

    def set_step_status(
        self,
        step_id: UUID,
        status: TaskStepStatus,
        *,
        output: JsonValue | None = None,
        error: str | None = None,
        increment_attempts: bool = False,
    ) -> TaskStepRecord:
        now = datetime.now(UTC)
        output_json = None if output is None else json.dumps(output, sort_keys=True)

        with self._database.connect() as connection:
            if increment_attempts:
                cursor = connection.execute(
                    """
                    UPDATE task_steps
                    SET
                        status = ?,
                        attempts = attempts + 1,
                        last_output_json = ?,
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        output_json,
                        error,
                        now.isoformat(),
                        str(step_id),
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE task_steps
                    SET
                        status = ?,
                        last_output_json = ?,
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        output_json,
                        error,
                        now.isoformat(),
                        str(step_id),
                    ),
                )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown task step: {step_id}")

            row = connection.execute(
                """
                SELECT
                    id,
                    task_id,
                    position,
                    tool_name,
                    arguments_json,
                    status,
                    attempts,
                    last_output_json,
                    last_error,
                    created_at,
                    updated_at
                FROM task_steps
                WHERE id = ?
                """,
                (str(step_id),),
            ).fetchone()

        assert row is not None
        return self._step_from_row(
            cast(
                tuple[
                    str,
                    str,
                    int,
                    str,
                    str,
                    str,
                    int,
                    str | None,
                    str | None,
                    str,
                    str,
                ],
                row,
            )
        )

    def retry_failed_step(self, task_id: UUID, step_id: UUID) -> TaskStepRecord:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT status
                FROM task_steps
                WHERE id = ? AND task_id = ?
                """,
                (str(step_id), str(task_id)),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown task step: {step_id}")
            if cast(tuple[str], row)[0] != "failed":
                raise ValueError("only failed task steps can be retried")

            connection.execute(
                """
                UPDATE task_steps
                SET
                    status = 'pending',
                    last_output_json = NULL,
                    last_error = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), str(step_id)),
            )
            connection.execute(
                """
                UPDATE tasks
                SET status = 'pending', failure = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), str(task_id)),
            )

        steps = self.list_steps(task_id)
        return next(step for step in steps if step.id == step_id)

    @staticmethod
    def _task_from_row(
        row: tuple[str, str, str, str | None, str, str],
    ) -> TaskRecord:
        identifier, goal, status, failure, created_at, updated_at = row
        return TaskRecord(
            id=UUID(identifier),
            goal=goal,
            status=cast(TaskStatus, status),
            failure=failure,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )

    @staticmethod
    def _step_from_row(
        row: tuple[
            str,
            str,
            int,
            str,
            str,
            str,
            int,
            str | None,
            str | None,
            str,
            str,
        ],
    ) -> TaskStepRecord:
        (
            identifier,
            task_id,
            position,
            tool_name,
            arguments_json,
            status,
            attempts,
            output_json,
            last_error,
            created_at,
            updated_at,
        ) = row

        arguments = cast(dict[str, JsonValue], json.loads(arguments_json))
        output = (
            None
            if output_json is None
            else cast(JsonValue, json.loads(output_json))
        )

        return TaskStepRecord(
            id=UUID(identifier),
            task_id=UUID(task_id),
            position=position,
            tool_name=tool_name,
            arguments=arguments,
            status=cast(TaskStepStatus, status),
            attempts=attempts,
            last_output=output,
            last_error=last_error,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )
