from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from ally.application import (
    AllyApplication,
    ApplicationNotFoundError,
    ApplicationStateError,
    ChatTurnRequest,
    KnowledgeTextIngestRequest,
    MemoryProposalRequest,
    RememberMemoryRequest,
    SupersedeMemoryRequest,
)
from ally.models import ChatRequest, ChatResponse
from ally.runtime_profiles import (
    InferenceTargetError,
    ResolvedInferenceTarget,
)
from ally.storage.sqlite import (
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
    SQLiteUserInstructionsStore,
)


class CapturingProvider:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.requests: list[ChatRequest] = []

    @property
    def name(self) -> str:
        return "capturing"

    def __enter__(self) -> CapturingProvider:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("unexpected model request")
        return ChatResponse(
            content=self._responses.pop(0),
            model="synthetic-model",
            provider=self.name,
        )


def _target(
    endpoint: str | None,
    model: str | None,
) -> ResolvedInferenceTarget:
    if endpoint is None and model is None:
        return ResolvedInferenceTarget(
            source="validated_profile",
            endpoint="http://127.0.0.1:8080/v1",
            model="synthetic-model",
            profile_id="a" * 64,
            runtime_name="synthetic-runtime",
            runtime_version="1",
        )
    if endpoint is None or model is None:
        raise InferenceTargetError(
            "development inference requires both endpoint and model"
        )
    return ResolvedInferenceTarget(
        source="development_override",
        endpoint=endpoint,
        model=model,
    )


def _application(
    tmp_path: Path,
    *,
    provider: CapturingProvider,
    resolver: Callable[
        [str | None, str | None],
        ResolvedInferenceTarget,
    ] = _target,
) -> tuple[AllyApplication, SQLiteUserInstructionsStore]:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
    instructions = SQLiteUserInstructionsStore(database)

    def provider_factory(
        target: ResolvedInferenceTarget,
    ) -> AbstractContextManager[CapturingProvider]:
        assert target.model
        return provider

    return (
        AllyApplication(
            conversations=SQLiteConversationStore(database),
            memories=SQLiteMemoryStore(database),
            knowledge=SQLiteKnowledgeStore(database),
            instructions=instructions,
            target_resolver=resolver,
            provider_factory=provider_factory,
        ),
        instructions,
    )


