"""Human-facing persistent task presentation adapter."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from ally.application import ApplicationNotFoundError, RunTaskRequest
from ally.composition import build_default_application
from ally.tasks import TaskPlan


def _parse_uuid(value: str, *, label: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {label}: {value}") from exc


def run_create_task(*, plan_path: str) -> int:
    path = Path(plan_path).expanduser().resolve()
    try:
        raw = path.read_text(encoding="utf-8")
        plan = TaskPlan.model_validate_json(raw)
    except OSError as exc:
        print(f"Task plan error: {exc}")
        return 2
    except ValidationError as exc:
        print(f"Task plan error: {exc}")
        return 2

    view = build_default_application().create_task(plan)
    print(f"Task: {view.task.id}")
    for step in view.steps:
        print(f"  {step.id}  {step.position}  {step.tool_name}")
    return 0


def run_list_tasks(*, limit: int) -> int:
    try:
        tasks = build_default_application().list_tasks(limit=limit)
    except ValueError as exc:
        print(f"Task error: {exc}")
        return 2

    if not tasks:
        print("No tasks.")
        return 0

    for task in tasks:
        print(f"{task.id}  {task.status}  {task.goal}")
    return 0


def run_show_task(*, task_id: str) -> int:
    try:
        view = build_default_application().task(
            _parse_uuid(task_id, label="task ID")
        )
    except (ApplicationNotFoundError, ValueError) as exc:
        print(exc)
        return 2

    task = view.task
    print(f"Task: {task.id}")
    print(f"Goal: {task.goal}")
    print(f"Status: {task.status}")
    if task.failure is not None:
        print(f"Failure: {task.failure}")
    print("Steps:")
    for step in view.steps:
        line = (
            f"  {step.position}  {step.id}  {step.status}  "
            f"attempts={step.attempts}  {step.tool_name}"
        )
        print(line)
        if step.last_error is not None:
            print(f"    error: {step.last_error}")
    return 0


def run_task(*, task_id: str, approved_steps: tuple[str, ...]) -> int:
    try:
        identifier = _parse_uuid(task_id, label="task ID")
        approvals = tuple(
            _parse_uuid(value, label="step ID") for value in approved_steps
        )
        view = build_default_application().run_task(
            RunTaskRequest(
                task_id=identifier,
                approved_steps=approvals,
            )
        )
    except (ApplicationNotFoundError, ValueError) as exc:
        print(f"Task error: {exc}")
        return 2

    task = view.task
    print(f"Task: {task.id}")
    print(f"Status: {task.status}")
    if task.failure is not None:
        print(f"Failure: {task.failure}")

    return 0 if task.status == "succeeded" else 2


def run_retry_task_step(*, task_id: str, step_id: str) -> int:
    try:
        step = build_default_application().retry_task_step(
            task_id=_parse_uuid(task_id, label="task ID"),
            step_id=_parse_uuid(step_id, label="step ID"),
        )
    except (ApplicationNotFoundError, ValueError) as exc:
        print(f"Task retry error: {exc}")
        return 2

    print(f"Step reset: {step.id}")
    print(f"Status: {step.status}")
    return 0
