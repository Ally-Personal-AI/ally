import pytest

from ally.commands.chat import run_chat
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
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    result = run_chat(
        endpoint="https://example.com/v1",
        model="remote-model",
        prompt="Private prompt that must not leave Ally.",
        conversation_id=None,
    )

    output = capsys.readouterr().out
    assert result == 2
    assert "loopback-only" in output
