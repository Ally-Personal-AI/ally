"""Strict PCM16 WAV inspection and loading for local voice input."""

from __future__ import annotations

import wave
from pathlib import Path

from ally.voice.models import (
    MAX_AUDIO_SECONDS,
    MAX_PCM_BYTES,
    MAX_SAMPLE_RATE_HZ,
    MIN_SAMPLE_RATE_HZ,
    AudioMetadata,
    PCM16Audio,
    VoiceAudioError,
)

MAX_WAV_FILE_BYTES = MAX_PCM_BYTES + 1024 * 1024


def _resolved_wav(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise VoiceAudioError("voice WAV input must not be a symbolic link")
    try:
        resolved = expanded.resolve(strict=True)
        size = resolved.stat().st_size
    except OSError as exc:
        raise VoiceAudioError("voice WAV input is unavailable") from exc
    if not resolved.is_file():
        raise VoiceAudioError("voice WAV input must be a regular file")
    if size > MAX_WAV_FILE_BYTES:
        raise VoiceAudioError("voice WAV input exceeds the size limit")
    return resolved


def _metadata(handle: wave.Wave_read) -> AudioMetadata:
    channels = handle.getnchannels()
    sample_width = handle.getsampwidth()
    sample_rate = handle.getframerate()
    frame_count = handle.getnframes()
    compression = handle.getcomptype()

    if compression != "NONE":
        raise VoiceAudioError("voice WAV input must use uncompressed PCM")
    if sample_width != 2:
        raise VoiceAudioError("voice WAV input must use signed 16-bit PCM")
    if channels not in {1, 2}:
        raise VoiceAudioError("voice WAV input must use one or two channels")
    if not MIN_SAMPLE_RATE_HZ <= sample_rate <= MAX_SAMPLE_RATE_HZ:
        raise VoiceAudioError("voice WAV sample rate is outside the supported range")
    if frame_count < 1:
        raise VoiceAudioError("voice WAV input contains no audio frames")

    pcm_bytes = frame_count * channels * sample_width
    if pcm_bytes > MAX_PCM_BYTES:
        raise VoiceAudioError("voice WAV PCM payload exceeds the size limit")
    duration_seconds = frame_count / sample_rate
    if duration_seconds > MAX_AUDIO_SECONDS:
        raise VoiceAudioError("voice WAV input exceeds the duration limit")

    return AudioMetadata(
        sample_rate_hz=sample_rate,
        channels=channels,
        frame_count=frame_count,
        pcm_bytes=pcm_bytes,
        duration_ms=duration_seconds * 1000.0,
    )


def inspect_pcm16_wav(path: Path) -> AudioMetadata:
    """Read only bounded WAV structure/metadata; never persist audio."""

    resolved = _resolved_wav(path)
    try:
        with wave.open(str(resolved), "rb") as handle:
            return _metadata(handle)
    except (EOFError, wave.Error) as exc:
        raise VoiceAudioError("voice WAV input is malformed or unsupported") from exc


def load_pcm16_wav(path: Path) -> PCM16Audio:
    """Load one bounded uncompressed PCM16 WAV into ephemeral memory."""

    resolved = _resolved_wav(path)
    try:
        with wave.open(str(resolved), "rb") as handle:
            metadata = _metadata(handle)
            pcm = handle.readframes(metadata.frame_count)
    except (EOFError, wave.Error) as exc:
        raise VoiceAudioError("voice WAV input is malformed or unsupported") from exc

    if len(pcm) != metadata.pcm_bytes:
        raise VoiceAudioError("voice WAV input ended before its declared frames")
    return PCM16Audio(
        pcm=pcm,
        sample_rate_hz=metadata.sample_rate_hz,
        channels=metadata.channels,
    )
