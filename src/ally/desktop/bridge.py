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
    KnowledgeTextIngestRequest,
    RunTaskRequest,
    SupersedeMemoryRequest,
)
from ally.composition import build_default_application
from ally.runtime_profiles import InferenceTargetError

BRIDGE_PROTOCOL_VERSION = 3
MAX_REQUEST_BYTES = 1024 * 1024

BridgeMethod = Literal[
    "bridge.info",
    "bootstrap",
    "conversation.create",
    "conversation.get",
    "conversation.send",
    "memory.list",
    "memory.get",
    "memory.search",
    "memory.supersede",
    "memory.retract",
    "knowledge.list",
    "knowledge.get",
    "knowledge.search",
    "knowledge.ingest_text",
    "task.get",
    "task.run",
    "task.approve_step",
    "task.retry_step",
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
                "memory.list",
                "memory.get",
                "memory.search",
                "memory.supersede",
                "memory.retract",
                "knowledge.list",
                "knowledge.get",
                "knowledge.search",
                "knowledge.ingest_text",
                "task.get",
                "task.run",
                "task.approve_step",
                "task.retry_step",
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
