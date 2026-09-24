from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory as RealTemporaryDirectory

import pytest

from ally.commands import validate as validate_commands
from ally.diagnostics import run_isolated_synthetic_workflows
from ally.diagnostics import workflows as workflow_module
from ally.models import ChatRequest, ChatResponse


class DeterministicWorkflowProvider:
    @property
    def name(self) -> str:
        return "synthetic-workflow-provider"

    def __enter__(self) -> DeterministicWorkflowProvider:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def close(self) -> None:
        return None

    def chat(self, request: ChatRequest) -> ChatResponse:
        system_text = "\n".join(
            message.content
            for message in request.messages
            if message.role == "system"
        )
        user_text = request.messages[-1].content

        if "planning component" in system_text:
            content = json.dumps(
                {
                    "goal": "Inspect the synthetic validation runtime",
                    "steps": [{"tool_name": "system.info", "arguments": {}}],
                }
            )
        elif "extract durable personal memory candidates" in system_text:
            content = json.dumps(
                {
                    "memories": [
                        {
                            "kind": "preference",
                            "content": "Synthetic subject prefers jasmine tea.",
                            "confidence": 0.99,
                            "importance": 0.8,
                        }
                    ]
                }
            )
        elif "retrieved reference" in user_text:
            assert "GLASS-482" in system_text
            content = "GLASS-482"
        elif "What synthetic validation token" in user_text:
            assert any(
                "ORCHID-731" in message.content
                for message in request.messages[:-1]
            )
            content = "ORCHID-731"
        elif "Remember the synthetic validation token" in user_text:
            content = "STORED_OK"
        else:
            raise AssertionError("unexpected synthetic validation prompt")

        return ChatResponse(
            content=content,
            model="synthetic-model",
            provider=self.name,
        )


class FailingWorkflowProvider(DeterministicWorkflowProvider):
    def chat(self, request: ChatRequest) -> ChatResponse:
        raise RuntimeError("PRIVATE-SYNTHETIC-OUTPUT-MUST-NOT-LEAK")


def test_isolated_synthetic_workflows_pass_all_checks() -> None:
    report = run_isolated_synthetic_workflows(
        provider=DeterministicWorkflowProvider(),
        model="synthetic-model",
    )

    assert report.successful
    assert {check.id for check in report.checks} == {
        "conversation.persistence",
        "memory.lifecycle",
        "knowledge.grounding",
        "tool.read_only",
        "task.persistence",
        "model.planning",
        "model.memory_proposal",
        "workspace.isolation",
    }
    assert all(check.status == "passed" for check in report.checks)


def test_isolated_workflow_report_never_contains_exception_messages() -> None:
    report = run_isolated_synthetic_workflows(
        provider=FailingWorkflowProvider(),
        model="synthetic-model",
    )

    assert not report.successful
    rendered = report.model_dump_json()
    assert "PRIVATE-SYNTHETIC-OUTPUT-MUST-NOT-LEAK" not in rendered
    assert "RuntimeError" in rendered
    assert any(check.status == "passed" for check in report.checks)
    assert any(check.status == "failed" for check in report.checks)


def test_isolated_workflow_removes_temporary_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Path] = []

    def tracking_temporary_directory(*, prefix: str) -> RealTemporaryDirectory[str]:
        temporary = RealTemporaryDirectory(prefix=prefix)
        created.append(Path(temporary.name))
        return temporary

    monkeypatch.setattr(
        workflow_module,
        "TemporaryDirectory",
        tracking_temporary_directory,
    )

    report = run_isolated_synthetic_workflows(
        provider=DeterministicWorkflowProvider(),
        model="synthetic-model",
    )

    assert report.successful
    assert len(created) == 1
    assert not created[0].exists()


def test_isolated_workflow_does_not_create_default_ally_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "default-config-must-not-exist"
    data_root = tmp_path / "default-data-must-not-exist"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_root))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_root))

    report = run_isolated_synthetic_workflows(
        provider=DeterministicWorkflowProvider(),
        model="synthetic-model",
    )

    assert report.successful
    assert not config_root.exists()
    assert not data_root.exists()


def test_synthetic_workflow_command_uses_safe_summary_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        validate_commands,
        "OpenAICompatibleProvider",
        lambda **_: DeterministicWorkflowProvider(),
    )

    result = validate_commands.run_synthetic_workflow_validation(
        endpoint="http://127.0.0.1:8080/v1",
        model="synthetic-model",
        json_output=True,
    )
    output = capsys.readouterr().out
    rendered = json.loads(output)

    assert result == 0
    assert rendered["successful"] is True
    assert rendered["model"] == "synthetic-model"
    assert "ORCHID-731" not in output
    assert "GLASS-482" not in output
    assert "jasmine" not in output.lower()
