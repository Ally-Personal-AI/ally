from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from ally.secrets.macos import MacOSKeychainSecretStore
from ally.secrets.macos_native import SecurityFrameworkKeychainBackend
from ally.secrets.store import SecretStoreUnavailableError


@dataclass
class FakeKeychainBackend:
    items: dict[tuple[str, str], bytes] = field(default_factory=lambda: {})
    failures: list[tuple[str, str]] = field(default_factory=lambda: [])

    def fail_once(self, *, operation: str, service: str) -> None:
        self.failures.append((operation, service))

    def _check_failure(self, *, operation: str, service: str) -> None:
        for index, failure in enumerate(self.failures):
            if failure == (operation, service):
                self.failures.pop(index)
                raise SecretStoreUnavailableError(
                    "macOS Keychain is unavailable or denied access"
                )

    def get(self, *, account: str, service: str) -> bytes | None:
        self._check_failure(operation="get", service=service)
        return self.items.get((service, account))

    def set(self, *, account: str, service: str, value: bytes) -> None:
        self._check_failure(operation="set", service=service)
        self.items[(service, account)] = value

    def delete(self, *, account: str, service: str) -> bool:
        self._check_failure(operation="delete", service=service)
        return self.items.pop((service, account), None) is not None


def build_store(backend: FakeKeychainBackend) -> MacOSKeychainSecretStore:
    return MacOSKeychainSecretStore(
        backend=backend,
        platform_name="darwin",
        service="test.ally.secrets",
    )


def test_keychain_store_round_trip_lists_updates_and_deletes() -> None:
    backend = FakeKeychainBackend()
    store = build_store(backend)

    store.set("service.beta", SecretStr("first line\nsecond line λ"))
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

    stored_payloads = tuple(backend.items.values())
    assert all(b"first line\nsecond line" not in value for value in stored_payloads)
    assert all(b"alpha-value" not in value for value in stored_payloads)
    assert all(b"replacement" not in value for value in stored_payloads)


def test_keychain_store_fails_closed_on_locked_or_denied_backend() -> None:
    backend = FakeKeychainBackend()
    backend.fail_once(operation="get", service="test.ally.secrets.index")
    store = build_store(backend)

    with pytest.raises(SecretStoreUnavailableError) as raised:
        store.list_names()

    assert "unavailable" in str(raised.value)


def test_keychain_set_rolls_back_when_reference_index_update_fails() -> None:
    backend = FakeKeychainBackend()
    store = build_store(backend)
    backend.fail_once(operation="set", service="test.ally.secrets.index")

    with pytest.raises(SecretStoreUnavailableError):
        store.set("service.token", SecretStr("new-value"))

    assert ("test.ally.secrets", "service.token") not in backend.items


def test_keychain_update_and_delete_restore_previous_value_on_index_failure() -> None:
    backend = FakeKeychainBackend()
    store = build_store(backend)
    store.set("service.token", SecretStr("original"))

    backend.fail_once(operation="set", service="test.ally.secrets.index")
    with pytest.raises(SecretStoreUnavailableError):
        store.set("service.token", SecretStr("replacement"))
    loaded = store.get("service.token")
    assert loaded is not None
    assert loaded.get_secret_value() == "original"

    backend.fail_once(operation="set", service="test.ally.secrets.index")
    with pytest.raises(SecretStoreUnavailableError):
        store.delete("service.token")
    loaded = store.get("service.token")
    assert loaded is not None
    assert loaded.get_secret_value() == "original"
    assert store.list_names() == ("service.token",)


def test_keychain_store_rejects_corrupt_item_and_index_data() -> None:
    backend = FakeKeychainBackend()
    store = build_store(backend)
    backend.items[("test.ally.secrets", "service.token")] = b"not-an-ally-item"

    with pytest.raises(SecretStoreUnavailableError, match="invalid format"):
        store.get("service.token")

    backend.items[("test.ally.secrets.index", "references")] = b"not-an-index"
    with pytest.raises(SecretStoreUnavailableError, match="invalid"):
        store.list_names()


def test_keychain_store_and_native_backend_are_unavailable_off_macos() -> None:
    with pytest.raises(SecretStoreUnavailableError, match="unavailable"):
        MacOSKeychainSecretStore(platform_name="linux")
    with pytest.raises(SecretStoreUnavailableError, match="unavailable"):
        SecurityFrameworkKeychainBackend(platform_name="linux")


def test_native_backend_redacts_framework_load_failures(tmp_path: Path) -> None:
    secret_marker = "synthetic-secret-in-missing-path"

    with pytest.raises(SecretStoreUnavailableError) as raised:
        SecurityFrameworkKeychainBackend(
            platform_name="darwin",
            security_framework=tmp_path / secret_marker,
            core_foundation_framework=tmp_path / "missing-core",
        )

    assert secret_marker not in str(raised.value)


def test_native_adapter_has_no_subprocess_secret_transport() -> None:
    sources = (
        Path("src/ally/secrets/macos.py").read_text(encoding="utf-8"),
        Path("src/ally/secrets/macos_native.py").read_text(encoding="utf-8"),
    )

    imported_modules = {
        alias.name
        for source in sources
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "subprocess" not in imported_modules
    assert all("/usr/bin/security" not in source for source in sources)
    assert "SecItemCopyMatching" in sources[1]
    assert "SecItemAdd" in sources[1]
    assert "SecItemUpdate" in sources[1]
    assert "SecItemDelete" in sources[1]


@pytest.mark.skipif(sys.platform != "darwin", reason="requires Apple frameworks")
def test_native_backend_round_trip_on_ephemeral_macos_runner() -> None:
    backend = SecurityFrameworkKeychainBackend()
    service = f"ai.ally.ci.synthetic.{uuid4()}"
    account = "ci-probe"
    value = b"synthetic-ci-secret"

    try:
        assert backend.get(account=account, service=service) is None
        backend.set(account=account, service=service, value=value)
        assert backend.get(account=account, service=service) == value
    finally:
        backend.delete(account=account, service=service)

    assert backend.get(account=account, service=service) is None
