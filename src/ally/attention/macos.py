"""Native macOS Notification Center attention adapter.

The current CLI/launch-agent phase uses Foundation's deprecated
NSUserNotificationCenter because modern UNUserNotificationCenter authorization
is app-bundle oriented. Keep the deprecated API isolated here so the sink can
be replaced without changing Ally's durable attention contract.
"""

# ctypes exposes Objective-C runtime symbols dynamically.
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import ctypes
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Literal, Protocol

from ally.attention.sinks import DELIVERABLE_ATTENTION_CLASSES
from ally.events import AttentionClass, EventRecord

_FOUNDATION = Path("/System/Library/Frameworks/Foundation.framework/Foundation")
_CORE_FOUNDATION = Path(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)
_OBJC = Path("/usr/lib/libobjc.A.dylib")
_UTF8_ENCODING = 0x08000100
_MAX_NOTIFICATION_TEXT = 500


class MacOSNotificationError(RuntimeError):
    """Raised when native notification delivery cannot complete safely."""


class MacOSNotificationUnavailableError(MacOSNotificationError):
    """Raised when the native macOS notification API is unavailable."""


NotificationAuthorizationVisibility = Literal["authorized", "denied", "not_determined", "unobservable"]


@dataclass(frozen=True)
class MacOSNotificationStatus:
    """Payload-free readiness information for the current CLI-native adapter."""

    supported: bool
    api_available: bool
    authorization: NotificationAuthorizationVisibility
    backend: str = "NSUserNotificationCenter"

    @property
    def ready(self) -> bool:
        return (
            self.supported
            and self.api_available
            and self.authorization != "denied"
        )


class MacOSNotificationBackend(Protocol):
    """Small native boundary used by the durable attention sink."""

    def contains(self, identifier: str) -> bool: ...

    def deliver(self, *, identifier: str, title: str, body: str) -> None: ...

    def status(self) -> MacOSNotificationStatus: ...


def _bounded_text(value: str) -> str:
    compact = " ".join(value.split()).strip()
    if len(compact) <= _MAX_NOTIFICATION_TEXT:
        return compact
    return compact[: _MAX_NOTIFICATION_TEXT - 1].rstrip() + "…"


def render_macos_notification(event: EventRecord) -> tuple[str, str]:
    """Render only explicit user-facing text, never an arbitrary payload dump."""

    title = "Ally"
    if event.attention == "interrupt":
        title = "Ally — Important"

    body: str | None = None
    for key in ("summary", "message"):
        value = event.payload.get(key)
        if isinstance(value, str) and value.strip():
            body = value
            break

    return title, _bounded_text(body or event.type)


