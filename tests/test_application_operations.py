from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path

import pytest
from pydantic import JsonValue

from ally.application import (
    AllyApplication,
    ApplicationOperations,
    ApplicationStateError,
    ApplicationUnavailableError,
    ApproveTaskStepRequest,
    RunTaskRequest,
)
from ally.events import NewEvent
from ally.instructions import UserInstructionsStore
from ally.models import ChatRequest, ChatResponse, ModelProvider
from ally.runtime_profiles import ResolvedInferenceTarget
from ally.security.tool_policy import DefaultToolPolicy
from ally.service import ServiceHealthReport
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteEventStore,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
    SQLiteServiceCycleRunStore,
    SQLiteTaskStore,
    SQLiteToolAuditStore,
    SQLiteUserInstructionsStore,
)
from ally.tasks import NewTaskStep, TaskPlan, TaskRunner
from ally.tools import ToolRegistry, ToolSpec
from ally.tools.executor import ToolExecutor


class NoopProvider:
    @property
    def name(self) -> str:
        return "noop"

    def chat(self, request: ChatRequest) -> ChatResponse:
        raise AssertionError("operational application tests must not invoke inference")

    def __enter__(self) -> NoopProvider:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class ReversibleTool:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="test.reversible",
            description="Synthetic reversible application-facade tool.",
            risk="reversible",
        )

    def run(self, arguments: dict[str, JsonValue]) -> JsonValue:
        self.calls += 1
        return {"calls": self.calls, "arguments": arguments}


def _target(
    endpoint: str | None,
    model: str | None,
) -> ResolvedInferenceTarget:
    return ResolvedInferenceTarget(
        source="validated_profile",
        endpoint="http://127.0.0.1:8080/v1",
        model="synthetic",
        profile_id="a" * 64,
        runtime_name="synthetic-runtime",
        runtime_version="1",
    )


def _provider(
    target: ResolvedInferenceTarget,
) -> AbstractContextManager[ModelProvider]:
    assert target.model == "synthetic"
    return NoopProvider()


def _core_stores(
    database: SQLiteDatabase,
) -> tuple[
    SQLiteConversationStore,
    SQLiteMemoryStore,
    SQLiteKnowledgeStore,
    UserInstructionsStore,
]:
    return (
        SQLiteConversationStore(database),
        SQLiteMemoryStore(database),
        SQLiteKnowledgeStore(database),
        SQLiteUserInstructionsStore(database),
    )


def _application(
    tmp_path: Path,
) -> tuple[
    AllyApplication,
    ReversibleTool,
    SQLiteEventStore,
    SQLiteAttentionDeliveryStore,
    SQLiteServiceCycleRunStore,
    ServiceHealthReport,
]:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
    conversations, memories, knowledge, instructions = _core_stores(database)

    tasks = SQLiteTaskStore(database)
    tool = ReversibleTool()
    registry = ToolRegistry()
    registry.register(tool)
    runner = TaskRunner(
        tasks,
        ToolExecutor(
            registry,
            DefaultToolPolicy(),
            SQLiteToolAuditStore(database),
        ),
    )
    events = SQLiteEventStore(database)
    deliveries = SQLiteAttentionDeliveryStore(database)
    service_runs = SQLiteServiceCycleRunStore(database)
    health = ServiceHealthReport(
        status="healthy",
        database_exists=True,
        database_integrity_ok=True,
        schema_current=True,
    )

    app = AllyApplication(
        conversations=conversations,
        memories=memories,
        knowledge=knowledge,
        instructions=instructions,
        target_resolver=_target,
        provider_factory=_provider,
        operations=ApplicationOperations(
            tasks=tasks,
            task_runner=runner,
            events=events,
            attention_deliveries=deliveries,
            service_runs=service_runs,
            service_health=lambda: health,
        ),
    )
    return app, tool, events, deliveries, service_runs, health


def test_task_execution_pauses_and_requires_exact_step_approval(
    tmp_path: Path,
) -> None:
    app, tool, _, _, _, _ = _application(tmp_path)
    view = app.create_task(
        TaskPlan(
            goal="Run a reversible synthetic operation",
            steps=(
                NewTaskStep(
                    tool_name="test.reversible",
                    arguments={"value": "synthetic"},
                ),
            ),
        )
    )

    paused = app.run_task(RunTaskRequest(task_id=view.task.id))

    assert paused.task.status == "waiting_approval"
    assert paused.steps[0].status == "approval_required"
    assert tool.calls == 0

    resumed = app.run_task(
        RunTaskRequest(
            task_id=view.task.id,
            approved_steps=(view.steps[0].id,),
        )
    )

    assert resumed.task.status == "succeeded"
    assert resumed.steps[0].status == "succeeded"
    assert resumed.steps[0].attempts == 2
    assert tool.calls == 1


