"""Audit contract for tool execution."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from ally.security.tool_policy import PolicyDecision
from ally.tools.models import ToolRisk, ToolStatus


class ToolAuditRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    invocation_id: UUID
    tool_name: str
    risk: ToolRisk | None
    decision: PolicyDecision | None
    status: ToolStatus
    arguments: dict[str, JsonValue]
    output: JsonValue | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime


class ToolAuditStore(Protocol):
    def append(self, record: ToolAuditRecord) -> None:
        ...

    def list(self, *, limit: int = 100) -> tuple[ToolAuditRecord, ...]:
        ...
