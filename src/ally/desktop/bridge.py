"""Bounded local stdio bridge for native Ally desktop presentation layers.

The bridge is a presentation adapter over ``AllyApplication``. It does not expose
an HTTP listener, does not accept raw runtime coordinates, and does not grant any
new task, tool, memory, or notification authority.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Literal, TextIO, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from ally import __version__
from ally.application import (
    AllyApplication,
    ApplicationNotFoundError,
    ApplicationStateError,
    ApplicationUnavailableError,
    ApproveTaskStepRequest,
    ChatTurnRequest,
    CompleteDesktopProactiveRequest,
    DesktopNotificationResultRequest,
    InstructionSelectorRequest,
    KnowledgeTextIngestRequest,
    MemoryProposalRequest,
    RememberMemoryRequest,
    ResolveUserInstructionsRequest,
    RunTaskRequest,
    SelectRuntimeProfileRequest,
    SetUserInstructionsEnabledRequest,
    SetUserInstructionsRequest,
    SupersedeMemoryRequest,
    TaskProposalRequest,
)
from ally.composition import build_default_application
from ally.memory import MemoryProposalBundle
from ally.research import WebSearchRequest
from ally.runtime_profiles import InferenceTargetError
from ally.tasks import NewTaskStep, TaskPlan

BRIDGE_PROTOCOL_VERSION = 14
MAX_REQUEST_BYTES = 1024 * 1024

BridgeMethod = Literal[
    "bridge.info",
    "bootstrap",
    "conversation.create",
    "conversation.get",
    "conversation.send",
    "conversation.search",
    "conversation.delete",
    "memory.list",
    "memory.get",
    "memory.remember",
    "memory.propose",
    "memory.accept_proposals",
    "memory.search",
    "memory.supersede",
    "memory.retract",
    "knowledge.list",
    "knowledge.get",
    "knowledge.search",
    "knowledge.ingest_text",
    "knowledge.delete",
    "instructions.list",
    "instructions.get",
    "instructions.set",
    "instructions.set_enabled",
    "instructions.clear",
    "instructions.resolve",
    "research.inspect",
    "research.search",
    "research.answer",
    "runtime.profiles",
    "runtime.select_profile",
    "runtime.deselect_profile",
    "task.propose",
    "task.create",
    "task.get",
    "task.run",
    "task.approve_step",
    "task.retry_step",
    "attention.events",
    "attention.get",
    "attention.mark_handled",
    "attention.delivery_history",
    "attention.notification_result",
    "service.prepare_proactive",
    "service.complete_proactive",
    "service.legacy_status",
    "service.retire_legacy",
    "service.health",
]
BridgeErrorCode = Literal[
    "invalid_request",
    "not_found",
    "unavailable",
    "inference_unavailable",
    "invalid_state",
    "operation_failed",
    "request_too_large",
]


class BridgeRequest(BaseModel):
    """One versioned request from a local presentation process."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    method: BridgeMethod
    params: dict[str, JsonValue] = Field(default_factory=dict)


class BridgeError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: BridgeErrorCode
    message: str = Field(min_length=1, max_length=200)


class BridgeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str | None
    ok: bool
    result: JsonValue | None = None
    error: BridgeError | None = None


class _EmptyParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _CreateConversationParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = Field(default=None, max_length=500)


class _ConversationParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    conversation_id: UUID


class _SendConversationParams(_ConversationParams):
    message: str = Field(min_length=1, max_length=1_000_000)


class _ConversationSearchParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=20, ge=1, le=50)


class _ListParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    limit: int = Field(default=100, ge=1, le=100)


class _MemoryListParams(_ListParams):
    kind: Literal[
        "episodic",
        "semantic",
        "procedural",
        "preference",
        "relational",
    ] | None = None
    include_inactive: bool = False


class _RememberMemoryParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(min_length=1, max_length=1_000_000)
    kind: Literal[
        "episodic",
        "semantic",
        "procedural",
        "preference",
        "relational",
    ] = "semantic"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    privacy: Literal["private", "shared", "public"] = "private"


