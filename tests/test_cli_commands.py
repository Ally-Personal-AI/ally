"""End-to-end coverage for the human-facing command composition layer."""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ally.cli import main
from ally.commands._storage import build_conversation_store
from ally.conversations import NewConversationMessage


@pytest.fixture(autouse=True)
def isolated_user_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep command tests away from the developer's real Ally state."""

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def invoke(
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    *,
    expected: int = 0,
) -> str:
    result = main(argv)
    captured = capsys.readouterr()
    assert result == expected, captured.out + captured.err
    return captured.out


def output_uuid(output: str, *, prefix: str = "") -> str:
    match = re.search(
        rf"{re.escape(prefix)}([0-9a-f]{{8}}-[0-9a-f]{{4}}-"
        r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        output,
    )
    assert match is not None, output
    UUID(match.group(1))
    return match.group(1)


def test_environment_configuration_evals_and_hardware_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert "Ally" in invoke(capsys, ["doctor"])
    assert "config.json" in invoke(capsys, ["config", "path"])
    assert '"schema_version": 1' in invoke(capsys, ["config", "show"])
    assert "config.json" in invoke(capsys, ["config", "init"])
    assert "Configuration validation: ok" in invoke(
        capsys,
        ["config", "validate"],
    )
    assert "Config error:" in invoke(
        capsys,
        ["config", "init"],
        expected=2,
    )

    summary = invoke(
        capsys,
        ["eval", "run", "--json"],
    )
    assert '"failed": 0' in summary

    profile = invoke(capsys, ["validate", "hardware", "--json"])
    assert '"python_version"' in profile

    assert "Local-first personal AI" in invoke(capsys, [])


def test_private_inference_commands_reject_remote_endpoints(
    capsys: pytest.CaptureFixture[str],
) -> None:
    remote = "https://example.com/v1"

    for arguments in (
        ["chat", "--model", "example", "--endpoint", remote, "--prompt", "Private"],
        [
            "memory",
            "propose",
            "Private source text.",
            "--model",
            "example",
            "--endpoint",
            remote,
        ],
        [
            "plan",
            "propose",
            "--model",
            "example",
            "--endpoint",
            remote,
            "--goal",
            "Private goal",
        ],
    ):
        output = invoke(capsys, arguments, expected=2)
        assert "loopback-only" in output


def test_memory_knowledge_and_conversation_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert "No memories." in invoke(capsys, ["memory", "list"])
    assert "No matching memories." in invoke(
        capsys,
        ["memory", "search", "missing"],
    )

    memory_id = output_uuid(invoke(capsys, ["memory", "remember", "Prefers green tea."]))
    assert "Prefers green tea." in invoke(
        capsys,
        ["memory", "show", memory_id],
    )
    assert "Prefers green tea." in invoke(
        capsys,
        ["memory", "search", "green"],
    )
    assert memory_id in invoke(capsys, ["memory", "list"])

    replacement_id = output_uuid(
        invoke(
            capsys,
            ["memory", "supersede", memory_id, "Prefers jasmine tea."],
        )
    )
    assert f"Superseded by: {replacement_id}" in invoke(
        capsys,
        ["memory", "show", memory_id],
    )
    assert replacement_id in invoke(
        capsys,
        ["memory", "retract", replacement_id],
    )
    assert "Retracted:" in invoke(
        capsys,
        ["memory", "show", replacement_id],
    )
    assert "Invalid memory ID" in invoke(
        capsys,
        ["memory", "show", "not-a-uuid"],
        expected=2,
    )
    assert "Memory not found" in invoke(
        capsys,
        ["memory", "show", str(uuid4())],
        expected=2,
    )

    assert "No knowledge sources." in invoke(capsys, ["knowledge", "list"])
    assert "No matching knowledge." in invoke(
        capsys,
        ["knowledge", "search", "missing"],
    )
    note = tmp_path / "greenhouse.txt"
    note.write_text(
        "The greenhouse uses drip irrigation and grows basil.\n",
        encoding="utf-8",
    )
    source_id = output_uuid(
        invoke(capsys, ["knowledge", "ingest", str(note)]),
        prefix="Source: ",
    )
    assert "greenhouse.txt" in invoke(capsys, ["knowledge", "list"])
    assert "Current chunks:" in invoke(
        capsys,
        ["knowledge", "show", source_id],
    )
    assert "drip irrigation" in invoke(
        capsys,
        ["knowledge", "search", "irrigation"],
    )
    assert "Invalid knowledge source ID" in invoke(
        capsys,
        ["knowledge", "show", "bad-id"],
        expected=2,
    )

    assert "No conversations." in invoke(capsys, ["conversations", "list"])
    conversation_store = build_conversation_store()
    conversation = conversation_store.create(title="Command smoke test")
    conversation_store.append_messages(
        conversation.id,
        (
            NewConversationMessage(role="user", content="Hello"),
            NewConversationMessage(role="assistant", content="Hi"),
        ),
    )
    assert "Command smoke test" in invoke(capsys, ["conversations", "list"])
    shown = invoke(capsys, ["conversations", "show", str(conversation.id)])
    assert "user: Hello" in shown
    assert "assistant: Hi" in shown
    assert "Invalid conversation ID" in invoke(
        capsys,
        ["conversations", "show", "bad-id"],
        expected=2,
    )