def test_application_chat_composes_instructions_grounding_and_persistence(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider(["SYNTHETIC_OK"])
    app, instructions = _application(tmp_path, provider=provider)
    instructions.set("Be concise and precise.")

    memory = app.remember(
        RememberMemoryRequest(
            content="The greenhouse tea marker is JASMINE-731.",
            kind="preference",
            importance=0.9,
        )
    )
    note = tmp_path / "greenhouse.txt"
    note.write_text(
        "The greenhouse validation code is GLASS-482.",
        encoding="utf-8",
    )
    ingested = app.ingest_knowledge_file(note)

    result = app.send_message(
        ChatTurnRequest(
            message="What are the greenhouse validation code and tea marker?",
        )
    )

    assert result.response.content == "SYNTHETIC_OK"
    assert result.target.source == "validated_profile"

    request = provider.requests[0]
    rendered = "\n".join(message.content for message in request.messages)
    assert "Be concise and precise." in rendered
    assert "JASMINE-731" in rendered
    assert "GLASS-482" in rendered
    assert "REFERENCE CONTEXT" in rendered

    view = app.conversation(result.conversation.id)
    assert [message.role for message in view.messages] == ["user", "assistant"]
    assert view.messages[0].content.startswith("What are the greenhouse")
    assert view.messages[1].content == "SYNTHETIC_OK"

    assert app.memory(memory.id).id == memory.id
    assert app.knowledge_source(ingested.source.id).source.id == ingested.source.id


def test_application_chat_resumes_existing_conversation(tmp_path: Path) -> None:
    provider = CapturingProvider(["FIRST", "SECOND"])
    app, _ = _application(tmp_path, provider=provider)

    first = app.send_message(ChatTurnRequest(message="First turn."))
    second = app.send_message(
        ChatTurnRequest(
            message="Second turn.",
            conversation_id=first.conversation.id,
        )
    )

    assert second.conversation.id == first.conversation.id
    assert [message.content for message in app.conversation(
        first.conversation.id
    ).messages] == [
        "First turn.",
        "FIRST",
        "Second turn.",
        "SECOND",
    ]
    second_request = provider.requests[1]
    assert any(message.content == "FIRST" for message in second_request.messages)


def test_application_resolves_target_before_conversation_access(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider([])

    def unavailable(
        endpoint: str | None,
        model: str | None,
    ) -> ResolvedInferenceTarget:
        raise InferenceTargetError("active validated runtime profile unavailable")

    app, _ = _application(
        tmp_path,
        provider=provider,
        resolver=unavailable,
    )

    with pytest.raises(InferenceTargetError):
        app.send_message(ChatTurnRequest(message="Private prompt."))

    assert SQLiteConversationStore(
        SQLiteDatabase(tmp_path / "ally.sqlite3")
    ).list() == ()


def test_application_runtime_status_is_payload_free_and_typed(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider([])
    ready, _ = _application(tmp_path / "ready", provider=provider)

    ready_status = ready.runtime_status()
    assert ready_status.state == "ready"
    target = ready_status.target
    assert target is not None
    assert target.profile_id == "a" * 64

    def unavailable(
        endpoint: str | None,
        model: str | None,
    ) -> ResolvedInferenceTarget:
        raise InferenceTargetError("PRIVATE-PATH-MUST-NOT-SURFACE")

    blocked, _ = _application(
        tmp_path / "blocked",
        provider=provider,
        resolver=unavailable,
    )
    status = blocked.runtime_status()

    assert status.state == "unavailable"
    assert status.error_code == "active_profile_unavailable"
    assert "PRIVATE" not in status.model_dump_json()


def test_application_memory_lifecycle_matches_domain_semantics(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider([])
    app, _ = _application(tmp_path, provider=provider)

    original = app.remember(
        RememberMemoryRequest(
            content="Prefers green tea.",
            kind="preference",
            importance=0.8,
        )
    )
    assert app.search_memories("green tea")[0].id == original.id

    replacement = app.supersede_memory(
        SupersedeMemoryRequest(
            memory_id=original.id,
            content="Prefers jasmine tea.",
        )
    )
    assert replacement.supersedes == original.id
    assert app.memory(original.id).superseded_by == replacement.id
    assert app.search_memories("green tea") == ()
    assert app.search_memories("jasmine")[0].id == replacement.id

    retracted = app.retract_memory(replacement.id)
    assert retracted.retracted_at is not None
    assert app.search_memories("jasmine") == ()

    with pytest.raises(ApplicationStateError, match="active memory"):
        app.supersede_memory(
            SupersedeMemoryRequest(
                memory_id=replacement.id,
                content="This correction must not revive a retracted memory.",
            )
        )

    with pytest.raises(ApplicationNotFoundError):
        app.memory(original.id.__class__(int=0))


def test_application_knowledge_views_and_search_are_serializable(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider([])
    app, _ = _application(tmp_path, provider=provider)
    note = tmp_path / "notes.txt"
    note.write_text(
        "Synthetic greenhouse uses drip irrigation.",
        encoding="utf-8",
    )

    ingested = app.ingest_knowledge_file(note)
    listed = app.list_knowledge_sources()
    view = app.knowledge_source(ingested.source.id)
    hits = app.search_knowledge("drip irrigation")

    assert listed[0].id == ingested.source.id
    assert view.revisions[-1].sha256 == ingested.revision.sha256
    assert len(view.current_chunks) >= 1
    assert hits[0].source.id == ingested.source.id
    assert "drip irrigation" in hits[0].chunk.content
    assert '"score"' in hits[0].model_dump_json()


def test_application_memory_proposals_remain_reviewable_until_acceptance(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider(
        [
            '{"memories":[{"kind":"preference","content":"Prefers jasmine tea.",'
            '"confidence":0.95,"importance":0.8}]}'
        ]
    )
    app, _ = _application(tmp_path, provider=provider)

    bundle = app.propose_memories(
        MemoryProposalRequest(
            text="I prefer jasmine tea.",
            source_type="user",
        )
    )

    assert bundle.memories[0].content == "Prefers jasmine tea."
    assert app.list_memories() == ()

    created = app.accept_memory_proposals(bundle, indices=(0,))

    assert len(created) == 1
    assert created[0].content == "Prefers jasmine tea."
    assert app.list_memories()[0].id == created[0].id

    with pytest.raises(ValueError, match="at least one"):
        app.accept_memory_proposals(bundle, indices=())
    with pytest.raises(ValueError, match="unique"):
        app.accept_memory_proposals(bundle, indices=(0, 0))


def test_application_supports_in_memory_text_knowledge_ingestion(
    tmp_path: Path,
) -> None:
    provider = CapturingProvider([])
    app, _ = _application(tmp_path, provider=provider)

    result = app.ingest_knowledge_text(
        KnowledgeTextIngestRequest(
            uri="ally-ui://synthetic/note",
            title="Synthetic note",
            text="The hydroponic validation marker is ROOT-519.",
        )
    )

    assert result.source.uri == "ally-ui://synthetic/note"
    assert result.source.title == "Synthetic note"
    hits = app.search_knowledge("hydroponic marker")
    assert hits[0].source.id == result.source.id
    assert "ROOT-519" in hits[0].chunk.content