class NativeMacOSNotificationBackend:
    """Direct Objective-C bridge to Foundation Notification Center."""

    def __init__(
        self,
        *,
        platform_name: str | None = None,
        foundation: Path = _FOUNDATION,
        core_foundation: Path = _CORE_FOUNDATION,
        objc: Path = _OBJC,
    ) -> None:
        platform = sys.platform if platform_name is None else platform_name
        if platform != "darwin":
            raise MacOSNotificationUnavailableError(
                "native notifications are supported only on macOS"
            )

        try:
            self._foundation = ctypes.CDLL(str(foundation))
            self._core = ctypes.CDLL(str(core_foundation))
            self._objc = ctypes.CDLL(str(objc))
            self._configure()
            self._notification_class = self._class("NSUserNotification")
            self._center_class = self._class("NSUserNotificationCenter")
            if not self._notification_class or not self._center_class:
                raise RuntimeError
        except Exception:
            raise MacOSNotificationUnavailableError(
                "macOS Notification Center API is unavailable"
            ) from None

    def _configure(self) -> None:
        self._objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self._objc.objc_getClass.restype = ctypes.c_void_p
        self._objc.sel_registerName.argtypes = [ctypes.c_char_p]
        self._objc.sel_registerName.restype = ctypes.c_void_p

        self._core.CFStringCreateWithBytes.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_uint32,
            ctypes.c_bool,
        ]
        self._core.CFStringCreateWithBytes.restype = ctypes.c_void_p
        self._core.CFRelease.argtypes = [ctypes.c_void_p]
        self._core.CFRelease.restype = None

        address = ctypes.cast(self._objc.objc_msgSend, ctypes.c_void_p).value
        if address is None:
            raise RuntimeError
        self._send_object = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(address)
        self._send_object_arg = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(address)
        self._send_void = ctypes.CFUNCTYPE(
            None,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(address)
        self._send_void_arg = ctypes.CFUNCTYPE(
            None,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(address)
        self._send_bool_arg = ctypes.CFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(address)
        self._send_uint = ctypes.CFUNCTYPE(
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )(address)
        self._send_object_index = ctypes.CFUNCTYPE(
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ulong,
        )(address)

    def _class(self, name: str) -> int:
        value = self._objc.objc_getClass(name.encode("ascii"))
        return 0 if value is None else int(value)

    def _selector(self, name: str) -> int:
        value = self._objc.sel_registerName(name.encode("ascii"))
        if value is None:
            raise MacOSNotificationUnavailableError(
                "macOS Notification Center API is unavailable"
            )
        return int(value)

    @contextmanager
    def _string(self, value: str) -> Generator[int, None, None]:
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
            raise MacOSNotificationError("notification text could not be prepared")
        string_ref = int(reference)
        try:
            yield string_ref
        finally:
            self._core.CFRelease(ctypes.c_void_p(string_ref))

    def _center(self) -> int:
        center = self._send_object(
            ctypes.c_void_p(self._center_class),
            ctypes.c_void_p(self._selector("defaultUserNotificationCenter")),
        )
        if center is None:
            raise MacOSNotificationUnavailableError(
                "macOS Notification Center is unavailable"
            )
        return int(center)

    def contains(self, identifier: str) -> bool:
        """Return whether Notification Center still tracks this delivery key."""

        try:
            center = self._center()
            notifications = self._send_object(
                ctypes.c_void_p(center),
                ctypes.c_void_p(self._selector("deliveredNotifications")),
            )
            if notifications is None:
                return False
            count = int(
                self._send_uint(
                    ctypes.c_void_p(notifications),
                    ctypes.c_void_p(self._selector("count")),
                )
            )
            with self._string(identifier) as identifier_ref:
                for index in range(count):
                    notification = self._send_object_index(
                        ctypes.c_void_p(notifications),
                        ctypes.c_void_p(self._selector("objectAtIndex:")),
                        index,
                    )
                    if notification is None:
                        continue
                    current = self._send_object(
                        ctypes.c_void_p(notification),
                        ctypes.c_void_p(self._selector("identifier")),
                    )
                    if current is None:
                        continue
                    if self._send_bool_arg(
                        ctypes.c_void_p(current),
                        ctypes.c_void_p(self._selector("isEqualToString:")),
                        ctypes.c_void_p(identifier_ref),
                    ):
                        return True
            return False
        except MacOSNotificationError:
            raise
        except Exception:
            raise MacOSNotificationError(
                "macOS notification state could not be read"
            ) from None

    def deliver(self, *, identifier: str, title: str, body: str) -> None:
        try:
            notification = self._send_object(
                ctypes.c_void_p(self._notification_class),
                ctypes.c_void_p(self._selector("new")),
            )
            if notification is None:
                raise MacOSNotificationError(
                    "macOS notification could not be created"
                )
            notification_ref = int(notification)
            try:
                for selector, value in (
                    ("setIdentifier:", identifier),
                    ("setTitle:", title),
                    ("setInformativeText:", body),
                ):
                    with self._string(value) as string_ref:
                        self._send_void_arg(
                            ctypes.c_void_p(notification_ref),
                            ctypes.c_void_p(self._selector(selector)),
                            ctypes.c_void_p(string_ref),
                        )
                self._send_void_arg(
                    ctypes.c_void_p(self._center()),
                    ctypes.c_void_p(self._selector("deliverNotification:")),
                    ctypes.c_void_p(notification_ref),
                )
            finally:
                self._send_void(
                    ctypes.c_void_p(notification_ref),
                    ctypes.c_void_p(self._selector("release")),
                )
        except MacOSNotificationError:
            raise
        except Exception:
            raise MacOSNotificationError(
                "macOS notification delivery failed"
            ) from None

    def status(self) -> MacOSNotificationStatus:
        return MacOSNotificationStatus(
            supported=True,
            api_available=True,
            authorization="unobservable",
        )


class MacOSNotificationSink:
    """Deliver Ally attention through macOS Notification Center."""

    def __init__(self, backend: MacOSNotificationBackend | None = None) -> None:
        self._backend = backend or NativeMacOSNotificationBackend()

    @property
    def id(self) -> str:
        return "macos.notification"

    @property
    def accepted_attention(self) -> tuple[AttentionClass, ...]:
        return DELIVERABLE_ATTENTION_CLASSES

    def deliver(
        self,
        event: EventRecord,
        *,
        delivery_key: str,
    ) -> None:
        if self._backend.contains(delivery_key):
            return
        title, body = render_macos_notification(event)
        self._backend.deliver(
            identifier=delivery_key,
            title=title,
            body=body,
        )

    def status(self) -> MacOSNotificationStatus:
        return self._backend.status()
