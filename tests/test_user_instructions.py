from pathlib import Path

import pytest

from ally.cli import build_parser, main
from ally.models import ChatRequest, ChatResponse
from ally.runtime import ConversationRuntime
from ally.storage.sqlite import SQLiteDatabase, SQLiteUserInstructionsStore


class RecordingProvider:
    def __init__(self) -> None:
        self.last_request: ChatRequest | None = None

    @property
    def name(self) -> str:
        return "recording"

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.last_request = request
        return ChatResponse(
            content="answer",
            model="synthetic",
            provider=self.name,
        )


def test_instruction_store_round_trip_and_clear(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    store = SQLiteUserInstructionsStore(SQLiteDatabase(path))

    assert store.get() is None

    created = store.set("Challenge my assumptions. Be concise.")
    assert created.content == "Challenge my assumptions. Be concise."

    reopened = SQLiteUserInstructionsStore(SQLiteDatabase(path))
    loaded = reopened.get()
    assert loaded is not None
    assert loaded.content == created.content
    assert loaded.created_at == created.created_at

    updated = reopened.set("Prefer detailed technical explanations.")
    assert updated.content == "Prefer detailed technical explanations."
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at

    assert reopened.clear() is True
    assert reopened.get() is None
    assert reopened.clear() is False


def test_instruction_store_rejects_empty_content(tmp_path: Path) -> None:
    store = SQLiteUserInstructionsStore(SQLiteDatabase(tmp_path / "ally.sqlite3"))

    with pytest.raises(ValueError, match="cannot be empty"):
        store.set("   ")


def test_conversation_runtime_composes_user_instructions() -> None:
    provider = RecordingProvider()
    runtime = ConversationRuntime(
        provider,
        system_prompt="Fixed Ally behavior.",
        user_instructions="Use terse bullet points.",
    )

    runtime.respond("Question")

    assert provider.last_request is not None
    system = provider.last_request.messages[0]
    assert system.role == "system"
    assert system.content == (
        "Fixed Ally behavior.\n\n"
        "User instructions:\nUse terse bullet points."
    )


def test_instructions_parser_commands() -> None:
    parser = build_parser()

    show = parser.parse_args(["instructions", "show"])
    set_value = parser.parse_args(
        ["instructions", "set", "Challenge assumptions."]
    )
    clear = parser.parse_args(["instructions", "clear"])

    assert show.instructions_command == "show"
    assert set_value.instructions_command == "set"
    assert set_value.content == "Challenge assumptions."
    assert clear.instructions_command == "clear"


def test_instruction_commands_use_private_user_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert main(["instructions", "show"]) == 0
    assert "No user instructions configured." in capsys.readouterr().out

    assert main(
        ["instructions", "set", "Prefer evidence and concise answers."]
    ) == 0
    assert "Prefer evidence and concise answers." in capsys.readouterr().out

    assert main(["instructions", "show"]) == 0
    assert "Prefer evidence and concise answers." in capsys.readouterr().out

    assert main(["instructions", "clear"]) == 0
    assert "User instructions cleared." in capsys.readouterr().out
