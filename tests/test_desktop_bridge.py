from __future__ import annotations

import json
import plistlib
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import cast

import pytest
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
from ally.egress import (
    DefaultEgressPolicy,
    EgressAuditRecord,
    EgressExecutor,
    EgressFieldSpec,
    EgressOperationSpec,
)
from ally.events import EventRuntime, NewEvent
from ally.models import ChatRequest, ChatResponse, ModelProvider
from ally.research import WEB_SEARCH_OPERATION, ResearchService
from ally.runtime_profiles import (
    EvidenceReference,
    InferenceTargetError,
    ResolvedInferenceTarget,
    RuntimeProfileCatalog,
    ValidatedRuntimeProfile,
    resolve_inference_target,
    runtime_profile_id,
)
from ally.scheduler import SchedulerRuntime
from ally.security.tool_policy import DefaultToolPolicy
from ally.service import (
    DesktopProactiveCoordinator,
    ServiceHealthReport,
    SQLiteServiceLeaseStore,
)
from ally.service.macos_launchd import (
    LaunchctlResult,
    MacOSLaunchdService,
    ManagedServicePaths,
)
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteEventStore,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
    SQLiteScheduleStore,
    SQLiteServiceCycleRunStore,
    SQLiteTaskStore,
    SQLiteToolAuditStore,
    SQLiteUserInstructionsStore,
)
from ally.tasks import NewTaskStep, TaskPlan, TaskRunner
from ally.tools import ToolRegistry, ToolSpec
from ally.tools.executor import ToolExecutor


class InMemoryEgressAuditStore:
    def __init__(self) -> None:
        self.records: list[EgressAuditRecord] = []

    def append(self, record: EgressAuditRecord) -> None:
        self.records.append(record)

    def list(self, *, limit: int = 100) -> tuple[EgressAuditRecord, ...]:
        return tuple(reversed(self.records[-limit:]))


class RecordingResearchAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []

    @property
    def service(self) -> str:
        return "synthetic.search"

    @property
    def operations(self) -> tuple[EgressOperationSpec, ...]:
        return (
            EgressOperationSpec(
                operation=WEB_SEARCH_OPERATION,
                fields=(
                    EgressFieldSpec(
                        name="query",
                        classification="explicit_outbound",
                    ),
                    EgressFieldSpec(
                        name="count",
                        classification="public",
                    ),
                ),
            ),
        )

    def send(
        self,
        operation: str,
        payload: dict[str, JsonValue],
    ) -> JsonValue:
        self.calls.append((operation, payload))
        return {
            "results": [
                {
                    "title": "Synthetic public result",
                    "url": "https://example.test/research",
                    "description": "Synthetic public snippet.",
                }
            ],
            "more_results_available": False,
        }


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


