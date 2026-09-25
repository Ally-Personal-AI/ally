"""Provider-neutral local speech contracts."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from ally.voice.models import PCM16Audio, SpeechTranscript

VoiceTrustDomain = Literal["local", "external"]


@runtime_checkable
class SpeechRecognizer(Protocol):
    """Convert local bounded audio to text."""

    @property
    def name(self) -> str:
        """Stable provider identifier."""
        ...

    @property
    def trust_domain(self) -> VoiceTrustDomain:
        """Whether audio processing stays inside Ally's local trust domain."""
        ...

    def transcribe(self, audio: PCM16Audio) -> SpeechTranscript:
        """Transcribe one ephemeral local audio clip."""
        ...


@runtime_checkable
class SpeechSynthesizer(Protocol):
    """Convert private assistant text to local bounded audio."""

    @property
    def name(self) -> str:
        """Stable provider identifier."""
        ...

    @property
    def trust_domain(self) -> VoiceTrustDomain:
        """Whether synthesis stays inside Ally's local trust domain."""
        ...

    def synthesize(self, text: str) -> PCM16Audio:
        """Synthesize one private assistant response."""
        ...
