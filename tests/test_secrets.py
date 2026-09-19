import pytest
from pydantic import SecretStr

from ally.secrets import InMemorySecretStore, SecretRef, resolve_secret


def test_secret_reference_contains_only_opaque_name() -> None:
    reference = SecretRef(name="service.api-token")

    assert reference.model_dump() == {"name": "service.api-token"}


def test_in_memory_secret_store_redacts_values() -> None:
    store = InMemorySecretStore()
    secret = SecretStr("synthetic-secret-value")

    store.set("service.api-token", secret)
    loaded = store.get("service.api-token")

    assert loaded is not None
    assert loaded.get_secret_value() == "synthetic-secret-value"
    assert str(loaded) == "**********"
    assert repr(loaded) != "synthetic-secret-value"
    assert store.list_names() == ("service.api-token",)
    assert "synthetic-secret-value" not in repr(store.list_names())


def test_resolve_secret_fails_closed_when_reference_is_missing() -> None:
    store = InMemorySecretStore()

    with pytest.raises(KeyError, match="secret not found"):
        resolve_secret(SecretRef(name="missing.secret"), store)


def test_secret_delete_returns_whether_value_existed() -> None:
    store = InMemorySecretStore()
    store.set("service.token", SecretStr("value"))

    assert store.delete("service.token") is True
    assert store.delete("service.token") is False
    assert store.get("service.token") is None


def test_in_memory_secret_store_rejects_invalid_name() -> None:
    store = InMemorySecretStore()

    with pytest.raises(ValueError):
        store.set("Contains Spaces", SecretStr("value"))