def test_exact_step_approval_cannot_implicitly_approve_later_steps(
    tmp_path: Path,
) -> None:
    app, tool, _, _, _, _ = _application(tmp_path)
    view = app.create_task(
        TaskPlan(
            goal="Run two reversible synthetic operations",
            steps=(
                NewTaskStep(
                    tool_name="test.reversible",
                    arguments={"value": "first"},
                ),
                NewTaskStep(
                    tool_name="test.reversible",
                    arguments={"value": "second"},
                ),
            ),
        )
    )

    first_pause = app.run_task(RunTaskRequest(task_id=view.task.id))
    assert first_pause.task.status == "waiting_approval"
    assert first_pause.steps[0].status == "approval_required"
    assert first_pause.steps[1].status == "pending"

    second_pause = app.approve_task_step(
        ApproveTaskStepRequest(
            task_id=view.task.id,
            step_id=view.steps[0].id,
        )
    )

    assert tool.calls == 1
    assert second_pause.task.status == "waiting_approval"
    assert second_pause.steps[0].status == "succeeded"
    assert second_pause.steps[1].status == "approval_required"

    finished = app.approve_task_step(
        ApproveTaskStepRequest(
            task_id=view.task.id,
            step_id=view.steps[1].id,
        )
    )
    assert finished.task.status == "succeeded"
    assert tool.calls == 2


def test_exact_step_approval_rejects_stale_or_nonpaused_steps(
    tmp_path: Path,
) -> None:
    app, _, _, _, _, _ = _application(tmp_path)
    view = app.create_task(
        TaskPlan(
            goal="Require exact approval",
            steps=(NewTaskStep(tool_name="test.reversible"),),
        )
    )

    with pytest.raises(ApplicationStateError, match="waiting"):
        app.approve_task_step(
            ApproveTaskStepRequest(
                task_id=view.task.id,
                step_id=view.steps[0].id,
            )
        )

    paused = app.run_task(RunTaskRequest(task_id=view.task.id))
    approved = app.approve_task_step(
        ApproveTaskStepRequest(
            task_id=view.task.id,
            step_id=paused.steps[0].id,
        )
    )
    assert approved.task.status == "succeeded"

    with pytest.raises(ApplicationStateError, match="waiting"):
        app.approve_task_step(
            ApproveTaskStepRequest(
                task_id=view.task.id,
                step_id=paused.steps[0].id,
            )
        )


def test_task_views_and_retry_preserve_existing_state_machine(
    tmp_path: Path,
) -> None:
    app, _, _, _, _, _ = _application(tmp_path)
    view = app.create_task(
        TaskPlan(
            goal="Unknown tool fails deterministically",
            steps=(NewTaskStep(tool_name="test.missing"),),
        )
    )

    failed = app.run_task(RunTaskRequest(task_id=view.task.id))
    assert failed.task.status == "failed"
    assert failed.steps[0].status == "failed"

    reset = app.retry_task_step(
        task_id=view.task.id,
        step_id=view.steps[0].id,
    )
    assert reset.status == "pending"
    assert app.task(view.task.id).task.status == "pending"
    assert app.list_tasks()[0].id == view.task.id


def test_pending_attention_and_history_are_read_only_views(
    tmp_path: Path,
) -> None:
    app, _, events, deliveries, _, _ = _application(tmp_path)
    event = events.create(
        NewEvent(
            type="synthetic.alert",
            source="test",
            importance="urgent",
            payload={"message": "synthetic"},
        ),
        attention="notify",
    )
    ignored = events.create(
        NewEvent(
            type="synthetic.remember",
            source="test",
            importance="routine",
        ),
        attention="remember",
    )

    pending = app.pending_attention()

    assert [item.id for item in pending] == [event.id]
    assert ignored.id not in {item.id for item in pending}
    assert events.get(event.id) is not None
    assert events.get(event.id).handled_at is None  # type: ignore[union-attr]

    delivery = deliveries.record_attempt(
        event_id=event.id,
        sink_id="synthetic",
        succeeded=False,
        error="synthetic",
    )
    assert app.attention_history(status="failed") == (delivery,)
    assert app.pending_attention()[0].id == event.id


def test_service_health_and_history_are_typed_read_only_results(
    tmp_path: Path,
) -> None:
    app, _, _, _, runs, health = _application(tmp_path)
    from datetime import UTC, datetime, timedelta

    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = runs.start(observed_at=started, started_at=started)
    finished = runs.finish(
        run.id,
        status="succeeded",
        finished_at=started + timedelta(seconds=1),
    )

    assert app.service_health() == health
    assert app.service_history() == (finished,)
    assert '"status":"healthy"' in app.service_health().model_dump_json()


def test_operations_fail_explicitly_when_not_composed(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
    conversations, memories, knowledge, instructions = _core_stores(database)
    app = AllyApplication(
        conversations=conversations,
        memories=memories,
        knowledge=knowledge,
        instructions=instructions,
        target_resolver=_target,
        provider_factory=_provider,
    )

    with pytest.raises(ApplicationUnavailableError, match="not composed"):
        app.list_tasks()
    with pytest.raises(ApplicationUnavailableError, match="not composed"):
        app.pending_attention()
    with pytest.raises(ApplicationUnavailableError, match="not composed"):
        app.service_health()
