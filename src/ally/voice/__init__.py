"""Local-only voice contracts and bounded audio handling."""

from ally.voice.models import (
    MAX_AUDIO_SECONDS,
    MAX_PCM_BYTES,
    MAX_SAMPLE_RATE_HZ,
    MIN_SAMPLE_RATE_HZ,
    AudioMetadata,
    PCM16Audio,
    SpeechTranscript,
    VoiceAudioError,
)
from ally.voice.providers import (
    SpeechRecognizer,
    SpeechSynthesizer,
    VoiceTrustDomain,
)
from ally.voice.wav import MAX_WAV_FILE_BYTES, inspect_pcm16_wav, load_pcm16_wav

__all__ = [
    "MAX_AUDIO_SECONDS",
    "MAX_PCM_BYTES",
    "MAX_SAMPLE_RATE_HZ",
    "MAX_WAV_FILE_BYTES",
    "MIN_SAMPLE_RATE_HZ",
    "AudioMetadata",
    "PCM16Audio",
    "SpeechRecognizer",
    "SpeechSynthesizer",
    "SpeechTranscript",
    "VoiceAudioError",
    "VoiceTrustDomain",
    "inspect_pcm16_wav",
    "load_pcm16_wav",
]
