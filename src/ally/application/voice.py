"""UI-neutral local-only voice-turn coordination."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ally.application.models import ChatTurnRequest, ChatTurnResult
from ally.voice import PCM16Audio, SpeechRecognizer, SpeechSynthesizer, SpeechTranscript


class VoiceTrustError(ValueError):
    """Raised before private audio/text reaches an untrusted voice provider."""


class VoiceTurnRequest(BaseModel):
    """One ephemeral speech input routed through Ally's existing chat authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    audio: PCM16Audio
    conversation_id: UUID | None = None
    project_key: str | None = None
    task_key: str | None = None
    session_instructions: str | None = Field(default=None, max_length=100_000)


class VoiceTurnResult(BaseModel):
    """Voice response without retaining the input audio payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transcript: SpeechTranscript
    chat: ChatTurnResult
    output_audio: PCM16Audio
    recognizer: str = Field(min_length=1, max_length=200)
    synthesizer: str = Field(min_length=1, max_length=200)


class VoiceChatApplication(Protocol):
    """Minimal application authority required by a voice turn."""

    def send_message(self, request: ChatTurnRequest) -> ChatTurnResult:
        ...


class VoiceTurnCoordinator:
    """Compose local ASR -> existing private chat -> local TTS."""

    def __init__(
        self,
        *,
        application: VoiceChatApplication,
        recognizer: SpeechRecognizer,
        synthesizer: SpeechSynthesizer,
    ) -> None:
        self._application = application
        self._recognizer = recognizer
        self._synthesizer = synthesizer

    @staticmethod
    def _require_local(provider: SpeechRecognizer | SpeechSynthesizer) -> None:
        if provider.trust_domain != "local":
            raise VoiceTrustError(
                "voice providers must remain inside Ally's local trust domain"
            )

    def turn(self, request: VoiceTurnRequest) -> VoiceTurnResult:
        """Execute one bounded turn without creating new inference/tool authority."""

        # Check both ends before either private audio or assistant text is processed.
        self._require_local(self._recognizer)
        self._require_local(self._synthesizer)

        transcript = self._recognizer.transcribe(request.audio)
        chat = self._application.send_message(
            ChatTurnRequest(
                message=transcript.text,
                conversation_id=request.conversation_id,
                project_key=request.project_key,
                task_key=request.task_key,
                session_instructions=request.session_instructions,
            )
        )
        output_audio = self._synthesizer.synthesize(chat.response.content)
        return VoiceTurnResult(
            transcript=transcript,
            chat=chat,
            output_audio=output_audio,
            recognizer=self._recognizer.name,
            synthesizer=self._synthesizer.name,
        )
