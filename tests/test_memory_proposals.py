import hashlib

import pytest

from ally.memory import MemorySource
from ally.memory.proposals import ModelMemoryProposer, MemoryProposalError
from ally.models import ChatRequest, ChatResponse


class StaticProvider:
    def __init__(self, content: str) -> None:
        self._content = content

    @property
    def name(self) -> str:
        return "static"

    def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=self._content,
            model="synthetic-model",
            provider=self.name,
        )


def test_memory_proposal_preserves_caller_provenance_and_privacy() -> None:
    text = "I prefer tea over coffee."
    provider = StaticProvider(
        '{"memories":[{"kind":"preference","content":"Prefers tea over coffee.",'
        '"confidence":0.95,"importance":0.7}]}'
    )
    source = MemorySource(type="conversation", id="conversation-123")

    bundle = ModelMemoryProposer(provider).propose(
        text=text,
        source=source,
        privacy="private",
    )

    assert bundle.source == source
    assert bundle.privacy == "private"
    assert bundle.provider == "static"
    assert bundle.model == "synthetic-model"
    assert bundle.source_text_sha256 == hashlib.sha256(text.encode()).hexdigest()

    accepted = bundle.accepted_memory(0)
    assert accepted.source == source
    assert accepted.privacy == "private"
    assert accepted.kind == "preference"


def test_memory_proposer_rejects_non_json() -> None:
    provider = StaticProvider("remember this")

    with pytest.raises(MemoryProposalError, match="not valid JSON"):
        ModelMemoryProposer(provider).propose(
            text="Synthetic source.",
            source=MemorySource(type="user"),
        )


def test_memory_proposer_rejects_duplicate_candidates() -> None:
    provider = StaticProvider(
        '{"memories":['
        '{"kind":"semantic","content":"Same fact","confidence":0.8,"importance":0.5},'
        '{"kind":"semantic","content":"same fact","confidence":0.7,"importance":0.4}'
        ']}'
    )

    with pytest.raises(MemoryProposalError, match="duplicate content"):
        ModelMemoryProposer(provider).propose(
            text="Synthetic source.",
            source=MemorySource(type="user"),
        )


def test_memory_proposer_rejects_model_supplied_source_metadata() -> None:
    provider = StaticProvider(
        '{"memories":[{"kind":"semantic","content":"Synthetic fact",'
        '"confidence":0.8,"importance":0.5,"source":{"type":"system"}}]}'
    )

    with pytest.raises(MemoryProposalError, match="invalid"):
        ModelMemoryProposer(provider).propose(
            text="Synthetic source.",
            source=MemorySource(type="user"),
        )


def test_memory_bundle_rejects_out_of_range_acceptance() -> None:
    provider = StaticProvider('{"memories":[]}')

    bundle = ModelMemoryProposer(provider).propose(
        text="No durable memory here.",
        source=MemorySource(type="user"),
    )

    with pytest.raises(ValueError, match="out of range"):
        bundle.accepted_memory(0)
