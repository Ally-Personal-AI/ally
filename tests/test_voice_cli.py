from __future__ import annotations

import json
import wave
from pathlib import Path

from ally.commands.voice import run_inspect_voice_wav


def test_voice_inspection_command_emits_path_free_json(
    tmp_path: Path,
    capsys,
) -> None:
    path = tmp_path / "private-name.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\x00\x00" * 1_600)

    assert run_inspect_voice_wav(path=str(path), json_output=True) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["sample_rate_hz"] == 16_000
    assert payload["duration_ms"] == 100.0
    assert "private-name.wav" not in output
