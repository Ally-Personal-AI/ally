from __future__ import annotations

import wave
from pathlib import Path

import pytest

from ally.voice import (
    PCM16Audio,
    VoiceAudioError,
    inspect_pcm16_wav,
    load_pcm16_wav,
)


def _write_wav(
    path: Path,
    *,
    channels: int = 1,
    sample_width: int = 2,
    sample_rate: int = 16_000,
    frames: int = 1_600,
) -> Path:
    sample = b"\x00" * sample_width * channels
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        handle.writeframes(sample * frames)
    return path


def test_inspect_pcm16_wav_returns_path_free_bounded_metadata(tmp_path: Path) -> None:
    path = _write_wav(tmp_path / "voice.wav")

    metadata = inspect_pcm16_wav(path)

    assert metadata.sample_rate_hz == 16_000
    assert metadata.channels == 1
    assert metadata.frame_count == 1_600
    assert metadata.pcm_bytes == 3_200
    assert metadata.duration_ms == pytest.approx(100.0)
    assert "voice.wav" not in metadata.model_dump_json()


def test_load_pcm16_wav_returns_ephemeral_pcm_clip(tmp_path: Path) -> None:
    path = _write_wav(tmp_path / "voice.wav", channels=2, frames=800)

    audio = load_pcm16_wav(path)

    assert isinstance(audio, PCM16Audio)
    assert audio.sample_rate_hz == 16_000
    assert audio.channels == 2
    assert audio.frame_count == 800
    assert audio.duration_seconds == pytest.approx(0.05)
    assert "pcm" not in audio.model_dump()
    assert "pcm" not in repr(audio)


def test_pcm16_wav_rejects_non_16_bit_audio(tmp_path: Path) -> None:
    path = _write_wav(tmp_path / "voice-8bit.wav", sample_width=1)

    with pytest.raises(VoiceAudioError, match="16-bit"):
        inspect_pcm16_wav(path)


def test_pcm16_wav_rejects_symlink_input(tmp_path: Path) -> None:
    target = _write_wav(tmp_path / "target.wav")
    link = tmp_path / "linked.wav"
    link.symlink_to(target)

    with pytest.raises(VoiceAudioError, match="symbolic link"):
        inspect_pcm16_wav(link)


def test_pcm_audio_rejects_partial_frames() -> None:
    with pytest.raises(ValueError, match="complete frames"):
        PCM16Audio(pcm=b"\x00\x00\x00", sample_rate_hz=16_000, channels=1)