class _MemoryProposalParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1, max_length=1_000_000)
    source_type: Literal["user"] = "user"
    privacy: Literal["private", "shared", "public"] = "private"


class _MemoryAcceptParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle: MemoryProposalBundle
    indices: tuple[int, ...] = Field(min_length=1, max_length=20)


class _MemoryParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: UUID


class _SupersedeMemoryParams(_MemoryParams):
    content: str = Field(min_length=1, max_length=1_000_000)


class _KnowledgeParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: UUID


class _KnowledgeIngestTextParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    uri: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=1000)
    text: str = Field(min_length=1, max_length=1_000_000)
    media_type: str = Field(default="text/plain", min_length=1, max_length=255)


class _SearchParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1, max_length=100_000)
    limit: int = Field(default=20, ge=1, le=100)


class _InstructionListParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    include_disabled: bool = True


class _ResearchParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(min_length=1, max_length=600)
    count: int = Field(default=5, ge=1, le=20)


class _ResearchSearchParams(_ResearchParams):
    approved: bool = False


class _RuntimeProfileParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class _AttentionListParams(_ListParams):
    handled: bool | None = None


class _AttentionEventParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID


class _AttentionHistoryParams(_ListParams):
    status: Literal["succeeded", "failed"] | None = None


class _DesktopProactiveParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schedule_limit: int = Field(default=100, ge=1, le=100)
    delivery_limit: int = Field(default=50, ge=1, le=100)


class _NotificationResultParams(_AttentionEventParams):
    run_id: UUID
    delivery_key: str = Field(min_length=1, max_length=512)
    succeeded: bool


class _CompleteProactiveParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID


class _TaskProposalParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    goal: str = Field(min_length=1, max_length=100_000)


class _TaskPlanStepParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_name: str = Field(min_length=1, max_length=256)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class _TaskPlanParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    goal: str = Field(min_length=1, max_length=100_000)
    steps: tuple[_TaskPlanStepParams, ...] = Field(min_length=1, max_length=100)


class _TaskCreateParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: _TaskPlanParams


class _TaskParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: UUID


class _TaskStepParams(_TaskParams):
    step_id: UUID


def _json_value(value: object) -> JsonValue:
    """Narrow Pydantic JSON-mode output to the recursive JsonValue contract."""

    return cast(JsonValue, value)


def _models_json(items: Sequence[BaseModel]) -> JsonValue:
    return _json_value([item.model_dump(mode="json") for item in items])


def _validate_params(model: type[BaseModel], params: dict[str, JsonValue]) -> BaseModel:
    return model.model_validate(params)