class BridgeLaunchctl:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.loaded = False

    def run(self, arguments: Sequence[str]) -> LaunchctlResult:
        call = tuple(arguments)
        self.calls.append(call)
        if call[0] == "print":
            return LaunchctlResult(0, "state = waiting\n") if self.loaded else LaunchctlResult(113)
        if call[0] == "bootout":
            self.loaded = False
            return LaunchctlResult(0)
        raise AssertionError(f"unexpected launchctl call: {call}")


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
    *,
    provider: CapturingProvider | None = None,
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
    planning_provider = provider or CapturingProvider([])
    app = AllyApplication(
        conversations=SQLiteConversationStore(database),
        memories=SQLiteMemoryStore(database),
        knowledge=SQLiteKnowledgeStore(database),
        instructions=SQLiteUserInstructionsStore(database),
        target_resolver=_target,
        provider_factory=lambda target: planning_provider,
        operations=ApplicationOperations(
            tasks=tasks,
            task_runner=runner,
            planning_tools=tuple(item.spec for item in registry.list()),
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


def _research_application(
    tmp_path: Path,
    *,
    provider: CapturingProvider | None = None,
    resolver: Callable[
        [str | None, str | None],
        ResolvedInferenceTarget,
    ] = _target,
) -> tuple[
    AllyApplication,
    RecordingResearchAdapter,
    InMemoryEgressAuditStore,
    CapturingProvider,
]:
    database = SQLiteDatabase(tmp_path / "research.sqlite3")
    tasks = SQLiteTaskStore(database)
    registry = ToolRegistry()
    adapter = RecordingResearchAdapter()
    audit = InMemoryEgressAuditStore()
    synthesis_provider = provider or CapturingProvider([])
    app = AllyApplication(
        conversations=SQLiteConversationStore(database),
        memories=SQLiteMemoryStore(database),
        knowledge=SQLiteKnowledgeStore(database),
        instructions=SQLiteUserInstructionsStore(database),
        target_resolver=resolver,
        provider_factory=lambda target: synthesis_provider,
        operations=ApplicationOperations(
            tasks=tasks,
            task_runner=TaskRunner(
                tasks,
                ToolExecutor(
                    registry,
                    DefaultToolPolicy(),
                    SQLiteToolAuditStore(database),
                ),
            ),
            events=SQLiteEventStore(database),
            attention_deliveries=SQLiteAttentionDeliveryStore(database),
            service_runs=SQLiteServiceCycleRunStore(database),
            service_health=lambda: ServiceHealthReport(
                status="healthy",
                database_exists=True,
                database_integrity_ok=True,
                schema_current=True,
            ),
            research=ResearchService(
                executor=EgressExecutor(DefaultEgressPolicy(), audit),
                adapter=adapter,
            ),
        ),
    )
    return app, adapter, audit, synthesis_provider


def _attention_application(
    tmp_path: Path,
    *,
    legacy_managed_service: MacOSLaunchdService | None = None,
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
    runs = SQLiteServiceCycleRunStore(database)
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
            service_runs=runs,
            service_health=lambda: ServiceHealthReport(
                status="healthy",
                database_exists=True,
                database_integrity_ok=True,
                schema_current=True,
            ),
            legacy_managed_service=legacy_managed_service,
            desktop_proactive=DesktopProactiveCoordinator(
                scheduler=SchedulerRuntime(
                    SQLiteScheduleStore(database),
                    EventRuntime(events),
                ),
                events=events,
                deliveries=deliveries,
                runs=runs,
                leases=SQLiteServiceLeaseStore(
                    tmp_path / "attention-runtime.sqlite3"
                ),
            ),
        ),
    )
    return app, events, deliveries


def _legacy_service(tmp_path: Path) -> tuple[MacOSLaunchdService, BridgeLaunchctl]:
    runner = BridgeLaunchctl()
    paths = ManagedServicePaths(
        plist=tmp_path / "Library" / "LaunchAgents" / "ai.ally.proactive-service.plist",
        stdout_log=tmp_path / "data" / "service" / "logs" / "stdout.log",
        stderr_log=tmp_path / "data" / "service" / "logs" / "stderr.log",
    )
    service = MacOSLaunchdService(
        paths=paths,
        runner=runner,
        executable=Path(sys.executable),
        uid=501,
        supported=True,
    )
    definition = service.definition()
    arguments_value = definition["ProgramArguments"]
    assert isinstance(arguments_value, list)
    arguments = cast(list[str], arguments_value.copy())
    arguments[0] = "/Applications/SyntheticOldAlly/bin/python"
    definition["ProgramArguments"] = arguments
    paths.plist.parent.mkdir(parents=True)
    paths.plist.write_bytes(
        plistlib.dumps(definition, fmt=plistlib.FMT_XML, sort_keys=True)
    )
    return service, runner


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


def test_bridge_direct_memory_capture_persists_exact_user_fields(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider([])
    app = _application(tmp_path, provider=provider)

    response = handle_request_json(
        app,
        _request(
            "memory.remember",
            {
                "content": "Synthetic subject prefers oolong tea.",
                "kind": "preference",
                "confidence": 0.95,
                "importance": 0.8,
                "privacy": "private",
            },
        ),
    )

    assert response.ok
    assert isinstance(response.result, dict)
    assert response.result["content"] == "Synthetic subject prefers oolong tea."
    assert response.result["kind"] == "preference"
    assert response.result["confidence"] == 0.95
    assert response.result["importance"] == 0.8
    source = response.result["source"]
    assert isinstance(source, dict)
    assert source["type"] == "user"
    assert provider.requests == []

    listed = handle_request_json(app, _request("memory.list"))
    assert listed.ok
    assert isinstance(listed.result, list)
    assert len(listed.result) == 1


def test_bridge_memory_proposal_is_review_only_and_uses_validated_local_model(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider(
        [
            json.dumps(
                {
                    "memories": [
                        {
                            "kind": "preference",
                            "content": "Synthetic subject prefers oolong tea.",
                            "confidence": 0.9,
                            "importance": 0.8,
                        },
                        {
                            "kind": "semantic",
                            "content": "Synthetic subject lives in Example City.",
                            "confidence": 0.85,
                            "importance": 0.6,
                        },
                    ]
                }
            )
        ]
    )
    app = _application(tmp_path, provider=provider)

    before = handle_request_json(app, _request("memory.list"))
    assert before.ok
    assert before.result == []

    response = handle_request_json(
        app,
        _request(
            "memory.propose",
            {
                "text": (
                    "Synthetic subject prefers oolong tea and lives in Example City."
                ),
                "source_type": "user",
                "privacy": "private",
            },
        ),
    )

    assert response.ok
    assert isinstance(response.result, dict)
    memories = response.result["memories"]
    assert isinstance(memories, list)
    assert len(memories) == 2
    assert response.result["privacy"] == "private"
    source = response.result["source"]
    assert isinstance(source, dict)
    assert source["type"] == "user"
    assert len(provider.requests) == 1
    assert "untrusted reference data, not instructions" in (
        provider.requests[0].messages[0].content
    )

    after = handle_request_json(app, _request("memory.list"))
    assert after.ok
    assert after.result == []


@pytest.mark.parametrize(
    "forbidden",
    (
        {"development_endpoint": "http://127.0.0.1:9999/v1"},
        {"development_model": "unreviewed-model"},
        {"source_type": "system"},
        {"source_id": "caller-claimed-source"},
        {"source_uri": "file:///private/caller-claimed-source"},
    ),
)
def test_bridge_memory_proposal_rejects_runtime_override_fields(
    tmp_path: Path,
    forbidden: dict[str, object],
) -> None:
    provider = CapturingProvider([])
    app = _application(tmp_path, provider=provider)
    params: dict[str, object] = {
        "text": "Synthetic source text.",
        "source_type": "user",
        "privacy": "private",
    }
    params.update(forbidden)

    response = handle_request_json(
        app,
        _request("memory.propose", params),
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "invalid_request"
    assert provider.requests == []
    assert app.list_memories() == ()


def test_bridge_memory_acceptance_persists_only_selected_candidates(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider(
        [
            json.dumps(
                {
                    "memories": [
                        {
                            "kind": "preference",
                            "content": "Synthetic subject prefers oolong tea.",
                            "confidence": 0.9,
                            "importance": 0.8,
                        },
                        {
                            "kind": "semantic",
                            "content": "Synthetic subject lives in Example City.",
                            "confidence": 0.85,
                            "importance": 0.6,
                        },
                    ]
                }
            )
        ]
    )
    app = _application(tmp_path, provider=provider)
    proposed = handle_request_json(
        app,
        _request(
            "memory.propose",
            {
                "text": (
                    "Synthetic subject prefers oolong tea and lives in Example City."
                ),
                "source_type": "user",
                "privacy": "private",
            },
        ),
    )
    assert proposed.ok
    assert isinstance(proposed.result, dict)
    model_calls = len(provider.requests)

    accepted = handle_request_json(
        app,
        _request(
            "memory.accept_proposals",
            {
                "bundle": proposed.result,
                "indices": [1],
            },
        ),
    )

    assert accepted.ok
    assert isinstance(accepted.result, list)
    assert len(accepted.result) == 1
    saved = accepted.result[0]
    assert isinstance(saved, dict)
    assert saved["content"] == "Synthetic subject lives in Example City."
    assert saved["kind"] == "semantic"
    source = saved["source"]
    assert isinstance(source, dict)
    assert source["type"] == "user"
    assert saved["privacy"] == "private"
    assert len(provider.requests) == model_calls

    records = app.list_memories()
    assert len(records) == 1
    assert records[0].content == "Synthetic subject lives in Example City."


@pytest.mark.parametrize("indices", ([0, 0], [99], [-1]))
def test_bridge_memory_acceptance_rejects_invalid_indices(
    tmp_path: Path,
    indices: list[int],
) -> None:
    provider = CapturingProvider(
        [
            json.dumps(
                {
                    "memories": [
                        {
                            "kind": "semantic",
                            "content": "Synthetic durable fact.",
                            "confidence": 0.9,
                            "importance": 0.7,
                        }
                    ]
                }
            )
        ]
    )
    app = _application(tmp_path, provider=provider)
    proposed = handle_request_json(
        app,
        _request(
            "memory.propose",
            {
                "text": "Synthetic durable fact.",
                "source_type": "user",
                "privacy": "private",
            },
        ),
    )
    assert proposed.ok
    assert isinstance(proposed.result, dict)

    rejected = handle_request_json(
        app,
        _request(
            "memory.accept_proposals",
            {
                "bundle": proposed.result,
                "indices": indices,
            },
        ),
    )

    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.code == "invalid_request"
    assert app.list_memories() == ()


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


def test_bridge_manages_scoped_instructions_without_authority_fields(
    tmp_path: Path,
) -> None:
    app = _application(tmp_path, provider=CapturingProvider([]))

    created = handle_request_json(
        app,
        _request(
            "instructions.set",
            {
                "scope": "global",
                "content": "Be concise.",
                "enabled": True,
            },
        ),
    )
    assert created.ok
    assert isinstance(created.result, dict)
    assert created.result["scope"] == "global"
    assert created.result["enabled"] is True

    project = handle_request_json(
        app,
        _request(
            "instructions.set",
            {
                "scope": "project",
                "scope_key": "synthetic-project",
                "content": "Prefer metric units.",
                "enabled": False,
            },
        ),
    )
    assert project.ok

    listed = handle_request_json(
        app,
        _request("instructions.list", {"include_disabled": True}),
    )
    assert listed.ok
    assert isinstance(listed.result, list)
    assert [item["scope"] for item in listed.result if isinstance(item, dict)] == [
        "global",
        "project",
    ]

    toggled = handle_request_json(
        app,
        _request(
            "instructions.set_enabled",
            {
                "scope": "project",
                "scope_key": "synthetic-project",
                "enabled": True,
            },
        ),
    )
    assert toggled.ok

    resolved = handle_request_json(
        app,
        _request(
            "instructions.resolve",
            {
                "project_key": "synthetic-project",
                "session_instructions": "Answer briefly.",
            },
        ),
    )
    assert resolved.ok
    assert isinstance(resolved.result, dict)
    contributions = resolved.result["contributions"]
    assert isinstance(contributions, list)
    assert [item["scope"] for item in contributions if isinstance(item, dict)] == [
        "global",
        "project",
        "session",
    ]

    rejected = handle_request_json(
        app,
        _request(
            "instructions.set",
            {
                "scope": "global",
                "content": "Synthetic instructions.",
                "tool_permission": "allow_all",
            },
        ),
    )
    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.code == "invalid_request"

    invalid_scope = handle_request_json(
        app,
        _request(
            "instructions.set",
            {
                "scope": "global",
                "scope_key": "must-not-exist",
                "content": "Synthetic instructions.",
            },
        ),
    )
    assert not invalid_scope.ok
    assert invalid_scope.error is not None
    assert invalid_scope.error.code == "invalid_request"

    cleared = handle_request_json(
        app,
        _request(
            "instructions.clear",
            {
                "scope": "project",
                "scope_key": "synthetic-project",
            },
        ),
    )
    assert cleared.ok
    assert cleared.result is True


def test_bridge_research_answer_stops_before_search_and_model_without_approval(
    tmp_path: Path,
) -> None:
    app, adapter, audit, provider = _research_application(tmp_path)

    response = handle_request_json(
        app,
        _request(
            "research.answer",
            {
                "query": "synthetic public research query",
                "count": 3,
                "approved": False,
            },
        ),
    )

    assert response.ok
    assert isinstance(response.result, dict)
    search = response.result["search"]
    assert isinstance(search, dict)
    assert search["status"] == "approval_required"
    assert response.result["synthesis_status"] == "not_run"
    assert response.result["synthesis"] is None
    assert adapter.calls == []
    assert provider.requests == []
    assert len(audit.records) == 1
    assert "synthetic public research query" not in audit.records[0].model_dump_json()


def test_bridge_research_answer_uses_local_model_after_approved_search(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider(
        [
            json.dumps(
                {
                    "answer": "The synthetic public result is supported. [1]",
                    "cited_result_indices": [1],
                    "insufficient_evidence": False,
                }
            )
        ]
    )
    app, adapter, audit, provider = _research_application(
        tmp_path,
        provider=provider,
    )
    query = "synthetic public research query"

    response = handle_request_json(
        app,
        _request(
            "research.answer",
            {
                "query": query,
                "count": 3,
                "approved": True,
            },
        ),
    )

    assert response.ok
    assert isinstance(response.result, dict)
    search = response.result["search"]
    synthesis = response.result["synthesis"]
    assert isinstance(search, dict)
    assert isinstance(synthesis, dict)
    assert search["status"] == "succeeded"
    assert response.result["synthesis_status"] == "succeeded"
    answer = synthesis["answer"]
    assert isinstance(answer, str)
    assert answer.endswith("[1]")
    assert synthesis["cited_result_indices"] == [1]
    assert adapter.calls == [
        (
            WEB_SEARCH_OPERATION,
            {"query": query, "count": 3},
        )
    ]
    assert len(provider.requests) == 1
    assert provider.requests[0].messages[0].role == "system"
    assert "untrusted evidence" in provider.requests[0].messages[0].content
    assert len(audit.records) == 1
    assert query not in audit.records[0].model_dump_json()


def test_bridge_research_answer_preserves_results_when_local_model_is_unavailable(
    tmp_path: Path,
) -> None:
    def unavailable(
        endpoint: str | None,
        model: str | None,
    ) -> ResolvedInferenceTarget:
        del endpoint, model
        raise InferenceTargetError("no active validated profile")

    app, adapter, audit, provider = _research_application(
        tmp_path,
        resolver=unavailable,
    )
    query = "synthetic public research query"

    response = handle_request_json(
        app,
        _request(
            "research.answer",
            {
                "query": query,
                "count": 3,
                "approved": True,
            },
        ),
    )

    assert response.ok
    assert isinstance(response.result, dict)
    search = response.result["search"]
    assert isinstance(search, dict)
    assert search["status"] == "succeeded"
    results = search["results"]
    assert isinstance(results, list)
    assert len(results) == 1
    assert response.result["synthesis_status"] == "unavailable"
    assert response.result["synthesis"] is None
    assert adapter.calls == [
        (
            WEB_SEARCH_OPERATION,
            {"query": query, "count": 3},
        )
    ]
    assert provider.requests == []
    assert len(audit.records) == 1


def test_bridge_research_answer_preserves_results_when_synthesis_fails(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider(
        [
            json.dumps(
                {
                    "answer": "Unsupported source. [2]",
                    "cited_result_indices": [2],
                    "insufficient_evidence": False,
                }
            )
        ]
    )
    app, adapter, _, provider = _research_application(
        tmp_path,
        provider=provider,
    )

    response = handle_request_json(
        app,
        _request(
            "research.answer",
            {
                "query": "synthetic public research query",
                "count": 3,
                "approved": True,
            },
        ),
    )

    assert response.ok
    assert isinstance(response.result, dict)
    search = response.result["search"]
    assert isinstance(search, dict)
    assert search["status"] == "succeeded"
    results = search["results"]
    assert isinstance(results, list)
    assert len(results) == 1
    assert response.result["synthesis_status"] == "failed"
    assert response.result["synthesis"] is None
    assert response.result["synthesis_error_class"] == "ResearchSynthesisError"
    assert len(adapter.calls) == 1
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "forbidden",
    (
        {"development_endpoint": "http://127.0.0.1:9999/v1"},
        {"development_model": "remote-model"},
        {"conversation_history": "private history"},
        {"memory": "private memory"},
        {"instructions": "private instructions"},
    ),
)
def test_bridge_research_answer_rejects_hidden_context_fields(
    tmp_path: Path,
    forbidden: dict[str, object],
) -> None:
    app, adapter, _, provider = _research_application(tmp_path)
    params: dict[str, object] = {
        "query": "synthetic public research query",
        "count": 3,
        "approved": True,
    }
    params.update(forbidden)

    response = handle_request_json(
        app,
        _request("research.answer", params),
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "invalid_request"
    assert adapter.calls == []
    assert provider.requests == []


def test_bridge_research_requires_exact_query_approval(
    tmp_path: Path,
) -> None:
    app, adapter, audit, _ = _research_application(tmp_path)
    query = "synthetic public research query"

    inspection = handle_request_json(
        app,
        _request(
            "research.inspect",
            {"query": query, "count": 3},
        ),
    )

    assert inspection.ok
    assert isinstance(inspection.result, dict)
    assert inspection.result["decision"] == "require_approval"
    assert query not in json.dumps(inspection.result)
    assert adapter.calls == []
    assert audit.records == []

    blocked = handle_request_json(
        app,
        _request(
            "research.search",
            {"query": query, "count": 3},
        ),
    )

    assert blocked.ok
    assert isinstance(blocked.result, dict)
    assert blocked.result["status"] == "approval_required"
    assert adapter.calls == []
    assert len(audit.records) == 1
    assert query not in audit.records[0].model_dump_json()

    approved = handle_request_json(
        app,
        _request(
            "research.search",
            {"query": query, "count": 3, "approved": True},
        ),
    )

    assert approved.ok
    assert isinstance(approved.result, dict)
    assert approved.result["status"] == "succeeded"
    results = approved.result["results"]
    assert isinstance(results, list)
    assert len(results) == 1
    first = results[0]
    assert isinstance(first, dict)
    assert first["title"] == "Synthetic public result"
    assert adapter.calls == [
        (
            WEB_SEARCH_OPERATION,
            {"query": query, "count": 3},
        )
    ]
    assert len(audit.records) == 2
    assert query not in audit.records[-1].model_dump_json()


def test_bridge_research_rejects_hidden_context_fields(
    tmp_path: Path,
) -> None:
    app, adapter, _, _ = _research_application(tmp_path)

    response = handle_request_json(
        app,
        _request(
            "research.search",
            {
                "query": "synthetic public research query",
                "count": 3,
                "approved": True,
                "conversation_history": "must never cross",
            },
        ),
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "invalid_request"
    assert adapter.calls == []


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


def test_bridge_prepares_minimized_notification_and_requires_exact_result(
    tmp_path: Path,
) -> None:
    app, events, deliveries = _attention_application(tmp_path)
    event = events.create(
        NewEvent(
            type="synthetic.app-owned-notification",
            source="bridge-test",
            importance="urgent",
            payload={
                "summary": "Synthetic visible reminder.",
                "private_detail": "must stay out of notification candidate",
            },
        ),
        attention="notify",
    )

    prepared = handle_request_json(
        app,
        _request("service.prepare_proactive"),
    )
    assert prepared.ok
    assert isinstance(prepared.result, dict)
    run = prepared.result["run"]
    assert isinstance(run, dict)
    run_id = run["id"]
    assert isinstance(run_id, str)
    assert run["status"] == "running"

    candidates = prepared.result["candidates"]
    assert isinstance(candidates, list)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, dict)
    assert candidate["event_id"] == str(event.id)
    assert candidate["title"] == "Ally"
    assert candidate["body"] == "Synthetic visible reminder."
    rendered = json.dumps(candidate, sort_keys=True)
    assert "private_detail" not in rendered

    delivery_key = candidate["delivery_key"]
    assert isinstance(delivery_key, str)

    rejected = handle_request_json(
        app,
        _request(
            "attention.notification_result",
            {
                "run_id": run_id,
                "event_id": str(event.id),
                "delivery_key": delivery_key,
                "succeeded": True,
                "title": "must not be accepted",
            },
        ),
    )
    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.code == "invalid_request"
    assert deliveries.get(event.id, "macos.notification") is None

    accepted = handle_request_json(
        app,
        _request(
            "attention.notification_result",
            {
                "run_id": run_id,
                "event_id": str(event.id),
                "delivery_key": delivery_key,
                "succeeded": True,
            },
        ),
    )
    assert accepted.ok
    assert isinstance(accepted.result, dict)
    assert accepted.result["status"] == "succeeded"
    assert accepted.result["sink_id"] == "macos.notification"

    completed = handle_request_json(
        app,
        _request("service.complete_proactive", {"run_id": run_id}),
    )
    assert completed.ok
    assert isinstance(completed.result, dict)
    assert completed.result["status"] == "succeeded"
    assert completed.result["delivery_attempts"] == 1
    assert completed.result["delivery_failures"] == 0

    prepared_again = handle_request_json(
        app,
        _request("service.prepare_proactive"),
    )
    assert prepared_again.ok
    assert isinstance(prepared_again.result, dict)
    assert prepared_again.result["candidates"] == []


def test_bridge_task_proposal_is_review_only_and_uses_registered_tools(
    tmp_path: Path,
) -> None:
    goal = "Use the reviewed reversible tool"
    provider = CapturingProvider(
        [
            json.dumps(
                {
                    "goal": goal,
                    "steps": [
                        {
                            "tool_name": "test.reversible",
                            "arguments": {"value": "synthetic"},
                        }
                    ],
                }
            )
        ]
    )
    app, tool = _task_application(tmp_path, provider=provider)

    assert app.list_tasks() == ()
    proposed = handle_request_json(
        app,
        _request("task.propose", {"goal": goal}),
    )

    assert proposed.ok
    assert isinstance(proposed.result, dict)
    assert proposed.result["goal"] == goal
    assert app.list_tasks() == ()
    assert tool.calls == 0
    assert len(provider.requests) == 1
    prompt = provider.requests[0].messages[-1].content
    assert "test.reversible" in prompt
    assert "Synthetic reversible desktop bridge tool." in prompt
    assert "system.info" not in prompt


def test_bridge_task_proposal_rejects_undeclared_model_tool_before_persistence(
    tmp_path: Path,
) -> None:
    goal = "Invent no tools"
    provider = CapturingProvider(
        [
            json.dumps(
                {
                    "goal": goal,
                    "steps": [
                        {
                            "tool_name": "undeclared.tool",
                            "arguments": {},
                        }
                    ],
                }
            )
        ]
    )
    app, tool = _task_application(tmp_path, provider=provider)

    response = handle_request_json(
        app,
        _request("task.propose", {"goal": goal}),
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "invalid_request"
    assert app.list_tasks() == ()
    assert tool.calls == 0


def test_bridge_task_create_persists_reviewed_plan_without_execution(
    tmp_path: Path,
) -> None:
    app, tool = _task_application(tmp_path)
    plan = {
        "goal": "Persist the reviewed plan",
        "steps": [
            {
                "tool_name": "test.reversible",
                "arguments": {"value": "reviewed"},
            }
        ],
    }

    created = handle_request_json(
        app,
        _request("task.create", {"plan": plan}),
    )

    assert created.ok
    assert isinstance(created.result, dict)
    task = created.result["task"]
    steps = created.result["steps"]
    assert isinstance(task, dict)
    assert isinstance(steps, list)
    assert task["goal"] == plan["goal"]
    assert task["status"] == "pending"
    assert len(app.list_tasks()) == 1
    assert tool.calls == 0
    assert isinstance(steps[0], dict)
    assert steps[0]["arguments"] == {"value": "reviewed"}


@pytest.mark.parametrize(
    "forbidden",
    (
        {"development_endpoint": "http://127.0.0.1:9999/v1"},
        {"development_model": "unreviewed-model"},
        {"tools": [{"name": "caller.tool"}]},
        {"approved": True},
        {"run": True},
    ),
)
def test_bridge_task_proposal_rejects_authority_bearing_fields(
    tmp_path: Path,
    forbidden: dict[str, object],
) -> None:
    app, tool = _task_application(tmp_path)
    params: dict[str, object] = {"goal": "Strict proposal"}
    params.update(forbidden)

    response = handle_request_json(app, _request("task.propose", params))

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "invalid_request"
    assert app.list_tasks() == ()
    assert tool.calls == 0


def test_bridge_task_create_rejects_approval_or_execution_fields(
    tmp_path: Path,
) -> None:
    app, tool = _task_application(tmp_path)
    response = handle_request_json(
        app,
        _request(
            "task.create",
            {
                "plan": {
                    "goal": "Strict creation",
                    "steps": [
                        {"tool_name": "test.reversible", "arguments": {}}
                    ],
                },
                "approved": True,
            },
        ),
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "invalid_request"
    assert app.list_tasks() == ()
    assert tool.calls == 0


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


def test_bridge_legacy_service_migration_is_path_free_and_exact(
    tmp_path: Path,
) -> None:
    service, runner = _legacy_service(tmp_path)
    runner.loaded = True
    app, _, _ = _attention_application(
        tmp_path,
        legacy_managed_service=service,
    )

    status = handle_request_json(app, _request("service.legacy_status"))

    assert status.ok
    assert isinstance(status.result, dict)
    assert status.result["definition_state"] == "recognized_legacy"
    assert status.result["configured"] is True
    assert status.result["can_retire"] is True
    rendered = status.model_dump_json()
    assert "plist" not in rendered
    assert "SyntheticOldAlly" not in rendered
    assert str(tmp_path) not in rendered

    rejected = handle_request_json(
        app,
        _request("service.retire_legacy", {"path": "/tmp/not-allowed"}),
    )
    assert not rejected.ok
    assert rejected.error is not None
    assert rejected.error.code == "invalid_request"
    assert service.paths.plist.exists()

    retired = handle_request_json(app, _request("service.retire_legacy"))
    assert retired.ok
    assert isinstance(retired.result, dict)
    assert retired.result["configured"] is False
    assert retired.result["definition_state"] == "absent"
    assert not service.paths.plist.exists()


def test_bridge_refuses_modified_legacy_service_retirement(tmp_path: Path) -> None:
    service, _ = _legacy_service(tmp_path)
    definition = plistlib.loads(service.paths.plist.read_bytes())
    definition["StartInterval"] = 10
    service.paths.plist.write_bytes(
        plistlib.dumps(definition, fmt=plistlib.FMT_XML, sort_keys=True)
    )
    app, _, _ = _attention_application(
        tmp_path,
        legacy_managed_service=service,
    )

    status = handle_request_json(app, _request("service.legacy_status"))
    assert status.ok
    assert isinstance(status.result, dict)
    assert status.result["definition_state"] == "modified"
    assert status.result["can_retire"] is False

    retired = handle_request_json(app, _request("service.retire_legacy"))
    assert not retired.ok
    assert retired.error is not None
    assert retired.error.code == "invalid_state"
    assert service.paths.plist.exists()
