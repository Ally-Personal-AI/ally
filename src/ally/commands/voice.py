"""Read-only development commands for bounded local voice audio."""

from __future__ import annotations

import json
from pathlib import Path

from ally.voice import VoiceAudioError, inspect_pcm16_wav


def run_inspect_voice_wav(*, path: str, json_output: bool) -> int:
    """Inspect WAV metadata without transcribing, persisting, or contacting a model."""

    try:
        metadata = inspect_pcm16_wav(Path(path))
    except VoiceAudioError as exc:
        print(f"Voice audio error: {exc}")
        return 2

    if json_output:
        print(json.dumps(metadata.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(f"Sample rate: {metadata.sample_rate_hz} Hz")
        print(f"Channels: {metadata.channels}")
        print(f"Frames: {metadata.frame_count}")
        print(f"PCM bytes: {metadata.pcm_bytes}")
        print(f"Duration: {metadata.duration_ms:.2f} ms")
    return 0
