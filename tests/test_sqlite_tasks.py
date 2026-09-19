from pathlib import Path

import pytest

from ally.storage.sqlite import SQLiteDatabase, SQLiteTaskStore
from ally.tasks import NewTaskStep, TaskPlan


def build_store(path: Path) -> SQLiteTaskStore:
    return SQLiteTaskStore(SQLiteDatabase(path))


def test_task_store_round_trips_plan_and_state(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    store = build_store(path)
    task, steps = store.create(
        TaskPlan(
            goal="Inspect synthetic environment",
            steps=(
                NewTaskStep(
                    tool_name="system.info",
                    arguments={"scope": "synthetic"},
                ),
            ),
        )
    )

    assert task.status == "pending"
    assert len(steps) == 1
    assert steps[0].attempts == 0

    store.set_task_status(task.id, "running")
    updated_step = store.set_step_status(
        steps[0].id,
        "running",
        increment_attempts=True,
    )
    store.set_step_status(
        steps[0].id,
        "succeeded",
        output={"ok": True},
    )
    store.set_task_status(task.id, "succeeded")

    reopened = build_store(path)
    loaded = reopened.get(task.id)
    loaded_steps = reopened.list_steps(task.id)

    assert loaded is not None
    assert loaded.status == "succeeded"
    assert updated_step.attempts == 1
    assert loaded_steps[0].status == "succeeded"
    assert loaded_steps[0].last_output == {"ok": True}


def test_retry_failed_step_resets_task_and_step(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    task, steps = store.create(
        TaskPlan(
            goal="Synthetic retry",
            steps=(NewTaskStep(tool_name="test.tool"),),
        )
    )
    store.set_step_status(steps[0].id, "failed", error="synthetic failure")
    store.set_task_status(task.id, "failed", failure="synthetic failure")

    reset = store.retry_failed_step(task.id, steps[0].id)

    reloaded = store.get(task.id)
    assert reset.status == "pending"
    assert reset.last_error is None
    assert reloaded is not None
    assert reloaded.status == "pending"
    assert reloaded.failure is None


def test_retry_rejects_non_failed_step(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    task, steps = store.create(
        TaskPlan(
            goal="Synthetic",
            steps=(NewTaskStep(tool_name="test.tool"),),
        )
    )

    with pytest.raises(ValueError, match="only failed"):
        store.retry_failed_step(task.id, steps[0].id)


def test_task_list_rejects_non_positive_limit(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")

    with pytest.raises(ValueError, match="positive"):
        store.list(limit=0)
