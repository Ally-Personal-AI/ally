"""macOS Keychain implementation of Ally's secret-store contract."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Never, Protocol, cast

from pydantic import SecretStr, ValidationError

from ally.secrets.models import SecretRef
from ally.secrets.store import SecretStoreUnavailableError

DEFAULT_KEYCHAIN_SERVICE = "ai.ally.secrets.v1"
_INDEX_SERVICE_SUFFIX = ".index"
_INDEX_ACCOUNT = "references"
_VALUE_PREFIX = "ally-secret-v1:"
_NOT_FOUND_MARKERS = (
    "could not be found",
    "errsecitemnotfound",
    "-25300",
)


@dataclass(frozen=True)
class KeychainCommandResult:
    """Sanitized subprocess result used by the Keychain adapter."""

    returncode: int
    stdout: str
    stderr: str


class KeychainCommandRunner(Protocol):
    """Injectable command boundary for deterministic platform tests."""

    def run(
        self,
        arguments: tuple[str, ...],
        *,
        input_text: str | None = None,
    ) -> KeychainCommandResult:
        ...


class SubprocessKeychainCommandRunner:
    """Run Apple's security tool without a shell or secret command arguments."""

    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Keychain command timeout must be positive")
        self._timeout_seconds = timeout_seconds

    def run(
        self,
        arguments: tuple[str, ...],
        *,
        input_text: str | None = None,
    ) -> KeychainCommandResult:
        try:
            completed = subprocess.run(
                arguments,
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError):
            raise SecretStoreUnavailableError(
                "macOS Keychain is unavailable or denied access"
            ) from None

        return KeychainCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _encode_value(value: str) -> str:
    payload = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return f"{_VALUE_PREFIX}{payload}"


def _decode_value(value: str) -> str:
    if not value.startswith(_VALUE_PREFIX):
        raise SecretStoreUnavailableError("macOS Keychain item has an invalid format")
    encoded = value.removeprefix(_VALUE_PREFIX)
    try:
        return base64.b64decode(
            encoded.encode("ascii"),
            altchars=b"-_",
            validate=True,
        ).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        raise SecretStoreUnavailableError(
            "macOS Keychain item has an invalid format"
        ) from None


class MacOSKeychainSecretStore:
    """Store Ally secret values in the current user's default Keychain.

    Secret values are encoded into a single prompt-safe line and sent on stdin
    to ``security add-generic-password -w``. They are never placed in argv.
    A separate Keychain item stores only the sorted opaque reference names.
    """

    def __init__(
        self,
        *,
        runner: KeychainCommandRunner | None = None,
        platform_name: str | None = None,
        service: str = DEFAULT_KEYCHAIN_SERVICE,
        executable: str = "/usr/bin/security",
    ) -> None:
        current_platform = sys.platform if platform_name is None else platform_name
        if current_platform != "darwin":
            raise SecretStoreUnavailableError(
                "the macOS Keychain backend is unavailable on this platform"
            )
        if not service or not executable:
            raise ValueError("Keychain service and executable must be non-empty")
        self._runner = runner or SubprocessKeychainCommandRunner()
        self._service = service
        self._index_service = f"{service}{_INDEX_SERVICE_SUFFIX}"
        self._executable = executable

    def _run(
        self,
        *arguments: str,
        input_text: str | None = None,
    ) -> KeychainCommandResult:
        return self._runner.run(
            (self._executable, *arguments),
            input_text=input_text,
        )

    @staticmethod
    def _is_missing(result: KeychainCommandResult) -> bool:
        if result.returncode == 44:
            return True
        lowered = result.stderr.lower()
        return any(marker in lowered for marker in _NOT_FOUND_MARKERS)

    @staticmethod
    def _raise_backend_error() -> Never:
        raise SecretStoreUnavailableError(
            "macOS Keychain is unavailable or denied access"
        )

    def _find_item(self, *, account: str, service: str) -> str | None:
        result = self._run(
            "find-generic-password",
            "-a",
            account,
            "-s",
            service,
            "-w",
        )
        if result.returncode == 0:
            return result.stdout.removesuffix("\n").removesuffix("\r")
        if self._is_missing(result):
            return None
        self._raise_backend_error()

    def _write_item(self, *, account: str, service: str, value: str) -> None:
        result = self._run(
            "add-generic-password",
            "-a",
            account,
            "-s",
            service,
            "-U",
            "-w",
            input_text=f"{value}\n",
        )
        if result.returncode != 0:
            self._raise_backend_error()

    def _delete_item(self, *, account: str, service: str) -> bool:
        result = self._run(
            "delete-generic-password",
            "-a",
            account,
            "-s",
            service,
        )
        if result.returncode == 0:
            return True
        if self._is_missing(result):
            return False
        self._raise_backend_error()

    def _load_index(self) -> tuple[str, ...]:
        raw = self._find_item(account=_INDEX_ACCOUNT, service=self._index_service)
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
        self._write_item(
            account=_INDEX_ACCOUNT,
            service=self._index_service,
            value=_encode_value(serialized),
        )

    def set(self, name: str, value: SecretStr) -> None:
        validated = SecretRef(name=name)
        names = self._load_index()
        previous = self._find_item(account=validated.name, service=self._service)
        if previous is not None:
            _decode_value(previous)

        self._write_item(
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
                    self._delete_item(account=validated.name, service=self._service)
                else:
                    self._write_item(
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
        raw = self._find_item(account=validated.name, service=self._service)
        if raw is None:
            return None
        return SecretStr(_decode_value(raw))

    def delete(self, name: str) -> bool:
        validated = SecretRef(name=name)
        names = self._load_index()
        previous = self._find_item(account=validated.name, service=self._service)
        if previous is None:
            if validated.name in names:
                self._save_index(tuple(item for item in names if item != validated.name))
            return False
        _decode_value(previous)

        if not self._delete_item(account=validated.name, service=self._service):
            self._raise_backend_error()
        try:
            self._save_index(tuple(item for item in names if item != validated.name))
        except SecretStoreUnavailableError:
            try:
                self._write_item(
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
