"""Interface-neutral proactive attention delivery."""

from ally.attention.models import AttentionDeliveryRecord, AttentionDeliveryStatus
from ally.attention.runtime import AttentionDeliveryRuntime
from ally.attention.sinks import AttentionSink, ConsoleAttentionSink
from ally.attention.store import AttentionDeliveryStore

__all__ = [
    "AttentionDeliveryRecord",
    "AttentionDeliveryRuntime",
    "AttentionDeliveryStatus",
    "AttentionDeliveryStore",
    "AttentionSink",
    "ConsoleAttentionSink",
]