def dispatch_request(app: AllyApplication, request: BridgeRequest) -> JsonValue:
    """Dispatch one request through the UI-neutral application facade."""

    if request.method == "bridge.info":
        _validate_params(_EmptyParams, request.params)
        return {
            "protocol_version": BRIDGE_PROTOCOL_VERSION,
            "ally_version": __version__,
            "transport": "stdio",
            "capabilities": [
                "bootstrap",
                "conversation.create",
                "conversation.get",
                "conversation.send",
                "conversation.search",
                "conversation.delete",
                "memory.list",
                "memory.get",
                "memory.remember",
                "memory.propose",
                "memory.accept_proposals",
                "memory.search",
                "memory.supersede",
                "memory.retract",
                "knowledge.list",
                "knowledge.get",
                "knowledge.search",
                "knowledge.ingest_text",
                "knowledge.delete",
                "instructions.list",
                "instructions.get",
                "instructions.set",
                "instructions.set_enabled",
                "instructions.clear",
                "instructions.resolve",
                "research.inspect",
                "research.search",
                "research.answer",
                "runtime.profiles",
                "runtime.select_profile",
                "runtime.deselect_profile",
                "task.propose",
                "task.create",
                "task.get",
                "task.run",
                "task.approve_step",
                "task.retry_step",
                "attention.events",
                "attention.get",
                "attention.mark_handled",
                "attention.delivery_history",
                "attention.notification_result",
                "service.prepare_proactive",
                "service.complete_proactive",
                "service.legacy_status",
                "service.retire_legacy",
                "service.health",
            ],
        }

    if request.method == "bootstrap":
        _validate_params(_EmptyParams, request.params)
        return _json_value(app.bootstrap().model_dump(mode="json"))

    if request.method == "conversation.create":
        params = cast(
            _CreateConversationParams,
            _validate_params(_CreateConversationParams, request.params),
        )
        return _json_value(
            app.create_conversation(title=params.title).model_dump(mode="json")
        )

    if request.method == "conversation.get":
        params = cast(
            _ConversationParams,
            _validate_params(_ConversationParams, request.params),
        )
        return _json_value(
            app.conversation(params.conversation_id).model_dump(mode="json")
        )

    if request.method == "conversation.send":
        params = cast(
            _SendConversationParams,
            _validate_params(_SendConversationParams, request.params),
        )
        result = app.send_message(
            ChatTurnRequest(
                conversation_id=params.conversation_id,
                message=params.message,
            )
        )
        return _json_value(result.model_dump(mode="json"))

    if request.method == "conversation.delete":
        params = cast(
            _ConversationParams,
            _validate_params(_ConversationParams, request.params),
        )
        return _json_value(app.delete_conversation(params.conversation_id))

    if request.method == "conversation.search":
        params = cast(
            _ConversationSearchParams,
            _validate_params(_ConversationSearchParams, request.params),
        )
        return _models_json(
            app.search_conversations(
                params.query,
                limit=params.limit,
            )
        )

    if request.method == "memory.list":
        params = cast(
            _MemoryListParams,
            _validate_params(_MemoryListParams, request.params),
        )
        return _models_json(
            app.list_memories(
                kind=params.kind,
                include_inactive=params.include_inactive,
                limit=params.limit,
            )
        )

    if request.method == "memory.remember":
        params = cast(
            _RememberMemoryParams,
            _validate_params(_RememberMemoryParams, request.params),
        )
        return _json_value(
            app.remember(
                RememberMemoryRequest(
                    content=params.content,
                    kind=params.kind,
                    confidence=params.confidence,
                    importance=params.importance,
                    privacy=params.privacy,
                )
            ).model_dump(mode="json")
        )

    if request.method == "memory.propose":
        params = cast(
            _MemoryProposalParams,
            _validate_params(_MemoryProposalParams, request.params),
        )
        return _json_value(
            app.propose_memories(
                MemoryProposalRequest(
                    text=params.text,
                    source_type=params.source_type,
                    privacy=params.privacy,
                )
            ).model_dump(mode="json")
        )

    if request.method == "memory.accept_proposals":
        params = cast(
            _MemoryAcceptParams,
            _validate_params(_MemoryAcceptParams, request.params),
        )
        return _models_json(
            app.accept_memory_proposals(
                params.bundle,
                indices=params.indices,
            )
        )

    if request.method == "memory.get":
        params = cast(
            _MemoryParams,
            _validate_params(_MemoryParams, request.params),
        )
        return _json_value(app.memory(params.memory_id).model_dump(mode="json"))

    if request.method == "memory.search":
        params = cast(
            _SearchParams,
            _validate_params(_SearchParams, request.params),
        )
        return _models_json(app.search_memories(params.query, limit=params.limit))

    if request.method == "memory.supersede":
        params = cast(
            _SupersedeMemoryParams,
            _validate_params(_SupersedeMemoryParams, request.params),
        )
        return _json_value(
            app.supersede_memory(
                SupersedeMemoryRequest(
                    memory_id=params.memory_id,
                    content=params.content,
                )
            ).model_dump(mode="json")
        )

    if request.method == "memory.retract":
        params = cast(
            _MemoryParams,
            _validate_params(_MemoryParams, request.params),
        )
        return _json_value(app.retract_memory(params.memory_id).model_dump(mode="json"))

    if request.method == "knowledge.list":
        params = cast(
            _ListParams,
            _validate_params(_ListParams, request.params),
        )
        return _models_json(app.list_knowledge_sources(limit=params.limit))

    if request.method == "knowledge.get":
        params = cast(
            _KnowledgeParams,
            _validate_params(_KnowledgeParams, request.params),
        )
        return _json_value(
            app.knowledge_source(params.source_id).model_dump(mode="json")
        )

    if request.method == "knowledge.delete":
        params = cast(
            _KnowledgeParams,
            _validate_params(_KnowledgeParams, request.params),
        )
        return _json_value(app.delete_knowledge_source(params.source_id))

    if request.method == "knowledge.search":
        params = cast(
            _SearchParams,
            _validate_params(_SearchParams, request.params),
        )
        return _models_json(app.search_knowledge(params.query, limit=params.limit))

    if request.method == "knowledge.ingest_text":
        params = cast(
            _KnowledgeIngestTextParams,
            _validate_params(_KnowledgeIngestTextParams, request.params),
        )
        return _json_value(
            app.ingest_knowledge_text(
                KnowledgeTextIngestRequest(
                    uri=params.uri,
                    title=params.title,
                    text=params.text,
                    media_type=params.media_type,
                )
            ).model_dump(mode="json")
        )

    if request.method == "instructions.list":
        params = cast(
            _InstructionListParams,
            _validate_params(_InstructionListParams, request.params),
        )
        return _models_json(
            app.list_user_instructions(
                include_disabled=params.include_disabled,
            )
        )

    if request.method == "instructions.get":
        params = cast(
            InstructionSelectorRequest,
            _validate_params(InstructionSelectorRequest, request.params),
        )
        return _json_value(
            app.user_instructions(params).model_dump(mode="json")
        )

    if request.method == "instructions.set":
        params = cast(
            SetUserInstructionsRequest,
            _validate_params(SetUserInstructionsRequest, request.params),
        )
        return _json_value(
            app.set_user_instructions(params).model_dump(mode="json")
        )

    if request.method == "instructions.set_enabled":
        params = cast(
            SetUserInstructionsEnabledRequest,
            _validate_params(SetUserInstructionsEnabledRequest, request.params),
        )
        return _json_value(
            app.set_user_instructions_enabled(params).model_dump(mode="json")
        )

    if request.method == "instructions.clear":
        params = cast(
            InstructionSelectorRequest,
            _validate_params(InstructionSelectorRequest, request.params),
        )
        return _json_value(app.clear_user_instructions(params))

    if request.method == "instructions.resolve":
        params = cast(
            ResolveUserInstructionsRequest,
            _validate_params(ResolveUserInstructionsRequest, request.params),
        )
        return _json_value(
            app.resolve_user_instructions(params).model_dump(mode="json")
        )

    if request.method == "research.inspect":
        params = cast(
            _ResearchParams,
            _validate_params(_ResearchParams, request.params),
        )
        return _json_value(
            app.inspect_web_research(
                WebSearchRequest(query=params.query, count=params.count)
            ).model_dump(mode="json")
        )

    if request.method == "research.search":
        params = cast(
            _ResearchSearchParams,
            _validate_params(_ResearchSearchParams, request.params),
        )
        return _json_value(
            app.search_web(
                WebSearchRequest(query=params.query, count=params.count),
                approved=params.approved,
            ).model_dump(mode="json")
        )

    if request.method == "research.answer":
        params = cast(
            _ResearchSearchParams,
            _validate_params(_ResearchSearchParams, request.params),
        )
        return _json_value(
            app.answer_web_research(
                WebSearchRequest(query=params.query, count=params.count),
                approved=params.approved,
            ).model_dump(mode="json")
        )

    if request.method == "runtime.profiles":
        _validate_params(_EmptyParams, request.params)
        return _json_value(
            app.runtime_profile_catalog().model_dump(mode="json")
        )

    if request.method == "runtime.select_profile":
        params = cast(
            _RuntimeProfileParams,
            _validate_params(_RuntimeProfileParams, request.params),
        )
        return _json_value(
            app.select_runtime_profile(
                SelectRuntimeProfileRequest(profile_id=params.profile_id)
            ).model_dump(mode="json")
        )

    if request.method == "runtime.deselect_profile":
        _validate_params(_EmptyParams, request.params)
        return _json_value(
            app.deselect_runtime_profile().model_dump(mode="json")
        )

    if request.method == "task.propose":
        params = cast(
            _TaskProposalParams,
            _validate_params(_TaskProposalParams, request.params),
        )
        return _json_value(
            app.propose_task(
                TaskProposalRequest(goal=params.goal)
            ).model_dump(mode="json")
        )

    if request.method == "task.create":
        params = cast(
            _TaskCreateParams,
            _validate_params(_TaskCreateParams, request.params),
        )
        plan = TaskPlan(
            goal=params.plan.goal,
            steps=tuple(
                NewTaskStep(
                    tool_name=step.tool_name,
                    arguments=step.arguments,
                )
                for step in params.plan.steps
            ),
        )
        return _json_value(app.create_task(plan).model_dump(mode="json"))

    if request.method == "task.get":
        params = cast(
            _TaskParams,
            _validate_params(_TaskParams, request.params),
        )
        return _json_value(app.task(params.task_id).model_dump(mode="json"))

    if request.method == "task.run":
        params = cast(
            _TaskParams,
            _validate_params(_TaskParams, request.params),
        )
        return _json_value(
            app.run_task(RunTaskRequest(task_id=params.task_id)).model_dump(mode="json")
        )

    if request.method == "task.approve_step":
        params = cast(
            _TaskStepParams,
            _validate_params(_TaskStepParams, request.params),
        )
        return _json_value(
            app.approve_task_step(
                ApproveTaskStepRequest(
                    task_id=params.task_id,
                    step_id=params.step_id,
                )
            ).model_dump(mode="json")
        )

    if request.method == "task.retry_step":
        params = cast(
            _TaskStepParams,
            _validate_params(_TaskStepParams, request.params),
        )
        app.retry_task_step(task_id=params.task_id, step_id=params.step_id)
        return _json_value(app.task(params.task_id).model_dump(mode="json"))

    if request.method == "attention.events":
        params = cast(
            _AttentionListParams,
            _validate_params(_AttentionListParams, request.params),
        )
        return _models_json(
            app.list_attention_events(
                limit=params.limit,
                handled=params.handled,
            )
        )

    if request.method == "attention.get":
        params = cast(
            _AttentionEventParams,
            _validate_params(_AttentionEventParams, request.params),
        )
        return _json_value(
            app.attention_event(params.event_id).model_dump(mode="json")
        )

    if request.method == "attention.mark_handled":
        params = cast(
            _AttentionEventParams,
            _validate_params(_AttentionEventParams, request.params),
        )
        return _json_value(
            app.mark_attention_handled(params.event_id).model_dump(mode="json")
        )

    if request.method == "attention.delivery_history":
        params = cast(
            _AttentionHistoryParams,
            _validate_params(_AttentionHistoryParams, request.params),
        )
        return _models_json(
            app.attention_history(
                limit=params.limit,
                status=params.status,
            )
        )

    if request.method == "attention.notification_result":
        params = cast(
            _NotificationResultParams,
            _validate_params(_NotificationResultParams, request.params),
        )
        return _json_value(
            app.record_desktop_notification_result(
                DesktopNotificationResultRequest(
                    run_id=params.run_id,
                    event_id=params.event_id,
                    delivery_key=params.delivery_key,
                    succeeded=params.succeeded,
                )
            ).model_dump(mode="json")
        )

    if request.method == "service.prepare_proactive":
        params = cast(
            _DesktopProactiveParams,
            _validate_params(_DesktopProactiveParams, request.params),
        )
        return _json_value(
            app.prepare_desktop_proactive(
                schedule_limit=params.schedule_limit,
                delivery_limit=params.delivery_limit,
            ).model_dump(mode="json")
        )

    if request.method == "service.complete_proactive":
        params = cast(
            _CompleteProactiveParams,
            _validate_params(_CompleteProactiveParams, request.params),
        )
        return _json_value(
            app.complete_desktop_proactive(
                CompleteDesktopProactiveRequest(run_id=params.run_id)
            ).model_dump(mode="json")
        )

    if request.method == "service.legacy_status":
        _validate_params(_EmptyParams, request.params)
        return _json_value(
            app.legacy_managed_service_status().model_dump(mode="json")
        )

    if request.method == "service.retire_legacy":
        _validate_params(_EmptyParams, request.params)
        return _json_value(
            app.retire_legacy_managed_service().model_dump(mode="json")
        )

    if request.method == "service.health":
        _validate_params(_EmptyParams, request.params)
        return _json_value(app.service_health().model_dump(mode="json"))

    raise AssertionError(f"unhandled bridge method: {request.method}")


