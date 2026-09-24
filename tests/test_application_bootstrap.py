from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from pydantic import JsonValue

from ally.application import (
    AllyApplication,
    ApplicationOperations,
    BootstrapLimits,
    RunTaskRequest,
)
from ally.conversations import (
    Conversation,
    ConversationMessage,
    ConversationStore,
    NewConversationMessage,
)
from ally.events import NewEvent
from ally.models import ChatRequest, ChatResponse, ModelProvider
from ally.runtime_profiles import InferenceTargetError, ResolvedInferenceTarget
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
        raise AssertionError("bootstrap tests must not invoke inference")

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
            description="Synthetic reversible bootstrap tool.",
            risk="reversible",
        )

    def run(self, arguments: dict[str, JsonValue]) -> JsonValue:
        self.calls += 1
        return {"calls": self.calls}


def _ready_target(
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


def _unavailable_target(
    endpoint: str | None,
    model: str | None,
) -> ResolvedInferenceTarget:
    raise InferenceTargetError("PRIVATE-RUNTIME-DETAIL")


def _provider(
    target: ResolvedInferenceTarget,
) -> AbstractContextManager[ModelProvider]:
    assert target.model == "synthetic"
    return NoopProvider()


def _build_application(
    tmp_path: Path,
    *,
    target_resolver: Callable[
        [str | None, str | None],
        ResolvedInferenceTarget,
    ] = _ready_target,
    conversations: ConversationStore | None = None,
    include_operations: bool = True,
) -> tuple[
    AllyApplication,
    SQLiteEventStore,
    SQLiteAttentionDeliveryStore,
    SQLiteServiceCycleRunStore,
]:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
    event_store = SQLiteEventStore(database)
    delivery_store = SQLiteAttentionDeliveryStore(database)
    service_runs = SQLiteServiceCycleRunStore(database)

    operations = None
    if include_operations:
        tasks = SQLiteTaskStore(database)
        registry = ToolRegistry()
        registry.register(ReversibleTool())
        operations = ApplicationOperations(
            tasks=tasks,
            task_runner=TaskRunner(
                tasks,
                ToolExecutor(
                    registry,
                    DefaultToolPolicy(),
                    SQLiteToolAuditStore(database),
                ),
            ),
            events=event_store,
            attention_deliveries=delivery_store,
            service_runs=service_runs,
            service_health=lambda: ServiceHealthReport(
                status="healthy",
                database_exists=True,
                database_integrity_ok=True,
                schema_current=True,
            ),
        )

    app = AllyApplication(
        conversations=conversations or SQLiteConversationStore(database),
        memories=SQLiteMemoryStore(database),
        knowledge=SQLiteKnowledgeStore(database),
        instructions=SQLiteUserInstructionsStore(database),
        target_resolver=target_resolver,
        provider_factory=_provider,
        operations=operations,
    )
    return app, event_store, delivery_store, service_runs


def test_bootstrap_empty_healthy_state_is_typed_and_serializable(
    tmp_path: Path,
) -> None:
    app, _, _, _ = _build_application(tmp_path)

    snapshot = app.bootstrap()

    assert snapshot.runtime.state == "ready"
    assert snapshot.conversations.state == "available"
    assert snapshot.conversations.items == ()
    assert snapshot.tasks.state == "available"
    assert snapshot.pending_attention.items == ()
    assert snapshot.attention_history.items == ()
    assert snapshot.service_history.items == ()
    assert snapshot.service_health.state == "available"
    assert snapshot.service_health.report is not None
    assert snapshot.service_health.report.status == "healthy"
    assert '"runtime"' in snapshot.model_dump_json()


def test_bootstrap_runtime_unavailable_does_not_block_local_dashboard(
    tmp_path: Path,
) -> None:
    app, _, _, _ = _build_application(
        tmp_path,
        target_resolver=_unavailable_target,
    )
    conversation = app.create_conversation(title="Local history still available")

    snapshot = app.bootstrap()

    assert snapshot.runtime.state == "unavailable"
    assert snapshot.runtime.error_code == "active_profile_unavailable"
    assert snapshot.conversations.state == "available"
    assert snapshot.conversations.items[0].id == conversation.id
    assert snapshot.tasks.state == "available"
    assert snapshot.service_health.state == "available"
    assert "PRIVATE-RUNTIME-DETAIL" not in snapshot.model_dump_json()


def test_bootstrap_operations_unavailable_degrades_explicitly(
    tmp_path: Path,
) -> None:
    app, _, _, _ = _build_application(
        tmp_path,
        include_operations=False,
    )

    snapshot = app.bootstrap()

    assert snapshot.conversations.state == "available"
    for section in (
        snapshot.tasks,
        snapshot.pending_attention,
        snapshot.attention_history,
        snapshot.service_history,
        snapshot.service_health,
    ):
        assert section.state == "unavailable"
        assert section.error_code == "operations_unavailable"


def test_bootstrap_surfaces_pending_approval_attention_and_service_history(
    tmp_path: Path,
) -> None:
    app, events, deliveries, service_runs = _build_application(tmp_path)
    conversation = app.create_conversation(title="Recent conversation")
    task = app.create_task(
        TaskPlan(
            goal="Needs user approval",
            steps=(NewTaskStep(tool_name="test.reversible"),),
        )
    )
    paused = app.run_task(RunTaskRequest(task_id=task.task.id))
    assert paused.task.status == "waiting_approval"

    event = events.create(
        NewEvent(
            type="synthetic.bootstrap",
            source="test",
            importance="urgent",
            payload={"message": "synthetic"},
        ),
        attention="notify",
    )
    delivery = deliveries.record_attempt(
        event_id=event.id,
        sink_id="synthetic",
        succeeded=False,
        error="synthetic",
    )
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = service_runs.start(observed_at=started, started_at=started)
    finished = service_runs.finish(
        run.id,
        status="succeeded",
        finished_at=started + timedelta(seconds=1),
    )

    snapshot = app.bootstrap(
        limits=BootstrapLimits(
            conversations=1,
            tasks=1,
            pending_attention=1,
            attention_history=1,
            service_history=1,
        )
    )

    assert snapshot.conversations.items == (conversation,)
    assert snapshot.tasks.items[0].id == task.task.id
    assert snapshot.tasks.items[0].status == "waiting_approval"
    assert snapshot.pending_attention.items == (event,)
    assert snapshot.attention_history.items == (delivery,)
    assert snapshot.service_history.items == (finished,)


class FailingConversationStore:
    def __init__(self, delegate: ConversationStore) -> None:
        self._delegate = delegate

    def create(self, *, title: str | None = None) -> Conversation:
        return self._delegate.create(title=title)

    def get(self, conversation_id: UUID) -> Conversation | None:
        return self._delegate.get(conversation_id)

    def list(self, *, limit: int = 50) -> tuple[Conversation, ...]:
        raise RuntimeError("PRIVATE-DB-PATH=/secret/location")

    def list_messages(
        self,
        conversation_id: UUID,
    ) -> tuple[ConversationMessage, ...]:
        return self._delegate.list_messages(conversation_id)

    def append_messages(
        self,
        conversation_id: UUID,
        messages: Sequence[NewConversationMessage],
    ) -> tuple[ConversationMessage, ...]:
        return self._delegate.append_messages(conversation_id, messages)


def test_bootstrap_isolates_section_failure_without_leaking_exception(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
    failing = FailingConversationStore(SQLiteConversationStore(database))
    app, _, _, _ = _build_application(
        tmp_path,
        conversations=failing,
    )

    snapshot = app.bootstrap()
    rendered = snapshot.model_dump_json()

    assert snapshot.conversations.state == "error"
    assert snapshot.conversations.error_code == "read_failed"
    assert snapshot.tasks.state == "available"
    assert snapshot.service_health.state == "available"
    assert "PRIVATE-DB-PATH" not in rendered
    assert "/secret/location" not in rendered
