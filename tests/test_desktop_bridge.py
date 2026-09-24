from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from pydantic import JsonValue

from ally import __version__
from ally.application import (
    AllyApplication,
    ApplicationOperations,
    RememberMemoryRequest,
)
from ally.desktop.bridge import MAX_REQUEST_BYTES, handle_request_json, serve
from ally.diagnostics import (
    EvaluationSuiteProfile,
    HardwareProfile,
    PerformanceObservations,
    RuntimeProfile,
)
from ally.events import NewEvent
from ally.models import ChatRequest, ChatResponse, ModelProvider
from ally.runtime_profiles import (
    EvidenceReference,
    InferenceTargetError,
    ResolvedInferenceTarget,
    RuntimeProfileCatalog,
    ValidatedRuntimeProfile,
    resolve_inference_target,
    runtime_profile_id,
)
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
    runtime_profiles: RuntimeProfileCatalog | None = None,
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
        runtime_profiles=runtime_profiles,
    )


def _installed_runtime_profile(
    tmp_path: Path,
) -> tuple[RuntimeProfileCatalog, ValidatedRuntimeProfile]:
    catalog = RuntimeProfileCatalog(tmp_path / "runtime-profiles")
    runtime = RuntimeProfile(
        name="synthetic-runtime",
        version="1.0",
        context_length=32768,
    )
    hardware = HardwareProfile(
        system="Darwin",
        release="25.0",
        machine="arm64",
        processor="arm",
        python_version="3.12.11",
        logical_cpu_count=16,
        total_memory_bytes=128 * 1024**3,
        apple_model="Mac17,1",
        apple_chip="Apple M5 Max",
    )
    suite = EvaluationSuiteProfile(
        core_sha256="a" * 64,
        provider_sha256="b" * 64,
        behavioral_sha256="c" * 64,
    )
    observations = PerformanceObservations(
        time_to_first_token_ms=120.0,
        generation_tokens_per_second=40.0,
        maximum_tested_context_tokens=16384,
    )
    capability = EvidenceReference(name="capability.json", sha256="d" * 64)
    privacy = EvidenceReference(name="privacy.json", sha256="e" * 64)
    workflows = EvidenceReference(name="workflows.json", sha256="f" * 64)
    profile_id = runtime_profile_id(
        ally_version=__version__,
        endpoint="http://127.0.0.1:8080/v1",
        model="synthetic-model",
        runtime=runtime,
        hardware=hardware,
        evaluation_suite=suite,
        observations=observations,
        capability_evidence=capability,
        privacy_evidence=privacy,
        workflow_evidence=workflows,
    )
    profile = ValidatedRuntimeProfile(
        profile_id=profile_id,
        generated_at=datetime(2026, 9, 24, tzinfo=UTC),
        ally_version=__version__,
        endpoint="http://127.0.0.1:8080/v1",
        model="synthetic-model",
        runtime=runtime,
        hardware=hardware,
        evaluation_suite=suite,
        observations=observations,
        capability_evidence=capability,
        privacy_evidence=privacy,
        workflow_evidence=workflows,
    )
    catalog.root.mkdir(parents=True)
    (catalog.root / f"{profile.profile_id}.json").write_text(
        profile.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return catalog, profile


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


def _attention_application(
    tmp_path: Path,
) -> tuple[
    AllyApplication,
    SQLiteEventStore,
    SQLiteAttentionDeliveryStore,
]:
    database = SQLiteDatabase(tmp_path / "attention.sqlite3")
    events = SQLiteEventStore(database)
    deliveries = SQLiteAttentionDeliveryStore(database)
    tasks = SQLiteTaskStore(database)
    registry = ToolRegistry()
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
            events=events,
            attention_deliveries=deliveries,
            service_runs=SQLiteServiceCycleRunStore(database),
            service_health=lambda: ServiceHealthReport(
                status="healthy",
                database_exists=True,
                database_integrity_ok=True,
                schema_current=True,
            ),
        ),
    )
    return app, events, deliveries


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