def _response_error(
    *,
    request_id: str | None,
    code: BridgeErrorCode,
    message: str,
) -> BridgeResponse:
    return BridgeResponse(
        id=request_id,
        ok=False,
        error=BridgeError(code=code, message=message),
    )


def handle_request_json(app: AllyApplication, raw: str) -> BridgeResponse:
    """Validate, dispatch, and sanitize one JSON request."""

    request_id: str | None = None
    try:
        request = BridgeRequest.model_validate_json(raw)
        request_id = request.id
        result = dispatch_request(app, request)
        return BridgeResponse(id=request.id, ok=True, result=result)
    except InferenceTargetError:
        return _response_error(
            request_id=request_id,
            code="inference_unavailable",
            message="No validated local inference profile is available.",
        )
    except ApplicationNotFoundError:
        return _response_error(
            request_id=request_id,
            code="not_found",
            message="The requested Ally state was not found.",
        )
    except ApplicationUnavailableError:
        return _response_error(
            request_id=request_id,
            code="unavailable",
            message="This Ally capability is not available in the current composition.",
        )
    except ApplicationStateError:
        return _response_error(
            request_id=request_id,
            code="invalid_state",
            message="The requested action is no longer valid for the current Ally state.",
        )
    except (ValidationError, ValueError):
        return _response_error(
            request_id=request_id,
            code="invalid_request",
            message="The desktop bridge request is invalid.",
        )
    except Exception:
        return _response_error(
            request_id=request_id,
            code="operation_failed",
            message="The Ally operation failed without exposing private diagnostics.",
        )


