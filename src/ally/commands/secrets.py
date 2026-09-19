"""Human-facing commands for opaque operating-system secret references."""

from __future__ import annotations

import getpass
import warnings

from pydantic import SecretStr, ValidationError

from ally.secrets import (
    SecretRef,
    SecretStore,
    SecretStoreError,
    build_system_secret_store,
)


def _open_store() -> SecretStore | None:
    try:
        return build_system_secret_store()
    except SecretStoreError:
        print("Secret store unavailable or access denied.")
        return None


def _validated_name(name: str) -> str | None:
    try:
        return SecretRef(name=name).name
    except ValidationError:
        print("Invalid secret reference name.")
        return None


def _read_secret_value() -> SecretStr | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            value = getpass.getpass("Secret value: ")
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("Secret entry cancelled; an interactive terminal is required.")
        return None
    return SecretStr(value)


def run_set_secret(*, name: str) -> int:
    validated = _validated_name(name)
    if validated is None:
        return 2
    store = _open_store()
    if store is None:
        return 2
    value = _read_secret_value()
    if value is None:
        return 2
    try:
        store.set(validated, value)
    except SecretStoreError:
        print("Secret operation failed; no value was displayed.")
        return 2
    print(f"Stored secret reference: {validated}")
    return 0


def run_list_secret_references() -> int:
    store = _open_store()
    if store is None:
        return 2
    try:
        names = store.list_names()
    except SecretStoreError:
        print("Secret operation failed; no values were displayed.")
        return 2
    if not names:
        print("No secret references.")
        return 0
    for name in names:
        print(name)
    return 0


def run_check_secret(*, name: str) -> int:
    validated = _validated_name(name)
    if validated is None:
        return 2
    store = _open_store()
    if store is None:
        return 2
    try:
        available = store.get(validated) is not None
    except SecretStoreError:
        print("Secret operation failed; no value was displayed.")
        return 2
    status = "available" if available else "missing"
    print(f"Secret reference {validated}: {status}")
    return 0 if available else 1


def run_delete_secret(*, name: str) -> int:
    validated = _validated_name(name)
    if validated is None:
        return 2
    store = _open_store()
    if store is None:
        return 2
    try:
        deleted = store.delete(validated)
    except SecretStoreError:
        print("Secret operation failed; no value was displayed.")
        return 2
    if not deleted:
        print(f"Secret reference {validated}: missing")
        return 1
    print(f"Deleted secret reference: {validated}")
    return 0
