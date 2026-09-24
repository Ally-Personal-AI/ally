from pathlib import Path

import pytest

from ally.cli import build_parser, main
from ally.instructions import (
    InstructionContext,
    instruction_contributions,
    render_instruction_contributions,
)
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


def build_store(path: Path) -> SQLiteUserInstructionsStore:
    return SQLiteUserInstructionsStore(SQLiteDatabase(path))


def test_instruction_store_preserves_global_compatibility(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    store = build_store(path)

    assert store.get() is None

    created = store.set("Challenge my assumptions. Be concise.")
    assert created.scope == "global"
    assert created.scope_key == ""
    assert created.enabled is True

    reopened = build_store(path)
    loaded = reopened.get()
    assert loaded is not None
    assert loaded.content == created.content
    assert loaded.created_at == created.created_at

    updated = reopened.set("Prefer detailed technical explanations.")
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at

    assert reopened.clear() is True
    assert reopened.get() is None
    assert reopened.clear() is False


def test_scoped_instructions_resolve_in_precedence_order(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    store.set("Global")
    store.set("Project", scope="project", scope_key="alpha")
    store.set("Conversation", scope="conversation", scope_key="conv-1")
    store.set("Task", scope="task", scope_key="task-1")
    store.set("Other project", scope="project", scope_key="other")

    resolved = store.resolve(
        InstructionContext(
            project_key="alpha",
            conversation_key="conv-1",
            task_key="task-1",
        )
    )

    assert [(item.scope, item.content) for item in resolved] == [
        ("global", "Global"),
        ("project", "Project"),
        ("conversation", "Conversation"),
        ("task", "Task"),
    ]


def test_disabled_scope_is_preserved_but_not_resolved(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    store.set("Global")
    store.set("Project", scope="project", scope_key="alpha")
    disabled = store.set_enabled(
        False,
        scope="project",
        scope_key="alpha",
    )

    assert disabled.enabled is False
    listed = store.list()
    assert [(item.scope, item.enabled) for item in listed] == [
        ("global", True),
        ("project", False),
    ]
    assert [item.content for item in store.resolve(InstructionContext(project_key="alpha"))] == [
        "Global"
    ]

    enabled = store.set_enabled(
        True,
        scope="project",
        scope_key="alpha",
    )
    assert enabled.enabled is True


def test_instruction_scope_validation(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")

    with pytest.raises(ValueError, match="require a scope key"):
        store.set("Project", scope="project")
    with pytest.raises(ValueError, match="cannot have a scope key"):
        store.set("Global", scope="global", scope_key="not-allowed")
    with pytest.raises(ValueError, match="cannot be empty"):
        store.set("   ")


def test_composition_preserves_provenance_and_session_last(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    store.set("Global")
    store.set("Project", scope="project", scope_key="alpha")
    context = InstructionContext(
        project_key="alpha",
        session_instructions="Temporary",
    )

    contributions = instruction_contributions(
        store.resolve(context),
        session_instructions=context.session_instructions,
    )
    rendered = render_instruction_contributions(contributions)

    assert [(item.scope, item.content) for item in contributions] == [
        ("global", "Global"),
        ("project", "Project"),
        ("session", "Temporary"),
    ]
    assert rendered == (
        "[global]\nGlobal\n\n"
        "[project:alpha]\nProject\n\n"
        "[session]\nTemporary"
    )


def test_conversation_runtime_composes_rendered_user_instructions() -> None:
    provider = RecordingProvider()
    runtime = ConversationRuntime(
        provider,
        system_prompt="Fixed Ally behavior.",
        user_instructions="[global]\nUse terse bullet points.",
    )

    runtime.respond("Question")

    assert provider.last_request is not None
    system = provider.last_request.messages[0]
    assert system.role == "system"
    assert system.content == (
        "Fixed Ally behavior.\n\n"
        "User instructions:\n[global]\nUse terse bullet points."
    )


def test_instructions_parser_supports_scopes_and_session_chat() -> None:
    parser = build_parser()

    set_value = parser.parse_args(
        [
            "instructions",
            "set",
            "Project rules",
            "--scope",
            "project",
            "--key",
            "alpha",
        ]
    )
    resolve = parser.parse_args(
        [
            "instructions",
            "resolve",
            "--project",
            "alpha",
            "--session",
            "Temporary",
        ]
    )
    chat = parser.parse_args(
        [
            "chat",
            "--instruction-project",
            "alpha",
            "--instruction-task",
            "task-1",
            "--session-instructions",
            "Temporary",
        ]
    )

    assert set_value.scope == "project"
    assert set_value.key == "alpha"
    assert resolve.project == "alpha"
    assert resolve.session == "Temporary"
    assert chat.instruction_project == "alpha"
    assert chat.instruction_task == "task-1"
    assert chat.session_instructions == "Temporary"


def test_instruction_commands_manage_private_scoped_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert main(["instructions", "set", "Global"]) == 0
    capsys.readouterr()
    assert main(
        [
            "instructions",
            "set",
            "Project",
            "--scope",
            "project",
            "--key",
            "alpha",
        ]
    ) == 0
    capsys.readouterr()

    assert main(["instructions", "list"]) == 0
    listed = capsys.readouterr().out
    assert "[global] enabled" in listed
    assert "[project:alpha] enabled" in listed

    assert main(
        [
            "instructions",
            "resolve",
            "--project",
            "alpha",
            "--session",
            "Temporary",
        ]
    ) == 0
    resolved = capsys.readouterr().out
    assert "[global]\nGlobal" in resolved
    assert "[project:alpha]\nProject" in resolved
    assert "[session]\nTemporary" in resolved

    assert main(
        [
            "instructions",
            "disable",
            "--scope",
            "project",
            "--key",
            "alpha",
        ]
    ) == 0
    assert "disabled" in capsys.readouterr().out

    assert main(
        [
            "instructions",
            "show",
            "--scope",
            "project",
            "--key",
            "alpha",
        ]
    ) == 0
    assert "disabled" in capsys.readouterr().out

    assert main(
        [
            "instructions",
            "clear",
            "--scope",
            "project",
            "--key",
            "alpha",
        ]
    ) == 0
    assert "cleared" in capsys.readouterr().out


def test_instruction_commands_fail_cleanly_without_required_scope_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert main(
        ["instructions", "set", "Project", "--scope", "project"]
    ) == 2
    assert "require a scope key" in capsys.readouterr().out
