from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from io import StringIO
from pathlib import Path

from pydantic import JsonValue

from ally.application import AllyApplication, ApplicationOperations
from ally.desktop.bridge import MAX_REQUEST_BYTES, handle_request_json, serve
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


class ReversibleTool:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="test.reversible",
            description="Synthetic reversible desktop bridge tool.",
            risk="reversible",
        )

    def run(self, arguments: dict[str, JsonValue]) -> JsonValue:
        self.calls += 1
        return {"calls": self.calls, "arguments": arguments}


class CapturingProvider:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.requests: list[ChatRequest] = []

    @property
    def name(self) -> str:
        return "synthetic-desktop"

    def __enter__(self) -> CapturingProvider:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            content=self.responses.pop(0),
            model="synthetic-model",
            provider=self.name,
        )


def _target(
    endpoint: str | None,
    model: str | None,
) -> ResolvedInferenceTarget:
    if endpoint is not None or model is not None:
        raise AssertionError("desktop bridge must not request development inference")
    return ResolvedInferenceTarget(
        source="validated_profile",
        endpoint="http://127.0.0.1:8080/v1",
        model="synthetic-model",
        profile_id="a" * 64,
        runtime_name="synthetic-runtime",
        runtime_version="1",
    )


def _application(
    tmp_path: Path,
    *,
    provider: CapturingProvider,
    resolver: Callable[
        [str | None, str | None],
        ResolvedInferenceTarget,
    ] = _target,
) -> AllyApplication:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")

    def provider_factory(
        target: ResolvedInferenceTarget,
    ) -> AbstractContextManager[ModelProvider]:
        assert target.model == "synthetic-model"
        return provider

    return AllyApplication(
        conversations=SQLiteConversationStore(database),
        memories=SQLiteMemoryStore(database),
        knowledge=SQLiteKnowledgeStore(database),
        instructions=SQLiteUserInstructionsStore(database),
        target_resolver=resolver,
        provider_factory=provider_factory,
    )


def _task_application(
    tmp_path: Path,
) -> tuple[AllyApplication, ReversibleTool]:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
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
    app = AllyApplication(
        conversations=SQLiteConversationStore(database),
        memories=SQLiteMemoryStore(database),
        knowledge=SQLiteKnowledgeStore(database),
        instructions=SQLiteUserInstructionsStore(database),
        target_resolver=_target,
        provider_factory=lambda target: CapturingProvider([]),
        operations=ApplicationOperations(
            tasks=tasks,
            task_runner=runner,
            events=SQLiteEventStore(database),
            attention_deliveries=SQLiteAttentionDeliveryStore(database),
            service_runs=SQLiteServiceCycleRunStore(database),
            service_health=lambda: ServiceHealthReport(
                status="healthy",
                database_exists=True,
                database_integrity_ok=True,
                schema_current=True,
            ),
        ),
    )
    return app, tool


def _request(method: str, params: dict[str, object] | None = None) -> str:
    return json.dumps(
        {
            "id": "synthetic-request",
            "method": method,
            "params": params or {},
        }
    )


def test_bridge_bootstrap_is_read_only_and_serializable(tmp_path: Path) -> None:
    provider = CapturingProvider([])
    app = _application(tmp_path, provider=provider)

    response = handle_request_json(app, _request("bootstrap"))

    assert response.ok
    assert response.error is None
    assert isinstance(response.result, dict)
    runtime = response.result["runtime"]
    assert isinstance(runtime, dict)
    assert runtime["state"] == "ready"
    assert provider.requests == []


def test_bridge_conversation_round_trip_uses_application_facade(tmp_path: Path) -> None:
    provider = CapturingProvider(["SYNTHETIC_REPLY"])
    app = _application(tmp_path, provider=provider)

    created = handle_request_json(app, _request("conversation.create"))
    assert created.ok
    assert isinstance(created.result, dict)
    conversation_id = created.result["id"]
    assert isinstance(conversation_id, str)

    sent = handle_request_json(
        app,
        _request(
            "conversation.send",
            {
                "conversation_id": conversation_id,
                "message": "Synthetic local-only message.",
            },
        ),
    )
    assert sent.ok
    assert isinstance(sent.result, dict)
    response = sent.result["response"]
    assert isinstance(response, dict)
    assert response["content"] == "SYNTHETIC_REPLY"
    assert len(provider.requests) == 1

    loaded = handle_request_json(
        app,
        _request("conversation.get", {"conversation_id": conversation_id}),
    )
    assert loaded.ok
    assert isinstance(loaded.result, dict)
    messages = loaded.result["messages"]
    assert isinstance(messages, list)
    assert [message["role"] for message in messages if isinstance(message, dict)] == [
        "user",
        "assistant",
    ]


