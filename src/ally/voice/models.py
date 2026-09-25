"""Bounded local audio and speech models for Ally voice turns."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_AUDIO_SECONDS = 120.0
MAX_PCM_BYTES = 32 * 1024 * 1024
MIN_SAMPLE_RATE_HZ = 8_000
MAX_SAMPLE_RATE_HZ = 48_000


class VoiceAudioError(ValueError):
    """Raised when audio cannot enter Ally's bounded local voice boundary."""


class AudioMetadata(BaseModel):
    """Path-free metadata for one bounded PCM16 audio clip."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_rate_hz: int = Field(ge=MIN_SAMPLE_RATE_HZ, le=MAX_SAMPLE_RATE_HZ)
    channels: int = Field(ge=1, le=2)
    frame_count: int = Field(ge=1)
    pcm_bytes: int = Field(ge=2, le=MAX_PCM_BYTES)
    duration_ms: float = Field(gt=0.0, le=MAX_AUDIO_SECONDS * 1000.0)


class PCM16Audio(BaseModel):
    """Ephemeral interleaved signed 16-bit little-endian PCM audio."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pcm: bytes = Field(repr=False, exclude=True)
    sample_rate_hz: int = Field(ge=MIN_SAMPLE_RATE_HZ, le=MAX_SAMPLE_RATE_HZ)
    channels: int = Field(ge=1, le=2)

    @model_validator(mode="after")
    def validate_audio(self) -> PCM16Audio:
        frame_bytes = self.channels * 2
        if not self.pcm:
            raise ValueError("PCM audio must contain at least one frame")
        if len(self.pcm) > MAX_PCM_BYTES:
            raise ValueError("PCM audio exceeds the voice size limit")
        if len(self.pcm) % frame_bytes != 0:
            raise ValueError("PCM audio length must align to complete frames")
        if self.duration_seconds > MAX_AUDIO_SECONDS:
            raise ValueError("PCM audio exceeds the voice duration limit")
        return self

    @property
    def frame_count(self) -> int:
        return len(self.pcm) // (self.channels * 2)

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate_hz

    def metadata(self) -> AudioMetadata:
        return AudioMetadata(
            sample_rate_hz=self.sample_rate_hz,
            channels=self.channels,
            frame_count=self.frame_count,
            pcm_bytes=len(self.pcm),
            duration_ms=self.duration_seconds * 1000.0,
        )


class SpeechTranscript(BaseModel):
    """Text produced locally from one bounded speech clip."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1, max_length=100_000)
    language: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def reject_blank_text(self) -> SpeechTranscript:
        if not self.text.strip():
            raise ValueError("speech transcript must contain non-whitespace text")
        return self
