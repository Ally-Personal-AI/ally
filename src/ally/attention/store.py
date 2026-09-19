"""Persistence contract for attention delivery attempts."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from ally.attention.models import AttentionDeliveryRecord, AttentionDeliveryStatus


class AttentionDeliveryStore(Protocol):
    def get(
        self,
        event_id: UUID,
        sink_id: str,
    ) -> AttentionDeliveryRecord | None:
        ...

    def record_attempt(
        self,
        *,
        event_id: UUID,
        sink_id: str,
        succeeded: bool,
        error: str | None = None,
    ) -> AttentionDeliveryRecord:
        ...

    def list(
        self,
        *,
        limit: int = 50,
        status: AttentionDeliveryStatus | None = None,
    ) -> tuple[AttentionDeliveryRecord, ...]:
        ...
