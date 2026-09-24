from pathlib import Path

import pytest

import ally.commands.chat as chat_module
from ally.commands.chat import run_chat
from ally.runtime_profiles import InferenceTargetError
from ally.security.network import private_grounding_allowed


def test_private_context_is_allowed_for_loopback() -> None:
    assert private_grounding_allowed(
        "http://127.0.0.1:8080/v1",
        allow_remote_private_context=False,
    )


def test_private_context_is_denied_for_remote() -> None:
    assert not private_grounding_allowed(
        "https://example.com/v1",
        allow_remote_private_context=False,
    )


def test_legacy_remote_private_context_opt_in_fails_closed() -> None:
    assert not private_grounding_allowed(
        "https://example.com/v1",
        allow_remote_private_context=True,
    )


def test_private_chat_rejects_remote_endpoint_before_inference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    result = run_chat(
        development_endpoint="https://example.com/v1",
        development_model="remote-model",
        prompt="Private prompt that must not leave Ally.",
        conversation_id=None,
    )

    output = capsys.readouterr().out
    assert result == 2
    assert "development inference override" in output



def test_chat_target_failure_precedes_private_state_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_target(**_: object) -> object:
        raise InferenceTargetError(
            "active validated runtime profile is unavailable or invalid"
        )

    def forbidden_store() -> object:
        raise AssertionError("conversation store must not be opened")

    monkeypatch.setattr(chat_module, "resolve_inference_target", fail_target)
    monkeypatch.setattr(chat_module, "build_conversation_store", forbidden_store)

    result = chat_module.run_chat(
        development_endpoint=None,
        development_model=None,
        prompt="Private prompt.",
        conversation_id=None,
    )

    assert result == 2
    assert "Inference target error:" in capsys.readouterr().out
