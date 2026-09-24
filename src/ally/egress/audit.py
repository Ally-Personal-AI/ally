"""Payload-free audit contract for external egress."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ally.egress.models import (
    EgressDecision,
    EgressFieldManifest,
    EgressStatus,
)


class EgressAuditRecord(BaseModel):
    """Persist only disclosure metadata, never outbound values or responses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    request_id: UUID
    service: str
    operation: str
    decision: EgressDecision
    status: EgressStatus
    approved: bool
    fields: tuple[EgressFieldManifest, ...]
    error_class: str | None = Field(default=None, max_length=128)
    started_at: datetime
    finished_at: datetime


class EgressAuditStore(Protocol):
    def append(self, record: EgressAuditRecord) -> None:
        ...

    def list(self, *, limit: int = 100) -> tuple[EgressAuditRecord, ...]:
        ...