def _write_response(output: TextIO, response: BridgeResponse) -> None:
    output.write(response.model_dump_json(exclude_none=True) + "\n")
    output.flush()


def _read_bounded_line(input_stream: TextIO) -> tuple[str | None, bool]:
    raw = input_stream.readline(MAX_REQUEST_BYTES + 2)
    if raw == "":
        return None, False
    encoded_size = len(raw.encode("utf-8"))
    if encoded_size > MAX_REQUEST_BYTES + 1:
        if not raw.endswith("\n"):
            while True:
                remainder = input_stream.readline(MAX_REQUEST_BYTES + 2)
                if remainder == "" or remainder.endswith("\n"):
                    break
        return None, True
    if not raw.endswith("\n") and encoded_size > MAX_REQUEST_BYTES:
        return None, True
    return raw.rstrip("\r\n"), False


def serve(
    app: AllyApplication,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
    once: bool = False,
) -> int:
    """Serve bounded newline-delimited requests over already-open local stdio."""

    while True:
        raw, too_large = _read_bounded_line(input_stream)
        if too_large:
            _write_response(
                output_stream,
                _response_error(
                    request_id=None,
                    code="request_too_large",
                    message="The desktop bridge request exceeds the size limit.",
                ),
            )
            if once:
                return 2
            continue
        if raw is None:
            return 0
        _write_response(output_stream, handle_request_json(app, raw))
        if once:
            return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ally-desktop-bridge",
        description="Local stdio bridge for the native Ally desktop shell.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Handle one stdin request and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    app = build_default_application()
    return serve(
        app,
        input_stream=sys.stdin,
        output_stream=sys.stdout,
        once=args.once,
    )


if __name__ == "__main__":  # pragma: no cover - console entry point owns coverage
    raise SystemExit(main())
