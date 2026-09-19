"""macOS Keychain implementation of Ally's secret-store contract."""

from __future__ import annotations

import base64
import json
import sys
from typing import Protocol, cast

from pydantic import SecretStr, ValidationError

from ally.secrets.macos_native import SecurityFrameworkKeychainBackend
from ally.secrets.models import SecretRef
from ally.secrets.store import SecretStoreUnavailableError

DEFAULT_KEYCHAIN_SERVICE = "ai.ally.secrets.v1"
_INDEX_SERVICE_SUFFIX = ".index"
_INDEX_ACCOUNT = "references"
_VALUE_PREFIX = b"ally-secret-v1:"


class KeychainBackend(Protocol):
    """Small byte-oriented boundary around an operating-system Keychain API."""

    def get(self, *, account: str, service: str) -> bytes | None:
        ...

    def set(self, *, account: str, service: str, value: bytes) -> None:
        ...

    def delete(self, *, account: str, service: str) -> bool:
        ...


def _encode_value(value: str) -> bytes:
    payload = base64.urlsafe_b64encode(value.encode("utf-8"))
    return _VALUE_PREFIX + payload


def _decode_value(value: bytes) -> str:
    if not value.startswith(_VALUE_PREFIX):
        raise SecretStoreUnavailableError("macOS Keychain item has an invalid format")
    encoded = value.removeprefix(_VALUE_PREFIX)
    try:
        return base64.b64decode(
            encoded,
            altchars=b"-_",
            validate=True,
        ).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        raise SecretStoreUnavailableError(
            "macOS Keychain item has an invalid format"
        ) from None


class MacOSKeychainSecretStore:
    """Store Ally secret values in the current user's default Keychain.

    Values cross a direct Apple Security-framework boundary and never enter a
    subprocess, command argument, environment variable, config file, or Ally
    database. A separate Keychain item stores only sorted opaque references.
    """

    def __init__(
        self,
        *,
        backend: KeychainBackend | None = None,
        platform_name: str | None = None,
        service: str = DEFAULT_KEYCHAIN_SERVICE,
    ) -> None:
        current_platform = sys.platform if platform_name is None else platform_name
        if current_platform != "darwin":
            raise SecretStoreUnavailableError(
                "the macOS Keychain backend is unavailable on this platform"
            )
        if not service:
            raise ValueError("Keychain service must be non-empty")
        self._backend = backend or SecurityFrameworkKeychainBackend()
        self._service = service
        self._index_service = f"{service}{_INDEX_SERVICE_SUFFIX}"

    def _load_index(self) -> tuple[str, ...]:
        raw = self._backend.get(
            account=_INDEX_ACCOUNT,
            service=self._index_service,
        )
        if raw is None:
            return ()
        try:
            parsed: object = json.loads(_decode_value(raw))
            if not isinstance(parsed, list):
                raise ValueError
            raw_items = cast(list[object], parsed)
            if not all(isinstance(name, str) for name in raw_items):
                raise ValueError
            raw_names = cast(list[str], raw_items)
            validated = tuple(SecretRef(name=name).name for name in raw_names)
        except (ValueError, ValidationError):
            raise SecretStoreUnavailableError(
                "macOS Keychain secret-reference index is invalid"
            ) from None
        if validated != tuple(sorted(set(validated))):
            raise SecretStoreUnavailableError(
                "macOS Keychain secret-reference index is invalid"
            )
        return validated

    def _save_index(self, names: tuple[str, ...]) -> None:
        serialized = json.dumps(names, separators=(",", ":"))
        self._backend.set(
            account=_INDEX_ACCOUNT,
            service=self._index_service,
            value=_encode_value(serialized),
        )

    def set(self, name: str, value: SecretStr) -> None:
        validated = SecretRef(name=name)
        names = self._load_index()
        previous = self._backend.get(
            account=validated.name,
            service=self._service,
        )
        if previous is not None:
            _decode_value(previous)

        self._backend.set(
            account=validated.name,
            service=self._service,
            value=_encode_value(value.get_secret_value()),
        )
        updated_names = tuple(sorted({*names, validated.name}))
        try:
            self._save_index(updated_names)
        except SecretStoreUnavailableError:
            try:
                if previous is None:
                    self._backend.delete(
                        account=validated.name,
                        service=self._service,
                    )
                else:
                    self._backend.set(
                        account=validated.name,
                        service=self._service,
                        value=previous,
                    )
            except SecretStoreUnavailableError:
                raise SecretStoreUnavailableError(
                    "macOS Keychain update failed and rollback could not be confirmed"
                ) from None
            raise

    def get(self, name: str) -> SecretStr | None:
        validated = SecretRef(name=name)
        raw = self._backend.get(
            account=validated.name,
            service=self._service,
        )
        if raw is None:
            return None
        return SecretStr(_decode_value(raw))

    def delete(self, name: str) -> bool:
        validated = SecretRef(name=name)
        names = self._load_index()
        previous = self._backend.get(
            account=validated.name,
            service=self._service,
        )
        if previous is None:
            if validated.name in names:
                self._save_index(tuple(item for item in names if item != validated.name))
            return False
        _decode_value(previous)

        if not self._backend.delete(
            account=validated.name,
            service=self._service,
        ):
            raise SecretStoreUnavailableError(
                "macOS Keychain changed during deletion"
            )
        try:
            self._save_index(tuple(item for item in names if item != validated.name))
        except SecretStoreUnavailableError:
            try:
                self._backend.set(
                    account=validated.name,
                    service=self._service,
                    value=previous,
                )
            except SecretStoreUnavailableError:
                raise SecretStoreUnavailableError(
                    "macOS Keychain deletion failed and rollback could not be confirmed"
                ) from None
            raise
        return True

    def list_names(self) -> tuple[str, ...]:
        return self._load_index()


def build_system_secret_store() -> MacOSKeychainSecretStore:
    """Build the supported secret store for the current operating system."""

    return MacOSKeychainSecretStore()
