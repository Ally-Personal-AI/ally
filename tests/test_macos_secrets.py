from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import pytest
from pydantic import SecretStr

from ally.secrets.macos import (
    KeychainCommandResult,
    MacOSKeychainSecretStore,
    SubprocessKeychainCommandRunner,
)
from ally.secrets.store import SecretStoreUnavailableError


@dataclass
class FakeKeychainRunner:
    items: dict[tuple[str, str], str] = field(default_factory=lambda: {})
    calls: list[tuple[tuple[str, ...], str | None]] = field(
        default_factory=lambda: []
    )
    failures: list[tuple[str, str, KeychainCommandResult]] = field(
        default_factory=lambda: []
    )

    def fail_once(
        self,
        *,
        operation: str,
        service: str,
        stderr: str = "interaction not allowed",
    ) -> None:
        self.failures.append(
            (
                operation,
                service,
                KeychainCommandResult(returncode=51, stdout="", stderr=stderr),
            )
        )

    def run(
        self,
        arguments: tuple[str, ...],
        *,
        input_text: str | None = None,
    ) -> KeychainCommandResult:
        self.calls.append((arguments, input_text))
        operation = arguments[1]
        account = arguments[arguments.index("-a") + 1]
        service = arguments[arguments.index("-s") + 1]

        for index, (failed_operation, failed_service, result) in enumerate(
            self.failures
        ):
            if operation == failed_operation and service == failed_service:
                self.failures.pop(index)
                return result

        key = (service, account)
        if operation == "find-generic-password":
            value = self.items.get(key)
            if value is None:
                return KeychainCommandResult(
                    returncode=44,
                    stdout="",
                    stderr="The specified item could not be found in the keychain.",
                )
            return KeychainCommandResult(
                returncode=0,
                stdout=f"{value}\n",
                stderr="",
            )
        if operation == "add-generic-password":
            assert arguments[-1] == "-w"
            assert input_text is not None
            self.items[key] = input_text.removesuffix("\n")
            return KeychainCommandResult(returncode=0, stdout="", stderr="")
        if operation == "delete-generic-password":
            if self.items.pop(key, None) is None:
                return KeychainCommandResult(
                    returncode=44,
                    stdout="",
                    stderr="errSecItemNotFound",
                )
            return KeychainCommandResult(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected Keychain operation: {operation}")


def build_store(runner: FakeKeychainRunner) -> MacOSKeychainSecretStore:
    return MacOSKeychainSecretStore(
        runner=runner,
        platform_name="darwin",
        service="test.ally.secrets",
        executable="/synthetic/security",
    )


def test_keychain_store_round_trip_lists_updates_and_deletes() -> None:
    runner = FakeKeychainRunner()
    store = build_store(runner)
    secret_value = "first line\nsecond line λ"

    store.set("service.beta", SecretStr(secret_value))
    store.set("service.alpha", SecretStr("alpha-value"))
    store.set("service.beta", SecretStr("replacement"))

    loaded = store.get("service.beta")
    assert loaded is not None
    assert loaded.get_secret_value() == "replacement"
    assert store.list_names() == ("service.alpha", "service.beta")
    assert store.delete("service.beta") is True
    assert store.delete("service.beta") is False
    assert store.get("service.beta") is None
    assert store.list_names() == ("service.alpha",)

    command_arguments = "\n".join(" ".join(arguments) for arguments, _ in runner.calls)
    assert secret_value not in command_arguments
    assert "alpha-value" not in command_arguments
    assert "replacement" not in command_arguments
    assert all(
        arguments[0] == "/synthetic/security" for arguments, _ in runner.calls
    )


def test_keychain_store_fails_closed_on_locked_or_denied_backend() -> None:
    runner = FakeKeychainRunner()
    runner.fail_once(
        operation="find-generic-password",
        service="test.ally.secrets.index",
        stderr="locked backend containing synthetic-secret-value",
    )
    store = build_store(runner)

    with pytest.raises(SecretStoreUnavailableError) as raised:
        store.list_names()

    assert "synthetic-secret-value" not in str(raised.value)
    assert "unavailable" in str(raised.value)


def test_keychain_set_rolls_back_when_reference_index_update_fails() -> None:
    runner = FakeKeychainRunner()
    store = build_store(runner)
    runner.fail_once(
        operation="add-generic-password",
        service="test.ally.secrets.index",
    )

    with pytest.raises(SecretStoreUnavailableError):
        store.set("service.token", SecretStr("new-value"))

    assert ("test.ally.secrets", "service.token") not in runner.items


def test_keychain_update_and_delete_restore_previous_value_on_index_failure() -> None:
    runner = FakeKeychainRunner()
    store = build_store(runner)
    store.set("service.token", SecretStr("original"))

    runner.fail_once(
        operation="add-generic-password",
        service="test.ally.secrets.index",
    )
    with pytest.raises(SecretStoreUnavailableError):
        store.set("service.token", SecretStr("replacement"))
    loaded = store.get("service.token")
    assert loaded is not None
    assert loaded.get_secret_value() == "original"

    runner.fail_once(
        operation="add-generic-password",
        service="test.ally.secrets.index",
    )
    with pytest.raises(SecretStoreUnavailableError):
        store.delete("service.token")
    loaded = store.get("service.token")
    assert loaded is not None
    assert loaded.get_secret_value() == "original"
    assert store.list_names() == ("service.token",)


def test_keychain_store_rejects_corrupt_item_and_index_data() -> None:
    runner = FakeKeychainRunner()
    store = build_store(runner)
    runner.items[("test.ally.secrets", "service.token")] = "not-an-ally-item"

    with pytest.raises(SecretStoreUnavailableError, match="invalid format"):
        store.get("service.token")

    runner.items[("test.ally.secrets.index", "references")] = "not-an-index"
    with pytest.raises(SecretStoreUnavailableError, match="invalid"):
        store.list_names()


def test_keychain_store_is_unavailable_off_macos() -> None:
    with pytest.raises(SecretStoreUnavailableError, match="unavailable"):
        MacOSKeychainSecretStore(platform_name="linux")


def test_subprocess_runner_redacts_spawn_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("synthetic-secret-value")

    monkeypatch.setattr(subprocess, "run", fail_run)
    runner = SubprocessKeychainCommandRunner()

    with pytest.raises(SecretStoreUnavailableError) as raised:
        runner.run(("/usr/bin/security", "example"), input_text="synthetic-secret-value")

    assert "synthetic-secret-value" not in str(raised.value)
