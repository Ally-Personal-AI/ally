from __future__ import annotations

import pytest

from ally.cli import main
from ally.commands import secrets as secret_commands
from ally.secrets import InMemorySecretStore, SecretStoreUnavailableError


def test_secret_cli_manages_references_without_printing_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = InMemorySecretStore()
    secret_value = "synthetic-never-print-this"

    def read_secret(prompt: str) -> str:
        return secret_value

    monkeypatch.setattr(secret_commands, "build_system_secret_store", lambda: store)
    monkeypatch.setattr(
        secret_commands.getpass,
        "getpass",
        read_secret,
    )

    assert main(["secrets", "set", "service.token"]) == 0
    assert main(["secrets", "list"]) == 0
    assert main(["secrets", "check", "service.token"]) == 0
    assert main(["secrets", "delete", "service.token"]) == 0
    assert main(["secrets", "check", "service.token"]) == 1
    assert main(["secrets", "delete", "service.token"]) == 1
    output = capsys.readouterr().out

    assert "Stored secret reference: service.token" in output
    assert "Secret reference service.token: available" in output
    assert "Secret reference service.token: missing" in output
    assert "Deleted secret reference: service.token" in output
    assert secret_value not in output


def test_secret_cli_redacts_backend_error_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unavailable() -> InMemorySecretStore:
        raise SecretStoreUnavailableError(
            "locked backend synthetic-never-print-this"
        )

    monkeypatch.setattr(secret_commands, "build_system_secret_store", unavailable)

    assert main(["secrets", "list"]) == 2
    output = capsys.readouterr().out
    assert output == "Secret store unavailable or access denied.\n"
    assert "synthetic-never-print-this" not in output


def test_secret_cli_does_not_echo_value_when_write_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FailingStore(InMemorySecretStore):
        def set(self, name: str, value: object) -> None:
            raise SecretStoreUnavailableError(
                "failed while handling synthetic-never-print-this"
            )

    secret_value = "synthetic-never-print-this"

    def read_secret(prompt: str) -> str:
        return secret_value

    monkeypatch.setattr(
        secret_commands,
        "build_system_secret_store",
        lambda: FailingStore(),
    )
    monkeypatch.setattr(
        secret_commands.getpass,
        "getpass",
        read_secret,
    )

    assert main(["secrets", "set", "service.token"]) == 2
    output = capsys.readouterr().out
    assert output == "Secret operation failed; no value was displayed.\n"
    assert secret_value not in output


def test_secret_cli_rejects_invalid_reference_before_prompting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prompted = False

    def prompt(prompt_text: str) -> str:
        nonlocal prompted
        prompted = True
        return "unused"

    monkeypatch.setattr(secret_commands.getpass, "getpass", prompt)

    assert main(["secrets", "set", "Contains Spaces"]) == 2
    assert capsys.readouterr().out == "Invalid secret reference name.\n"
    assert prompted is False
