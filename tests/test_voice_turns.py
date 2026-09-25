from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ally.application import (
    VoiceTrustError,
    VoiceTurnCoordinator,
    VoiceTurnRequest,
)
from ally.application.models import ChatTurnRequest, ChatTurnResult
from ally.conversations import Conversation
from ally.models import ChatResponse
from ally.runtime_profiles import ResolvedInferenceTarget
from ally.voice import PCM16Audio, SpeechTranscript, VoiceTrustDomain


class FakeApplication:
    def __init__(self) -> None:
        self.requests: list[ChatTurnRequest] = []

    def send_message(self, request: ChatTurnRequest) -> ChatTurnResult:
        self.requests.append(request)
        now = datetime.now(UTC)
        return ChatTurnResult(
            conversation=Conversation(
                id=request.conversation_id or uuid4(),
                title="Synthetic voice",
                created_at=now,
                updated_at=now,
            ),
            response=ChatResponse(
                content="Synthetic assistant response.",
                model="synthetic",
                provider="synthetic-local",
            ),
            target=ResolvedInferenceTarget(
                source="development_override",
                endpoint="http://127.0.0.1:12345/v1",
                model="synthetic",
            ),
        )


class FakeRecognizer:
    def __init__(self, trust_domain: VoiceTrustDomain = "local") -> None:
        self._trust_domain = trust_domain
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake-asr"

    @property
    def trust_domain(self) -> VoiceTrustDomain:
        return self._trust_domain

    def transcribe(self, audio: PCM16Audio) -> SpeechTranscript:
        self.calls += 1
        assert audio.frame_count > 0
        return SpeechTranscript(text="Synthetic voice input.")


class FakeSynthesizer:
    def __init__(self, trust_domain: VoiceTrustDomain = "local") -> None:
        self._trust_domain = trust_domain
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "fake-tts"

    @property
    def trust_domain(self) -> VoiceTrustDomain:
        return self._trust_domain

    def synthesize(self, text: str) -> PCM16Audio:
        self.calls.append(text)
        return PCM16Audio(
            pcm=b"\x00\x00" * 800,
            sample_rate_hz=16_000,
            channels=1,
        )


def _audio() -> PCM16Audio:
    return PCM16Audio(
        pcm=b"\x00\x00" * 1_600,
        sample_rate_hz=16_000,
        channels=1,
    )


def test_voice_turn_reuses_existing_chat_authority() -> None:
    application = FakeApplication()
    recognizer = FakeRecognizer()
    synthesizer = FakeSynthesizer()
    coordinator = VoiceTurnCoordinator(
        application=application,
        recognizer=recognizer,
        synthesizer=synthesizer,
    )

    result = coordinator.turn(
        VoiceTurnRequest(
            audio=_audio(),
            project_key="synthetic-project",
            session_instructions="Synthetic voice session instruction.",
        )
    )

    assert recognizer.calls == 1
    assert len(application.requests) == 1
    request = application.requests[0]
    assert request.message == "Synthetic voice input."
    assert request.project_key == "synthetic-project"
    assert request.session_instructions == "Synthetic voice session instruction."
    assert request.development_endpoint is None
    assert request.development_model is None
    assert synthesizer.calls == ["Synthetic assistant response."]
    assert result.transcript.text == "Synthetic voice input."
    assert result.output_audio.frame_count == 800
    assert result.recognizer == "fake-asr"
    assert result.synthesizer == "fake-tts"
    assert "audio" not in result.model_dump()


@pytest.mark.parametrize(
    ("recognizer_domain", "synthesizer_domain"),
    (("external", "local"), ("local", "external")),
)
def test_voice_turn_rejects_any_external_provider_before_processing(
    recognizer_domain: VoiceTrustDomain,
    synthesizer_domain: VoiceTrustDomain,
) -> None:
    application = FakeApplication()
    recognizer = FakeRecognizer(recognizer_domain)
    synthesizer = FakeSynthesizer(synthesizer_domain)
    coordinator = VoiceTurnCoordinator(
        application=application,
        recognizer=recognizer,
        synthesizer=synthesizer,
    )

    with pytest.raises(VoiceTrustError, match="local trust domain"):
        coordinator.turn(VoiceTurnRequest(audio=_audio()))

    assert recognizer.calls == 0
    assert synthesizer.calls == []
    assert application.requests == []


def test_voice_turn_request_has_no_raw_inference_override() -> None:
    with pytest.raises(ValidationError):
        VoiceTurnRequest.model_validate(
            {
                "audio": _audio(),
                "development_endpoint": "http://127.0.0.1:12345/v1",
                "development_model": "synthetic",
            }
        )
