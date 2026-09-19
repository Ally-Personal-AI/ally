"""Secret-store abstraction independent of any operating-system backend."""

from __future__ import annotations

from typing import Protocol

from pydantic import SecretStr

from ally.secrets.models import SecretRef


class SecretStoreError(RuntimeError):
    """Base error for secret-store operations.

    Error messages must never contain secret values or raw backend diagnostics.
    """


class SecretStoreUnavailableError(SecretStoreError):
    """Raised when the platform secret store cannot be used safely."""


class SecretStore(Protocol):
    """Backend contract for credentials and other secret values."""

    def set(self, name: str, value: SecretStr) -> None:
        ...

    def get(self, name: str) -> SecretStr | None:
        ...

    def delete(self, name: str) -> bool:
        ...

    def list_names(self) -> tuple[str, ...]:
        ...


class InMemorySecretStore:
    """Ephemeral backend for tests and development only."""

    def __init__(self) -> None:
        self._values: dict[str, SecretStr] = {}

    def set(self, name: str, value: SecretStr) -> None:
        validated = SecretRef(name=name)
        self._values[validated.name] = value

    def get(self, name: str) -> SecretStr | None:
        validated = SecretRef(name=name)
        return self._values.get(validated.name)

    def delete(self, name: str) -> bool:
        validated = SecretRef(name=name)
        return self._values.pop(validated.name, None) is not None

    def list_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._values))


def resolve_secret(reference: SecretRef, store: SecretStore) -> SecretStr:
    """Resolve one opaque secret reference or fail closed."""

    value = store.get(reference.name)
    if value is None:
        raise KeyError(f"secret not found: {reference.name}")
    return value