def test_bridge_rejects_raw_runtime_coordinates(tmp_path: Path) -> None:
    provider = CapturingProvider([])
    app = _application(tmp_path, provider=provider)
    created = app.create_conversation(title="Synthetic")

    response = handle_request_json(
        app,
        _request(
            "conversation.send",
            {
                "conversation_id": str(created.id),
                "message": "Synthetic private message.",
                "development_endpoint": "http://127.0.0.1:9999/v1",
                "development_model": "unvalidated-model",
            },
        ),
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "invalid_request"
    assert provider.requests == []


def test_bridge_sanitizes_inference_selection_failures(tmp_path: Path) -> None:
    provider = CapturingProvider([])

    def unavailable(
        endpoint: str | None,
        model: str | None,
    ) -> ResolvedInferenceTarget:
        raise InferenceTargetError("PRIVATE-PATH-AND-RUNTIME-DETAIL")

    app = _application(tmp_path, provider=provider, resolver=unavailable)
    created = app.create_conversation(title="Synthetic")

    response = handle_request_json(
        app,
        _request(
            "conversation.send",
            {
                "conversation_id": str(created.id),
                "message": "Synthetic private message.",
            },
        ),
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "inference_unavailable"
    rendered = response.model_dump_json()
    assert "PRIVATE-PATH" not in rendered
    assert "Synthetic private message" not in rendered


def test_bridge_task_approval_is_exactly_one_paused_step(
    tmp_path: Path,
) -> None:
    app, tool = _task_application(tmp_path)
    view = app.create_task(
        TaskPlan(
            goal="Two exact desktop approvals",
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

    started = handle_request_json(
        app,
        _request("task.run", {"task_id": str(view.task.id)}),
    )
    assert started.ok
    assert isinstance(started.result, dict)
    steps = started.result["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    second_step = steps[1]
    assert isinstance(first_step, dict)
    assert isinstance(second_step, dict)
    assert first_step["status"] == "approval_required"
    assert second_step["status"] == "pending"

    first = handle_request_json(
        app,
        _request(
            "task.approve_step",
            {
                "task_id": str(view.task.id),
                "step_id": str(view.steps[0].id),
            },
        ),
    )
    assert first.ok
    assert tool.calls == 1
    assert isinstance(first.result, dict)
    first_steps = first.result["steps"]
    assert isinstance(first_steps, list)
    completed_step = first_steps[0]
    next_step = first_steps[1]
    assert isinstance(completed_step, dict)
    assert isinstance(next_step, dict)
    assert completed_step["status"] == "succeeded"
    assert next_step["status"] == "approval_required"

    second = handle_request_json(
        app,
        _request(
            "task.approve_step",
            {
                "task_id": str(view.task.id),
                "step_id": str(view.steps[1].id),
            },
        ),
    )
    assert second.ok
    assert tool.calls == 2
    assert isinstance(second.result, dict)
    task = second.result["task"]
    assert isinstance(task, dict)
    assert task["status"] == "succeeded"


def test_bridge_rejects_bulk_or_stale_task_approval(
    tmp_path: Path,
) -> None:
    app, tool = _task_application(tmp_path)
    view = app.create_task(
        TaskPlan(
            goal="Reject ambiguous desktop approval",
            steps=(NewTaskStep(tool_name="test.reversible"),),
        )
    )

    bulk = handle_request_json(
        app,
        _request(
            "task.run",
            {
                "task_id": str(view.task.id),
                "approved_steps": [str(view.steps[0].id)],
            },
        ),
    )
    assert not bulk.ok
    assert bulk.error is not None
    assert bulk.error.code == "invalid_request"
    assert tool.calls == 0

    stale = handle_request_json(
        app,
        _request(
            "task.approve_step",
            {
                "task_id": str(view.task.id),
                "step_id": str(view.steps[0].id),
            },
        ),
    )
    assert not stale.ok
    assert stale.error is not None
    assert stale.error.code == "invalid_state"
    assert tool.calls == 0


def test_bridge_retry_requires_an_explicit_failed_step(
    tmp_path: Path,
) -> None:
    app, _ = _task_application(tmp_path)
    view = app.create_task(
        TaskPlan(
            goal="Retry one failed desktop step",
            steps=(NewTaskStep(tool_name="test.missing"),),
        )
    )

    failed = handle_request_json(
        app,
        _request("task.run", {"task_id": str(view.task.id)}),
    )
    assert failed.ok
    assert isinstance(failed.result, dict)
    failed_steps = failed.result["steps"]
    assert isinstance(failed_steps, list)
    failed_step = failed_steps[0]
    assert isinstance(failed_step, dict)
    assert failed_step["status"] == "failed"

    retried = handle_request_json(
        app,
        _request(
            "task.retry_step",
            {
                "task_id": str(view.task.id),
                "step_id": str(view.steps[0].id),
            },
        ),
    )
    assert retried.ok
    assert isinstance(retried.result, dict)
    task = retried.result["task"]
    steps = retried.result["steps"]
    assert isinstance(task, dict)
    assert isinstance(steps, list)
    reset_step = steps[0]
    assert isinstance(reset_step, dict)
    assert task["status"] == "pending"
    assert reset_step["status"] == "pending"

    stale = handle_request_json(
        app,
        _request(
            "task.retry_step",
            {
                "task_id": str(view.task.id),
                "step_id": str(view.steps[0].id),
            },
        ),
    )
    assert not stale.ok
    assert stale.error is not None
    assert stale.error.code == "invalid_state"


def test_bridge_bounds_stdio_requests_without_echoing_payload(tmp_path: Path) -> None:
    provider = CapturingProvider([])
    app = _application(tmp_path, provider=provider)
    input_stream = StringIO("X" * (MAX_REQUEST_BYTES + 10) + "\n")
    output_stream = StringIO()

    exit_code = serve(
        app,
        input_stream=input_stream,
        output_stream=output_stream,
        once=True,
    )

    assert exit_code == 2
    response = output_stream.getvalue()
    assert "request_too_large" in response
    assert "XXXXX" not in response
