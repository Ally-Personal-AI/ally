"""Narrow ctypes adapter for Apple's modern Security-framework item APIs."""

# ctypes exposes dynamically loaded function symbols as Any. Keep that escape
# hatch contained in this infrastructure-only module.
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import ctypes
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Never

from ally.secrets.store import SecretStoreUnavailableError

_SECURITY_FRAMEWORK = Path(
    "/System/Library/Frameworks/Security.framework/Security"
)
_CORE_FOUNDATION_FRAMEWORK = Path(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)
_UTF8_ENCODING = 0x08000100
_ERR_SEC_DUPLICATE_ITEM = -25299
_ERR_SEC_ITEM_NOT_FOUND = -25300


class SecurityFrameworkKeychainBackend:
    """Read and mutate generic-password items through ``SecItem*`` APIs."""

    def __init__(
        self,
        *,
        platform_name: str | None = None,
        security_framework: Path = _SECURITY_FRAMEWORK,
        core_foundation_framework: Path = _CORE_FOUNDATION_FRAMEWORK,
    ) -> None:
        current_platform = sys.platform if platform_name is None else platform_name
        if current_platform != "darwin":
            raise SecretStoreUnavailableError(
                "the Apple Security framework is unavailable on this platform"
            )
        try:
            self._security = ctypes.CDLL(str(security_framework))
            self._core = ctypes.CDLL(str(core_foundation_framework))
            self._configure_functions()
            self._load_constants()
        except Exception:
            raise SecretStoreUnavailableError(
                "macOS Keychain is unavailable or denied access"
            ) from None

    def _configure_functions(self) -> None:
        self._security.SecItemCopyMatching.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._security.SecItemCopyMatching.restype = ctypes.c_int32
        self._security.SecItemAdd.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._security.SecItemAdd.restype = ctypes.c_int32
        self._security.SecItemUpdate.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._security.SecItemUpdate.restype = ctypes.c_int32
        self._security.SecItemDelete.argtypes = [ctypes.c_void_p]
        self._security.SecItemDelete.restype = ctypes.c_int32

        self._core.CFStringCreateWithBytes.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_uint32,
            ctypes.c_bool,
        ]
        self._core.CFStringCreateWithBytes.restype = ctypes.c_void_p
        self._core.CFDataCreate.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_long,
        ]
        self._core.CFDataCreate.restype = ctypes.c_void_p
        self._core.CFDataGetLength.argtypes = [ctypes.c_void_p]
        self._core.CFDataGetLength.restype = ctypes.c_long
        self._core.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
        self._core.CFDataGetBytePtr.restype = ctypes.c_void_p
        self._core.CFDictionaryCreate.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._core.CFDictionaryCreate.restype = ctypes.c_void_p
        self._core.CFRelease.argtypes = [ctypes.c_void_p]
        self._core.CFRelease.restype = None

    @staticmethod
    def _pointer_constant(library: ctypes.CDLL, name: str) -> int:
        value = ctypes.c_void_p.in_dll(library, name).value
        if value is None:
            raise RuntimeError(f"missing framework constant: {name}")
        return value

    def _load_constants(self) -> None:
        self._class = self._pointer_constant(self._security, "kSecClass")
        self._generic_password = self._pointer_constant(
            self._security,
            "kSecClassGenericPassword",
        )
        self._attr_service = self._pointer_constant(
            self._security,
            "kSecAttrService",
        )
        self._attr_account = self._pointer_constant(
            self._security,
            "kSecAttrAccount",
        )
        self._value_data = self._pointer_constant(self._security, "kSecValueData")
        self._return_data = self._pointer_constant(
            self._security,
            "kSecReturnData",
        )
        self._match_limit = self._pointer_constant(
            self._security,
            "kSecMatchLimit",
        )
        self._match_limit_one = self._pointer_constant(
            self._security,
            "kSecMatchLimitOne",
        )
        self._boolean_true = self._pointer_constant(self._core, "kCFBooleanTrue")

    @staticmethod
    def _raise_backend_error() -> Never:
        raise SecretStoreUnavailableError(
            "macOS Keychain is unavailable or denied access"
        )

    def _release(self, reference: int) -> None:
        self._core.CFRelease(ctypes.c_void_p(reference))

    def _string(self, value: str) -> int:
        encoded = value.encode("utf-8")
        buffer = ctypes.create_string_buffer(encoded)
        reference = self._core.CFStringCreateWithBytes(
            None,
            ctypes.cast(buffer, ctypes.c_void_p),
            len(encoded),
            _UTF8_ENCODING,
            False,
        )
        if reference is None:
            raise MemoryError
        return int(reference)

    def _data(self, value: bytes) -> int:
        buffer = ctypes.create_string_buffer(value)
        reference = self._core.CFDataCreate(
            None,
            ctypes.cast(buffer, ctypes.c_void_p),
            len(value),
        )
        if reference is None:
            raise MemoryError
        return int(reference)

    @contextmanager
    def _dictionary(
        self,
        entries: tuple[tuple[int, int], ...],
        *,
        owned_values: tuple[int, ...] = (),
    ) -> Generator[int, None, None]:
        keys = (ctypes.c_void_p * len(entries))(
            *(ctypes.c_void_p(key) for key, _ in entries)
        )
        values = (ctypes.c_void_p * len(entries))(
            *(ctypes.c_void_p(value) for _, value in entries)
        )
        dictionary = self._core.CFDictionaryCreate(
            None,
            keys,
            values,
            len(entries),
            None,
            None,
        )
        if dictionary is None:
            for value in owned_values:
                self._release(value)
            raise MemoryError
        try:
            yield int(dictionary)
        finally:
            self._release(int(dictionary))
            for value in owned_values:
                self._release(value)

    @contextmanager
    def _item_query(
        self,
        *,
        account: str,
        service: str,
        return_data: bool = False,
    ) -> Generator[int, None, None]:
        account_ref = self._string(account)
        service_ref = self._string(service)
        entries = [
            (self._class, self._generic_password),
            (self._attr_account, account_ref),
            (self._attr_service, service_ref),
        ]
        if return_data:
            entries.extend(
                (
                    (self._return_data, self._boolean_true),
                    (self._match_limit, self._match_limit_one),
                )
            )
        with self._dictionary(
            tuple(entries),
            owned_values=(account_ref, service_ref),
        ) as query:
            yield query

    def _get(self, *, account: str, service: str) -> bytes | None:
        result = ctypes.c_void_p()
        with self._item_query(
            account=account,
            service=service,
            return_data=True,
        ) as query:
            status = self._security.SecItemCopyMatching(
                ctypes.c_void_p(query),
                ctypes.byref(result),
            )
        if status == _ERR_SEC_ITEM_NOT_FOUND:
            return None
        if status != 0 or result.value is None:
            self._raise_backend_error()

        data_ref = int(result.value)
        try:
            length = int(self._core.CFDataGetLength(ctypes.c_void_p(data_ref)))
            if length == 0:
                return b""
            pointer = self._core.CFDataGetBytePtr(ctypes.c_void_p(data_ref))
            if pointer is None:
                self._raise_backend_error()
            return ctypes.string_at(pointer, length)
        finally:
            self._release(data_ref)

    def get(self, *, account: str, service: str) -> bytes | None:
        try:
            return self._get(account=account, service=service)
        except SecretStoreUnavailableError:
            raise
        except Exception:
            self._raise_backend_error()

    def _update(self, *, account: str, service: str, value: bytes) -> int:
        value_ref = self._data(value)
        with self._dictionary(
            ((self._value_data, value_ref),),
            owned_values=(value_ref,),
        ) as changes, self._item_query(account=account, service=service) as query:
            return int(
                self._security.SecItemUpdate(
                    ctypes.c_void_p(query),
                    ctypes.c_void_p(changes),
                )
            )

    def _set(self, *, account: str, service: str, value: bytes) -> None:
        status = self._update(account=account, service=service, value=value)
        if status == 0:
            return
        if status != _ERR_SEC_ITEM_NOT_FOUND:
            self._raise_backend_error()

        account_ref = self._string(account)
        service_ref = self._string(service)
        value_ref = self._data(value)
        with self._dictionary(
            (
                (self._class, self._generic_password),
                (self._attr_account, account_ref),
                (self._attr_service, service_ref),
                (self._value_data, value_ref),
            ),
            owned_values=(account_ref, service_ref, value_ref),
        ) as attributes:
            status = self._security.SecItemAdd(
                ctypes.c_void_p(attributes),
                None,
            )
        if status == _ERR_SEC_DUPLICATE_ITEM:
            if self._update(account=account, service=service, value=value) == 0:
                return
            self._raise_backend_error()
        if status != 0:
            self._raise_backend_error()

    def set(self, *, account: str, service: str, value: bytes) -> None:
        try:
            self._set(account=account, service=service, value=value)
        except SecretStoreUnavailableError:
            raise
        except Exception:
            self._raise_backend_error()

    def _delete(self, *, account: str, service: str) -> bool:
        with self._item_query(account=account, service=service) as query:
            status = self._security.SecItemDelete(ctypes.c_void_p(query))
        if status == 0:
            return True
        if status == _ERR_SEC_ITEM_NOT_FOUND:
            return False
        self._raise_backend_error()

    def delete(self, *, account: str, service: str) -> bool:
        try:
            return self._delete(account=account, service=service)
        except SecretStoreUnavailableError:
            raise
        except Exception:
            self._raise_backend_error()