def test_event_schedule_source_attention_and_service_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert "No events." in invoke(capsys, ["events", "list"])
    assert "valid JSON" in invoke(
        capsys,
        ["events", "emit", "bad.event", "--payload", "{"],
        expected=2,
    )
    assert "JSON object" in invoke(
        capsys,
        ["events", "emit", "bad.event", "--payload", "[]"],
        expected=2,
    )

    event_id = output_uuid(
        invoke(
            capsys,
            [
                "events",
                "emit",
                "system.alert",
                "--importance",
                "critical",
                "--payload",
                '{"summary":"Synthetic alert"}',
            ],
        ),
        prefix="Event: ",
    )
    assert event_id in invoke(capsys, ["events", "list", "--pending"])
    assert "Synthetic alert" in invoke(capsys, ["events", "show", event_id])
    assert event_id in invoke(capsys, ["attention", "pending"])
    assert "Delivery attempts: 1" in invoke(capsys, ["attention", "deliver"])
    assert event_id in invoke(capsys, ["attention", "history"])
    assert event_id in invoke(capsys, ["events", "handle", event_id])
    assert "Invalid event ID" in invoke(
        capsys,
        ["events", "show", "bad-id"],
        expected=2,
    )

    assert "No schedules." in invoke(capsys, ["schedules", "list"])
    schedule_id = output_uuid(
        invoke(
            capsys,
            [
                "schedules",
                "create",
                "--name",
                "Daily synthetic",
                "--event-type",
                "synthetic.daily",
                "--at",
                "2026-01-01T12:00:00+00:00",
                "--every-seconds",
                "300",
                "--payload",
                '{"kind":"test"}',
            ],
        )
    )
    assert "Daily synthetic" in invoke(capsys, ["schedules", "list"])
    assert "Interval seconds: 300" in invoke(
        capsys,
        ["schedules", "show", schedule_id],
    )
    assert "disabled" in invoke(
        capsys,
        ["schedules", "disable", schedule_id],
    )
    assert "enabled" in invoke(
        capsys,
        ["schedules", "enable", schedule_id],
    )
    assert "event=" in invoke(
        capsys,
        ["schedules", "tick", "--at", "2026-01-01T12:10:00+00:00"],
    )

    assert "No event-source checkpoints." in invoke(
        capsys,
        ["sources", "checkpoints"],
    )
    observations = tmp_path / "observations.jsonl"
    observations.write_text(
        json.dumps(
            {
                "external_id": "external-1",
                "event_type": "external.changed",
                "importance": "important",
                "payload": {"name": "synthetic"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert "Published: 1" in invoke(
        capsys,
        [
            "sources",
            "poll-jsonl",
            "--source-id",
            "synthetic.source",
            str(observations),
            "--at",
            "2026-01-01T13:00:00+00:00",
        ],
    )
    assert "synthetic.source" in invoke(capsys, ["sources", "checkpoints"])
    assert "Successful polls: 1" in invoke(
        capsys,
        ["sources", "checkpoint", "synthetic.source"],
    )

    watched = tmp_path / "watched"
    watched.mkdir()
    assert "Published: 0" in invoke(
        capsys,
        [
            "sources",
            "poll-filesystem",
            "--source-id",
            "files.watched",
            str(watched),
            "--importance",
            "important",
        ],
    )
    (watched / "new.txt").write_text("PRIVATE-CONTENT", encoding="utf-8")
    filesystem_report = invoke(
        capsys,
        [
            "sources",
            "poll-filesystem",
            "--source-id",
            "files.watched",
            str(watched),
            "--importance",
            "important",
            "--json",
        ],
    )
    assert '"event_type"' not in filesystem_report
    assert '"type": "filesystem.created"' in filesystem_report
    assert "PRIVATE-CONTENT" not in filesystem_report

    assert "No service leases." in invoke(capsys, ["service", "leases"])
    assert '"status": "succeeded"' in invoke(
        capsys,
        [
            "service",
            "cycle",
            "--at",
            "2026-01-01T13:00:00+00:00",
            "--sink",
            "console",
            "--json",
        ],
    )
    assert '"status": "succeeded"' in invoke(
        capsys,
        ["service", "history", "--json"],
    )
    health_result = main(["service", "health", "--json"])
    health = capsys.readouterr().out
    assert health_result in (0, 1)
    assert '"checks"' in health


def test_tools_tasks_data_and_skill_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert "system.info" in invoke(capsys, ["tools", "list"])
    assert "Status: succeeded" in invoke(
        capsys,
        ["tools", "run", "system.info"],
    )
    assert "system.info" in invoke(capsys, ["tools", "audit"])
    assert "valid JSON" in invoke(
        capsys,
        ["tools", "run", "system.info", "--arguments", "{"],
        expected=2,
    )

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "goal": "Inspect the local runtime",
                "steps": [{"tool_name": "system.info", "arguments": {}}],
            }
        ),
        encoding="utf-8",
    )
    task_output = invoke(capsys, ["tasks", "create", str(plan_path)])
    task_id = output_uuid(task_output, prefix="Task: ")
    step_id = output_uuid(task_output)
    assert "Inspect the local runtime" in invoke(capsys, ["tasks", "list"])
    assert "Steps:" in invoke(capsys, ["tasks", "show", task_id])
    assert "Status: succeeded" in invoke(capsys, ["tasks", "run", task_id])
    assert "Task retry error" in invoke(
        capsys,
        ["tasks", "retry", task_id, step_id],
        expected=2,
    )

    archive = tmp_path / "ally.ally-backup"
    restored = tmp_path / "restored.sqlite3"
    assert "Archive:" in invoke(capsys, ["data", "backup", str(archive)])
    assert "Backup validation: ok" in invoke(
        capsys,
        ["data", "validate", str(archive)],
    )
    assert str(restored) in invoke(
        capsys,
        [
            "data",
            "restore",
            str(archive),
            "--destination",
            str(restored),
        ],
    )

    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "skill.toml").write_text(
        "\n".join(
            (
                'id = "sample.skill"',
                'name = "Sample Skill"',
                'version = "1.0.0"',
                'description = "Synthetic command test skill."',
                'entrypoint = "skill_code:run"',
                'execution = "python_subprocess_v1"',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (skill / "skill_code.py").write_text(
        "def run(data):\n    return {'echo': data.get('value')}\n",
        encoding="utf-8",
    )

    assert "Skill: sample.skill" in invoke(
        capsys,
        ["skills", "inspect", str(skill)],
    )
    assert "manifest is valid" in invoke(
        capsys,
        ["skills", "validate", str(skill)],
    )
    assert "Installed sample.skill@1.0.0" in invoke(
        capsys,
        ["skills", "install", str(skill)],
    )
    assert "disabled" in invoke(capsys, ["skills", "installed"])
    assert "Enabled sample.skill@1.0.0" in invoke(
        capsys,
        ["skills", "enable", "sample.skill", "1.0.0"],
    )
    assert '"echo": 7' in invoke(
        capsys,
        [
            "skills",
            "run",
            "sample.skill",
            "1.0.0",
            "--input",
            '{"value":7}',
        ],
    )
    assert "sample.skill@1.0.0" in invoke(capsys, ["skills", "audit"])
    assert "Disabled sample.skill@1.0.0" in invoke(
        capsys,
        ["skills", "disable", "sample.skill", "1.0.0"],
    )
    assert "Uninstalled sample.skill@1.0.0" in invoke(
        capsys,
        ["skills", "uninstall", "sample.skill", "1.0.0"],
    )
