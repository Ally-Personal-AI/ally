"""Payload-free audit contract for external egress."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    service: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    operation: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    decision: EgressDecision
    status: EgressStatus
    approved: bool
    fields: tuple[EgressFieldManifest, ...]
    error_class: str | None = Field(default=None, max_length=128)
    started_at: datetime
    finished_at: datetime

    @model_validator(mode="after")
    def validate_state(self) -> EgressAuditRecord:
        expected = {
            "succeeded": "allow",
            "failed": "allow",
            "approval_required": "require_approval",
            "denied": "deny",
        }[self.status]
        if self.decision != expected:
            raise ValueError("egress audit status is inconsistent with decision")
        if self.status == "failed" and self.error_class is None:
            raise ValueError("failed egress audit requires error_class")
        if self.status in {"succeeded", "approval_required"} and self.error_class is not None:
            raise ValueError("successful/pending egress audit cannot retain error_class")
        return self


class EgressAuditStore(Protocol):
    def append(self, record: EgressAuditRecord) -> None:
        ...

    def list(self, *, limit: int = 100) -> tuple[EgressAuditRecord, ...]:
        ...