def test_bridge_memory_correction_preserves_history_and_retraction(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider([])
    app = _application(tmp_path, provider=provider)
    original = app.remember(
        RememberMemoryRequest(
            content="Synthetic subject prefers green tea.",
            kind="preference",
            importance=0.8,
        )
    )

    loaded = handle_request_json(
        app,
        _request("memory.get", {"memory_id": str(original.id)}),
    )
    assert loaded.ok
    assert isinstance(loaded.result, dict)
    assert loaded.result["content"] == "Synthetic subject prefers green tea."

    corrected = handle_request_json(
        app,
        _request(
            "memory.supersede",
            {
                "memory_id": str(original.id),
                "content": "Synthetic subject prefers jasmine tea.",
            },
        ),
    )
    assert corrected.ok
    assert isinstance(corrected.result, dict)
    replacement_id = corrected.result["id"]
    assert isinstance(replacement_id, str)
    assert corrected.result["supersedes"] == str(original.id)

    historical = handle_request_json(
        app,
        _request("memory.get", {"memory_id": str(original.id)}),
    )
    assert historical.ok
    assert isinstance(historical.result, dict)
    assert historical.result["superseded_by"] == replacement_id

    stale = handle_request_json(
        app,
        _request(
            "memory.supersede",
            {
                "memory_id": str(original.id),
                "content": "This stale correction must not be written.",
            },
        ),
    )
    assert not stale.ok
    assert stale.error is not None
    assert stale.error.code == "invalid_state"

    retracted = handle_request_json(
        app,
        _request("memory.retract", {"memory_id": replacement_id}),
    )
    assert retracted.ok
    assert isinstance(retracted.result, dict)
    assert retracted.result["retracted_at"] is not None

    listed = handle_request_json(app, _request("memory.list"))
    assert listed.ok
    assert listed.result == []


def test_bridge_knowledge_text_ingest_detail_and_search_are_local_contracts(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider([])
    app = _application(tmp_path, provider=provider)

    ingested = handle_request_json(
        app,
        _request(
            "knowledge.ingest_text",
            {
                "uri": "ally-desktop://note/synthetic-001",
                "title": "Synthetic hydroponics note",
                "text": "The hydroponic validation marker is ROOT-519.",
                "media_type": "text/plain",
            },
        ),
    )
    assert ingested.ok
    assert isinstance(ingested.result, dict)
    source = ingested.result["source"]
    assert isinstance(source, dict)
    source_id = source["id"]
    assert isinstance(source_id, str)

    detail = handle_request_json(
        app,
        _request("knowledge.get", {"source_id": source_id}),
    )
    assert detail.ok
    assert isinstance(detail.result, dict)
    revisions = detail.result["revisions"]
    chunks = detail.result["current_chunks"]
    assert isinstance(revisions, list)
    assert isinstance(chunks, list)
    assert len(revisions) == 1
    assert len(chunks) >= 1
    first_chunk = chunks[0]
    assert isinstance(first_chunk, dict)
    chunk_content = first_chunk["content"]
    assert isinstance(chunk_content, str)
    assert "ROOT-519" in chunk_content

    searched = handle_request_json(
        app,
        _request(
            "knowledge.search",
            {"query": "hydroponic marker", "limit": 10},
        ),
    )
    assert searched.ok
    assert isinstance(searched.result, list)
    assert len(searched.result) >= 1
    hit = searched.result[0]
    assert isinstance(hit, dict)
    hit_source = hit["source"]
    assert isinstance(hit_source, dict)
    assert hit_source["id"] == source_id

    path_attempt = handle_request_json(
        app,
        _request(
            "knowledge.ingest_text",
            {
                "uri": "ally-desktop://note/synthetic-002",
                "title": "Synthetic rejected path request",
                "text": "Synthetic content.",
                "path": "/private/synthetic.txt",
            },
        ),
    )
    assert not path_attempt.ok
    assert path_attempt.error is not None
    assert path_attempt.error.code == "invalid_request"


def test_bridge_runtime_profile_selection_accepts_only_installed_ids(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider([])
    catalog, profile = _installed_runtime_profile(tmp_path)

    def resolver(
        endpoint: str | None,
        model: str | None,
    ) -> ResolvedInferenceTarget:
        return resolve_inference_target(
            development_endpoint=endpoint,
            development_model=model,
            active_profile_resolver=catalog.active,
        )

    app = _application(
        tmp_path,
        provider=provider,
        resolver=resolver,
        runtime_profiles=catalog,
    )

    listed = handle_request_json(app, _request("runtime.profiles"))
    assert listed.ok
    assert isinstance(listed.result, dict)
    items = listed.result["items"]
    assert isinstance(items, list)
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, dict)
    assert item["profile_id"] == profile.profile_id
    assert item["active"] is False
    assert "endpoint" not in item

    rejected = handle_request_json(
        app,
        _request(
            "runtime.select_profile",
            {
                "profile_id": "0" * 64,
                "endpoint": "http://127.0.0.1:9999/v1",
            },
        ),
    )
    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.code == "invalid_request"

    selected = handle_request_json(
        app,
        _request(
            "runtime.select_profile",
            {"profile_id": profile.profile_id},
        ),
    )
    assert selected.ok
    assert isinstance(selected.result, dict)
    assert selected.result["active_profile_id"] == profile.profile_id

    bootstrap = handle_request_json(app, _request("bootstrap"))
    assert bootstrap.ok
    assert isinstance(bootstrap.result, dict)
    runtime = bootstrap.result["runtime"]
    assert isinstance(runtime, dict)
    assert runtime["state"] == "ready"
    target = runtime["target"]
    assert isinstance(target, dict)
    assert target["profile_id"] == profile.profile_id

    deselected = handle_request_json(app, _request("runtime.deselect_profile"))
    assert deselected.ok
    assert isinstance(deselected.result, dict)
    assert deselected.result["active_profile_id"] is None


def test_bridge_attention_center_detail_history_and_handled_state(
    tmp_path: Path,
) -> None:
    app, events, deliveries = _attention_application(tmp_path)
    event = events.create(
        NewEvent(
            type="synthetic.desktop-attention",
            source="bridge-test",
            importance="urgent",
            payload={
                "summary": "Synthetic attention summary.",
                "private_detail": "kept local in detail only",
            },
        ),
        attention="notify",
    )
    delivery = deliveries.record_attempt(
        event_id=event.id,
        sink_id="macos.notification",
        succeeded=True,
    )

    listed = handle_request_json(
        app,
        _request("attention.events", {"limit": 100, "handled": False}),
    )
    assert listed.ok
    assert isinstance(listed.result, list)
    listed_ids: list[str] = []
    for item in listed.result:
        assert isinstance(item, dict)
        item_id = item["id"]
        assert isinstance(item_id, str)
        listed_ids.append(item_id)
    assert listed_ids == [str(event.id)]

    detail = handle_request_json(
        app,
        _request("attention.get", {"event_id": str(event.id)}),
    )
    assert detail.ok
    assert isinstance(detail.result, dict)
    detail_event = detail.result["event"]
    detail_deliveries = detail.result["deliveries"]
    assert isinstance(detail_event, dict)
    assert isinstance(detail_deliveries, list)
    payload = detail_event["payload"]
    assert isinstance(payload, dict)
    summary = payload["summary"]
    assert isinstance(summary, str)
    assert summary == "Synthetic attention summary."
    first_delivery = detail_deliveries[0]
    assert isinstance(first_delivery, dict)
    first_delivery_id = first_delivery["id"]
    assert isinstance(first_delivery_id, str)
    assert first_delivery_id == str(delivery.id)

    history = handle_request_json(
        app,
        _request(
            "attention.delivery_history",
            {"limit": 100, "status": "succeeded"},
        ),
    )
    assert history.ok
    assert isinstance(history.result, list)
    first_history = history.result[0]
    assert isinstance(first_history, dict)
    history_event_id = first_history["event_id"]
    assert isinstance(history_event_id, str)
    assert history_event_id == str(event.id)

    rejected = handle_request_json(
        app,
        _request(
            "attention.mark_handled",
            {
                "event_id": str(event.id),
                "deliver": True,
            },
        ),
    )
    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.code == "invalid_request"
    assert events.get(event.id) is not None
    assert events.get(event.id).handled_at is None  # type: ignore[union-attr]

    handled = handle_request_json(
        app,
        _request("attention.mark_handled", {"event_id": str(event.id)}),
    )
    assert handled.ok
    assert isinstance(handled.result, dict)
    handled_event = handled.result["event"]
    assert isinstance(handled_event, dict)
    assert handled_event["handled_at"] is not None

    pending = handle_request_json(
        app,
        _request("attention.events", {"limit": 100, "handled": False}),
    )
    assert pending.ok
    assert pending.result == []


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
