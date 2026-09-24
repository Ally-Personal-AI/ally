"""Interface-neutral proactive attention delivery."""

from ally.attention.factory import (
    AttentionSinkName,
    build_attention_sink,
    macos_notification_status,
)
from ally.attention.macos import (
    MacOSNotificationError,
    MacOSNotificationSink,
    MacOSNotificationStatus,
    NativeMacOSNotificationBackend,
    render_macos_notification,
)
from ally.attention.models import AttentionDeliveryRecord, AttentionDeliveryStatus
from ally.attention.runtime import AttentionDeliveryRuntime, delivery_key
from ally.attention.sinks import (
    DELIVERABLE_ATTENTION_CLASSES,
    AttentionSink,
    ConsoleAttentionSink,
)
from ally.attention.store import AttentionDeliveryStore

__all__ = [
    "DELIVERABLE_ATTENTION_CLASSES",
    "AttentionDeliveryRecord",
    "AttentionDeliveryRuntime",
    "AttentionDeliveryStatus",
    "AttentionDeliveryStore",
    "AttentionSink",
    "AttentionSinkName",
    "ConsoleAttentionSink",
    "MacOSNotificationError",
    "MacOSNotificationSink",
    "MacOSNotificationStatus",
    "NativeMacOSNotificationBackend",
    "build_attention_sink",
    "delivery_key",
    "macos_notification_status",
    "render_macos_notification",
]
