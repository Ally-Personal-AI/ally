"""Secret references and storage contracts."""

from ally.secrets.macos import MacOSKeychainSecretStore, build_system_secret_store
from ally.secrets.models import SecretRef
from ally.secrets.store import (
    InMemorySecretStore,
    SecretStore,
    SecretStoreError,
    SecretStoreUnavailableError,
    resolve_secret,
)

__all__ = [
    "InMemorySecretStore",
    "MacOSKeychainSecretStore",
    "SecretRef",
    "SecretStore",
    "SecretStoreError",
    "SecretStoreUnavailableError",
    "build_system_secret_store",
    "resolve_secret",
]
